import re
from collections.abc import Callable

import pytest

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[A-Za-z]|\]8;;[^\x1b\x07]*(?:\x1b\\|\x07))")


@pytest.fixture(autouse=True)
def _plain_cli_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "120")


@pytest.fixture
def visible() -> Callable[[str], str]:
    def _visible(text: str) -> str:
        return _ANSI_RE.sub("", text)

    return _visible
