"""Shared Cursor Cloud Agents API v1 helpers for repository automation.

This module is not part of the CAPT runtime package. It authenticates to
Cursor, posts create-agent requests, and interprets create responses. It
never prints API keys, authorization headers, or response payloads.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

type CreateAgentOutcome = Literal["created", "already_dispatched"]

CURSOR_AGENTS_URL = "https://api.cursor.com/v1/agents"
CURSOR_AGENT_URL_PREFIX = "https://cursor.com/agents/"
CURSOR_HTTP_TIMEOUT_SECONDS = 30
AGENT_ID_CONFLICT = "agent_id_conflict"


class CursorApiError(Exception):
    """Cursor API failure. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str


@dataclass(frozen=True, slots=True)
class CreateAgentResult:
    outcome: CreateAgentOutcome
    agent_id: str
    agent_url: str
    run_id: str | None
    message: str


def authorization_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode()).decode("ascii")
    return f"Basic {token}"


def post_json(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=CURSOR_HTTP_TIMEOUT_SECONDS) as response:
            return HttpResponse(int(response.status), response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(int(exc.code), payload)
    except urllib.error.URLError:
        raise CursorApiError("Cursor API request failed") from None


def agent_url(agent_id: str) -> str:
    return f"{CURSOR_AGENT_URL_PREFIX}{agent_id}"


def interpret_create_agent_response(subject: str, agent_id: str, response: HttpResponse) -> CreateAgentResult:
    """Interpret a Cursor create-agent HTTP response without exposing payloads."""
    if response.status_code == 201:
        return _created_result(subject, agent_id, response.body)
    if response.status_code == 409:
        code = cursor_error_code(response.body)
        if code == AGENT_ID_CONFLICT:
            return CreateAgentResult(
                outcome="already_dispatched",
                agent_id=agent_id,
                agent_url=agent_url(agent_id),
                run_id=None,
                message=f"{subject} already dispatched to Cursor agent {agent_id}; not creating another agent",
            )
        if code is None:
            raise CursorApiError("Cursor API returned HTTP 409")
        raise CursorApiError(f"Cursor API returned HTTP 409 ({code})")
    raise CursorApiError(f"Cursor API returned HTTP {response.status_code}")


def cursor_error_code(body: str) -> str | None:
    parsed = _load_json_value(body)
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if not isinstance(code, str) or not code:
        return None
    return code


def _created_result(subject: str, agent_id: str, body: str) -> CreateAgentResult:
    parsed = _load_json_value(body)
    resolved_url = agent_url(agent_id)
    run_id: str | None = None
    if isinstance(parsed, dict):
        agent = parsed.get("agent")
        if isinstance(agent, dict):
            returned_id = agent.get("id")
            if isinstance(returned_id, str) and returned_id:
                agent_id = returned_id
            returned_url = agent.get("url")
            if isinstance(returned_url, str) and returned_url.startswith(CURSOR_AGENT_URL_PREFIX):
                resolved_url = returned_url
        run = parsed.get("run")
        if isinstance(run, dict):
            returned_run = run.get("id")
            if isinstance(returned_run, str) and returned_run:
                run_id = returned_run
    return CreateAgentResult(
        outcome="created",
        agent_id=agent_id,
        agent_url=resolved_url,
        run_id=run_id,
        message=f"{subject} dispatched to Cursor agent {agent_id}",
    )


def _load_json_value(text: str) -> object:
    try:
        return json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        return None
