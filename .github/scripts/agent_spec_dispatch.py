"""Deterministic manual Spec Agent dispatch for Agent Task Issues.

This module is repository automation, not part of the CAPT runtime package.
It validates `workflow_dispatch` Issue preconditions and builds an idempotent
Cursor Cloud Agents API v1 create request for specification authoring. It
never mutates lifecycle or risk labels, never rewrites the Issue body, and
never creates the approved-spec comment.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TextIO

from agent_dispatch import (
    OWNER_REPO,
    REPOSITORY_URL,
    STARTING_REF,
    DispatchError,
    DispatchIssue,
    dispatch_issue_from_mapping,
    read_dispatch_issue,
)
from agent_lifecycle import LIFECYCLE_LABELS, RISK_LABELS, GitHubApiResponse
from cursor_agents import (
    CURSOR_AGENTS_URL,
    CursorApiError,
    HttpResponse,
    authorization_header,
    interpret_create_agent_response,
    post_json,
)

type SpecDispatchOutcome = Literal["created"]

NEEDS_DESIGN = "needs:design"
SPEC_AGENT_IDENTITY = "spec-agent"
REQUIRED_GITHUB_REF = "refs/heads/main"
DISPATCH_REF_ENV = "CAPT_SPEC_DISPATCH_REF"
_AGENT_ID_NAMESPACE = uuid.NAMESPACE_URL
_ISSUE_NUMBER = re.compile(r"^[1-9][0-9]*$")


class SpecDispatchError(Exception):
    """Invalid Spec Agent dispatch input or Cursor API failure. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class SpecDispatchPlan:
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
class SpecDispatchResult:
    outcome: SpecDispatchOutcome
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


def parse_issue_number(value: str) -> int:
    if not _ISSUE_NUMBER.fullmatch(value):
        raise SpecDispatchError("issue number must be a positive integer")
    return int(value)


def spec_issue_from_mapping(payload: Mapping[str, object], what: str) -> DispatchIssue:
    try:
        return dispatch_issue_from_mapping(payload, what)
    except DispatchError as exc:
        raise SpecDispatchError(str(exc)) from None


def plan_spec_dispatch(issue: DispatchIssue) -> SpecDispatchPlan:
    """Validate Issue preconditions and build the Cursor create request."""
    validate_spec_dispatch_preconditions(issue)
    request = build_create_agent_request(issue.number)
    return SpecDispatchPlan(
        issue_number=issue.number,
        request=request,
        message=f"Issue #{issue.number} is eligible for Spec Agent dispatch",
    )


def validate_spec_dispatch_preconditions(issue: DispatchIssue) -> None:
    if issue.is_pull_request:
        raise SpecDispatchError(f"#{issue.number} is a pull request; Spec Agent dispatch requires a GitHub Issue")
    if issue.state != "open":
        raise SpecDispatchError(f"Issue #{issue.number} is {issue.state}; Spec Agent dispatch requires an open Issue")
    lifecycle = _require_single_lifecycle(issue.number, issue.labels)
    if lifecycle != NEEDS_DESIGN:
        raise SpecDispatchError(
            f"Issue #{issue.number} lifecycle is {lifecycle}; Spec Agent dispatch requires {NEEDS_DESIGN}"
        )
    _require_single_risk(issue.number, issue.labels)


