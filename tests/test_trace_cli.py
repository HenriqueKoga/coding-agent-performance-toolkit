import socket
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app
from coding_agent_performance.trace.cli import serve_collector
from coding_agent_performance.trace.collector import LOOPBACK_HOST, OtlpHttpCollector
from coding_agent_performance.trace.storage import CaptureWriter

runner = CliRunner()


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return int(sock.getsockname()[1])


def test_trace_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "--help"], color=False)

    assert result.exit_code == 0
    assert "collect" in visible(result.output)


def test_trace_collect_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "collect", "--help"], color=False)

    assert result.exit_code == 0
    assert "claude-code" in visible(result.output)


def test_trace_collect_claude_code_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "collect", "claude-code", "--help"], color=False)
    text = visible(result.output)

    assert result.exit_code == 0
    assert "--port" in text
    assert "--output" in text


def test_invalid_port_is_rejected(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["trace", "collect", "claude-code", "--port", "70000", "--output", str(tmp_path / "capture.jsonl")],
    )

    assert result.exit_code != 0
    assert "Port must be between 1 and 65535." in result.output
    assert "Traceback" not in result.output


def test_existing_output_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    result = runner.invoke(app, ["trace", "collect", "claude-code", "--output", str(path)])

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "Traceback" not in result.output
    assert path.read_text(encoding="utf-8") == "{}\n"


def test_bind_error_is_readable(tmp_path: Path) -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind((LOOPBACK_HOST, 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    try:
        result = runner.invoke(
            app,
            ["trace", "collect", "claude-code", "--port", str(port), "--output", str(tmp_path / "capture.jsonl")],
        )
    finally:
        occupied.close()

    assert result.exit_code != 0
    assert "already in use" in result.output
    assert "Traceback" not in result.output


def test_started_output_shows_absolute_path_and_safe_snippet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("coding_agent_performance.trace.cli.serve_collector", lambda collector: None)
    output = tmp_path / "capture.jsonl"
    result = runner.invoke(
        app,
        ["trace", "collect", "claude-code", "--port", str(_unused_port()), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert str(output.resolve()) in result.stdout
    assert "http://127.0.0.1:" in result.stdout
    assert "/v1/logs" in result.stdout
    assert "/v1/metrics" in result.stdout
    assert "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json" in result.stdout
    assert "OTEL_LOG_USER_PROMPTS=0" in result.stdout
    assert "OTEL_LOG_ASSISTANT_RESPONSES=0" in result.stdout
    assert "OTEL_LOG_TOOL_DETAILS=0" in result.stdout
    assert "OTEL_LOG_TOOL_CONTENT=0" in result.stdout
    assert "Collector stopped" in result.stdout
    assert "log batches: 0" in result.stdout


def test_keyboard_interrupt_returns_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def interrupt(_collector: OtlpHttpCollector) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("coding_agent_performance.trace.cli.serve_collector", interrupt)
    result = runner.invoke(
        app,
        [
            "trace",
            "collect",
            "claude-code",
            "--port",
            str(_unused_port()),
            "--output",
            str(tmp_path / "capture.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "Collector stopped" in result.stdout
    assert "Traceback" not in result.output


def test_serve_collector_blocks_until_stop(tmp_path: Path) -> None:
    writer = CaptureWriter.create(tmp_path / "capture.jsonl")
    collector = OtlpHttpCollector(host=LOOPBACK_HOST, port=0, writer=writer, source="claude-code")
    collector.start()
    thread = threading.Thread(target=serve_collector, args=(collector,), daemon=True)
    thread.start()
    collector.stop()
    thread.join(timeout=2)
    collector.close()
    assert not thread.is_alive()
