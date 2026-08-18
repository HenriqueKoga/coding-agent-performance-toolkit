"""Deterministic Agent Task lifecycle planning for GitHub pull requests.

This module is repository automation, not part of the CAPT runtime package.
It honors an explicit PR-body opt-out, otherwise parses the pull-request
template `Closes #<issue>` contract and plans label mutations. It never
applies `agent:ready`.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

type PullRequestAction = Literal["opened", "ready_for_review"]
type RiskLabel = Literal["risk:low", "risk:medium", "risk:high"]
type LifecycleLabel = Literal[
    "needs:design",
    "needs:human-review",
    "agent:ready",
    "agent:working",
    "agent:blocked",
]

AGENT_READY = "agent:ready"
AGENT_WORKING = "agent:working"
NEEDS_HUMAN_REVIEW = "needs:human-review"

RISK_LABELS: tuple[RiskLabel, ...] = ("risk:low", "risk:medium", "risk:high")
LIFECYCLE_LABELS: tuple[LifecycleLabel, ...] = (
    "needs:design",
    "needs:human-review",
    "agent:ready",
    "agent:working",
    "agent:blocked",
)

GITHUB_REST_READ_MAX_ATTEMPTS = 3
GITHUB_REST_READ_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_GITHUB_HTTP_STATUSES = frozenset({500, 502, 503, 504})

LIFECYCLE_OPT_OUT_MARKER = "<!-- capt-lifecycle: ignore -->"
LIFECYCLE_OPT_OUT_VALUE = "ignore"

_CLOSES_LINE = re.compile(r"^[ \t]*Closes #(\d+)[ \t]*$", re.MULTILINE)
_LIFECYCLE_NAMESPACE_LINE = re.compile(
    r"^[ \t]*<!--[ \t]*(capt-lifecycle(?:[ \t:].*?)?)[ \t]*-->[ \t]*$",
    re.MULTILINE,
)
_LIFECYCLE_DIRECTIVE = re.compile(r"^capt-lifecycle:[ \t]*(.*?)[ \t]*$")
_GITHUB_HTTP_STATUS = re.compile(r"\bHTTP (\d{3})\b")


class LifecycleError(Exception):
    """Invalid or inconsistent lifecycle input. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class PullRequestEvent:
    action: PullRequestAction
    body: str


