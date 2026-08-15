import json
import os
from pathlib import Path

import pytest

from coding_agent_performance.trace.capture import MAX_LINE_BYTES, CaptureError, CaptureReader
from tests.helpers.otlp import envelope, resource_logs
from tests.helpers.synthetic_capture import FIXTURE_PATH


def _write(path: Path, rows: list[object]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_reads_valid_capture() -> None:
    envelopes = list(CaptureReader(FIXTURE_PATH))

    assert len(envelopes) == 4
    assert {item.source for item in envelopes} == {"claude-code"}
    assert [item.signal for item in envelopes] == ["logs", "logs", "metrics", "metrics"]
    assert envelopes[0].received_at.tzinfo is not None


def test_empty_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(CaptureError, match="empty capture") as exc_info:
        list(CaptureReader(path))
    assert "empty.jsonl" in str(exc_info.value)
    assert exc_info.value.line is None


def test_empty_line_fails(tmp_path: Path) -> None:
    path = tmp_path / "blank.jsonl"
    path.write_bytes(b"\n")

    with pytest.raises(CaptureError, match="empty line") as exc_info:
        list(CaptureReader(path))
    assert exc_info.value.line == 1
    assert "blank.jsonl:1" in str(exc_info.value)


def test_invalid_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(CaptureError, match="invalid JSON") as exc_info:
        list(CaptureReader(path))
    assert "not-json" not in str(exc_info.value)
    assert "{not-json" not in str(exc_info.value)


def test_invalid_utf8_fails(tmp_path: Path) -> None:
    path = tmp_path / "binary.jsonl"
    path.write_bytes(b"\xff\n")

    with pytest.raises(CaptureError, match="invalid UTF-8") as exc_info:
        list(CaptureReader(path))
    assert exc_info.value.line == 1


def test_line_over_limit_fails(tmp_path: Path) -> None:
    path = tmp_path / "huge.jsonl"
    path.write_bytes(b"x" * 32 + b"\n")

    with pytest.raises(CaptureError, match="size limit") as exc_info:
        list(CaptureReader(path, max_line_bytes=16))
    assert exc_info.value.line == 1
    assert "x" * 16 not in str(exc_info.value)


def test_default_line_limit_matches_collector_envelope() -> None:
    assert MAX_LINE_BYTES == 16 * 1024 * 1024


def test_incompatible_schema_version(tmp_path: Path) -> None:
    path = _write(tmp_path / "v2.jsonl", [envelope(signal="logs", payload=resource_logs([]), schema_version=2)])

    with pytest.raises(CaptureError, match="unsupported schema_version 2") as exc_info:
        list(CaptureReader(path))
    assert "v2.jsonl:1" in str(exc_info.value)


def test_mixed_sources_fail(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "mixed.jsonl",
        [
            envelope(signal="logs", payload=resource_logs([]), source="claude-code"),
            envelope(signal="metrics", payload={"resourceMetrics": []}, source="other"),
        ],
    )

    with pytest.raises(CaptureError, match="mixed sources") as exc_info:
        list(CaptureReader(path))
    assert exc_info.value.line == 2


def test_invalid_signal(tmp_path: Path) -> None:
    row = envelope(signal="logs", payload=resource_logs([]))
    row["signal"] = "traces"
    path = _write(tmp_path / "signal.jsonl", [row])

    with pytest.raises(CaptureError, match="signal must be logs or metrics"):
        list(CaptureReader(path))


def test_timestamp_without_timezone(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "naive.jsonl",
        [envelope(signal="logs", payload=resource_logs([]), received_at="2026-08-15T10:00:00")],
    )

    with pytest.raises(CaptureError, match="timezone"):
        list(CaptureReader(path))


def test_payload_must_be_object(tmp_path: Path) -> None:
    row = envelope(signal="logs", payload=resource_logs([]))
    row["payload"] = []
    path = _write(tmp_path / "payload.jsonl", [row])

    with pytest.raises(CaptureError, match="payload must be a JSON object"):
        list(CaptureReader(path))


def test_logs_payload_requires_resource_logs(tmp_path: Path) -> None:
    path = _write(tmp_path / "nologs.jsonl", [envelope(signal="logs", payload={"resourceMetrics": []})])

    with pytest.raises(CaptureError, match="resourceLogs"):
        list(CaptureReader(path))


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CaptureError, match="directory") as exc_info:
        list(CaptureReader(tmp_path))
    assert tmp_path.name in str(exc_info.value)


