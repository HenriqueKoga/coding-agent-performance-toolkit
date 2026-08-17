"""Deterministic Cursor Cloud Agent dispatch for Agent Task Issues.

This module is repository automation, not part of the CAPT runtime package.
It validates `agent:ready` Issue preconditions and builds an idempotent
Cursor Cloud Agents API v1 create request. It never mutates lifecycle or
risk labels.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

from agent_lifecycle import (
    AGENT_READY,
    GITHUB_REST_READ_MAX_ATTEMPTS,
    GITHUB_REST_READ_RETRY_DELAY_SECONDS,
    LIFECYCLE_LABELS,
    RISK_LABELS,
    GitHubApiResponse,
    github_http_status_from_stderr,
    is_retryable_github_http_status,
)

type DispatchOutcome = Literal["created", "already_dispatched"]

OWNER_REPO = "HenriqueKoga/coding-agent-performance-toolkit"
REPOSITORY_URL = f"https://github.com/{OWNER_REPO}"
STARTING_REF = "main"
CURSOR_AGENTS_URL = "https://api.cursor.com/v1/agents"
CURSOR_AGENT_URL_PREFIX = "https://cursor.com/agents/"
CURSOR_HTTP_TIMEOUT_SECONDS = 30
AGENT_ID_CONFLICT = "agent_id_conflict"
HUMAN_SENDER_TYPE = "User"

_AGENT_ID_NAMESPACE = uuid.NAMESPACE_URL


class DispatchError(Exception):
    """Invalid dispatch input or Cursor API failure. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class DispatchIssue:
    number: int
    state: str
    title: str
    body: str
    labels: tuple[str, ...]
    is_pull_request: bool


@dataclass(frozen=True, slots=True)
class LabeledIssueEvent:
    added_label: str
    sender_type: str
    issue: DispatchIssue


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    issue_number: int
    request: dict[str, object]
    message: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "issue_number": self.issue_number,
            "request": self.request,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class DispatchResult:
    outcome: DispatchOutcome
    issue_number: int
    agent_id: str
    agent_url: str
    run_id: str | None
    message: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "issue_number": self.issue_number,
            "agent_id": self.agent_id,
            "agent_url": self.agent_url,
            "run_id": self.run_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str


def load_labeled_issue_event(path: Path) -> LabeledIssueEvent:
    payload = _load_json_object(path, "GitHub event file")
    if payload.get("action") != "labeled":
        raise DispatchError("GitHub event action is not a supported issues labeled event")
    added_label = _require_label_name(payload.get("label"), "GitHub event label")
    sender_type = _require_human_sender(payload.get("sender"))
    issue_payload = payload.get("issue")
    if not isinstance(issue_payload, dict):
        raise DispatchError("GitHub event does not contain issue metadata")
    return LabeledIssueEvent(
        added_label=added_label,
        sender_type=sender_type,
        issue=dispatch_issue_from_mapping(issue_payload, "GitHub event issue"),
    )


def dispatch_issue_from_mapping(payload: Mapping[str, object], what: str) -> DispatchIssue:
    number = payload.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise DispatchError(f"{what} number must be a positive integer")
    state = payload.get("state")
    if not isinstance(state, str) or not state:
        raise DispatchError(f"{what} state is not a string")
    title_value = payload.get("title")
    if title_value is None:
        title = ""
    elif isinstance(title_value, str):
        title = title_value
    else:
        raise DispatchError(f"{what} title is not a string")
    body_value = payload.get("body")
    if body_value is None:
        body = ""
    elif isinstance(body_value, str):
        body = body_value
    else:
        raise DispatchError(f"{what} body is not a string")
    return DispatchIssue(
        number=number,
        state=state,
        title=title,
        body=body,
        labels=_label_names(payload.get("labels"), f"{what} labels"),
        is_pull_request="pull_request" in payload,
    )


