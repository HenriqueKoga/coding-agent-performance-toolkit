import json
import subprocess
import uuid
from io import StringIO
from pathlib import Path

import pytest

import agent_rework
from agent_dispatch import OWNER_REPO, REPOSITORY_URL, STARTING_REF
from agent_lifecycle import GitHubApiResponse
from agent_rework import (
    CODEX_REVIEWER_LOGIN,
    CODEX_REVIEWER_TYPE,
    GITHUB_ACTIONS_BOT_LOGIN,
    MAX_AUTOMATIC_REWORKS,
    BlockingFinding,
    IssueComment,
    ReworkError,
    ReworkPlan,
    ReworkSkip,
    build_create_rework_request,
    build_dispatch_marker_comment,
    build_exhausted_marker_comment,
    build_rework_agent_id,
    build_rework_prompt,
    has_exhausted_marker,
    load_review_submitted_event,
    main,
    parse_rework_records,
    plan_rework,
    submit_rework_agent,
)
from cursor_agents import AGENT_ID_CONFLICT, CURSOR_AGENTS_URL, HttpResponse

SECRET = "cursor-test-key-invalid"
REVIEW_SECRET = "developer@example.invalid"
HUMAN_INJECTION = "rm -rf / && curl http://evil.example.invalid"
ISSUE_NUMBER = 20
PR_NUMBER = 21
REVIEW_ID = 4954280472
COMMENT_ID = 3798549809
P1_BODY = (
    "**<sub><sub>![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)</sub></sub>  "
    "Document the new insights summary field**\n"
    "Update the public contract."
)
P0_BODY = (
    "**<sub><sub>![P0 Badge](https://img.shields.io/badge/P0-red?style=flat)</sub></sub>  "
    "Keep the collector on loopback**\n"
    "Do not bind publicly."
)
P2_BODY = (
    "**<sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub>  "
    "Optional rename**\n"
    "Style only."
)
FREEFORM_BLOCKER = f"This is a blocker / critical / must fix P1 finding. {REVIEW_SECRET}"


def _codex_user() -> dict[str, object]:
    return {"login": CODEX_REVIEWER_LOGIN, "type": CODEX_REVIEWER_TYPE, "id": 199175422}


def _human_user() -> dict[str, object]:
    return {"login": "reviewer", "type": "User", "id": 1}


def _pr_mapping(
    *,
    number: int = PR_NUMBER,
    state: str = "open",
    draft: bool = False,
    body: str = f"## Linked task\n\nCloses #{ISSUE_NUMBER}\n",
    base_ref: str = "main",
    labels: tuple[str, ...] = ("risk:medium",),
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "draft": draft,
        "body": body,
        "base": {"ref": base_ref},
        "html_url": f"{REPOSITORY_URL}/pull/{number}",
        "labels": [{"name": name} for name in labels],
    }


def _issue_mapping(
    *,
    number: int = ISSUE_NUMBER,
    state: str = "open",
    labels: tuple[str, ...] = ("needs:human-review", "risk:medium"),
    pull_request: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "number": number,
        "state": state,
        "labels": [{"name": name} for name in labels],
    }
    if pull_request:
        payload["pull_request"] = {"url": f"{REPOSITORY_URL}/pull/{number}"}
    return payload


