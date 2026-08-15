"""Streaming reader and shared schema for CAPT JSONL captures."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from coding_agent_performance.trace.json_codec import InvalidJsonError, loads_json

SCHEMA_VERSION: Final = 1
MAX_LINE_BYTES: Final = 16 * 1024 * 1024
_SIGNALS: Final = frozenset({"logs", "metrics"})
_PAYLOAD_KEYS: Final = {"logs": "resourceLogs", "metrics": "resourceMetrics"}


class CaptureError(Exception):
    """Invalid capture file or envelope."""

    def __init__(self, path: Path, reason: str, *, line: int | None = None) -> None:
        self.path = path
        self.line = line
        self.reason = reason
        location = path.name if line is None else f"{path.name}:{line}"
        super().__init__(f"Invalid capture at {location}: {reason}")


@dataclass(frozen=True, slots=True)
class CaptureEnvelope:
    schema_version: int
    received_at: datetime
    source: str
    signal: str
    payload: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "received_at": self.received_at.isoformat(),
                "source": self.source,
                "signal": self.signal,
                "payload": self.payload,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


class CaptureReader:
    """Read a CAPT JSONL capture line by line without loading the file."""

    def __init__(self, path: Path, *, max_line_bytes: int = MAX_LINE_BYTES) -> None:
        self.path = path
        self.max_line_bytes = max_line_bytes

    def __iter__(self) -> Iterator[CaptureEnvelope]:
        _assert_readable_file(self.path)
        source: str | None = None
        envelopes = 0
        try:
            with self.path.open("rb") as handle:
                line_number = 0
                while True:
                    raw = handle.readline(self.max_line_bytes + 1)
                    if not raw:
                        break
                    line_number += 1
                    if len(raw) > self.max_line_bytes and not raw.endswith(b"\n"):
                        raise CaptureError(self.path, "line exceeds size limit", line=line_number)
                    if raw.endswith(b"\n"):
                        raw = raw[:-1]
                    if raw.endswith(b"\r"):
                        raw = raw[:-1]
                    if not raw:
                        raise CaptureError(self.path, "empty line", line=line_number)
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        raise CaptureError(self.path, "invalid UTF-8", line=line_number) from None
                    envelope = _parse_envelope(self.path, line_number, text)
                    if source is None:
                        source = envelope.source
                    elif envelope.source != source:
                        raise CaptureError(self.path, "mixed sources are not allowed", line=line_number)
                    envelopes += 1
                    yield envelope
        except OSError as exc:
            detail = exc.strerror or str(exc) or "read error"
            raise CaptureError(self.path, detail) from exc
        if envelopes == 0:
            raise CaptureError(self.path, "empty capture")


def _assert_readable_file(path: Path) -> None:
    try:
        if path.is_dir():
            raise CaptureError(path, "path is a directory")
        if not path.exists():
            raise CaptureError(path, "file does not exist")
        if not path.is_file():
            raise CaptureError(path, "path is not a regular file")
    except OSError as exc:
        detail = exc.strerror or str(exc) or "read error"
        raise CaptureError(path, detail) from exc


def _parse_envelope(path: Path, line: int, text: str) -> CaptureEnvelope:
    try:
        parsed: object = loads_json(text)
    except InvalidJsonError:
        raise CaptureError(path, "invalid JSON", line=line) from None
    if not isinstance(parsed, dict):
        raise CaptureError(path, "JSON root must be an object", line=line)

    schema_version = parsed.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise CaptureError(path, f"unsupported schema_version {schema_version}", line=line)

    received_at = _parse_received_at(path, line, parsed.get("received_at"))

    source = parsed.get("source")
    if not isinstance(source, str) or not source.strip():
        raise CaptureError(path, "source must be a non-empty string", line=line)

    signal = parsed.get("signal")
    if signal not in _SIGNALS:
        raise CaptureError(path, "signal must be logs or metrics", line=line)

    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        raise CaptureError(path, "payload must be a JSON object", line=line)

    expected_key = _PAYLOAD_KEYS[signal]
    value = payload.get(expected_key)
    if not isinstance(value, list):
        raise CaptureError(path, f"payload must contain {expected_key}", line=line)

    return CaptureEnvelope(
        schema_version=SCHEMA_VERSION,
        received_at=received_at,
        source=source,
        signal=signal,
        payload=payload,
    )


def _parse_received_at(path: Path, line: int, value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise CaptureError(path, "received_at must be an ISO 8601 timestamp", line=line)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CaptureError(path, "received_at must be an ISO 8601 timestamp", line=line) from None
    if parsed.tzinfo is None:
        raise CaptureError(path, "received_at must include a timezone", line=line)
    return parsed