def read_dispatch_issue(
    repository: str,
    issue_number: int,
    *,
    run_api: Callable[[str], GitHubApiResponse] | None = None,
    sleep: Callable[[float], None] | None = None,
    notify: Callable[[str], None] | None = None,
) -> DispatchIssue:
    """Read Issue metadata from GitHub REST, retrying only bounded transient 5xx failures."""
    _require_positive_issue_number(issue_number)
    owner_repo = _require_owner_repo(repository)
    runner = _run_gh_api if run_api is None else run_api
    sleeper = time.sleep if sleep is None else sleep
    log = _print_stderr if notify is None else notify
    path = f"repos/{owner_repo}/issues/{issue_number}"
    last_status: int | None = None
    attempt = 0
    for attempt in range(1, GITHUB_REST_READ_MAX_ATTEMPTS + 1):
        response = runner(path)
        if response.returncode == 0:
            return _issue_from_rest_payload(response.stdout)
        last_status = github_http_status_from_stderr(response.stderr)
        if not is_retryable_github_http_status(last_status) or attempt == GITHUB_REST_READ_MAX_ATTEMPTS:
            break
        log(
            f"GitHub REST issue #{issue_number} read returned HTTP {last_status} "
            f"(attempt {attempt}/{GITHUB_REST_READ_MAX_ATTEMPTS}); retrying"
        )
        sleeper(GITHUB_REST_READ_RETRY_DELAY_SECONDS)
    raise DispatchError(_rest_read_failure_message(issue_number, last_status, attempt))


def plan_dispatch(added_label: str, issue: DispatchIssue) -> DispatchPlan:
    """Validate Issue preconditions and build the Cursor create request."""
    validate_dispatch_preconditions(added_label, issue)
    request = build_create_agent_request(issue.number)
    return DispatchPlan(
        issue_number=issue.number,
        request=request,
        message=f"Issue #{issue.number} is eligible for Cursor Cloud Agent dispatch",
    )


def validate_dispatch_preconditions(added_label: str, issue: DispatchIssue) -> None:
    if added_label != AGENT_READY:
        raise DispatchError("dispatch runs only when the added label is agent:ready")
    if issue.is_pull_request:
        raise DispatchError(f"#{issue.number} is a pull request; dispatch requires a GitHub Issue")
    if issue.state != "open":
        raise DispatchError(f"Issue #{issue.number} is {issue.state}; dispatch requires an open Issue")
    lifecycle = _require_single_lifecycle(issue.number, issue.labels)
    if lifecycle != AGENT_READY:
        raise DispatchError(f"Issue #{issue.number} lifecycle is {lifecycle}; expected {AGENT_READY}")
    _require_single_risk(issue.number, issue.labels)


def build_prompt(issue_number: int) -> str:
    _require_positive_issue_number(issue_number)
    return (
        f"Implement GitHub Issue #{issue_number} in {OWNER_REPO}.\n"
        "\n"
        "Before making changes:\n"
        "- read AGENTS.md;\n"
        "- read the relevant repository documentation;\n"
        f"- read GitHub Issue #{issue_number} and treat it as the complete task specification.\n"
        "\n"
        "Do not expand scope.\n"
        "Do not mutate lifecycle or risk labels.\n"
        "Run the repository's required validation.\n"
        f"Open a Draft Pull Request with exactly one standalone `Closes #{issue_number}` line.\n"
        "Do not mark the PR ready for review until implementation and validation are complete.\n"
        "Do not merge the PR.\n"
    )


def build_agent_id(issue_number: int) -> str:
    """Return a deterministic `bc-<uuid>` derived from repository + Issue identity."""
    _require_positive_issue_number(issue_number)
    issue_url = f"{REPOSITORY_URL}/issues/{issue_number}"
    return f"bc-{uuid.uuid5(_AGENT_ID_NAMESPACE, issue_url)}"


def build_create_agent_request(issue_number: int) -> dict[str, object]:
    _require_positive_issue_number(issue_number)
    return {
        "agentId": build_agent_id(issue_number),
        "prompt": {"text": build_prompt(issue_number)},
        "name": f"Issue #{issue_number}",
        "repos": [{"url": REPOSITORY_URL, "startingRef": STARTING_REF}],
        "mode": "agent",
        "autoCreatePR": False,
    }


def submit_create_agent(
    issue_number: int,
    request: Mapping[str, object],
    api_key: str,
    *,
    post: Callable[[str, dict[str, str], bytes], HttpResponse] | None = None,
) -> DispatchResult:
    _require_positive_issue_number(issue_number)
    if not api_key:
        raise DispatchError("CURSOR_API_KEY is not set")
    agent_id = request.get("agentId")
    if not isinstance(agent_id, str) or not agent_id:
        raise DispatchError("Cursor request is missing agentId")
    expected_id = build_agent_id(issue_number)
    if agent_id != expected_id:
        raise DispatchError("Cursor request agentId does not match the Issue identity")
    payload = json.dumps(dict(request), allow_nan=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": _authorization_header(api_key),
        "Content-Type": "application/json",
    }
    poster = _post_json if post is None else post
    response = poster(CURSOR_AGENTS_URL, headers, payload)
    return interpret_cursor_create_response(issue_number, agent_id, response)