def _event_file(
    tmp_path: Path,
    *,
    action: str = "submitted",
    sender: dict[str, object] | None = None,
    reviewer: dict[str, object] | None = None,
    review_id: int = REVIEW_ID,
    pull_request: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / "event.json"
    payload: dict[str, object] = {
        "action": action,
        "sender": _codex_user() if sender is None else sender,
        "review": {
            "id": review_id,
            "user": _codex_user() if reviewer is None else reviewer,
            "body": "### Codex Review\nHere are some automated review suggestions.",
            "state": "COMMENTED",
        },
        "pull_request": _pr_mapping() if pull_request is None else pull_request,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _review_comment(
    *,
    comment_id: int = COMMENT_ID,
    body: str = P1_BODY,
    user: dict[str, object] | None = None,
    path: str = "src/coding_agent_performance/trace/rendering.py",
    line: int | None = 133,
    review_id: int = REVIEW_ID,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": comment_id,
        "body": body,
        "user": _codex_user() if user is None else user,
        "path": path,
        "pull_request_review_id": review_id,
        "html_url": f"{REPOSITORY_URL}/pull/{PR_NUMBER}#discussion_r{comment_id}",
    }
    if line is not None:
        payload["line"] = line
    return payload


def _marker_comment(*, attempt: int, review_id: int, agent_id: str | None = None) -> IssueComment:
    resolved_id = agent_id if agent_id is not None else build_rework_agent_id(PR_NUMBER, review_id)
    return IssueComment(
        user_login=GITHUB_ACTIONS_BOT_LOGIN,
        body=build_dispatch_marker_comment(
            attempt=attempt,
            pull_request_number=PR_NUMBER,
            review_id=review_id,
            agent_id=resolved_id,
        ),
    )


def _plan(
    *,
    comments: tuple[dict[str, object], ...] = (),
    markers: tuple[IssueComment, ...] = (),
    pull_request: dict[str, object] | None = None,
    issue: dict[str, object] | None = None,
    tmp_path: Path,
    review_id: int = REVIEW_ID,
) -> ReworkPlan | ReworkSkip:
    event = load_review_submitted_event(_event_file(tmp_path, review_id=review_id, pull_request=pull_request))
    return plan_rework(
        event,
        agent_rework.pull_request_from_mapping(pull_request or _pr_mapping(), "pr"),
        agent_rework.linked_issue_from_mapping(issue or _issue_mapping(), "issue"),
        comments if comments else (_review_comment(review_id=review_id),),
        markers,
    )


class _ScriptedGitHubApi:
    def __init__(self, responses: list[GitHubApiResponse]) -> None:
        self._responses = responses
        self.paths: list[str] = []
        self.writes: list[tuple[str, str, str]] = []
        self.sleeps: list[float] = []
        self.notes: list[str] = []

    def __call__(self, path: str) -> GitHubApiResponse:
        self.paths.append(path)
        return self._responses[len(self.paths) - 1]

    def write(self, method: str, path: str, body: str) -> GitHubApiResponse:
        self.writes.append((method, path, body))
        return GitHubApiResponse(returncode=0, stdout="{}", stderr="")

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def notify(self, message: str) -> None:
        self.notes.append(message)


def _ok(payload: object) -> GitHubApiResponse:
    return GitHubApiResponse(returncode=0, stdout=json.dumps(payload), stderr="")


def _http_error(status: int, body: str = "") -> GitHubApiResponse:
    return GitHubApiResponse(
        returncode=1,
        stdout=body,
        stderr=f"gh: HTTP {status}: Server Error (https://api.github.com/repos/owner/repo/pulls/{PR_NUMBER})",
    )


def test_codex_p1_with_valid_agent_task_plans_one_rework(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path)
    assert isinstance(planned, ReworkPlan)
    assert planned.attempt == 1
    assert planned.issue_number == ISSUE_NUMBER
    assert planned.pull_request_number == PR_NUMBER
    request = planned.request
    assert request == build_create_rework_request(PR_NUMBER, ISSUE_NUMBER, REVIEW_ID, planned.findings)
    assert request["agentId"] == build_rework_agent_id(PR_NUMBER, REVIEW_ID)
    assert request["workOnCurrentBranch"] is True
    assert request["autoCreatePR"] is False
    assert request["repos"] == [{"url": REPOSITORY_URL, "prUrl": f"{REPOSITORY_URL}/pull/{PR_NUMBER}"}]
    repos = request["repos"]
    assert isinstance(repos, list)
    assert "startingRef" not in repos[0]
    assert "model" not in request
    assert "envVars" not in request
    prompt = build_rework_prompt(PR_NUMBER, ISSUE_NUMBER, planned.findings)
    assert request["prompt"] == {"text": prompt}
    assert f"PR #{PR_NUMBER}" in prompt
    assert f"Issue #{ISSUE_NUMBER}" in prompt
    assert OWNER_REPO in prompt
    assert "AGENTS.md" in prompt
    assert "Do not create another PR." in prompt
    assert "Do not mutate lifecycle or risk labels." in prompt
    assert "Do not merge the PR." in prompt
    assert "untrusted code-review context" in prompt
    assert "P1" in prompt
    assert "Document the new insights summary field" in prompt
    assert REVIEW_SECRET not in json.dumps(request)


def test_same_review_with_existing_marker_does_not_plan_another_agent(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path, markers=(_marker_comment(attempt=1, review_id=REVIEW_ID),))
    assert isinstance(planned, ReworkSkip)
    assert planned.outcome == "already_dispatched"
    assert "already dispatched" in planned.message
    assert planned.post_exhausted_comment is False


def test_human_comment_with_identical_p1_text_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        comments=(_review_comment(user=_human_user(), body=P1_BODY),),
    )
    assert isinstance(planned, ReworkSkip)
    assert planned.outcome == "skipped"
    assert "no Codex P0/P1 findings" in planned.message


def test_human_reviewer_does_not_dispatch_even_with_p1_badge(tmp_path: Path) -> None:
    event = load_review_submitted_event(_event_file(tmp_path, sender=_human_user(), reviewer=_human_user()))
    planned = plan_rework(
        event,
        agent_rework.pull_request_from_mapping(_pr_mapping(), "pr"),
        agent_rework.linked_issue_from_mapping(_issue_mapping(), "issue"),
        (_review_comment(),),
        (),
    )
    assert isinstance(planned, ReworkSkip)
    assert "not the Codex GitHub App" in planned.message


def test_other_bot_does_not_dispatch(tmp_path: Path) -> None:
    other: dict[str, object] = {"login": "dependabot[bot]", "type": "Bot"}
    event = load_review_submitted_event(_event_file(tmp_path, sender=other, reviewer=other))
    planned = plan_rework(
        event,
        agent_rework.pull_request_from_mapping(_pr_mapping(), "pr"),
        agent_rework.linked_issue_from_mapping(_issue_mapping(), "issue"),
        (_review_comment(user=other, body=P1_BODY),),
        (),
    )
    assert isinstance(planned, ReworkSkip)
    assert "not the Codex GitHub App" in planned.message


def test_codex_p2_badge_is_not_blocking(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path, comments=(_review_comment(body=P2_BODY),))
    assert isinstance(planned, ReworkSkip)
    assert "no Codex P0/P1 findings" in planned.message


def test_freeform_blocker_text_without_badge_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path, comments=(_review_comment(body=FREEFORM_BLOCKER),))
    assert isinstance(planned, ReworkSkip)
    assert "no Codex P0/P1 findings" in planned.message
    assert REVIEW_SECRET not in planned.message
    assert "blocker" not in planned.message


