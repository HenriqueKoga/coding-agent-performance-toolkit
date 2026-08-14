import runpy
import sys
from collections.abc import Callable

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app
from coding_agent_performance.diagnostics import CheckResult, CheckStatus, DiagnosticReport

runner = CliRunner()


def test_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["--help"], color=False)
    text = visible(result.output)

    assert result.exit_code == 0
    assert "capt" in text
    assert "doctor" in text
    assert "--version" in text


def test_version() -> None:
    result = runner.invoke(app, ["--version"], color=False)

    assert result.exit_code == 0
    assert result.stdout.strip() == "capt 0.1.0"


def test_doctor_help() -> None:
    result = runner.invoke(app, ["doctor", "--help"], color=False)

    assert result.exit_code == 0
    assert "local environment" in result.stdout.lower()


def test_doctor_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.cli.collect_diagnostics",
        lambda: DiagnosticReport(
            checks=(
                CheckResult(status=CheckStatus.OK, detail="Python 3.14.6", essential=True),
                CheckResult(status=CheckStatus.OK, detail="Git 2.51.0", essential=True),
                CheckResult(status=CheckStatus.WARN, detail="Claude Code was not found"),
                CheckResult(status=CheckStatus.WARN, detail="Codex was not found"),
            )
        ),
    )

    result = runner.invoke(app, ["doctor"], color=False)

    assert result.exit_code == 0
    assert "[OK] Python 3.14.6" in result.stdout
    assert "[OK] Git 2.51.0" in result.stdout
    assert "[WARN] Claude Code was not found" in result.stdout
    assert "[WARN] Codex was not found" in result.stdout


def test_doctor_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "coding_agent_performance.cli.collect_diagnostics",
        lambda: DiagnosticReport(
            checks=(
                CheckResult(status=CheckStatus.OK, detail="Python 3.14.6", essential=True),
                CheckResult(status=CheckStatus.FAIL, detail="Git was not found", essential=True),
            )
        ),
    )

    result = runner.invoke(app, ["doctor"], color=False)

    assert result.exit_code == 1
    assert "[FAIL] Git was not found" in result.stdout


def test_module_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["capt", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("coding_agent_performance", run_name="__main__")

    assert exc_info.value.code in {0, None}
