import errno
import os
import stat
from pathlib import Path

import pytest

from coding_agent_performance.trace.handoff_output import HandoffOutputError, write_handoff_file

_CONTENT = "handoff-body\n"


def _temp_siblings(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.name.startswith(".capt-tmp-"))


def _assert_path_free(message: str, *paths: Path) -> None:
    for path in paths:
        assert str(path) not in message
        assert str(path.resolve()) not in message
        assert str(path.parent) not in message or path.parent == Path(".")


def test_creates_new_file_with_complete_content(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.txt"
    write_handoff_file(destination, _CONTENT, overwrite=False)
    assert destination.read_text(encoding="utf-8") == _CONTENT
    assert _temp_siblings(tmp_path) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_new_file_uses_posix_0600(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.txt"
    write_handoff_file(destination, _CONTENT, overwrite=False)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_exclusive_publish_collision_uses_basename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "handoff.txt"
    publish = "link" if os.name == "posix" else "rename"

    def exists(_source: str, _target: str) -> None:
        raise FileExistsError(errno.EEXIST, "File exists")

    monkeypatch.setattr(os, publish, exists)
    with pytest.raises(HandoffOutputError, match=r"Handoff file already exists: handoff\.txt") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=False)
    assert not destination.exists()
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), destination, tmp_path)


def test_failed_publish_removes_temp_and_leaves_destination_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "handoff.txt"
    publish = "link" if os.name == "posix" else "rename"

    def boom(_source: str, _target: str) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, publish, boom)
    with pytest.raises(HandoffOutputError, match="No space left on device") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=False)
    assert not destination.exists()
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), destination, tmp_path)


def test_successful_publish_does_not_rollback_if_temp_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "handoff.txt"
    real_unlink = Path.unlink

    def busy_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.startswith(".capt-tmp-"):
            raise OSError("device busy")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy_unlink)
    write_handoff_file(destination, _CONTENT, overwrite=False)
    assert destination.read_text(encoding="utf-8") == _CONTENT


def test_existing_regular_file_without_overwrite_is_unchanged(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("previous\n", encoding="utf-8")
    with pytest.raises(HandoffOutputError, match=r"Handoff file already exists: handoff\.txt") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=False)
    assert destination.read_text(encoding="utf-8") == "previous\n"
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), destination, tmp_path)
    assert "handoff.txt" in str(exc_info.value)


def test_overwrite_replaces_regular_file(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("previous\n", encoding="utf-8")
    write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.read_text(encoding="utf-8") == _CONTENT
    assert _temp_siblings(tmp_path) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_replaced_file_uses_posix_0600(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("previous\n", encoding="utf-8")
    os.chmod(destination, 0o644)
    write_handoff_file(destination, _CONTENT, overwrite=True)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_symlink_destination_is_refused_even_with_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("keep\n", encoding="utf-8")
    destination = tmp_path / "link.txt"
    destination.symlink_to(target)
    with pytest.raises(HandoffOutputError, match="path is a symbolic link") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep\n"
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), destination, target, tmp_path)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_dangling_symlink_is_refused_even_with_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "dangling.txt"
    destination.symlink_to(tmp_path / "missing-target.txt")
    with pytest.raises(HandoffOutputError, match="path is a symbolic link"):
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.is_symlink()
    assert _temp_siblings(tmp_path) == []


def test_directory_destination_is_refused_even_with_overwrite(tmp_path: Path) -> None:
    with pytest.raises(HandoffOutputError, match="path is a directory") as exc_info:
        write_handoff_file(tmp_path, _CONTENT, overwrite=True)
    assert tmp_path.is_dir()
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), tmp_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_fifo_destination_is_refused_even_with_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "handoff.fifo"
    os.mkfifo(destination)
    with pytest.raises(HandoffOutputError, match="path is not a regular file") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert stat.S_ISFIFO(os.lstat(destination).st_mode)
    assert _temp_siblings(tmp_path) == []
    _assert_path_free(str(exc_info.value), destination, tmp_path)


def test_missing_parent_is_refused_and_not_created(tmp_path: Path) -> None:
    parent = tmp_path / "missing"
    destination = parent / "handoff.txt"
    with pytest.raises(HandoffOutputError, match="parent directory does not exist") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert not parent.exists()
    _assert_path_free(str(exc_info.value), destination, parent, tmp_path)


def test_non_directory_parent_is_refused(tmp_path: Path) -> None:
    parent = tmp_path / "not-a-dir"
    parent.write_text("file\n", encoding="utf-8")
    destination = parent / "handoff.txt"
    with pytest.raises(HandoffOutputError, match="parent path is not a directory") as exc_info:
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert parent.read_text(encoding="utf-8") == "file\n"
    _assert_path_free(str(exc_info.value), destination, parent, tmp_path)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_parent_symlink_to_directory_is_allowed(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent)
    destination = linked_parent / "handoff.txt"
    write_handoff_file(destination, _CONTENT, overwrite=False)
    assert (real_parent / "handoff.txt").read_text(encoding="utf-8") == _CONTENT


def test_expands_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    write_handoff_file(Path("~/handoff.txt"), _CONTENT, overwrite=False)
    assert (tmp_path / "handoff.txt").read_text(encoding="utf-8") == _CONTENT


def test_dash_is_an_ordinary_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_handoff_file(Path("-"), _CONTENT, overwrite=False)
    assert (tmp_path / "-").read_text(encoding="utf-8") == _CONTENT


def test_does_not_follow_destination_by_resolving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "handoff.txt"

    def boom(self: Path) -> Path:
        raise AssertionError("destination must not be resolved")

    monkeypatch.setattr(Path, "resolve", boom)
    write_handoff_file(destination, _CONTENT, overwrite=False)
    assert destination.read_text(encoding="utf-8") == _CONTENT


def _patch_nofollow_open(
    monkeypatch: pytest.MonkeyPatch, *, errno_code: int, strerror: str, unlink: bool = False
) -> None:
    real_open = os.open

    def open_maybe(path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if flags == os.O_WRONLY | os.O_NOFOLLOW:
            if unlink:
                Path(os.fsdecode(path)).unlink()
            raise OSError(errno_code, strerror)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", open_maybe)


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW required")
def test_force_replace_maps_eloop_to_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("old\n", encoding="utf-8")
    _patch_nofollow_open(monkeypatch, errno_code=errno.ELOOP, strerror="Too many levels of symbolic links")
    with pytest.raises(HandoffOutputError, match="path is a symbolic link"):
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.read_text(encoding="utf-8") == "old\n"
    assert _temp_siblings(tmp_path) == []


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW required")
def test_force_replace_maps_eisdir_to_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("old\n", encoding="utf-8")
    _patch_nofollow_open(monkeypatch, errno_code=errno.EISDIR, strerror="Is a directory")
    with pytest.raises(HandoffOutputError, match="path is a directory"):
        write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.read_text(encoding="utf-8") == "old\n"


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW required")
def test_force_replace_allows_vanished_regular_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "handoff.txt"
    destination.write_text("old\n", encoding="utf-8")
    _patch_nofollow_open(monkeypatch, errno_code=errno.ENOENT, strerror="No such file or directory", unlink=True)
    write_handoff_file(destination, _CONTENT, overwrite=True)
    assert destination.read_text(encoding="utf-8") == _CONTENT