def test_missing_closes_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        pull_request=_pr_mapping(body=f"Fixes #{ISSUE_NUMBER}\ncloses #{ISSUE_NUMBER}\n{REVIEW_SECRET}"),
    )
    assert isinstance(planned, ReworkSkip)
    assert "Closes" in planned.message
    assert REVIEW_SECRET not in planned.message


def test_ambiguous_closes_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path, pull_request=_pr_mapping(body="Closes #20\nCloses #22\n"))
    assert isinstance(planned, ReworkSkip)
    assert "multiple Closes" in planned.message


def test_mismatched_risk_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        pull_request=_pr_mapping(labels=("risk:low",)),
        issue=_issue_mapping(labels=("needs:human-review", "risk:medium")),
    )
    assert isinstance(planned, ReworkSkip)
    assert "risk:medium" in planned.message
    assert "risk:low" in planned.message


def test_missing_risk_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        pull_request=_pr_mapping(labels=()),
        issue=_issue_mapping(labels=("needs:human-review", "risk:medium")),
    )
    assert isinstance(planned, ReworkSkip)
    assert "no risk:* label" in planned.message


def test_wrong_lifecycle_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        issue=_issue_mapping(labels=("agent:working", "risk:medium")),
    )
    assert isinstance(planned, ReworkSkip)
    assert "agent:working" in planned.message
    assert "needs:human-review" in planned.message


