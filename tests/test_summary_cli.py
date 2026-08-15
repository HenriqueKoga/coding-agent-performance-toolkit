import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app
from tests.helpers.otlp import envelope, resource_logs
from tests.helpers.synthetic_capture import FIXTURE_PATH, SENSITIVE_MARKERS

runner = CliRunner()


def test_summarize_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "summarize", "--help"], color=False)
    text = visible(result.output)
    assert result.exit_code == 0
    assert "CAPTURE" in text or "capture" in text.lower()
    assert "--format" in text
    assert "json" in text
    assert "text" in text


def test_default_format_is_text() -> None:
    result = runner.invoke(app, ["trace", "summarize", str(FIXTURE_PATH)], color=False)
    assert result.exit_code == 0
    assert result.stdout.startswith("Capture")
    assert "Model usage" in result.stdout
    assert result.stdout.strip()[0] != "{"
    assert "synthetic-capture.jsonl" in result.stdout
    assert str(FIXTURE_PATH.resolve()) not in result.stdout


def test_json_format_is_only_json() -> None:
    result = runner.invoke(app, ["trace", "summarize", str(FIXTURE_PATH), "--format", "json"], color=False)
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    json.dumps(parsed, allow_nan=False)
    assert parsed["schema_version"] == 1
    assert parsed["capture"]["file"] == "synthetic-capture.jsonl"
    assert not result.stderr
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    for marker in SENSITIVE_MARKERS:
        assert marker not in result.stdout


def test_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["trace", "summarize", str(tmp_path / "missing.jsonl")], color=False)
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert "Traceback" not in result.output


def test_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{not-json\n", encoding="utf-8")
    result = runner.invoke(app, ["trace", "summarize", str(path)], color=False)
    assert result.exit_code == 1
    assert "invalid JSON" in result.output
    assert "bad.jsonl:1" in result.output
    assert "{not-json" not in result.output
    assert "Traceback" not in result.output


def test_empty_capture(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["trace", "summarize", str(path)], color=False)
    assert result.exit_code == 1
    assert "empty capture" in result.output
    assert "Traceback" not in result.output


def test_empty_recognized_data(tmp_path: Path) -> None:
    path = tmp_path / "none.jsonl"
    path.write_text(json.dumps(envelope(signal="logs", payload=resource_logs([]))) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["trace", "summarize", str(path)], color=False)
    assert result.exit_code == 1
    assert "no recognized telemetry" in result.output


def test_oserror_during_summarize(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    path.write_text("{}\n", encoding="utf-8")

    def boom(_path: Path) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr("coding_agent_performance.trace.cli.summarize_capture", boom)
    result = runner.invoke(app, ["trace", "summarize", str(path)], color=False)
    assert result.exit_code == 1
    assert "permission denied" in result.output
    assert "Traceback" not in result.output


def test_directory_is_rejected(tmp_path: Path) -> None:
    result = runner.invoke(app, ["trace", "summarize", str(tmp_path)], color=False)
    assert result.exit_code == 1
    assert "directory" in result.output
    assert "Traceback" not in result.output
