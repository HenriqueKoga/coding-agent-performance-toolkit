import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app

runner = CliRunner()


def _touch_capture(directory: Path, name: str, mtime_ns: int, contents: bytes = b"{}\n") -> Path:
    path = directory / name
    path.write_bytes(contents)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_trace_help_includes_list(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "--help"], color=False)
    text = visible(result.output)
    assert result.exit_code == 0
    assert "list" in text
    assert "summarize" in text


def test_list_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "list", "--help"], color=False)
    text = visible(result.output).lower()
    assert result.exit_code == 0
    assert "list local captures without reading their contents" in text


def test_list_orders_newest_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    modified_newer = datetime(2026, 8, 17, 16, 25, 10, tzinfo=UTC)
    modified_older = datetime(2026, 8, 17, 16, 25, 9, tzinfo=UTC)
    _touch_capture(tmp_path, "older.jsonl", int(modified_older.timestamp()) * 1_000_000_000, b"aa")
    _touch_capture(tmp_path, "newer.jsonl", int(modified_newer.timestamp()) * 1_000_000_000, b"bbbb")
    _touch_capture(tmp_path, "notes.txt", int(modified_newer.timestamp()) * 1_000_000_000 + 1_000)
    nested = tmp_path / "nested"
    nested.mkdir()
    _touch_capture(nested, "hidden.jsonl", int(modified_newer.timestamp()) * 1_000_000_000 + 2_000)
    (tmp_path / "dir.jsonl").mkdir()
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "list"], color=False)

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines == [
        "newer.jsonl  4  2026-08-17T16:25:10Z",
        "older.jsonl  2  2026-08-17T16:25:09Z",
    ]
    assert str(tmp_path) not in result.output
    assert "hidden.jsonl" not in result.stdout
    assert "notes.txt" not in result.stdout


def test_list_tie_breaks_by_filename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mtime_ns = int(datetime(2026, 8, 17, 16, 25, 9, tzinfo=UTC).timestamp()) * 1_000_000_000
    _touch_capture(tmp_path, "alpha.jsonl", mtime_ns)
    _touch_capture(tmp_path, "zeta.jsonl", mtime_ns)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "list"], color=False)

    assert result.exit_code == 0
    names = [line.split("  ", maxsplit=1)[0] for line in result.stdout.splitlines()]
    assert names == ["zeta.jsonl", "alpha.jsonl"]


def test_list_missing_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "captures"
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: missing)
    result = runner.invoke(app, ["trace", "list"], color=False)
    assert result.exit_code == 0
    assert result.stdout == "No capture files found.\n"
    assert str(missing) not in result.output


def test_list_empty_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)
    result = runner.invoke(app, ["trace", "list"], color=False)
    assert result.exit_code == 0
    assert result.stdout == "No capture files found.\n"
    assert str(tmp_path) not in result.output


def test_list_rejects_non_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "not-a-dir"
    path.write_text("payload-should-not-leak\n", encoding="utf-8")
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: path)
    result = runner.invoke(app, ["trace", "list"], color=False)
    assert result.exit_code == 1
    assert "not a directory" in result.output
    assert "Traceback" not in result.output
    assert "payload-should-not-leak" not in result.output
    assert str(path) not in result.output


def test_list_oserror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    def fail_scandir(_path: Path) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr("coding_agent_performance.trace.storage.os.scandir", fail_scandir)
    result = runner.invoke(app, ["trace", "list"], color=False)
    assert result.exit_code == 1
    assert "Could not read default capture directory" in result.output
    assert "permission denied" in result.output
    assert "Traceback" not in result.output
    assert str(tmp_path) not in result.output


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_list_excludes_symlinks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real = _touch_capture(tmp_path, "real.jsonl", 1_000)
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symbolic links are not supported")
    os.utime(link, ns=(2_000, 2_000), follow_symlinks=False)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "list"], color=False)

    assert result.exit_code == 0
    assert "real.jsonl" in result.stdout
    assert "link.jsonl" not in result.stdout


def test_list_escapes_unsafe_filenames(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    modified = datetime(2026, 8, 17, 16, 25, 9, tzinfo=UTC)
    mtime_ns = int(modified.timestamp()) * 1_000_000_000
    _touch_capture(tmp_path, "bad\nname\twith\rcr\x1b[31m.jsonl", mtime_ns, b"xx")
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "list"], color=False)

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0] == "bad\\nname\\twith\\rcr\\x1b[31m.jsonl  2  2026-08-17T16:25:09Z"
    assert "\x1b" not in result.stdout
    assert str(tmp_path) not in result.output


def test_list_does_not_read_or_parse_capture_contents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b'{"secret":"payload-must-not-leak"}\n'
    _touch_capture(tmp_path, "capture.jsonl", 1_000, payload)
    monkeypatch.setattr("coding_agent_performance.trace.cli.default_captures_dir", lambda: tmp_path)

    result = runner.invoke(app, ["trace", "list"], color=False)

    assert result.exit_code == 0
    assert "capture.jsonl" in result.stdout
    assert "payload-must-not-leak" not in result.output
    assert str(tmp_path) not in result.output