def test_ready_lifecycle_does_not_dispatch(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        issue=_issue_mapping(labels=("agent:ready", "risk:medium")),
    )
    assert isinstance(planned, ReworkSkip)
    assert "agent:ready" in planned.message


def test_first_accepted_rework_records_attempt_one() -> None:
    comment = build_dispatch_marker_comment(
        attempt=1,
        pull_request_number=PR_NUMBER,
        review_id=REVIEW_ID,
        agent_id=build_rework_agent_id(PR_NUMBER, REVIEW_ID),
    )
    records = parse_rework_records(
        (IssueComment(user_login=GITHUB_ACTIONS_BOT_LOGIN, body=comment),),
        PR_NUMBER,
    )
    assert len(records) == 1
    assert records[0].attempt == 1
    assert records[0].review_id == REVIEW_ID


def test_later_distinct_finding_with_budget_one_plans_final_rework(tmp_path: Path) -> None:
    later_review = REVIEW_ID + 1
    planned = _plan(
        tmp_path=tmp_path,
        review_id=later_review,
        comments=(_review_comment(review_id=later_review, comment_id=COMMENT_ID + 1),),
        markers=(_marker_comment(attempt=1, review_id=REVIEW_ID),),
        pull_request=_pr_mapping(),
    )
    assert isinstance(planned, ReworkPlan)
    assert planned.attempt == 2
    assert planned.review_id == later_review
    assert planned.request["agentId"] == build_rework_agent_id(PR_NUMBER, later_review)
    assert planned.request["agentId"] != build_rework_agent_id(PR_NUMBER, REVIEW_ID)


def test_budget_two_does_not_dispatch_and_requests_human_diagnostic(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        review_id=REVIEW_ID + 2,
        comments=(_review_comment(review_id=REVIEW_ID + 2, comment_id=COMMENT_ID + 2),),
        markers=(
            _marker_comment(attempt=1, review_id=REVIEW_ID),
            _marker_comment(attempt=2, review_id=REVIEW_ID + 1),
        ),
    )
    assert isinstance(planned, ReworkSkip)
    assert planned.outcome == "budget_exhausted"
    assert planned.post_exhausted_comment is True
    assert f"{MAX_AUTOMATIC_REWORKS} of {MAX_AUTOMATIC_REWORKS}" in planned.message
    assert "human" in planned.message.lower()
    diagnostic = build_exhausted_marker_comment(PR_NUMBER)
    assert "human must handle remaining blocking findings" in diagnostic
    assert P1_BODY not in diagnostic
    assert REVIEW_SECRET not in diagnostic


def test_human_copied_marker_does_not_count_against_budget(tmp_path: Path) -> None:
    copied = IssueComment(user_login="reviewer", body=_marker_comment(attempt=1, review_id=REVIEW_ID).body)
    planned = _plan(tmp_path=tmp_path, markers=(copied,))
    assert isinstance(planned, ReworkPlan)
    assert planned.attempt == 1