def build_prompt(issue_number: int) -> str:
    _require_positive_issue_number(issue_number)
    return (
        f"Author a specification for GitHub Issue #{issue_number} in {OWNER_REPO}.\n"
        "\n"
        "Before writing artifacts:\n"
        "- read AGENTS.md;\n"
        "- read docs/spec-kit.md;\n"
        "- read the relevant ADRs and repository documentation;\n"
        f"- read GitHub Issue #{issue_number} as the original feature brief.\n"
        "\n"
        "The Issue body is the immutable original feature brief. Do not rewrite the Issue body.\n"
        "\n"
        "Perform specification work only. Do not implement product or runtime code.\n"
        "Do not change CAPT runtime code, public CLI behavior, capture or summary schemas, "
        "provider adapters, persistence, network behavior, runtime dependencies, or GitHub "
        "Actions operational workflows.\n"
        "\n"
        "Expected workflow:\n"
        "1. speckit-specify\n"
        "2. speckit-clarify only when materially necessary\n"
        "3. speckit-plan\n"
        "4. speckit-tasks\n"
        "5. speckit-analyze\n"
        "6. persist analyze.md\n"
        "\n"
        "Open one specification-only review PR targeting `main`.\n"
        "Copy `.github/spec-review-pull-request.md` as the pull-request body.\n"
        "That body must include:\n"
        "- a standalone `<!-- capt-lifecycle: ignore -->` line;\n"
        f"- valid versioned `capt-spec:v1` metadata for Issue #{issue_number} "
        "and the canonical spec.md path;\n"
        f"- a standalone `Related to #{issue_number}` line;\n"
        f"- no standalone `Closes #{issue_number}` line.\n"
        "\n"
        "Do not apply or mutate `agent:ready` or any other lifecycle or risk labels.\n"
        "Do not run `/speckit.implement`.\n"
        "Do not run `/speckit.taskstoissues`.\n"
        "Do not create a second Agent Task Issue.\n"
        "Do not create the approved-spec Issue comment.\n"
        "Stop after opening the specification review PR for human review.\n"
        "Do not merge the PR.\n"
    )


def build_agent_id(issue_number: int) -> str:
    """Return a deterministic `bc-<uuid>` derived from repository + Issue + Spec Agent role."""
    _require_positive_issue_number(issue_number)
    identity = f"{REPOSITORY_URL}/issues/{issue_number}/{SPEC_AGENT_IDENTITY}"
    return f"bc-{uuid.uuid5(_AGENT_ID_NAMESPACE, identity)}"


def build_create_agent_request(issue_number: int) -> dict[str, object]:
    _require_positive_issue_number(issue_number)
    return {
        "agentId": build_agent_id(issue_number),
        "prompt": {"text": build_prompt(issue_number)},
        "name": f"Spec Agent Issue #{issue_number}",
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
) -> SpecDispatchResult:
    _require_positive_issue_number(issue_number)
    if not api_key:
        raise SpecDispatchError("CURSOR_API_KEY is not set")
    agent_id = request.get("agentId")
    if not isinstance(agent_id, str) or not agent_id:
        raise SpecDispatchError("Cursor request is missing agentId")
    expected_id = build_agent_id(issue_number)
    if agent_id != expected_id:
        raise SpecDispatchError("Cursor request agentId does not match the Spec Agent Issue identity")
    payload = json.dumps(dict(request), allow_nan=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": authorization_header(api_key),
        "Content-Type": "application/json",
    }
    poster = post_json if post is None else post
    try:
        response = poster(CURSOR_AGENTS_URL, headers, payload)
        return interpret_cursor_create_response(issue_number, agent_id, response)
    except CursorApiError as exc:
        raise SpecDispatchError(str(exc)) from None


def interpret_cursor_create_response(issue_number: int, agent_id: str, response: HttpResponse) -> SpecDispatchResult:
    _require_positive_issue_number(issue_number)
    try:
        created = interpret_create_agent_response(f"Issue #{issue_number}", agent_id, response)
    except CursorApiError as exc:
        raise SpecDispatchError(str(exc)) from None
    if created.outcome != "created":
        raise SpecDispatchError(created.message)
    return SpecDispatchResult(
        outcome="created",
        issue_number=issue_number,
        agent_id=created.agent_id,
        agent_url=created.agent_url,
        run_id=created.run_id,
        message=created.message,
    )


def require_trusted_dispatch_ref(ref: str | None = None) -> None:
    """Refuse Actions runs that were not started from main."""
    value = os.environ.get(DISPATCH_REF_ENV, "") if ref is None else ref
    if not value:
        return
    if value != REQUIRED_GITHUB_REF:
        raise SpecDispatchError("Spec Agent dispatch must run from main")


