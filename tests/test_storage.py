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
    default_captures_dir,
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