@dataclass(frozen=True, slots=True)
class LifecyclePlan:
    issue_number: int
    issue_add: tuple[str, ...]
    issue_remove: tuple[str, ...]
    pr_add: tuple[str, ...]
    message: str

    @property
    def noop(self) -> bool:
        return not self.issue_add and not self.issue_remove and not self.pr_add

    def to_json_dict(self) -> dict[str, object]:
        return {
            "issue_number": self.issue_number,
            "issue_add": list(self.issue_add),
            "issue_remove": list(self.issue_remove),
            "pr_add": list(self.pr_add),
            "noop": self.noop,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class GitHubApiResponse:
    returncode: int
    stdout: str
    stderr: str


def has_lifecycle_opt_out(body: str) -> bool:
    """Return True when the pull-request body opts out of Agent Task lifecycle."""
    normalized = _normalize_pr_body(body)
    payloads = tuple(match.strip() for match in _LIFECYCLE_NAMESPACE_LINE.findall(normalized))
    if not payloads:
        return False
    if any(_lifecycle_directive_value(payload) != LIFECYCLE_OPT_OUT_VALUE for payload in payloads):
        raise LifecycleError("pull request body contains an invalid or ambiguous capt-lifecycle marker")
    if _CLOSES_LINE.search(normalized) is not None:
        raise LifecycleError("pull request body combines capt-lifecycle opt-out with a Closes #<issue> link")
    return True


def _lifecycle_directive_value(payload: str) -> str | None:
    match = _LIFECYCLE_DIRECTIVE.fullmatch(payload)
    if match is None:
        return None
    return match.group(1)


def parse_linked_issue_number(body: str) -> int:
    """Return the single `Closes #<issue>` target from a pull-request body."""
    if has_lifecycle_opt_out(body):
        raise LifecycleError("pull request body opts out of Agent Task lifecycle")
    matches = _CLOSES_LINE.findall(_normalize_pr_body(body))
    issue_numbers = [int(match) for match in matches if int(match) > 0]
    unique_issues = tuple(dict.fromkeys(issue_numbers))
    if not unique_issues:
        raise LifecycleError("pull request body does not contain a supported Closes #<issue> link")
    if len(unique_issues) > 1:
        rendered = ", ".join(f"#{number}" for number in unique_issues)
        raise LifecycleError(f"pull request body contains multiple Closes #<issue> links: {rendered}")
    return unique_issues[0]


def load_pull_request_event(path: Path) -> PullRequestEvent:
    payload = _load_json_object(path, "GitHub event file")
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        raise LifecycleError("GitHub event does not contain pull request metadata")
    body_value = pull_request.get("body")
    if body_value is None:
        body = ""
    elif isinstance(body_value, str):
        body = body_value
    else:
        raise LifecycleError("pull request body is not a string")
    match payload.get("action"):
        case "opened":
            return PullRequestEvent(action="opened", body=body)
        case "ready_for_review":
            return PullRequestEvent(action="ready_for_review", body=body)
        case _:
            raise LifecycleError("GitHub event action is not a supported pull_request lifecycle event")


def is_retryable_github_http_status(status_code: int | None) -> bool:
    """Return True only for transient GitHub HTTP 5xx statuses that may be retried."""
    return status_code in RETRYABLE_GITHUB_HTTP_STATUSES


def github_http_status_from_stderr(stderr: str) -> int | None:
    """Parse a `gh api` HTTP status from stderr without returning the payload."""
    match = _GITHUB_HTTP_STATUS.search(stderr)
    if match is None:
        return None
    return int(match.group(1))


def read_issue_label_names(
    repository: str,
    issue_number: int,
    *,
    run_api: Callable[[str], GitHubApiResponse] | None = None,
    sleep: Callable[[float], None] | None = None,
    notify: Callable[[str], None] | None = None,
) -> tuple[str, ...]:
    """Read Issue labels from GitHub REST, retrying only bounded transient 5xx failures."""
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
            return _label_names_from_issue_payload(response.stdout)
        last_status = github_http_status_from_stderr(response.stderr)
        if not is_retryable_github_http_status(last_status) or attempt == GITHUB_REST_READ_MAX_ATTEMPTS:
            break
        log(
            f"GitHub REST issue #{issue_number} read returned HTTP {last_status} "
            f"(attempt {attempt}/{GITHUB_REST_READ_MAX_ATTEMPTS}); retrying"
        )
        sleeper(GITHUB_REST_READ_RETRY_DELAY_SECONDS)
    raise LifecycleError(_rest_read_failure_message(issue_number, last_status, attempt))


def plan_lifecycle(
    action: PullRequestAction,
    issue_number: int,
    issue_labels: Sequence[str],
    pr_labels: Sequence[str],
) -> LifecyclePlan:
    """Plan Issue and PR label mutations, or raise without a partial plan."""
    risk = _require_single_risk(issue_number, issue_labels)
    lifecycle = _optional_lifecycle(issue_number, issue_labels)
    match action:
        case "opened":
            return _plan_opened(issue_number, lifecycle, risk, pr_labels)
        case "ready_for_review":
            return _plan_ready_for_review(issue_number, lifecycle, risk)


def _plan_opened(
    issue_number: int,
    lifecycle: LifecycleLabel | None,
    risk: RiskLabel,
    pr_labels: Sequence[str],
) -> LifecyclePlan:
    pr_add = _risk_label_to_add(issue_number, risk, pr_labels)
    if lifecycle == AGENT_READY:
        return LifecyclePlan(
            issue_number=issue_number,
            issue_add=(AGENT_WORKING,),
            issue_remove=(AGENT_READY,),
            pr_add=pr_add,
            message=(f"Issue #{issue_number} {AGENT_READY} -> {AGENT_WORKING}; copy {risk} to the pull request"),
        )
    if lifecycle == AGENT_WORKING:
        if not pr_add:
            return LifecyclePlan(
                issue_number=issue_number,
                issue_add=(),
                issue_remove=(),
                pr_add=(),
                message=f"Issue #{issue_number} already {AGENT_WORKING}; no label changes",
            )
        return LifecyclePlan(
            issue_number=issue_number,
            issue_add=(),
            issue_remove=(),
            pr_add=pr_add,
            message=f"Issue #{issue_number} already {AGENT_WORKING}; copy {risk} to the pull request",
        )
    return _no_transition(issue_number, lifecycle, AGENT_READY, "opened")


def _plan_ready_for_review(
    issue_number: int,
    lifecycle: LifecycleLabel | None,
    risk: RiskLabel,
) -> LifecyclePlan:
    if lifecycle == AGENT_WORKING:
        return LifecyclePlan(
            issue_number=issue_number,
            issue_add=(NEEDS_HUMAN_REVIEW,),
            issue_remove=(AGENT_WORKING,),
            pr_add=(),
            message=(f"Issue #{issue_number} {AGENT_WORKING} -> {NEEDS_HUMAN_REVIEW}; {risk} unchanged"),
        )
    if lifecycle == NEEDS_HUMAN_REVIEW:
        return LifecyclePlan(
            issue_number=issue_number,
            issue_add=(),
            issue_remove=(),
            pr_add=(),
            message=f"Issue #{issue_number} already {NEEDS_HUMAN_REVIEW}; {risk} unchanged",
        )
    return _no_transition(issue_number, lifecycle, AGENT_WORKING, "ready_for_review")


def _no_transition(
    issue_number: int,
    lifecycle: LifecycleLabel | None,
    expected: LifecycleLabel,
    event_name: str,
) -> LifecyclePlan:
    actual = "absent" if lifecycle is None else lifecycle
    return LifecyclePlan(
        issue_number=issue_number,
        issue_add=(),
        issue_remove=(),
        pr_add=(),
        message=(
            f"Issue #{issue_number} lifecycle is {actual}; expected {expected} for pull_request {event_name}; "
            "no label changes"
        ),
    )


def _require_single_risk(issue_number: int, labels: Sequence[str]) -> RiskLabel:
    risks = tuple(label for label in RISK_LABELS if label in labels)
    if not risks:
        raise LifecycleError(f"Issue #{issue_number} has no risk:* label")
    if len(risks) > 1:
        rendered = ", ".join(risks)
        raise LifecycleError(f"Issue #{issue_number} has multiple risk:* labels: {rendered}")
    return risks[0]


def _optional_lifecycle(issue_number: int, labels: Sequence[str]) -> LifecycleLabel | None:
    present = tuple(label for label in LIFECYCLE_LABELS if label in labels)
    if not present:
        return None
    if len(present) > 1:
        rendered = ", ".join(present)
        raise LifecycleError(f"Issue #{issue_number} has multiple lifecycle labels: {rendered}")
    return present[0]


def _risk_label_to_add(issue_number: int, risk: RiskLabel, pr_labels: Sequence[str]) -> tuple[str, ...]:
    present = tuple(label for label in RISK_LABELS if label in pr_labels)
    if not present:
        return (risk,)
    if present == (risk,):
        return ()
    if len(present) == 1:
        raise LifecycleError(
            f"pull request already has {present[0]}; refusing to replace it with Issue #{issue_number} {risk}"
        )
    rendered = ", ".join(present)
    raise LifecycleError(f"pull request has multiple risk:* labels: {rendered}")


def _normalize_pr_body(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n")


def _load_json_object(path: Path, what: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, RecursionError, json.JSONDecodeError, ValueError:
        raise LifecycleError(f"{what} is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise LifecycleError(f"{what} must be a JSON object")
    return parsed


def _load_label_list(text: str, what: str) -> tuple[str, ...]:
    try:
        parsed: object = json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        raise LifecycleError(f"{what} is not valid JSON") from None
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise LifecycleError(f"{what} must be a JSON array of strings")
    return tuple(parsed)


def _require_positive_issue_number(issue_number: int) -> None:
    if issue_number <= 0:
        raise LifecycleError("issue number must be positive")


def _require_owner_repo(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise LifecycleError("GitHub repository must be owner/repo")
    return repository


def _repository_from_cli(repo_arg: str | None) -> str:
    if repo_arg:
        return repo_arg
    value = os.environ.get("GH_REPO", "")
    if not value:
        raise LifecycleError("GH_REPO is not set")
    return value


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
        raise LifecycleError("GitHub CLI is not available for REST issue read") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _label_names_from_issue_payload(text: str) -> tuple[str, ...]:
    try:
        parsed: object = json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        raise LifecycleError("GitHub REST issue response is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise LifecycleError("GitHub REST issue response must be a JSON object")
    labels = parsed.get("labels")
    if not isinstance(labels, list):
        raise LifecycleError("GitHub REST issue response is missing labels")
    names: list[str] = []
    for item in labels:
        if not isinstance(item, dict):
            raise LifecycleError("GitHub REST issue labels are invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise LifecycleError("GitHub REST issue labels are invalid")
        names.append(name)
    return tuple(names)


def _rest_read_failure_message(issue_number: int, status_code: int | None, attempts: int) -> str:
    if status_code is None:
        attempt_word = "attempt" if attempts == 1 else "attempts"
        return f"GitHub REST issue #{issue_number} read failed after {attempts} {attempt_word}"
    if is_retryable_github_http_status(status_code):
        return f"GitHub REST issue #{issue_number} read failed with HTTP {status_code} after {attempts} attempts"
    return f"GitHub REST issue #{issue_number} read failed with HTTP {status_code}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan Agent Task lifecycle label mutations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_link = subparsers.add_parser("parse-link", help="Print the single Closes #<issue> target.")
    parse_link.add_argument("--event-file", type=Path, required=True)

    opt_out = subparsers.add_parser(
        "opt-out",
        help="Print whether the pull request opts out of Agent Task lifecycle.",
    )
    opt_out.add_argument("--event-file", type=Path, required=True)

    read_labels = subparsers.add_parser("read-issue-labels", help="Read Issue labels from GitHub REST.")
    read_labels.add_argument("--issue", dest="issue_number", type=int, required=True)
    read_labels.add_argument("--repo", default=None)

    plan = subparsers.add_parser("plan", help="Print a JSON lifecycle plan.")
    plan.add_argument("--event-file", type=Path, required=True)
    plan.add_argument("--issue-labels-json", required=True)
    plan.add_argument("--pr-labels-json", required=True)

    return parser


def _run_parse_link(event_file: Path, stdout: TextIO) -> int:
    event = load_pull_request_event(event_file)
    issue_number = parse_linked_issue_number(event.body)
    print(issue_number, file=stdout)
    return 0


def _run_opt_out(event_file: Path, stdout: TextIO) -> int:
    event = load_pull_request_event(event_file)
    opted_out = has_lifecycle_opt_out(event.body)
    payload: dict[str, object] = {"opt_out": opted_out}
    if opted_out:
        payload["message"] = "pull request opted out of Agent Task lifecycle; no label changes"
    print(json.dumps(payload, allow_nan=False), file=stdout)
    return 0


def _run_read_issue_labels(issue_number: int, repo_arg: str | None, stdout: TextIO) -> int:
    labels = read_issue_label_names(_repository_from_cli(repo_arg), issue_number)
    print(json.dumps(list(labels), allow_nan=False), file=stdout)
    return 0


def _run_plan(
    event_file: Path,
    issue_labels_json: str,
    pr_labels_json: str,
    stdout: TextIO,
) -> int:
    event = load_pull_request_event(event_file)
    issue_number = parse_linked_issue_number(event.body)
    plan = plan_lifecycle(
        action=event.action,
        issue_number=issue_number,
        issue_labels=_load_label_list(issue_labels_json, "issue labels"),
        pr_labels=_load_label_list(pr_labels_json, "pull request labels"),
    )
    if AGENT_READY in plan.issue_add:
        raise LifecycleError("refusing to add agent:ready automatically")
    print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    output = sys.stdout if stdout is None else stdout
    try:
        match args.command:
            case "parse-link":
                return _run_parse_link(args.event_file, output)
            case "opt-out":
                return _run_opt_out(args.event_file, output)
            case "read-issue-labels":
                return _run_read_issue_labels(args.issue_number, args.repo, output)
            case "plan":
                return _run_plan(
                    args.event_file,
                    args.issue_labels_json,
                    args.pr_labels_json,
                    output,
                )
            case _:
                raise LifecycleError("unknown command")
    except LifecycleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
