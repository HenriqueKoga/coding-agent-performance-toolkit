"""Deterministic approved-specification handoff for Agent Task Issues.

This module is repository automation, not part of the CAPT runtime package.
It records an approved Spec Kit path on an existing Issue after a valid
specification PR merges. It never rewrites Issue bodies and never applies
`agent:ready`.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

from agent_lifecycle import (
    AGENT_READY,
    GITHUB_REST_READ_MAX_ATTEMPTS,
    GITHUB_REST_READ_RETRY_DELAY_SECONDS,
    LIFECYCLE_LABELS,
    NEEDS_HUMAN_REVIEW,
    GitHubApiResponse,
    LifecycleError,
    github_http_status_from_stderr,
    has_lifecycle_opt_out,
    is_retryable_github_http_status,
)

type SpecHandoffOutcome = Literal["skipped", "created", "updated", "unchanged"]
type CommentAction = Literal["create", "update", "unchanged"]

NEEDS_DESIGN = "needs:design"
SPEC_HANDOFF_LIFECYCLES: tuple[str, ...] = (NEEDS_DESIGN, NEEDS_HUMAN_REVIEW)
REQUIRED_BASE_REF = "main"
SPEC_METADATA_VERSION = "v1"
APPROVED_MARKER_VERSION = "v1"
GITHUB_ACTIONS_BOT_LOGIN = "github-actions[bot]"
GITHUB_ACTIONS_BOT_TYPE = "Bot"
CANONICAL_ARTIFACTS = ("spec.md", "plan.md", "tasks.md", "analyze.md")
MAX_COMMENT_PAGES = 10
COMMENTS_PER_PAGE = 100

_SPEC_PATH = re.compile(r"^specs/[a-z0-9]+(?:-[a-z0-9]+)*/spec.md$")
_RELATED_LINE = re.compile(r"^[ \t]*Related to #(\d+)[ \t]*$", re.MULTILINE)
_SPEC_BLOCK = re.compile(
    r"^[ \t]*<!--[ \t]*capt-spec:([^\n]*?)[ \t]*\n(.*?)^[ \t]*-->[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_APPROVED_BLOCK = re.compile(
    r"^[ \t]*<!--[ \t]*capt-spec-approved:([^\n]*?)[ \t]*\n(.*?)^[ \t]*-->[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_FIELD_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)$")
_ISSUE_FIELD = re.compile(r"^[1-9][0-9]*$")
_PR_FIELD = re.compile(r"^[1-9][0-9]*$")


class SpecApprovalError(Exception):
    """Invalid specification metadata or handoff input. The message is safe to print."""


@dataclass(frozen=True, slots=True)
class SpecMetadata:
    issue_number: int
    spec_path: str

    @property
    def feature_dir(self) -> str:
        return str(Path(self.spec_path).parent)

    def artifact_path(self, name: str) -> str:
        return f"{self.feature_dir}/{name}"


@dataclass(frozen=True, slots=True)
class ApprovedSpec:
    issue_number: int
    pull_request_number: int
    spec_path: str

    @property
    def feature_dir(self) -> str:
        return str(Path(self.spec_path).parent)

    def artifact_path(self, name: str) -> str:
        return f"{self.feature_dir}/{name}"


@dataclass(frozen=True, slots=True)
class MergedPullRequestEvent:
    action: str
    number: int
    merged: bool
    body: str
    base_ref: str


@dataclass(frozen=True, slots=True)
class IssueComment:
    comment_id: int
    body: str
    user_login: str
    user_type: str


@dataclass(frozen=True, slots=True)
class SpecTargetIssue:
    number: int
    state: str
    labels: tuple[str, ...]
    is_pull_request: bool


@dataclass(frozen=True, slots=True)
class SpecHandoffPlan:
    outcome: SpecHandoffOutcome
    issue_number: int | None
    pull_request_number: int | None
    spec_path: str | None
    comment_body: str | None
    comment_action: CommentAction | None
    existing_comment_id: int | None
    issue_add: tuple[str, ...]
    issue_remove: tuple[str, ...]
    mutate_issue_body: Literal[False]
    message: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "issue_number": self.issue_number,
            "pull_request_number": self.pull_request_number,
            "spec_path": self.spec_path,
            "comment_body": self.comment_body,
            "comment_action": self.comment_action,
            "existing_comment_id": self.existing_comment_id,
            "issue_add": list(self.issue_add),
            "issue_remove": list(self.issue_remove),
            "mutate_issue_body": self.mutate_issue_body,
            "message": self.message,
        }


def parse_spec_metadata(body: str) -> SpecMetadata | None:
    """Return v1 specification metadata, or None when the PR has no capt-spec block."""
    normalized = _normalize_body(body)
    blocks = tuple(_SPEC_BLOCK.finditer(normalized))
    if not blocks:
        return None
    if len(blocks) > 1:
        raise SpecApprovalError("pull request body contains duplicate capt-spec metadata blocks")
    match = blocks[0]
    version = match.group(1).strip()
    if version != SPEC_METADATA_VERSION:
        raise SpecApprovalError("pull request body contains unsupported or malformed capt-spec metadata")
    fields = _parse_metadata_fields(match.group(2), "capt-spec metadata")
    unexpected = tuple(key for key in fields if key not in {"issue", "spec"})
    if unexpected:
        raise SpecApprovalError("pull request body contains unsupported capt-spec metadata fields")
    if "issue" not in fields or "spec" not in fields:
        raise SpecApprovalError("pull request body is missing required capt-spec metadata fields")
    return SpecMetadata(issue_number=_parse_issue_field(fields["issue"]), spec_path=_parse_spec_path(fields["spec"]))


def related_issue_numbers(body: str) -> tuple[int, ...]:
    """Return unique standalone `Related to #<issue>` targets in order of appearance."""
    numbers = [int(match) for match in _RELATED_LINE.findall(_normalize_body(body)) if int(match) > 0]
    return tuple(dict.fromkeys(numbers))


def require_related_issue_agreement(body: str, metadata: SpecMetadata) -> None:
    related = related_issue_numbers(body)
    if not related:
        return
    if len(related) > 1:
        raise SpecApprovalError("pull request body contains multiple Related to #<issue> links")
    if related[0] != metadata.issue_number:
        raise SpecApprovalError("capt-spec issue does not match Related to #<issue>")


def validate_canonical_artifacts(repo_root: Path, metadata: SpecMetadata) -> None:
    """Confirm required Spec Kit artifacts exist under the declared feature directory."""
    root = _require_repo_root(repo_root)
    spec_path = root / metadata.spec_path
    if spec_path.is_symlink() or not spec_path.is_file():
        raise SpecApprovalError("approved specification is missing required canonical artifacts")
    try:
        spec_path.resolve().relative_to(root.resolve())
    except ValueError:
        raise SpecApprovalError("approved specification is missing required canonical artifacts") from None
    for name in CANONICAL_ARTIFACTS:
        artifact = root / metadata.artifact_path(name)
        if artifact.is_symlink() or not artifact.is_file():
            raise SpecApprovalError("approved specification is missing required canonical artifacts")


def build_approved_comment(metadata: SpecMetadata, pull_request_number: int) -> str:
    _require_positive_issue_number(metadata.issue_number)
    _require_positive_issue_number(pull_request_number)
    spec = metadata.spec_path
    plan = metadata.artifact_path("plan.md")
    tasks = metadata.artifact_path("tasks.md")
    analyze = metadata.artifact_path("analyze.md")
    return (
        f"<!-- capt-spec-approved:{APPROVED_MARKER_VERSION}\n"
        f"issue: {metadata.issue_number}\n"
        f"pr: {pull_request_number}\n"
        f"spec: {spec}\n"
        "-->\n"
        "\n"
        "Approved specification index for this Agent Task.\n"
        "\n"
        f"- Specification PR: #{pull_request_number}\n"
        f"- Canonical spec: `{spec}`\n"
        f"- Plan: `{plan}`\n"
        f"- Tasks: `{tasks}`\n"
        f"- Analysis: `{analyze}`\n"
        "\n"
        "The Issue body remains the original feature brief. Spec Kit artifacts are the approved "
        "requirements, design, and tasks. When they conflict, the merged `spec.md` is authoritative. "
        "Labels remain the operational lifecycle state.\n"
    )


def parse_approved_spec(body: str) -> ApprovedSpec | None:
    """Return the managed approved-spec payload, or None when the marker is absent."""
    normalized = _normalize_body(body)
    blocks = tuple(_APPROVED_BLOCK.finditer(normalized))
    if not blocks:
        return None
    if len(blocks) > 1:
        raise SpecApprovalError("approved-spec comment contains duplicate capt-spec-approved metadata blocks")
    match = blocks[0]
    version = match.group(1).strip()
    if version != APPROVED_MARKER_VERSION:
        raise SpecApprovalError("approved-spec comment contains unsupported or malformed capt-spec-approved metadata")
    fields = _parse_metadata_fields(match.group(2), "capt-spec-approved metadata")
    unexpected = tuple(key for key in fields if key not in {"issue", "pr", "spec"})
    if unexpected:
        raise SpecApprovalError("approved-spec comment contains unsupported capt-spec-approved metadata fields")
    if "issue" not in fields or "pr" not in fields or "spec" not in fields:
        raise SpecApprovalError("approved-spec comment is missing required capt-spec-approved metadata fields")
    return ApprovedSpec(
        issue_number=_parse_issue_field(fields["issue"]),
        pull_request_number=_parse_pr_field(fields["pr"]),
        spec_path=_parse_spec_path(fields["spec"]),
    )


def resolve_approved_spec(issue_number: int, comments: Sequence[IssueComment]) -> ApprovedSpec | None:
    """Return the single managed approved spec for an Issue, or None when none exists."""
    _require_positive_issue_number(issue_number)
    managed = _trusted_approved_comments(comments)
    if not managed:
        return None
    if len(managed) > 1:
        raise SpecApprovalError(f"Issue #{issue_number} has multiple capt-spec-approved comments")
    approved = managed[0][1]
    if approved.issue_number != issue_number:
        raise SpecApprovalError("approved-spec comment issue does not match the Agent Task Issue")
    return approved


def load_merged_pull_request_event(path: Path) -> MergedPullRequestEvent:
    payload = _load_json_object(path, "GitHub event file")
    if payload.get("action") != "closed":
        raise SpecApprovalError("GitHub event action is not a supported pull_request closed event")
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        raise SpecApprovalError("GitHub event does not contain pull request metadata")
    number = pull_request.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise SpecApprovalError("pull request number must be a positive integer")
    merged = pull_request.get("merged")
    if not isinstance(merged, bool):
        raise SpecApprovalError("pull request merged flag is not a boolean")
    body_value = pull_request.get("body")
    if body_value is None:
        body = ""
    elif isinstance(body_value, str):
        body = body_value
    else:
        raise SpecApprovalError("pull request body is not a string")
    base = pull_request.get("base")
    if not isinstance(base, dict):
        raise SpecApprovalError("pull request base is missing")
    base_ref = base.get("ref")
    if not isinstance(base_ref, str) or not base_ref:
        raise SpecApprovalError("pull request base ref is not a string")
    return MergedPullRequestEvent(action="closed", number=number, merged=merged, body=body, base_ref=base_ref)


def classify_spec_event(event: MergedPullRequestEvent) -> SpecMetadata | None:
    """Return metadata when a merged spec PR should record an approved spec.

    Unmerged PRs, implementation PRs, and opted-out PRs without capt-spec
    metadata follow the compatibility skip path. Invalid metadata fails closed.
    """
    if not event.merged:
        return None
    try:
        opted_out = has_lifecycle_opt_out(event.body)
    except LifecycleError as exc:
        raise SpecApprovalError(str(exc)) from None
    if not opted_out:
        return None
    metadata = parse_spec_metadata(event.body)
    if metadata is None:
        return None
    require_related_issue_agreement(event.body, metadata)
    if event.base_ref != REQUIRED_BASE_REF:
        raise SpecApprovalError("specification pull request base is not main")
    return metadata


def skip_message(event: MergedPullRequestEvent) -> str:
    if not event.merged:
        return f"pull request #{event.number} was not merged; no approved-spec handoff"
    try:
        opted_out = has_lifecycle_opt_out(event.body)
    except LifecycleError as exc:
        raise SpecApprovalError(str(exc)) from None
    if not opted_out:
        return f"pull request #{event.number} is not a specification lifecycle opt-out; no approved-spec handoff"
    return (
        f"pull request #{event.number} has no capt-spec metadata; "
        "no specs/ directory was selected and Issue body was not rewritten"
    )


def require_spec_handoff_target(target: SpecTargetIssue) -> None:
    """Fail closed unless the target is an open Issue in specification-stage lifecycle."""
    _require_positive_issue_number(target.number)
    if target.is_pull_request:
        raise SpecApprovalError(f"#{target.number} is a pull request; approved-spec handoff requires a GitHub Issue")
    if target.state != "open":
        raise SpecApprovalError(
            f"Issue #{target.number} is {target.state}; approved-spec handoff requires an open Issue"
        )
    present = tuple(label for label in LIFECYCLE_LABELS if label in target.labels)
    if not present:
        raise SpecApprovalError(f"Issue #{target.number} has no lifecycle label")
    if len(present) > 1:
        rendered = ", ".join(present)
        raise SpecApprovalError(f"Issue #{target.number} has multiple lifecycle labels: {rendered}")
    if present[0] not in SPEC_HANDOFF_LIFECYCLES:
        raise SpecApprovalError(
            f"Issue #{target.number} lifecycle is {present[0]}; "
            "approved-spec handoff requires needs:design or needs:human-review"
        )


def plan_spec_handoff(
    event: MergedPullRequestEvent,
    metadata: SpecMetadata,
    issue_labels: Sequence[str],
    comments: Sequence[IssueComment],
    *,
    repo_root: Path,
    issue_state: str = "open",
    is_pull_request: bool = False,
) -> SpecHandoffPlan:
    """Plan the managed comment upsert and any allowed lifecycle label transition."""
    if event.number <= 0:
        raise SpecApprovalError("pull request number must be positive")
    require_spec_handoff_target(
        SpecTargetIssue(
            number=metadata.issue_number,
            state=issue_state,
            labels=tuple(issue_labels),
            is_pull_request=is_pull_request,
        )
    )
    validate_canonical_artifacts(repo_root, metadata)
    issue_add, issue_remove = _plan_issue_labels(metadata.issue_number, issue_labels)
    if AGENT_READY in issue_add:
        raise SpecApprovalError("refusing to add agent:ready automatically")
    comment_body = build_approved_comment(metadata, event.number)
    existing = _managed_comment(metadata.issue_number, comments)
    if existing is None:
        action: CommentAction = "create"
        outcome: SpecHandoffOutcome = "created"
        comment_id = None
        message = f"Issue #{metadata.issue_number} approved specification recorded from pull request #{event.number}"
    elif existing.body == comment_body:
        action = "unchanged"
        outcome = "unchanged"
        comment_id = existing.comment_id
        message = f"Issue #{metadata.issue_number} approved specification comment already current"
    else:
        action = "update"
        outcome = "updated"
        comment_id = existing.comment_id
        message = f"Issue #{metadata.issue_number} approved specification comment updated"
    if issue_add:
        message = f"{message}; {NEEDS_DESIGN} -> {NEEDS_HUMAN_REVIEW}"
    return SpecHandoffPlan(
        outcome=outcome,
        issue_number=metadata.issue_number,
        pull_request_number=event.number,
        spec_path=metadata.spec_path,
        comment_body=comment_body,
        comment_action=action,
        existing_comment_id=comment_id,
        issue_add=issue_add,
        issue_remove=issue_remove,
        mutate_issue_body=False,
        message=message,
    )


def read_spec_target_issue(
    repository: str,
    issue_number: int,
    *,
    run_api: Callable[[str], GitHubApiResponse] | None = None,
    sleep: Callable[[float], None] | None = None,
    notify: Callable[[str], None] | None = None,
) -> SpecTargetIssue:
    """Read Issue identity from GitHub REST without returning the Issue body."""
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
            target = spec_target_from_mapping(
                _load_json_object_text(response.stdout, "GitHub REST issue"),
                "GitHub REST issue",
            )
            if target.number != issue_number:
                raise SpecApprovalError("GitHub REST issue number does not match capt-spec metadata")
            return target
        last_status = github_http_status_from_stderr(response.stderr)
        if not is_retryable_github_http_status(last_status) or attempt == GITHUB_REST_READ_MAX_ATTEMPTS:
            break
        log(
            f"GitHub REST issue #{issue_number} read returned HTTP {last_status} "
            f"(attempt {attempt}/{GITHUB_REST_READ_MAX_ATTEMPTS}); retrying"
        )
        sleeper(GITHUB_REST_READ_RETRY_DELAY_SECONDS)
    raise SpecApprovalError(_rest_read_failure_message(f"issue #{issue_number}", last_status, attempt))


def spec_target_from_mapping(payload: Mapping[str, object], what: str) -> SpecTargetIssue:
    number = payload.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise SpecApprovalError(f"{what} number must be a positive integer")
    state = payload.get("state")
    if not isinstance(state, str) or not state:
        raise SpecApprovalError(f"{what} state is not a string")
    labels_value = payload.get("labels")
    if not isinstance(labels_value, list):
        raise SpecApprovalError(f"{what} is missing labels")
    names: list[str] = []
    for item in labels_value:
        if isinstance(item, str):
            names.append(item)
            continue
        if not isinstance(item, dict):
            raise SpecApprovalError(f"{what} labels are invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise SpecApprovalError(f"{what} labels are invalid")
        names.append(name)
    return SpecTargetIssue(
        number=number,
        state=state,
        labels=tuple(names),
        is_pull_request="pull_request" in payload,
    )


def skipped_plan(event: MergedPullRequestEvent) -> SpecHandoffPlan:
    return SpecHandoffPlan(
        outcome="skipped",
        issue_number=None,
        pull_request_number=event.number,
        spec_path=None,
        comment_body=None,
        comment_action=None,
        existing_comment_id=None,
        issue_add=(),
        issue_remove=(),
        mutate_issue_body=False,
        message=skip_message(event),
    )


def read_issue_comments(
    repository: str,
    issue_number: int,
    *,
    run_api: Callable[[str], GitHubApiResponse] | None = None,
    sleep: Callable[[float], None] | None = None,
    notify: Callable[[str], None] | None = None,
) -> tuple[IssueComment, ...]:
    """Read Issue comments from GitHub REST, retrying only bounded transient 5xx failures."""
    _require_positive_issue_number(issue_number)
    owner_repo = _require_owner_repo(repository)
    items: list[dict[str, object]] = []
    for page in range(1, MAX_COMMENT_PAGES + 1):
        path = f"repos/{owner_repo}/issues/{issue_number}/comments?per_page={COMMENTS_PER_PAGE}&page={page}"
        parsed = _read_json_array(
            path,
            f"issue #{issue_number} comments",
            run_api=run_api,
            sleep=sleep,
            notify=notify,
        )
        items.extend(parsed)
        if len(parsed) < COMMENTS_PER_PAGE:
            break
    comments: list[IssueComment] = []
    for item in items:
        comments.append(_comment_from_mapping(item, f"GitHub REST issue #{issue_number} comments"))
    return tuple(comments)


def apply_comment(
    repository: str,
    plan: SpecHandoffPlan,
    *,
    write_api: Callable[[str, str, str], GitHubApiResponse] | None = None,
) -> None:
    """Create or update the managed approved-spec comment. Never edits the Issue body."""
    if plan.outcome == "skipped" or plan.comment_action in {None, "unchanged"}:
        return
    if plan.issue_number is None or plan.comment_body is None:
        raise SpecApprovalError("approved-spec plan is missing comment fields")
    owner_repo = _require_owner_repo(repository)
    payload = json.dumps({"body": plan.comment_body}, allow_nan=False)
    writer = _run_gh_api_write if write_api is None else write_api
    if plan.comment_action == "create":
        path = f"repos/{owner_repo}/issues/{plan.issue_number}/comments"
        response = writer("POST", path, payload)
        _require_write_ok(response, f"GitHub comment on issue #{plan.issue_number}")
        return
    if plan.comment_action == "update":
        if plan.existing_comment_id is None:
            raise SpecApprovalError("approved-spec plan is missing the managed comment id")
        path = f"repos/{owner_repo}/issues/comments/{plan.existing_comment_id}"
        response = writer("PATCH", path, payload)
        _require_write_ok(response, f"GitHub comment on issue #{plan.issue_number}")
        return
    raise SpecApprovalError("approved-spec plan has an unknown comment action")


def apply_issue_labels(
    issue_number: int,
    issue_add: Sequence[str],
    issue_remove: Sequence[str],
    *,
    run_command: Callable[[Sequence[str]], GitHubApiResponse] | None = None,
) -> None:
    """Apply planned Issue label mutations without editing the Issue body."""
    _require_positive_issue_number(issue_number)
    if AGENT_READY in issue_add:
        raise SpecApprovalError("refusing to add agent:ready automatically")
    if not issue_add and not issue_remove:
        return
    args = ["gh", "issue", "edit", str(issue_number)]
    for label in issue_add:
        args.extend(["--add-label", label])
    for label in issue_remove:
        args.extend(["--remove-label", label])
    if "--body" in args:
        raise SpecApprovalError("refusing to rewrite an Issue body")
    runner = _run_gh_command if run_command is None else run_command
    response = runner(args)
    if response.returncode != 0:
        status = github_http_status_from_stderr(response.stderr)
        if status is None:
            raise SpecApprovalError(f"GitHub issue #{issue_number} label update failed")
        raise SpecApprovalError(f"GitHub issue #{issue_number} label update failed with HTTP {status}")


def comments_from_mapping(value: object, what: str) -> tuple[IssueComment, ...]:
    if not isinstance(value, list):
        raise SpecApprovalError(f"{what} must be a JSON array")
    comments: list[IssueComment] = []
    for item in value:
        if not isinstance(item, dict):
            raise SpecApprovalError(f"{what} are invalid")
        comments.append(_comment_from_mapping(item, what))
    return tuple(comments)


def _plan_issue_labels(issue_number: int, labels: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present = tuple(label for label in LIFECYCLE_LABELS if label in labels)
    if len(present) > 1:
        rendered = ", ".join(present)
        raise SpecApprovalError(f"Issue #{issue_number} has multiple lifecycle labels: {rendered}")
    if present == (NEEDS_DESIGN,):
        return ((NEEDS_HUMAN_REVIEW,), (NEEDS_DESIGN,))
    return ((), ())


def _managed_comment(issue_number: int, comments: Sequence[IssueComment]) -> IssueComment | None:
    managed = _trusted_approved_comments(comments)
    if not managed:
        return None
    if len(managed) > 1:
        raise SpecApprovalError(f"Issue #{issue_number} has multiple capt-spec-approved comments")
    comment, parsed = managed[0]
    if parsed.issue_number != issue_number:
        raise SpecApprovalError("approved-spec comment issue does not match the Agent Task Issue")
    return comment


def _trusted_approved_comments(
    comments: Sequence[IssueComment],
) -> tuple[tuple[IssueComment, ApprovedSpec], ...]:
    managed: list[tuple[IssueComment, ApprovedSpec]] = []
    for comment in comments:
        if not _is_trusted_automation_comment(comment):
            continue
        parsed = parse_approved_spec(comment.body)
        if parsed is None:
            continue
        managed.append((comment, parsed))
    return tuple(managed)


def _is_trusted_automation_comment(comment: IssueComment) -> bool:
    return comment.user_login == GITHUB_ACTIONS_BOT_LOGIN and comment.user_type == GITHUB_ACTIONS_BOT_TYPE


def _comment_from_mapping(item: Mapping[str, object], what: str) -> IssueComment:
    comment_id = item.get("id")
    body = item.get("body")
    user = item.get("user")
    if not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id <= 0:
        raise SpecApprovalError(f"{what} are invalid")
    if not isinstance(body, str):
        raise SpecApprovalError(f"{what} are invalid")
    if not isinstance(user, dict):
        raise SpecApprovalError(f"{what} are invalid")
    login = user.get("login")
    user_type = user.get("type")
    if not isinstance(login, str) or not login or not isinstance(user_type, str) or not user_type:
        raise SpecApprovalError(f"{what} are invalid")
    return IssueComment(comment_id=comment_id, body=body, user_login=login, user_type=user_type)


def _parse_metadata_fields(block: str, what: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _FIELD_LINE.fullmatch(line)
        if match is None:
            raise SpecApprovalError(f"{what} is malformed")
        key = match.group(1)
        value = match.group(2).strip()
        if key in fields:
            raise SpecApprovalError(f"{what} contains conflicting fields")
        if not value:
            raise SpecApprovalError(f"{what} is missing required values")
        fields[key] = value
    return fields


def _parse_issue_field(value: str) -> int:
    if _ISSUE_FIELD.fullmatch(value) is None:
        raise SpecApprovalError("capt-spec issue is missing or invalid")
    return int(value)


def _parse_pr_field(value: str) -> int:
    if _PR_FIELD.fullmatch(value) is None:
        raise SpecApprovalError("capt-spec-approved pull request is missing or invalid")
    return int(value)


def _parse_spec_path(value: str) -> str:
    if "\\" in value or value.startswith("/") or "/./" in value or "/../" in value:
        raise SpecApprovalError("declared spec path is not a canonical specs/<feature>/spec.md path")
    if _SPEC_PATH.fullmatch(value) is None:
        raise SpecApprovalError("declared spec path is not a canonical specs/<feature>/spec.md path")
    return value


def _normalize_body(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n")


def _require_repo_root(repo_root: Path) -> Path:
    try:
        root = repo_root.resolve()
    except OSError:
        raise SpecApprovalError("repository root is not readable") from None
    if not root.is_dir():
        raise SpecApprovalError("repository root is not a directory")
    return root


def _require_positive_issue_number(issue_number: int) -> None:
    if issue_number <= 0:
        raise SpecApprovalError("issue number must be positive")


def _require_owner_repo(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise SpecApprovalError("GitHub repository must be owner/repo")
    return repository


def _repository_from_cli(repo_arg: str | None) -> str:
    if repo_arg:
        return repo_arg
    value = os.environ.get("GH_REPO", "")
    if not value:
        raise SpecApprovalError("GH_REPO is not set")
    return value


def _load_json_object(path: Path, what: str) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, RecursionError, json.JSONDecodeError, ValueError:
        raise SpecApprovalError(f"{what} is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise SpecApprovalError(f"{what} must be a JSON object")
    return parsed


def _load_json_value(text: str) -> object:
    try:
        return json.loads(text)
    except RecursionError, json.JSONDecodeError, ValueError:
        return None


def _load_json_object_text(text: str, what: str) -> dict[str, object]:
    parsed = _load_json_value(text)
    if not isinstance(parsed, dict):
        raise SpecApprovalError(f"{what} must be a JSON object")
    return parsed


def _load_label_list(text: str, what: str) -> tuple[str, ...]:
    parsed = _load_json_value(text)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise SpecApprovalError(f"{what} must be a JSON array of strings")
    return tuple(parsed)


def _load_plan(text: str) -> SpecHandoffPlan:
    parsed = _load_json_value(text)
    if not isinstance(parsed, dict):
        raise SpecApprovalError("approved-spec plan must be a JSON object")
    return _plan_from_mapping(parsed)


def _plan_from_mapping(payload: Mapping[str, object]) -> SpecHandoffPlan:
    outcome = _require_handoff_outcome(payload.get("outcome"))
    issue_number = _optional_positive_int(payload.get("issue_number"), "issue_number")
    pull_request_number = _optional_positive_int(payload.get("pull_request_number"), "pull_request_number")
    spec_path_value = payload.get("spec_path")
    if spec_path_value is None:
        spec_path = None
    elif isinstance(spec_path_value, str):
        spec_path = spec_path_value
    else:
        raise SpecApprovalError("approved-spec plan spec_path is invalid")
    comment_body_value = payload.get("comment_body")
    if comment_body_value is None:
        comment_body = None
    elif isinstance(comment_body_value, str):
        comment_body = comment_body_value
    else:
        raise SpecApprovalError("approved-spec plan comment_body is invalid")
    comment_action = _optional_comment_action(payload.get("comment_action"))
    existing_comment_id = _optional_positive_int(payload.get("existing_comment_id"), "existing_comment_id")
    issue_add = _string_tuple(payload.get("issue_add"), "issue_add")
    issue_remove = _string_tuple(payload.get("issue_remove"), "issue_remove")
    mutate_issue_body = payload.get("mutate_issue_body")
    if mutate_issue_body is not False:
        raise SpecApprovalError("approved-spec plan must not rewrite the Issue body")
    message = payload.get("message")
    if not isinstance(message, str):
        raise SpecApprovalError("approved-spec plan message is invalid")
    return SpecHandoffPlan(
        outcome=outcome,
        issue_number=issue_number,
        pull_request_number=pull_request_number,
        spec_path=spec_path,
        comment_body=comment_body,
        comment_action=comment_action,
        existing_comment_id=existing_comment_id,
        issue_add=issue_add,
        issue_remove=issue_remove,
        mutate_issue_body=False,
        message=message,
    )


def _optional_positive_int(value: object, what: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SpecApprovalError(f"approved-spec plan {what} is invalid")
    return value


def _require_handoff_outcome(value: object) -> SpecHandoffOutcome:
    if value == "skipped":
        return "skipped"
    if value == "created":
        return "created"
    if value == "updated":
        return "updated"
    if value == "unchanged":
        return "unchanged"
    raise SpecApprovalError("approved-spec plan outcome is invalid")


def _optional_comment_action(value: object) -> CommentAction | None:
    if value is None:
        return None
    if value == "create":
        return "create"
    if value == "update":
        return "update"
    if value == "unchanged":
        return "unchanged"
    raise SpecApprovalError("approved-spec plan comment_action is invalid")


def _string_tuple(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SpecApprovalError(f"approved-spec plan {what} is invalid")
    return tuple(value)


def _read_json_array(
    path: str,
    what: str,
    *,
    run_api: Callable[[str], GitHubApiResponse] | None,
    sleep: Callable[[float], None] | None,
    notify: Callable[[str], None] | None,
) -> list[dict[str, object]]:
    runner = _run_gh_api if run_api is None else run_api
    sleeper = time.sleep if sleep is None else sleep
    log = _print_stderr if notify is None else notify
    last_status: int | None = None
    attempt = 0
    for attempt in range(1, GITHUB_REST_READ_MAX_ATTEMPTS + 1):
        response = runner(path)
        if response.returncode == 0:
            parsed = _load_json_value(response.stdout)
            if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
                raise SpecApprovalError(f"GitHub REST {what} response must be a JSON array of objects")
            return [item for item in parsed if isinstance(item, dict)]
        last_status = github_http_status_from_stderr(response.stderr)
        if not is_retryable_github_http_status(last_status) or attempt == GITHUB_REST_READ_MAX_ATTEMPTS:
            break
        log(
            f"GitHub REST {what} read returned HTTP {last_status} "
            f"(attempt {attempt}/{GITHUB_REST_READ_MAX_ATTEMPTS}); retrying"
        )
        sleeper(GITHUB_REST_READ_RETRY_DELAY_SECONDS)
    raise SpecApprovalError(_rest_read_failure_message(what, last_status, attempt))


def _rest_read_failure_message(what: str, status_code: int | None, attempts: int) -> str:
    if status_code is None:
        attempt_word = "attempt" if attempts == 1 else "attempts"
        return f"GitHub REST {what} read failed after {attempts} {attempt_word}"
    if is_retryable_github_http_status(status_code):
        return f"GitHub REST {what} read failed with HTTP {status_code} after {attempts} attempts"
    return f"GitHub REST {what} read failed with HTTP {status_code}"


def _require_write_ok(response: GitHubApiResponse, what: str) -> None:
    if response.returncode == 0:
        return
    status = github_http_status_from_stderr(response.stderr)
    if status is None:
        raise SpecApprovalError(f"{what} failed")
    raise SpecApprovalError(f"{what} failed with HTTP {status}")


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
        raise SpecApprovalError("GitHub CLI is not available for REST issue read") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _run_gh_api_write(method: str, path: str, body: str) -> GitHubApiResponse:
    try:
        completed = subprocess.run(
            ["gh", "api", "--method", method, path, "--input", "-"],
            input=body,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        raise SpecApprovalError("GitHub CLI is not available for REST comment write") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _run_gh_command(args: Sequence[str]) -> GitHubApiResponse:
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        raise SpecApprovalError("GitHub CLI is not available for issue label update") from None
    return GitHubApiResponse(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record an approved specification on an Agent Task Issue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify", help="Print whether a merged PR should record an approved spec.")
    classify.add_argument("--event-file", type=Path, required=True)

    plan = subparsers.add_parser("plan", help="Print a JSON approved-spec handoff plan.")
    plan.add_argument("--event-file", type=Path, required=True)
    plan.add_argument("--issue-labels-json", default="[]")
    plan.add_argument("--comments-json", default="[]")
    plan.add_argument("--repo-root", type=Path, default=Path("."))

    apply_comment = subparsers.add_parser("apply-comment", help="Create or update the managed approved-spec comment.")
    apply_comment.add_argument("--plan-json", required=True)
    apply_comment.add_argument("--repo", default=None)

    handoff = subparsers.add_parser("handoff", help="Record the approved specification for a merged spec PR.")
    handoff.add_argument("--event-file", type=Path, required=True)
    handoff.add_argument("--repo-root", type=Path, default=Path("."))
    handoff.add_argument("--repo", default=None)

    return parser


def _run_classify(event_file: Path, stdout: TextIO) -> int:
    event = load_merged_pull_request_event(event_file)
    metadata = classify_spec_event(event)
    if metadata is None:
        payload: dict[str, object] = {"handoff": False, "message": skip_message(event)}
    else:
        payload = {
            "handoff": True,
            "issue_number": metadata.issue_number,
            "spec_path": metadata.spec_path,
            "message": f"pull request #{event.number} has valid capt-spec metadata for Issue #{metadata.issue_number}",
        }
    print(json.dumps(payload, allow_nan=False), file=stdout)
    return 0


def _run_plan(
    event_file: Path,
    issue_labels_json: str,
    comments_json: str,
    repo_root: Path,
    stdout: TextIO,
) -> int:
    event = load_merged_pull_request_event(event_file)
    metadata = classify_spec_event(event)
    if metadata is None:
        print(json.dumps(skipped_plan(event).to_json_dict(), allow_nan=False), file=stdout)
        return 0
    comments = comments_from_mapping(_load_json_value(comments_json), "comments")
    plan = plan_spec_handoff(
        event,
        metadata,
        _load_label_list(issue_labels_json, "issue labels"),
        comments,
        repo_root=repo_root,
    )
    if AGENT_READY in plan.issue_add:
        raise SpecApprovalError("refusing to add agent:ready automatically")
    if plan.mutate_issue_body:
        raise SpecApprovalError("refusing to rewrite an Issue body")
    print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def _run_apply_comment(plan_json: str, repo_arg: str | None, stdout: TextIO) -> int:
    plan = _load_plan(plan_json)
    apply_comment(_repository_from_cli(repo_arg), plan)
    print(json.dumps({"outcome": plan.outcome, "mutate_issue_body": False}, allow_nan=False), file=stdout)
    return 0


def _run_handoff(event_file: Path, repo_root: Path, repo_arg: str | None, stdout: TextIO) -> int:
    event = load_merged_pull_request_event(event_file)
    metadata = classify_spec_event(event)
    if metadata is None:
        plan = skipped_plan(event)
        print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
        return 0
    repository = _repository_from_cli(repo_arg)
    target = read_spec_target_issue(repository, metadata.issue_number)
    require_spec_handoff_target(target)
    comments = read_issue_comments(repository, metadata.issue_number)
    plan = plan_spec_handoff(
        event,
        metadata,
        target.labels,
        comments,
        repo_root=repo_root,
        issue_state=target.state,
        is_pull_request=target.is_pull_request,
    )
    if AGENT_READY in plan.issue_add:
        raise SpecApprovalError("refusing to add agent:ready automatically")
    if plan.mutate_issue_body:
        raise SpecApprovalError("refusing to rewrite an Issue body")
    apply_comment(repository, plan)
    if plan.issue_number is not None:
        apply_issue_labels(plan.issue_number, plan.issue_add, plan.issue_remove)
    print(json.dumps(plan.to_json_dict(), allow_nan=False), file=stdout)
    return 0


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    output = sys.stdout if stdout is None else stdout
    try:
        match args.command:
            case "classify":
                return _run_classify(args.event_file, output)
            case "plan":
                return _run_plan(
                    args.event_file,
                    args.issue_labels_json,
                    args.comments_json,
                    args.repo_root,
                    output,
                )
            case "apply-comment":
                return _run_apply_comment(args.plan_json, args.repo, output)
            case "handoff":
                return _run_handoff(args.event_file, args.repo_root, args.repo, output)
            case _:
                raise SpecApprovalError("unknown command")
    except SpecApprovalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