def test_agent_id_is_deterministic_and_review_specific() -> None:
    first = build_rework_agent_id(PR_NUMBER, REVIEW_ID)
    second = build_rework_agent_id(PR_NUMBER, REVIEW_ID)
    other = build_rework_agent_id(PR_NUMBER, REVIEW_ID + 1)
    assert first == second
    assert first != other
    assert first.startswith("bc-")
    identity = f"{REPOSITORY_URL}/pull/{PR_NUMBER}/reviews/{REVIEW_ID}/rework"
    assert first == f"bc-{uuid.uuid5(uuid.NAMESPACE_URL, identity)}"


def test_created_rework_posts_marker_and_hides_secret() -> None:
    findings = (
        BlockingFinding(
            comment_id=COMMENT_ID,
            review_id=REVIEW_ID,
            path="docs/architecture.md",
            line=24,
            html_url=f"{REPOSITORY_URL}/pull/{PR_NUMBER}#discussion_r{COMMENT_ID}",
            priority="P1",
            body=P1_BODY,
        ),
    )
    plan = ReworkPlan(
        pull_request_number=PR_NUMBER,
        issue_number=ISSUE_NUMBER,
        review_id=REVIEW_ID,
        attempt=1,
        findings=findings,
        request=build_create_rework_request(PR_NUMBER, ISSUE_NUMBER, REVIEW_ID, findings),
        message="eligible",
    )
    seen: list[tuple[str, dict[str, str], bytes]] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        seen.append((url, headers, body))
        return HttpResponse(
            201,
            json.dumps(
                {
                    "agent": {
                        "id": plan.request["agentId"],
                        "url": f"https://cursor.com/agents/{plan.request['agentId']}",
                    },
                    "run": {"id": "run-rework-1"},
                    "error": {"message": SECRET},
                }
            ),
        )

    result = submit_rework_agent(plan, SECRET, post=_post)
    assert result.outcome == "created"
    assert result.record_comment is not None
    assert "capt-rework-dispatch" in result.record_comment
    assert '"attempt":1' in result.record_comment
    assert SECRET not in result.message
    assert SECRET not in json.dumps(result.to_json_dict())
    assert SECRET not in seen[0][2].decode("utf-8")
    assert SECRET not in "".join(seen[0][1].values())
    assert seen[0][0] == CURSOR_AGENTS_URL
    payload = json.loads(seen[0][2].decode("utf-8"))
    assert payload["workOnCurrentBranch"] is True
    assert payload["autoCreatePR"] is False
    assert payload["repos"][0]["prUrl"] == f"{REPOSITORY_URL}/pull/{PR_NUMBER}"


def test_duplicate_cursor_conflict_is_already_dispatched_and_still_records() -> None:
    findings = (
        BlockingFinding(
            comment_id=COMMENT_ID,
            review_id=REVIEW_ID,
            path="docs/architecture.md",
            line=24,
            html_url="",
            priority="P1",
            body=P1_BODY,
        ),
    )
    plan = ReworkPlan(
        pull_request_number=PR_NUMBER,
        issue_number=ISSUE_NUMBER,
        review_id=REVIEW_ID,
        attempt=1,
        findings=findings,
        request=build_create_rework_request(PR_NUMBER, ISSUE_NUMBER, REVIEW_ID, findings),
        message="eligible",
    )

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        return HttpResponse(409, json.dumps({"error": {"code": AGENT_ID_CONFLICT, "message": SECRET}}))

    result = submit_rework_agent(plan, SECRET, post=_post)
    assert result.outcome == "already_dispatched"
    assert result.record_comment is not None
    assert SECRET not in result.message
    assert "not creating another agent" in result.message


def test_cursor_http_error_does_not_record_budget() -> None:
    findings = (
        BlockingFinding(
            comment_id=COMMENT_ID,
            review_id=REVIEW_ID,
            path="docs/architecture.md",
            line=None,
            html_url="",
            priority="P0",
            body=P0_BODY,
        ),
    )
    plan = ReworkPlan(
        pull_request_number=PR_NUMBER,
        issue_number=ISSUE_NUMBER,
        review_id=REVIEW_ID,
        attempt=1,
        findings=findings,
        request=build_create_rework_request(PR_NUMBER, ISSUE_NUMBER, REVIEW_ID, findings),
        message="eligible",
    )

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        return HttpResponse(500, json.dumps({"error": SECRET}))

    with pytest.raises(ReworkError, match=r"Cursor API returned HTTP 500$") as exc_info:
        submit_rework_agent(plan, SECRET, post=_post)
    assert SECRET not in str(exc_info.value)