def interpret_cursor_create_response(issue_number: int, agent_id: str, response: HttpResponse) -> DispatchResult:
    _require_positive_issue_number(issue_number)
    if response.status_code == 201:
        return _created_result(issue_number, agent_id, response.body)
    if response.status_code == 409:
        code = _cursor_error_code(response.body)
        if code == AGENT_ID_CONFLICT:
            return DispatchResult(
                outcome="already_dispatched",
                issue_number=issue_number,
                agent_id=agent_id,
                agent_url=_agent_url(agent_id),
                run_id=None,
                message=(
                    f"Issue #{issue_number} already dispatched to Cursor agent {agent_id}; not creating another agent"
                ),
            )
        if code is None:
            raise DispatchError("Cursor API returned HTTP 409")
        raise DispatchError(f"Cursor API returned HTTP 409 ({code})")
    raise DispatchError(f"Cursor API returned HTTP {response.status_code}")


def _created_result(issue_number: int, agent_id: str, body: str) -> DispatchResult:
    parsed = _load_json_value(body)
    agent_url = _agent_url(agent_id)
    run_id: str | None = None
    if isinstance(parsed, dict):
        agent = parsed.get("agent")
        if isinstance(agent, dict):
            returned_id = agent.get("id")
            if isinstance(returned_id, str) and returned_id:
                agent_id = returned_id
            returned_url = agent.get("url")
            if isinstance(returned_url, str) and returned_url.startswith(CURSOR_AGENT_URL_PREFIX):
                agent_url = returned_url
        run = parsed.get("run")
        if isinstance(run, dict):
            returned_run = run.get("id")
            if isinstance(returned_run, str) and returned_run:
                run_id = returned_run
    return DispatchResult(
        outcome="created",
        issue_number=issue_number,
        agent_id=agent_id,
        agent_url=agent_url,
        run_id=run_id,
        message=f"Issue #{issue_number} dispatched to Cursor agent {agent_id}",
    )


def _cursor_error_code(body: str) -> str | None:
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


def _authorization_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode()).decode("ascii")
    return f"Basic {token}"


