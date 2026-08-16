import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from stat import S_IMODE

import pytest

from coding_agent_performance.trace.storage import (
    SCHEMA_VERSION,
    CaptureStorageError,
    CaptureWriter,
    LatestCaptureError,
    default_captures_dir,
    latest_capture,
    make_envelope,
    new_capture_path,
)


def test_creates_directory_and_file(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    path = captures / "claude-code-test.jsonl"
    writer = CaptureWriter.create(path)
    try:
        assert captures.is_dir()
        assert path.is_file()
        assert writer.path == path.resolve()
        assert writer.path.is_absolute()
    finally:
        writer.close()


def test_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(CaptureStorageError, match="already exists"):
        CaptureWriter.create(path)


def test_exclusive_create_does_not_replace_bytes(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    first = CaptureWriter.create(path)
    first.close()
    original = path.read_bytes()

    with pytest.raises(CaptureStorageError, match="already exists"):
        CaptureWriter.create(path)

    assert path.read_bytes() == original


def test_one_json_line_per_envelope(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    writer.append(make_envelope(source="claude-code", signal="logs", payload={"resourceLogs": []}))
    writer.append(make_envelope(source="claude-code", signal="metrics", payload={"resourceMetrics": []}))
    writer.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["signal"] == "logs"
    assert first["payload"] == {"resourceLogs": []}
    assert second["signal"] == "metrics"
    assert second["payload"] == {"resourceMetrics": []}
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["source"] == "claude-code"


def test_received_at_is_timezone_aware(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    writer.append(make_envelope(source="claude-code", signal="logs", payload={"resourceLogs": []}))
    writer.close()

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    parsed = datetime.fromisoformat(row["received_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == UTC.utcoffset(parsed)


def test_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    writer.append(
        make_envelope(
            source="claude-code",
            signal="logs",
            payload={"note": "café 日本語"},
        )
    )
    writer.close()

    text = path.read_text(encoding="utf-8")
    assert "café 日本語" in text
    assert "\\u" not in text
    assert json.loads(text.splitlines()[0])["payload"]["note"] == "café 日本語"


def test_flush_and_close(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    writer.append(make_envelope(source="claude-code", signal="logs", payload={"n": 1}))
    assert path.read_text(encoding="utf-8").endswith("\n")
    writer.close()
    writer.close()
    with pytest.raises(CaptureStorageError, match="closed"):
        writer.append(make_envelope(source="claude-code", signal="logs", payload={"n": 2}))


@pytest.mark.skipif(os.name != "posix", reason="POSIX capture permissions")
def test_posix_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    writer.close()
    assert S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX capture permissions")
def test_posix_directory_mode(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    writer = CaptureWriter.create(captures / "capture.jsonl", restrict_directory=True)
    writer.close()
    assert S_IMODE(captures.stat().st_mode) == 0o700


def test_concurrent_writes_remain_valid_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)

    def write_row(index: int) -> None:
        writer.append(make_envelope(source="claude-code", signal="logs", payload={"n": index}))

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write_row, range(40)))
    finally:
        writer.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 40
    numbers = {json.loads(line)["payload"]["n"] for line in lines}
    assert numbers == set(range(40))


def test_default_captures_dir_uses_platformdirs() -> None:
    path = default_captures_dir()
    assert path.name == "captures"
    assert path.parent.name == "capt"
    assert path.is_absolute()


def test_prepare_directory_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_mkdir(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(CaptureStorageError, match="capture directory"):
        CaptureWriter.create(tmp_path / "nested" / "capture.jsonl")


def test_to_json_rejects_non_finite_numbers() -> None:
    envelope = make_envelope(source="claude-code", signal="logs", payload={"resourceLogs": [{"n": float("nan")}]})
    with pytest.raises(ValueError, match="not JSON compliant"):
        envelope.to_json()


def test_writer_rejects_non_finite_without_leaking_payload(tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    writer = CaptureWriter.create(path)
    envelope = make_envelope(source="claude-code", signal="logs", payload={"resourceLogs": [{"n": float("inf")}]})
    try:
        with pytest.raises(CaptureStorageError, match="serialize") as exc_info:
            writer.append(envelope)
        message = str(exc_info.value)
        assert "inf" not in message.lower()
        assert "resourceLogs" not in message
        assert path.read_text(encoding="utf-8") == ""
    finally:
        writer.close()


def test_new_capture_path_shape(tmp_path: Path) -> None:
    path = new_capture_path(tmp_path, "claude-code")
    assert path.parent == tmp_path
    assert path.name.startswith("claude-code-")
    assert path.name.endswith(".jsonl")
    assert "T" in path.name
    assert path.name.endswith("Z-" + path.name.rsplit("-", 1)[1])


def _touch_capture(directory: Path, name: str, mtime_ns: int) -> Path:
    path = directory / name
    path.write_text("{}\n", encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_latest_capture_selects_highest_mtime(tmp_path: Path) -> None:
    older = _touch_capture(tmp_path, "older.jsonl", 1_000)
    newer = _touch_capture(tmp_path, "newer.jsonl", 2_000)
    _touch_capture(tmp_path, "notes.txt", 3_000)
    nested = tmp_path / "nested"
    nested.mkdir()
    _touch_capture(nested, "hidden.jsonl", 4_000)
    (tmp_path / "dir.jsonl").mkdir()

    selected = latest_capture(tmp_path)

    assert selected == newer
    assert selected != older


def test_latest_capture_tie_breaks_by_filename(tmp_path: Path) -> None:
    _touch_capture(tmp_path, "alpha.jsonl", 5_000)
    winner = _touch_capture(tmp_path, "zeta.jsonl", 5_000)

    assert latest_capture(tmp_path) == winner


def test_latest_capture_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "captures"
    with pytest.raises(LatestCaptureError, match="does not exist") as exc_info:
        latest_capture(missing)
    assert str(missing) not in str(exc_info.value)
    assert "{}" not in str(exc_info.value)


def test_latest_capture_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(LatestCaptureError, match="No capture files") as exc_info:
        latest_capture(tmp_path)
    assert str(tmp_path) not in str(exc_info.value)


def test_latest_capture_rejects_non_directory(tmp_path: Path) -> None:
    path = tmp_path / "not-a-dir"
    path.write_text("payload-should-not-leak\n", encoding="utf-8")
    with pytest.raises(LatestCaptureError, match="not a directory") as exc_info:
        latest_capture(path)
    assert "payload-should-not-leak" not in str(exc_info.value)
    assert str(path) not in str(exc_info.value)


def test_latest_capture_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_scandir(_path: Path) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr("coding_agent_performance.trace.storage.os.scandir", fail_scandir)
    with pytest.raises(LatestCaptureError, match="Could not read default capture directory") as exc_info:
        latest_capture(tmp_path)
    assert "permission denied" in str(exc_info.value)
    assert str(tmp_path) not in str(exc_info.value)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_latest_capture_excludes_symlinks(tmp_path: Path) -> None:
    real = _touch_capture(tmp_path, "real.jsonl", 1_000)
    link = tmp_path / "newer-link.jsonl"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symbolic links are not supported")
    os.utime(link, ns=(2_000, 2_000), follow_symlinks=False)

    assert latest_capture(tmp_path) == real
