import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app
from tests.helpers.otlp import envelope, resource_logs
from tests.helpers.synthetic_capture import FIXTURE_PATH, SENSITIVE_MARKERS, write_synthetic_capture

runner = CliRunner()


def test_summarize_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "summarize", "--help"], color=False)
    text = visible(result.output)
    assert result.exit_code == 0
    assert "CAPTURE" in text or "capture" in text.lower()
    assert "--format" in text
    assert "--latest" in text
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


def _seed_capture(directory: Path, name: str, mtime_ns: int) -> Path:
    path = write_synthetic_capture(directory / name)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_latest_summarizes_newest_capture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_capture(tmp_path, "older.jsonl", 1_000)
    newest = _seed_capture(tmp_path, "newest.jsonl", 2_000)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "summarize", "--latest"], color=False)

    assert result.exit_code == 0
    assert result.stdout.startswith("Capture")
    assert "newest.jsonl" in result.stdout
    assert "older.jsonl" not in result.stdout
    assert str(newest.resolve()) not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_latest_text_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_capture(tmp_path, "capture.jsonl", 1_000)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "summarize", "--latest", "--format", "text"], color=False)

    assert result.exit_code == 0
    assert "Model usage" in result.stdout
    assert result.stdout.strip()[0] != "{"


def test_latest_json_format_is_only_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    newest = _seed_capture(tmp_path, "latest.jsonl", 2_000)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "summarize", "--latest", "--format", "json"], color=False)

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    json.dumps(parsed, allow_nan=False)
    assert parsed["schema_version"] == 1
    assert parsed["capture"]["file"] == "latest.jsonl"
    assert not result.stderr
    assert result.stdout.strip().startswith("{")
    assert result.stdout.strip().endswith("}")
    assert str(newest.resolve()) not in result.stdout
    for marker in SENSITIVE_MARKERS:
        assert marker not in result.stdout


def test_latest_tie_breaks_by_filename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_capture(tmp_path, "alpha.jsonl", 5_000)
    _seed_capture(tmp_path, "zeta.jsonl", 5_000)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "summarize", "--latest", "--format", "json"], color=False)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["capture"]["file"] == "zeta.jsonl"


def test_path_and_latest_are_mutually_exclusive() -> None:
    result = runner.invoke(app, ["trace", "summarize", str(FIXTURE_PATH), "--latest"], color=False)
    assert result.exit_code == 1
    assert "not both" in result.output
    assert "Traceback" not in result.output
    assert str(FIXTURE_PATH.resolve()) not in result.output


def test_missing_path_and_latest_is_rejected() -> None:
    result = runner.invoke(app, ["trace", "summarize"], color=False)
    assert result.exit_code == 1
    assert "capture path or --latest" in result.output
    assert "Traceback" not in result.output


def test_latest_missing_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "captures"
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: missing)
    result = runner.invoke(app, ["trace", "summarize", "--latest"], color=False)
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert "Traceback" not in result.output
    assert str(missing) not in result.output


def test_latest_empty_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)
    result = runner.invoke(app, ["trace", "summarize", "--latest"], color=False)
    assert result.exit_code == 1
    assert "No capture files" in result.output
    assert "Traceback" not in result.output
    assert str(tmp_path) not in result.output


def test_latest_directory_oserror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    def fail_scandir(_path: Path) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr("coding_agent_performance.trace.storage.os.scandir", fail_scandir)
    result = runner.invoke(app, ["trace", "summarize", "--latest"], color=False)
    assert result.exit_code == 1
    assert "Could not read default capture directory" in result.output
    assert "permission denied" in result.output
    assert "Traceback" not in result.output
    assert str(tmp_path) not in result.output


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_latest_excludes_symlinks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real = _seed_capture(tmp_path, "real.jsonl", 1_000)
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symbolic links are not supported")
    os.utime(link, ns=(2_000, 2_000), follow_symlinks=False)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "summarize", "--latest", "--format", "json"], color=False)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["capture"]["file"] == "real.jsonl"
    assert "link.jsonl" not in result.stdout