def require_supported_repository(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise SpecDispatchError("GitHub repository must be owner/repo")
    if repository != OWNER_REPO:
        raise SpecDispatchError(f"Spec Agent dispatch operates only on {OWNER_REPO}")
    return repository


def _require_single_risk(issue_number: int, labels: Sequence[str]) -> str:
    risks = tuple(label for label in RISK_LABELS if label in labels)
    if not risks:
        raise SpecDispatchError(f"Issue #{issue_number} has no risk:* label")
    if len(risks) > 1:
        rendered = ", ".join(risks)
        raise SpecDispatchError(f"Issue #{issue_number} has multiple risk:* labels: {rendered}")
    return risks[0]


def _require_single_lifecycle(issue_number: int, labels: Sequence[str]) -> str:
    present = tuple(label for label in LIFECYCLE_LABELS if label in labels)
    if not present:
        raise SpecDispatchError(f"Issue #{issue_number} has no lifecycle label")
    if len(present) > 1:
        rendered = ", ".join(present)
        raise SpecDispatchError(f"Issue #{issue_number} has multiple lifecycle labels: {rendered}")
    return present[0]


def _load_json_value(text: str) -> object:
    try:
        return json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        return None


def _load_request_object(text: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        raise SpecDispatchError("Cursor request is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise SpecDispatchError("Cursor request must be a JSON object")
    return parsed


def _require_positive_issue_number(issue_number: int) -> None:
    if isinstance(issue_number, bool) or issue_number <= 0:
        raise SpecDispatchError("issue number must be a positive integer")


def _repository_from_cli(repo_arg: str | None) -> str:
    if repo_arg:
        return repo_arg
    value = os.environ.get("GH_REPO", "")
    if not value:
        raise SpecDispatchError("GH_REPO is not set")
    return value


def _api_key_from_env() -> str:
    return os.environ.get("CURSOR_API_KEY", "")


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
        raise SpecDispatchError("GitHub CLI is not available for REST issue read") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _read_issue(repository: str, issue_number: int) -> DispatchIssue:
    try:
        return read_dispatch_issue(repository, issue_number, run_api=_run_gh_api)
    except DispatchError as exc:
        raise SpecDispatchError(str(exc)) from None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch one Spec Agent for an Agent Task Issue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_issue = subparsers.add_parser("parse-issue", help="Validate and print the Issue number.")
    parse_issue.add_argument("--issue", dest="issue_number", required=True)

    plan = subparsers.add_parser("plan", help="Validate preconditions and print the Cursor request JSON.")
    plan.add_argument("--issue-json", required=True)

    submit = subparsers.add_parser("submit", help="POST a planned Cursor create request.")
    submit.add_argument("--issue", dest="issue_number", required=True)
    submit.add_argument("--request-json", required=True)

    dispatch = subparsers.add_parser("dispatch", help="Validate the Issue and create one Spec Agent.")
    dispatch.add_argument("--issue", dest="issue_number", required=True)
    dispatch.add_argument("--repo", default=None)

    return parser


def _run_parse_issue(issue_token: str, stdout: TextIO) -> int:
    print(parse_issue_number(issue_token), file=stdout)
    return 0


def _run_plan(issue_json: str, stdout: TextIO) -> int:
    parsed = _load_json_value(issue_json)
    if not isinstance(parsed, dict):
        raise SpecDispatchError("issue JSON must be a JSON object")
    issue = spec_issue_from_mapping(parsed, "issue JSON")
    plan = plan_spec_dispatch(issue)
    print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def _run_submit(issue_token: str, request_json: str, stdout: TextIO) -> int:
    issue_number = parse_issue_number(issue_token)
    request = _load_request_object(request_json)
    result = submit_create_agent(issue_number, request, _api_key_from_env())
    print(json.dumps(result.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def _run_dispatch(issue_token: str, repo_arg: str | None, stdout: TextIO) -> int:
    require_trusted_dispatch_ref()
    issue_number = parse_issue_number(issue_token)
    repository = require_supported_repository(_repository_from_cli(repo_arg))
    issue = _read_issue(repository, issue_number)
    if issue.number != issue_number:
        raise SpecDispatchError("GitHub REST issue number does not match the requested Issue")
    plan = plan_spec_dispatch(issue)
    result = submit_create_agent(plan.issue_number, plan.request, _api_key_from_env())
    print(json.dumps(result.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    output = sys.stdout if stdout is None else stdout
    try:
        match args.command:
            case "parse-issue":
                return _run_parse_issue(args.issue_number, output)
            case "plan":
                return _run_plan(args.issue_json, output)
            case "submit":
                return _run_submit(args.issue_number, args.request_json, output)
            case "dispatch":
                return _run_dispatch(args.issue_number, args.repo, output)
            case _:
                raise SpecDispatchError("unknown command")
    except SpecDispatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