def test_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    with pytest.raises(CaptureError, match="does not exist"):
        list(CaptureReader(path))


def test_crlf_line_is_accepted(tmp_path: Path) -> None:
    row = envelope(signal="logs", payload=resource_logs([]))
    path = tmp_path / "crlf.jsonl"
    path.write_bytes((json.dumps(row) + "\r\n").encode("utf-8"))
    assert len(list(CaptureReader(path))) == 1


def test_json_array_root_fails(tmp_path: Path) -> None:
    path = tmp_path / "array.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="JSON root must be an object"):
        list(CaptureReader(path))


def test_empty_source_fails(tmp_path: Path) -> None:
    path = _write(tmp_path / "source.jsonl", [envelope(signal="logs", payload=resource_logs([]), source=" ")])
    with pytest.raises(CaptureError, match="source must be a non-empty string"):
        list(CaptureReader(path))


def test_invalid_timestamp_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "ts.jsonl",
        [envelope(signal="logs", payload=resource_logs([]), received_at="not-a-date")],
    )
    with pytest.raises(CaptureError, match="ISO 8601"):
        list(CaptureReader(path))


def test_non_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "fifo.jsonl"
    os.mkfifo(path)
    with pytest.raises(CaptureError, match="regular file"):
        list(CaptureReader(path))


def test_read_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path / "perm.jsonl", [envelope(signal="logs", payload=resource_logs([]))])

    def fail_open(*_args: object, **_kwargs: object) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(CaptureError, match="permission denied"):
        list(CaptureReader(path))


def test_error_includes_filename_and_line_but_not_payload(tmp_path: Path) -> None:
    secret = "developer@example.invalid"
    row = envelope(signal="logs", payload=resource_logs([{"body": {"stringValue": secret}}]))
    row["schema_version"] = 9
    path = _write(tmp_path / "secret.jsonl", [row])

    with pytest.raises(CaptureError) as exc_info:
        list(CaptureReader(path))
    message = str(exc_info.value)
    assert "secret.jsonl:1" in message
    assert secret not in message
    assert "resourceLogs" not in message


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_json_constants(tmp_path: Path, token: str) -> None:
    path = tmp_path / "nonfinite.jsonl"
    path.write_text(
        '{"schema_version":1,"received_at":"2026-08-15T10:00:00+00:00",'
        '"source":"claude-code","signal":"logs",'
        f'"payload":{{"resourceLogs":[{{"n":{token}}}]}}}}\n',
        encoding="utf-8",
    )
    with pytest.raises(CaptureError, match="invalid JSON") as exc_info:
        list(CaptureReader(path))
    message = str(exc_info.value)
    assert "nonfinite.jsonl:1" in message
    assert token not in message
    assert "resourceLogs" not in message


def test_rejects_overflow_float(tmp_path: Path) -> None:
    path = tmp_path / "overflow.jsonl"
    path.write_text(
        '{"schema_version":1,"received_at":"2026-08-15T10:00:00+00:00",'
        '"source":"claude-code","signal":"logs",'
        '"payload":{"resourceLogs":[{"n":1e999}]}}\n',
        encoding="utf-8",
    )
    with pytest.raises(CaptureError, match="invalid JSON") as exc_info:
        list(CaptureReader(path))
    assert "1e999" not in str(exc_info.value)
