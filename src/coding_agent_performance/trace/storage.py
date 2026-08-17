"""Local JSONL capture storage for raw OTLP envelopes."""

import os
import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, TextIO

from platformdirs import user_state_path

from coding_agent_performance.trace.capture import SCHEMA_VERSION, CaptureEnvelope

_FILE_FLAGS: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY
_DIR_MODE: Final = 0o700
_FILE_MODE: Final = 0o600


class CaptureStorageError(Exception):
    """Expected failure while creating or writing a capture file."""


class LatestCaptureError(Exception):
    """Expected failure while selecting the newest local capture."""


class CaptureListError(Exception):
    """Expected failure while listing local captures."""


@dataclass(frozen=True, slots=True)
class CaptureListing:
    name: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class _CaptureCandidate:
    name: str
    size_bytes: int
    mtime_ns: int


def default_captures_dir() -> Path:
    return user_state_path("capt", appauthor=False) / "captures"


def new_capture_path(directory: Path, prefix: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{prefix}-{timestamp}-{secrets.token_hex(3)}.jsonl"


def latest_capture(directory: Path) -> Path:
    try:
        if not directory.exists():
            raise LatestCaptureError("Default capture directory does not exist.")
        if not directory.is_dir():
            raise LatestCaptureError("Default capture path is not a directory.")
        selected = _select_latest_capture(directory)
    except LatestCaptureError:
        raise
    except OSError as exc:
        raise LatestCaptureError(_directory_read_error(exc)) from exc
    if selected is None:
        raise LatestCaptureError("No capture files found in the default capture directory.")
    return selected


def list_captures(directory: Path) -> tuple[CaptureListing, ...]:
    try:
        if not directory.exists():
            return ()
        if not directory.is_dir():
            raise CaptureListError("Default capture path is not a directory.")
        candidates = _scan_eligible_captures(directory)
    except CaptureListError:
        raise
    except OSError as exc:
        raise CaptureListError(_directory_read_error(exc)) from exc
    return tuple(_to_listing(candidate) for candidate in candidates)


def _select_latest_capture(directory: Path) -> Path | None:
    selected: _CaptureCandidate | None = None
    for candidate in _iter_eligible_captures(directory):
        if selected is None or _capture_order_key(candidate) > _capture_order_key(selected):
            selected = candidate
    if selected is None:
        return None
    return directory / selected.name


def _scan_eligible_captures(directory: Path) -> list[_CaptureCandidate]:
    candidates = list(_iter_eligible_captures(directory))
    candidates.sort(key=_capture_order_key, reverse=True)
    return candidates


def _iter_eligible_captures(directory: Path) -> Iterator[_CaptureCandidate]:
    with os.scandir(directory) as entries:
        for entry in entries:
            if not _is_eligible_capture(entry):
                continue
            stat_result = entry.stat(follow_symlinks=False)
            yield _CaptureCandidate(
                name=entry.name,
                size_bytes=stat_result.st_size,
                mtime_ns=stat_result.st_mtime_ns,
            )


def _capture_order_key(candidate: _CaptureCandidate) -> tuple[int, str]:
    return (candidate.mtime_ns, candidate.name)


def _is_eligible_capture(entry: os.DirEntry[str]) -> bool:
    return entry.name.endswith(".jsonl") and not entry.is_symlink() and entry.is_file(follow_symlinks=False)


def _to_listing(candidate: _CaptureCandidate) -> CaptureListing:
    return CaptureListing(
        name=candidate.name,
        size_bytes=candidate.size_bytes,
        modified_at=_utc_datetime_from_mtime_ns(candidate.mtime_ns),
    )


def _utc_datetime_from_mtime_ns(mtime_ns: int) -> datetime:
    seconds, nanos = divmod(mtime_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=nanos // 1_000)


def _directory_read_error(exc: OSError) -> str:
    detail = exc.strerror or str(exc) or "read error"
    return f"Could not read default capture directory: {detail}"


def make_envelope(*, source: str, signal: str, payload: dict[str, object]) -> CaptureEnvelope:
    received_at = datetime.now(UTC)
    return CaptureEnvelope(
        schema_version=SCHEMA_VERSION,
        received_at=received_at,
        source=source,
        signal=signal,
        payload=payload,
    )


class CaptureWriter:
    def __init__(self, path: Path, file: TextIO) -> None:
        self.path = path
        self._file = file
        self._lock = threading.Lock()
        self._closed = False

    @classmethod
    def create(cls, path: Path, *, restrict_directory: bool = True) -> CaptureWriter:
        resolved = path.expanduser().resolve()
        if resolved.exists():
            raise CaptureStorageError(f"Capture file already exists: {resolved}")
        _prepare_directory(resolved.parent, restrict=restrict_directory)
        try:
            fd = os.open(resolved, _FILE_FLAGS, _FILE_MODE if os.name == "posix" else 0o666)
        except FileExistsError as exc:
            raise CaptureStorageError(f"Capture file already exists: {resolved}") from exc
        except OSError as exc:
            detail = exc.strerror or str(exc)
            raise CaptureStorageError(f"Could not create capture file: {detail}") from exc
        try:
            if os.name == "posix":
                os.chmod(resolved, _FILE_MODE)
            file = os.fdopen(fd, "w", encoding="utf-8")
        except OSError as exc:
            os.close(fd)
            resolved.unlink(missing_ok=True)
            detail = exc.strerror or str(exc)
            raise CaptureStorageError(f"Could not create capture file: {detail}") from exc
        return cls(resolved, file)

    def append(self, envelope: CaptureEnvelope) -> None:
        try:
            line = envelope.to_json()
        except TypeError, ValueError:
            raise CaptureStorageError("Could not serialize capture envelope.") from None
        with self._lock:
            if self._closed:
                raise CaptureStorageError("Capture file is closed.")
            self._file.write(line)
            self._file.write("\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._file.flush()
            self._file.close()
            self._closed = True


def _prepare_directory(directory: Path, *, restrict: bool) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if restrict and os.name == "posix":
            os.chmod(directory, _DIR_MODE)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise CaptureStorageError(f"Could not create capture directory: {detail}") from exc