def test_missing_api_key_does_not_call_cursor() -> None:
    findings = (
        BlockingFinding(
            comment_id=COMMENT_ID,
            review_id=REVIEW_ID,
            path="docs/architecture.md",
            line=24,
            html_url="",
            priority="P1",
            body=P1_BODY,
        ),
    )
    plan = ReworkPlan(
        pull_request_number=PR_NUMBER,
        issue_number=ISSUE_NUMBER,
        review_id=REVIEW_ID,
        attempt=1,
        findings=findings,
        request=build_create_rework_request(PR_NUMBER, ISSUE_NUMBER, REVIEW_ID, findings),
        message="eligible",
    )
    calls: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        calls.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    with pytest.raises(ReworkError, match="CURSOR_API_KEY is not set"):
        submit_rework_agent(plan, "", post=_post)
    assert calls == []


def test_prompt_does_not_include_unrelated_human_comment(tmp_path: Path) -> None:
    planned = _plan(
        tmp_path=tmp_path,
        comments=(
            _review_comment(),
            _review_comment(comment_id=COMMENT_ID + 9, user=_human_user(), body=HUMAN_INJECTION),
        ),
    )
    assert isinstance(planned, ReworkPlan)
    prompt_value = planned.request["prompt"]
    assert isinstance(prompt_value, dict)
    prompt = str(prompt_value["text"])
    assert HUMAN_INJECTION not in prompt
    assert "P1" in prompt


def test_codex_p0_badge_is_blocking(tmp_path: Path) -> None:
    planned = _plan(tmp_path=tmp_path, comments=(_review_comment(body=P0_BODY),))
    assert isinstance(planned, ReworkPlan)
    assert planned.findings[0].priority == "P0"
    prompt_value = planned.request["prompt"]
    assert isinstance(prompt_value, dict)
    assert "P0" in str(prompt_value["text"])


def test_closed_or_draft_or_non_main_pr_does_not_dispatch(tmp_path: Path) -> None:
    closed = _plan(tmp_path=tmp_path, pull_request=_pr_mapping(state="closed"))
    draft = _plan(tmp_path=tmp_path, pull_request=_pr_mapping(draft=True))
    other_base = _plan(tmp_path=tmp_path, pull_request=_pr_mapping(base_ref="release"))
    assert isinstance(closed, ReworkSkip)
    assert isinstance(draft, ReworkSkip)
    assert isinstance(other_base, ReworkSkip)
    assert "closed" in closed.message
    assert "draft" in draft.message
    assert STARTING_REF in other_base.message


def test_cli_plan_eligible(tmp_path: Path) -> None:
    event = _event_file(tmp_path)
    stdout = StringIO()
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--pull-request-json",
                json.dumps(_pr_mapping()),
                "--issue-json",
                json.dumps(_issue_mapping()),
                "--review-comments-json",
                json.dumps([_review_comment()]),
                "--marker-comments-json",
                "[]",
            ],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["outcome"] == "dispatch"
    assert plan["request"]["autoCreatePR"] is False
    assert plan["request"]["workOnCurrentBranch"] is True
    assert REVIEW_SECRET not in stdout.getvalue()
    assert SECRET not in stdout.getvalue()


