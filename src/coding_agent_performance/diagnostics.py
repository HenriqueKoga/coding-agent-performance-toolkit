"""Collect and render local environment diagnostics."""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

COMMAND_TIMEOUT_SECONDS: Final = 5
REQUIRED_PYTHON: Final = (3, 14)
VERSION_PATTERN: Final = re.compile(r"\d+(?:\.\d+)+")


class CheckStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: CheckStatus
    detail: str
    essential: bool = False


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        return all(check.status is not CheckStatus.FAIL or not check.essential for check in self.checks)


def collect_diagnostics() -> DiagnosticReport:
    return DiagnosticReport(
        checks=(
            check_python(),
            check_tool(name="Git", command="git", essential=True),
            check_tool(name="Claude Code", command="claude", essential=False),
            check_tool(name="Codex", command="codex", essential=False),
        )
    )


def render_report(report: DiagnosticReport) -> str:
    return "\n".join(f"[{check.status}] {check.detail}" for check in report.checks)


def check_python() -> CheckResult:
    info = sys.version_info
    detail = f"Python {info.major}.{info.minor}.{info.micro}"
    if (info.major, info.minor) >= REQUIRED_PYTHON:
        return CheckResult(status=CheckStatus.OK, detail=detail, essential=True)
    return CheckResult(
        status=CheckStatus.FAIL,
        detail=f"{detail} (requires 3.14 or later)",
        essential=True,
    )


def check_tool(*, name: str, command: str, essential: bool) -> CheckResult:
    executable = shutil.which(command)
    if executable is None:
        status = CheckStatus.FAIL if essential else CheckStatus.WARN
        return CheckResult(status=status, detail=f"{name} was not found", essential=essential)

    parsed_version = query_version(executable)
    if parsed_version is None:
        status = CheckStatus.FAIL if essential else CheckStatus.WARN
        return CheckResult(status=status, detail=f"{name} could not be queried", essential=essential)
    return CheckResult(status=CheckStatus.OK, detail=f"{name} {parsed_version}", essential=essential)


def query_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.TimeoutExpired:
        return None

    if completed.returncode != 0:
        return None
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return parse_version(output)


def parse_version(output: str) -> str | None:
    match = VERSION_PATTERN.search(output)
    if match is None:
        return None
    return match.group(0)
