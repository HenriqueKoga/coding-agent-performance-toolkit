import subprocess
from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest

from coding_agent_performance.diagnostics import (
    CheckResult,
    CheckStatus,
    DiagnosticReport,
    check_python,
    check_tool,
    collect_diagnostics,
    parse_version,
    query_version,
    render_report,
)


def _which_from(commands: Mapping[str, str | None]) -> Callable[[str], str | None]:
    def which(command: str) -> str | None:
        return commands.get(command)

    return which


def _completed(
    args: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_check_python_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.sys",
        SimpleNamespace(version_info=SimpleNamespace(major=3, minor=14, micro=6)),
    )

    result = check_python()

    assert result.status is CheckStatus.OK
    assert result.detail == "Python 3.14.6"
    assert result.essential is True


def test_check_python_incompatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.sys",
        SimpleNamespace(version_info=SimpleNamespace(major=3, minor=13, micro=2)),
    )

    result = check_python()

    assert result.status is CheckStatus.FAIL
    assert result.detail == "Python 3.13.2 (requires 3.14 or later)"
    assert result.essential is True


def test_git_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"git": "/usr/bin/git"}))

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs.get("shell", False) is False
        return _completed(args, stdout="git version 2.51.0\n")

    monkeypatch.setattr("coding_agent_performance.diagnostics.subprocess.run", fake_run)

    result = check_tool(name="Git", command="git", essential=True)

    assert result.status is CheckStatus.OK
    assert result.detail == "Git 2.51.0"


def test_git_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"git": None}))

    result = check_tool(name="Git", command="git", essential=True)

    assert result.status is CheckStatus.FAIL
    assert result.detail == "Git was not found"


def test_claude_code_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"claude": "/usr/bin/claude"}))
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, stdout="2.1.211 (Claude Code)\n"),
    )

    result = check_tool(name="Claude Code", command="claude", essential=False)

    assert result.status is CheckStatus.OK
    assert result.detail == "Claude Code 2.1.211"


def test_claude_code_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"claude": None}))

    result = check_tool(name="Claude Code", command="claude", essential=False)

    assert result.status is CheckStatus.WARN
    assert result.detail == "Claude Code was not found"


def test_codex_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"codex": "/usr/bin/codex"}))
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, stdout="codex-cli 0.50.0\n"),
    )

    result = check_tool(name="Codex", command="codex", essential=False)

    assert result.status is CheckStatus.OK
    assert result.detail == "Codex 0.50.0"


def test_codex_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"codex": None}))

    result = check_tool(name="Codex", command="codex", essential=False)

    assert result.status is CheckStatus.WARN
    assert result.detail == "Codex was not found"


def test_version_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"git": "/usr/bin/git"}))
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="fatal: broken\n"),
    )

    result = check_tool(name="Git", command="git", essential=True)

    assert result.status is CheckStatus.FAIL
    assert result.detail == "Git could not be queried"


def test_optional_version_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"codex": "/usr/bin/codex"}))
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, returncode=1, stderr="error\n"),
    )

    result = check_tool(name="Codex", command="codex", essential=False)

    assert result.status is CheckStatus.WARN
    assert result.detail == "Codex could not be queried"


def test_version_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=args, timeout=5)

    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"git": "/usr/bin/git"}))
    monkeypatch.setattr("coding_agent_performance.diagnostics.subprocess.run", raise_timeout)

    result = check_tool(name="Git", command="git", essential=True)

    assert result.status is CheckStatus.FAIL
    assert result.detail == "Git could not be queried"


def test_version_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_oserror(_args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("exec format error")

    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"claude": "/usr/bin/claude"}))
    monkeypatch.setattr("coding_agent_performance.diagnostics.subprocess.run", raise_oserror)

    result = check_tool(name="Claude Code", command="claude", essential=False)

    assert result.status is CheckStatus.WARN
    assert result.detail == "Claude Code could not be queried"


def test_unexpected_version_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coding_agent_performance.diagnostics.shutil.which", _which_from({"git": "/usr/bin/git"}))
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, stdout="not a version string\n"),
    )

    result = check_tool(name="Git", command="git", essential=True)

    assert result.status is CheckStatus.FAIL
    assert result.detail == "Git could not be queried"


def test_parse_version() -> None:
    assert parse_version("git version 2.51.0") == "2.51.0"
    assert parse_version("2.1.211 (Claude Code)") == "2.1.211"
    assert parse_version("not a version string") is None
    assert parse_version("") is None


def test_query_version_reads_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.subprocess.run",
        lambda args, **_kwargs: _completed(args, stdout="", stderr="2.3.4\n"),
    )

    assert query_version("/usr/bin/claude") == "2.3.4"


def test_collect_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.sys",
        SimpleNamespace(version_info=SimpleNamespace(major=3, minor=14, micro=6)),
    )
    monkeypatch.setattr(
        "coding_agent_performance.diagnostics.shutil.which",
        _which_from({"git": "/usr/bin/git", "claude": None, "codex": "/usr/bin/codex"}),
    )

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        executable = args[0]
        if executable == "/usr/bin/git":
            return _completed(args, stdout="git version 2.51.0\n")
        if executable == "/usr/bin/codex":
            return _completed(args, stdout="0.42.0\n")
        return _completed(args, returncode=1, stderr="missing\n")

    monkeypatch.setattr("coding_agent_performance.diagnostics.subprocess.run", fake_run)

    report = collect_diagnostics()
    rendered = render_report(report)

    assert report.ok is True
    assert rendered.splitlines() == [
        "[OK] Python 3.14.6",
        "[OK] Git 2.51.0",
        "[WARN] Claude Code was not found",
        "[OK] Codex 0.42.0",
    ]


def test_report_not_ok_when_essential_fails() -> None:
    report = DiagnosticReport(
        checks=(
            CheckResult(status=CheckStatus.FAIL, detail="Python 3.13.2 (requires 3.14 or later)", essential=True),
            CheckResult(status=CheckStatus.WARN, detail="Codex was not found"),
        )
    )

    assert report.ok is False
    assert render_report(report) == ("[FAIL] Python 3.13.2 (requires 3.14 or later)\n[WARN] Codex was not found")