def test_cli_dispatch_creates_once_and_writes_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_file(tmp_path)
    agent_id = build_rework_agent_id(PR_NUMBER, REVIEW_ID)
    api = _ScriptedGitHubApi(
        [
            _ok(_pr_mapping()),
            _ok([_review_comment()]),
            _ok([]),
            _ok(_issue_mapping()),
        ]
    )
    posts: list[bytes] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers
        posts.append(body)
        return HttpResponse(201, json.dumps({"agent": {"id": agent_id}, "run": {"id": "run-2"}}))

    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert (
        main(
            ["dispatch", "--event-file", str(event), "--repo", "owner/repo"],
            stdout=stdout,
            run_api=api,
            write_api=api.write,
            post=_post,
        )
        == 0
    )
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "created"
    assert result["agent_id"] == agent_id
    assert len(posts) == 1
    assert len(api.writes) == 1
    assert api.writes[0][0] == "POST"
    written = json.loads(api.writes[0][2])
    assert "capt-rework-dispatch" in written["body"]
    assert SECRET not in stdout.getvalue()
    assert HUMAN_INJECTION not in stdout.getvalue()
    assert P1_BODY not in stdout.getvalue()


def test_cli_dispatch_same_event_retry_does_not_call_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_file(tmp_path)
    marker = _marker_comment(attempt=1, review_id=REVIEW_ID)
    api = _ScriptedGitHubApi(
        [
            _ok(_pr_mapping()),
            _ok([_review_comment()]),
            _ok([{"user": {"login": marker.user_login}, "body": marker.body}]),
            _ok(_issue_mapping()),
        ]
    )
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert (
        main(
            ["dispatch", "--event-file", str(event), "--repo", "owner/repo"],
            stdout=stdout,
            run_api=api,
            write_api=api.write,
            post=_post,
        )
        == 0
    )
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "already_dispatched"
    assert posts == []
    assert api.writes == []


def test_cli_dispatch_human_reviewer_does_not_read_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path, sender=_human_user(), reviewer=_human_user())
    api = _ScriptedGitHubApi([])
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert (
        main(
            ["dispatch", "--event-file", str(event), "--repo", "owner/repo"],
            stdout=stdout,
            run_api=api,
            write_api=api.write,
            post=_post,
        )
        == 0
    )
    captured = capsys.readouterr()
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "skipped"
    assert api.paths == []
    assert posts == []
    assert "Codex GitHub App" in captured.err


