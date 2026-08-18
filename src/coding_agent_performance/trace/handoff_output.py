"""Exclusive local file writer for compact trace handoffs."""

import errno
import os
import secrets
import stat
from pathlib import Path
from typing import Final

_FILE_FLAGS: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY
_FILE_MODE: Final = 0o600
_TEMP_PREFIX: Final = ".capt-tmp-"
_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)


class HandoffOutputError(Exception):
    """Expected failure while persisting a handoff file."""


def write_handoff_file(path: Path, content: str, *, overwrite: bool) -> None:
    destination = path.expanduser()
    _require_parent_directory(destination.parent)
    _classify_destination(destination, overwrite=overwrite)
    fd, temp = _create_temp_file(destination.parent)
    published = False
    try:
        _write_temp(fd, temp, content)
        _publish(temp, destination, overwrite=overwrite)
        published = True
    except HandoffOutputError:
        _remove_temp(temp)
        raise
    except OSError as exc:
        _remove_temp(temp)
        raise HandoffOutputError(_os_error_message(exc)) from exc
    if published:
        _remove_temp_after_success(temp)


def _classify_destination(path: Path, *, overwrite: bool) -> None:
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        if exc.errno == errno.ENOTDIR:
            raise HandoffOutputError("Could not write handoff file: parent path is not a directory.") from exc
        raise HandoffOutputError(_os_error_message(exc)) from exc
    if stat.S_ISREG(status.st_mode):
        if overwrite:
            return
        raise HandoffOutputError(f"Handoff file already exists: {path.name}")
    raise HandoffOutputError(_non_regular_message(status.st_mode))


def _require_parent_directory(parent: Path) -> None:
    if parent.is_dir():
        return
    if parent.exists():
        raise HandoffOutputError("Could not write handoff file: parent path is not a directory.")
    raise HandoffOutputError("Could not write handoff file: parent directory does not exist.")


def _create_temp_file(parent: Path) -> tuple[int, Path]:
    while True:
        temp = parent / f"{_TEMP_PREFIX}{secrets.token_hex(8)}"
        try:
            mode = _FILE_MODE if os.name == "posix" else 0o666
            return os.open(temp, _FILE_FLAGS, mode), temp
        except FileExistsError:
            continue
        except OSError as exc:
            raise HandoffOutputError(_os_error_message(exc)) from exc


def _write_temp(fd: int, temp: Path, content: str) -> None:
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except OSError:
        os.close(fd)
        temp.unlink(missing_ok=True)
        raise
    try:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    except OSError:
        handle.close()
        temp.unlink(missing_ok=True)
        raise
    handle.close()
    if os.name == "posix":
        os.chmod(temp, _FILE_MODE)


def _publish(temp: Path, destination: Path, *, overwrite: bool) -> None:
    if overwrite:
        _publish_replace(temp, destination)
        return
    _publish_exclusive(temp, destination)


def _publish_exclusive(temp: Path, destination: Path) -> None:
    try:
        if os.name == "posix":
            os.link(temp, destination)
        else:
            os.rename(temp, destination)
    except OSError as exc:
        if exc.errno == errno.EEXIST or isinstance(exc, FileExistsError):
            raise HandoffOutputError(f"Handoff file already exists: {destination.name}") from exc
        raise HandoffOutputError(_os_error_message(exc)) from exc


def _publish_replace(temp: Path, destination: Path) -> None:
    if os.name == "posix" and _NOFOLLOW:
        _confirm_regular_file_nofollow(destination)
    try:
        os.replace(temp, destination)
    except OSError as exc:
        raise HandoffOutputError(_os_error_message(exc)) from exc


def _confirm_regular_file_nofollow(destination: Path) -> None:
    try:
        fd = os.open(destination, os.O_WRONLY | _NOFOLLOW)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise HandoffOutputError(_replace_open_error(exc)) from exc
    try:
        status = os.fstat(fd)
    except OSError as exc:
        raise HandoffOutputError(_os_error_message(exc)) from exc
    finally:
        os.close(fd)
    if stat.S_ISREG(status.st_mode):
        return
    raise HandoffOutputError(_non_regular_message(status.st_mode))


def _replace_open_error(exc: OSError) -> str:
    if exc.errno == errno.ELOOP:
        return "Could not write handoff file: path is a symbolic link."
    if exc.errno == errno.EISDIR:
        return "Could not write handoff file: path is a directory."
    return _os_error_message(exc)


def _remove_temp(temp: Path) -> None:
    temp.unlink(missing_ok=True)


def _remove_temp_after_success(temp: Path) -> None:
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        return


def _non_regular_message(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "Could not write handoff file: path is a symbolic link."
    if stat.S_ISDIR(mode):
        return "Could not write handoff file: path is a directory."
    return "Could not write handoff file: path is not a regular file."


def _os_error_message(exc: OSError) -> str:
    detail = exc.strerror or "write error"
    return f"Could not write handoff file: {detail}"