def _post_json(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=CURSOR_HTTP_TIMEOUT_SECONDS) as response:
            return HttpResponse(int(response.status), response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(int(exc.code), payload)
    except urllib.error.URLError:
        raise DispatchError("Cursor API request failed") from None


def _agent_url(agent_id: str) -> str:
    return f"{CURSOR_AGENT_URL_PREFIX}{agent_id}"


def _require_single_risk(issue_number: int, labels: Sequence[str]) -> str:
    risks = tuple(label for label in RISK_LABELS if label in labels)
    if not risks:
        raise DispatchError(f"Issue #{issue_number} has no risk:* label")
    if len(risks) > 1:
        rendered = ", ".join(risks)
        raise DispatchError(f"Issue #{issue_number} has multiple risk:* labels: {rendered}")
    return risks[0]


def _require_single_lifecycle(issue_number: int, labels: Sequence[str]) -> str:
    present = tuple(label for label in LIFECYCLE_LABELS if label in labels)
    if not present:
        raise DispatchError(f"Issue #{issue_number} has no lifecycle label")
    if len(present) > 1:
        rendered = ", ".join(present)
        raise DispatchError(f"Issue #{issue_number} has multiple lifecycle labels: {rendered}")
    return present[0]


def _label_names(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DispatchError(f"{what} must be a JSON array")
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            names.append(item)
            continue
        if not isinstance(item, dict):
            raise DispatchError(f"{what} are invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise DispatchError(f"{what} are invalid")
        names.append(name)
    return tuple(names)


def _require_label_name(value: object, what: str) -> str:
    if not isinstance(value, dict):
        raise DispatchError(f"{what} is missing")
    name = value.get("name")
    if not isinstance(name, str) or not name:
        raise DispatchError(f"{what} name is not a string")
    return name


def _require_human_sender(value: object) -> str:
    if not isinstance(value, dict):
        raise DispatchError("GitHub event sender is missing")
    sender_type = value.get("type")
    if not isinstance(sender_type, str) or not sender_type:
        raise DispatchError("GitHub event sender type is not a string")
    if sender_type != HUMAN_SENDER_TYPE:
        raise DispatchError(f"GitHub event sender type is {sender_type}; dispatch requires {HUMAN_SENDER_TYPE}")
    return sender_type


def _issue_from_rest_payload(text: str) -> DispatchIssue:
    parsed = _load_json_value(text)
    if not isinstance(parsed, dict):
        raise DispatchError("GitHub REST issue response must be a JSON object")
    return dispatch_issue_from_mapping(parsed, "GitHub REST issue")


def _load_json_object(path: Path, what: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, RecursionError, json.JSONDecodeError, ValueError:
        raise DispatchError(f"{what} is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise DispatchError(f"{what} must be a JSON object")
    return parsed


def _load_json_value(text: str) -> object:
    try:
        return json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        return None


def _load_request_object(text: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        raise DispatchError("Cursor request is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise DispatchError("Cursor request must be a JSON object")
    return parsed


def _require_positive_issue_number(issue_number: int) -> None:
    if issue_number <= 0:
        raise DispatchError("issue number must be positive")


def _require_owner_repo(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise DispatchError("GitHub repository must be owner/repo")
    return repository


def _repository_from_cli(repo_arg: str | None) -> str:
    if repo_arg:
        return repo_arg
    value = os.environ.get("GH_REPO", "")
    if not value:
        raise DispatchError("GH_REPO is not set")
    return value


def _api_key_from_env() -> str:
    return os.environ.get("CURSOR_API_KEY", "")


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _run_gh_api(path: str) -> GitHubApiResponse:
    try:
        completed = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        raise DispatchError("GitHub CLI is not available for REST issue read") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _rest_read_failure_message(issue_number: int, status_code: int | None, attempts: int) -> str:
    if status_code is None:
        attempt_word = "attempt" if attempts == 1 else "attempts"
        return f"GitHub REST issue #{issue_number} read failed after {attempts} {attempt_word}"
    if is_retryable_github_http_status(status_code):
        return f"GitHub REST issue #{issue_number} read failed with HTTP {status_code} after {attempts} attempts"
    return f"GitHub REST issue #{issue_number} read failed with HTTP {status_code}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch one Cursor Cloud Agent for an Agent Task Issue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_event = subparsers.add_parser("parse-event", help="Print the labeled Issue number.")
    parse_event.add_argument("--event-file", type=Path, required=True)

    plan = subparsers.add_parser("plan", help="Validate preconditions and print the Cursor request JSON.")
    plan.add_argument("--event-file", type=Path, required=True)
    plan.add_argument("--issue-json", required=True)

    submit = subparsers.add_parser("submit", help="POST a planned Cursor create request.")
    submit.add_argument("--issue", dest="issue_number", type=int, required=True)
    submit.add_argument("--request-json", required=True)

    dispatch = subparsers.add_parser("dispatch", help="Validate the labeled Issue and create one Cursor agent.")
    dispatch.add_argument("--event-file", type=Path, required=True)
    dispatch.add_argument("--repo", default=None)

    return parser


def _run_parse_event(event_file: Path, stdout: TextIO) -> int:
    event = load_labeled_issue_event(event_file)
    if event.added_label != AGENT_READY:
        raise DispatchError("dispatch runs only when the added label is agent:ready")
    print(event.issue.number, file=stdout)
    return 0


def _run_plan(event_file: Path, issue_json: str, stdout: TextIO) -> int:
    event = load_labeled_issue_event(event_file)
    parsed = _load_json_value(issue_json)
    if not isinstance(parsed, dict):
        raise DispatchError("issue JSON must be a JSON object")
    issue = dispatch_issue_from_mapping(parsed, "issue JSON")
    if issue.number != event.issue.number:
        raise DispatchError("issue JSON number does not match the GitHub event")
    plan = plan_dispatch(event.added_label, issue)
    print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def _run_submit(issue_number: int, request_json: str, stdout: TextIO) -> int:
    request = _load_request_object(request_json)
    result = submit_create_agent(issue_number, request, _api_key_from_env())
    print(json.dumps(result.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def _run_dispatch(event_file: Path, repo_arg: str | None, stdout: TextIO) -> int:
    event = load_labeled_issue_event(event_file)
    issue = read_dispatch_issue(_repository_from_cli(repo_arg), event.issue.number)
    if issue.number != event.issue.number:
        raise DispatchError("GitHub REST issue number does not match the GitHub event")
    plan = plan_dispatch(event.added_label, issue)
    result = submit_create_agent(plan.issue_number, plan.request, _api_key_from_env())
    print(json.dumps(result.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    output = sys.stdout if stdout is None else stdout
    try:
        match args.command:
            case "parse-event":
                return _run_parse_event(args.event_file, output)
            case "plan":
                return _run_plan(args.event_file, args.issue_json, output)
            case "submit":
                return _run_submit(args.issue_number, args.request_json, output)
            case "dispatch":
                return _run_dispatch(args.event_file, args.repo, output)
            case _:
                raise DispatchError("unknown command")
    except DispatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