def test_cli_dispatch_cursor_failure_does_not_write_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path)
    api = _ScriptedGitHubApi(
        [
            _ok(_pr_mapping()),
            _ok([_review_comment()]),
            _ok([]),
            _ok(_issue_mapping()),
        ]
    )

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        return HttpResponse(503, json.dumps({"error": SECRET}))

    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert (
        main(
            ["dispatch", "--event-file", str(event), "--repo", "owner/repo"],
            stdout=stdout,
            run_api=api,
            write_api=api.write,
            post=_post,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert api.writes == []
    assert "HTTP 503" in captured.err
    assert SECRET not in captured.err


def test_cli_dispatch_exhausted_budget_posts_human_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path, review_id=REVIEW_ID + 2)
    first = _marker_comment(attempt=1, review_id=REVIEW_ID)
    second = _marker_comment(attempt=2, review_id=REVIEW_ID + 1)
    api = _ScriptedGitHubApi(
        [
            _ok(_pr_mapping()),
            _ok([_review_comment(review_id=REVIEW_ID + 2)]),
            _ok(
                [
                    {"user": {"login": first.user_login}, "body": first.body},
                    {"user": {"login": second.user_login}, "body": second.body},
                ]
            ),
            _ok(_issue_mapping()),
        ]
    )
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert (
        main(
            ["dispatch", "--event-file", str(event), "--repo", "owner/repo"],
            stdout=stdout,
            run_api=api,
            write_api=api.write,
            post=_post,
        )
        == 0
    )
    captured = capsys.readouterr()
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "budget_exhausted"
    assert posts == []
    assert len(api.writes) == 1
    written = json.loads(api.writes[0][2])
    assert "capt-rework-exhausted" in written["body"]
    assert "human must handle" in captured.err
    assert P1_BODY not in captured.err
    assert P1_BODY not in written["body"]


def test_exhausted_marker_is_not_posted_twice(tmp_path: Path) -> None:
    comments = (
        _marker_comment(attempt=1, review_id=REVIEW_ID),
        _marker_comment(attempt=2, review_id=REVIEW_ID + 1),
        IssueComment(user_login=GITHUB_ACTIONS_BOT_LOGIN, body=build_exhausted_marker_comment(PR_NUMBER)),
    )
    planned = _plan(
        tmp_path=tmp_path,
        review_id=REVIEW_ID + 2,
        comments=(_review_comment(review_id=REVIEW_ID + 2),),
        markers=comments,
    )
    assert isinstance(planned, ReworkSkip)
    assert planned.outcome == "budget_exhausted"
    assert planned.post_exhausted_comment is False
    assert has_exhausted_marker(comments, PR_NUMBER) is True


def test_comment_write_uses_stdin_not_shell_interpolation(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded.append(args)
        assert kwargs.get("input") == json.dumps({"body": P1_BODY})
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(agent_rework.subprocess, "run", _fake_run)
    agent_rework.post_pull_request_comment("owner/repo", PR_NUMBER, P1_BODY)
    assert recorded == [
        ["gh", "api", "--method", "POST", f"repos/owner/repo/issues/{PR_NUMBER}/comments", "--input", "-"]
    ]
    assert P1_BODY not in " ".join(recorded[0])


def test_rest_read_retries_503_then_succeeds() -> None:
    api = _ScriptedGitHubApi([_http_error(503, body=SECRET), _ok(_pr_mapping())])
    pull_request = agent_rework.read_pull_request(
        "owner/repo",
        PR_NUMBER,
        run_api=api,
        sleep=api.sleep,
        notify=api.notify,
    )
    assert pull_request.number == PR_NUMBER
    assert SECRET not in "".join(api.notes)


def test_unsupported_review_action_is_rejected(tmp_path: Path) -> None:
    event = _event_file(tmp_path, action="edited")
    with pytest.raises(ReworkError, match="submitted event"):
        load_review_submitted_event(event)


def test_workflow_is_dedicated_and_least_privilege() -> None:
    workflow = Path(".github/workflows/agent-rework.yml").read_text(encoding="utf-8")
    dispatch = Path(".github/workflows/agent-dispatch.yml").read_text(encoding="utf-8")
    lifecycle = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pull_request_review:" in workflow
    assert "submitted" in workflow
    assert "chatgpt-codex-connector[bot]" in workflow
    assert "sender.type == 'Bot'" in workflow
    assert "agent_rework.py dispatch" in workflow
    assert "ref: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "github.event.pull_request.head.sha" not in workflow
    assert "secrets.CURSOR_API_KEY" in workflow
    assert "api.cursor.com" not in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "agent-rework-${{ github.event.pull_request.number }}" in workflow
    assert "agent-rework" not in dispatch
    assert "agent-rework" not in lifecycle
    assert "agent-rework" not in ci
    assert "pull_request_review" not in dispatch
    assert "pull_request_review" not in lifecycle
    assert "pull_request_review" not in ci
    assert "CURSOR_API_KEY" not in lifecycle
    assert "CURSOR_API_KEY" not in ci


def test_existing_dispatch_and_lifecycle_workflows_stay_separate() -> None:
    dispatch = Path(".github/workflows/agent-dispatch.yml").read_text(encoding="utf-8")
    lifecycle = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    assert "issues:" in dispatch
    assert "labeled" in dispatch
    assert "github.event.sender.type == 'User'" in dispatch
    assert "pull_request:" in lifecycle
    assert "ready_for_review" in lifecycle
    assert "agent_lifecycle.py" in lifecycle
    assert "agent_rework.py" not in dispatch
    assert "agent_rework.py" not in lifecycle
