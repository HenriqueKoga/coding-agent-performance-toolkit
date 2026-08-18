import json
import uuid
from io import StringIO
from pathlib import Path

import pytest

import agent_dispatch
import agent_spec_dispatch
from agent_dispatch import OWNER_REPO, REPOSITORY_URL, STARTING_REF
from agent_lifecycle import GitHubApiResponse, plan_lifecycle
from agent_spec_dispatch import (
    CURSOR_AGENTS_URL,
    DISPATCH_REF_ENV,
    HttpResponse,
    SpecDispatchError,
    build_agent_id,
    build_create_agent_request,
    build_prompt,
    interpret_cursor_create_response,
    main,
    parse_issue_number,
    plan_spec_dispatch,
    require_supported_repository,
    require_trusted_dispatch_ref,
    spec_issue_from_mapping,
    submit_create_agent,
    validate_spec_dispatch_preconditions,
)
from cursor_agents import AGENT_ID_CONFLICT

SECRET = "cursor-test-key-invalid"
ISSUE_BODY_SECRET = "developer@example.invalid"


def _issue_mapping(
    *,
    number: int = 18,
    state: str = "open",
    title: str = "Specify dispatch",
    body: str = f"secret {ISSUE_BODY_SECRET}",
    labels: tuple[str, ...] = ("needs:design", "risk:low"),
    pull_request: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "number": number,
        "state": state,
        "title": title,
        "body": body,
        "labels": [{"name": name} for name in labels],
    }
    if pull_request:
        payload["pull_request"] = {"url": "https://github.com/example/repo/pull/18"}
    return payload


def _issue_json(
    *,
    number: int = 18,
    state: str = "open",
    title: str = "Specify dispatch",
    body: str = f"secret {ISSUE_BODY_SECRET}",
    labels: tuple[str, ...] = ("needs:design", "risk:low"),
    pull_request: bool = False,
) -> str:
    return json.dumps(
        _issue_mapping(
            number=number,
            state=state,
            title=title,
            body=body,
            labels=labels,
            pull_request=pull_request,
        )
    )


def _ok_issue(
    *,
    number: int = 18,
    state: str = "open",
    labels: tuple[str, ...] = ("needs:design", "risk:low"),
    pull_request: bool = False,
) -> GitHubApiResponse:
    return GitHubApiResponse(
        returncode=0,
        stdout=_issue_json(number=number, state=state, labels=labels, pull_request=pull_request),
        stderr="",
    )


def _http_error(status: int, body: str = "") -> GitHubApiResponse:
    return GitHubApiResponse(
        returncode=1,
        stdout=body,
        stderr=f"gh: HTTP {status}: Server Error (https://api.github.com/repos/{OWNER_REPO}/issues/18)",
    )


class _ScriptedGitHubApi:
    def __init__(self, responses: list[GitHubApiResponse]) -> None:
        self._responses = responses
        self.paths: list[str] = []
        self.sleeps: list[float] = []
        self.notes: list[str] = []

    def __call__(self, path: str) -> GitHubApiResponse:
        self.paths.append(path)
        return self._responses[len(self.paths) - 1]

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def notify(self, message: str) -> None:
        self.notes.append(message)


def test_open_design_issue_with_one_risk_plans_one_request() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(), "issue")
    plan = plan_spec_dispatch(issue)
    request = plan.request
    prompt = build_prompt(18)
    assert plan.issue_number == 18
    assert request == build_create_agent_request(18)
    assert request["agentId"] == build_agent_id(18)
    assert request["prompt"] == {"text": prompt}
    assert request["repos"] == [{"url": REPOSITORY_URL, "startingRef": STARTING_REF}]
    assert request["mode"] == "agent"
    assert request["autoCreatePR"] is False
    assert "model" not in request
    assert "envVars" not in request
    assert ISSUE_BODY_SECRET not in json.dumps(request)
    assert ISSUE_BODY_SECRET not in plan.message
    assert plan.to_json_dict().keys() == {"issue_number", "request", "message"}


def test_planner_does_not_plan_lifecycle_or_body_mutation() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(), "issue")
    plan = plan_spec_dispatch(issue)
    payload = json.dumps(plan.to_json_dict())
    source = Path(".github/scripts/agent_spec_dispatch.py").read_text(encoding="utf-8")
    assert "issue_add" not in payload
    assert "issue_remove" not in payload
    assert "apply_issue_labels" not in source
    assert "gh issue edit" not in source
    assert "/labels" not in source
    assert ISSUE_BODY_SECRET not in payload


def test_pull_request_does_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(pull_request=True), "issue")
    with pytest.raises(SpecDispatchError, match="is a pull request"):
        validate_spec_dispatch_preconditions(issue)


def test_closed_issue_does_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(state="closed"), "issue")
    with pytest.raises(SpecDispatchError, match="is closed"):
        plan_spec_dispatch(issue)


@pytest.mark.parametrize(
    "lifecycle",
    ("needs:human-review", "agent:ready", "agent:working", "agent:blocked"),
)
def test_non_design_lifecycle_does_not_plan_dispatch(lifecycle: str) -> None:
    issue = spec_issue_from_mapping(_issue_mapping(labels=(lifecycle, "risk:low")), "issue")
    with pytest.raises(SpecDispatchError, match=f"lifecycle is {lifecycle}"):
        plan_spec_dispatch(issue)


def test_missing_lifecycle_label_does_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(labels=("risk:low",)), "issue")
    with pytest.raises(SpecDispatchError, match="has no lifecycle label"):
        plan_spec_dispatch(issue)


def test_conflicting_lifecycle_labels_do_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(
        _issue_mapping(labels=("needs:design", "agent:ready", "risk:low")),
        "issue",
    )
    with pytest.raises(SpecDispatchError, match="multiple lifecycle labels: needs:design, agent:ready"):
        plan_spec_dispatch(issue)


def test_missing_risk_label_does_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(_issue_mapping(labels=("needs:design",)), "issue")
    with pytest.raises(SpecDispatchError, match="has no risk:\\* label"):
        plan_spec_dispatch(issue)


def test_multiple_risk_labels_do_not_plan_dispatch() -> None:
    issue = spec_issue_from_mapping(
        _issue_mapping(labels=("needs:design", "risk:low", "risk:medium")),
        "issue",
    )
    with pytest.raises(SpecDispatchError, match="multiple risk:\\* labels: risk:low, risk:medium"):
        plan_spec_dispatch(issue)


@pytest.mark.parametrize("value", ("", "0", "-1", "18.0", "abc", "018", "1e2"))
def test_malformed_issue_number_is_rejected(value: str) -> None:
    with pytest.raises(SpecDispatchError, match="positive integer"):
        parse_issue_number(value)


def test_parse_issue_number_accepts_positive_integer() -> None:
    assert parse_issue_number("18") == 18


def test_unsupported_repository_is_rejected() -> None:
    with pytest.raises(SpecDispatchError, match="operates only on HenriqueKoga/coding-agent-performance-toolkit"):
        require_supported_repository("other/repo")


def test_trusted_dispatch_ref_rejects_non_main() -> None:
    with pytest.raises(SpecDispatchError, match="must run from main"):
        require_trusted_dispatch_ref("refs/heads/cursor/issue-66-5f18")


def test_trusted_dispatch_ref_accepts_main_and_local_unset() -> None:
    require_trusted_dispatch_ref("refs/heads/main")
    require_trusted_dispatch_ref("")


def test_prompt_contains_required_specification_contract() -> None:
    issue_number = 18
    prompt = build_prompt(issue_number)
    assert f"Issue #{issue_number}" in prompt
    assert OWNER_REPO in prompt
    assert "AGENTS.md" in prompt
    assert "docs/spec-kit.md" in prompt
    assert "relevant ADRs" in prompt
    assert "original feature brief" in prompt
    assert "immutable original feature brief" in prompt
    assert "Do not rewrite the Issue body." in prompt
    assert "Perform specification work only." in prompt
    assert "Do not implement product or runtime code." in prompt
    specify_at = prompt.index("1. speckit-specify")
    clarify_at = prompt.index("2. speckit-clarify only when materially necessary")
    plan_at = prompt.index("3. speckit-plan")
    tasks_at = prompt.index("4. speckit-tasks")
    analyze_at = prompt.index("5. speckit-analyze")
    persist_at = prompt.index("6. persist analyze.md")
    assert specify_at < clarify_at < plan_at < tasks_at < analyze_at < persist_at
    assert "targeting `main`" in prompt
    assert ".github/spec-review-pull-request.md" in prompt
    assert "`<!-- capt-lifecycle: ignore -->`" in prompt
    assert "`capt-spec:v1`" in prompt
    assert f"`Related to #{issue_number}`" in prompt
    assert f"`Closes #{issue_number}`" in prompt
    assert "no standalone" in prompt
    assert "Do not apply or mutate `agent:ready`" in prompt
    assert "Do not run `/speckit.implement`." in prompt
    assert "Do not run `/speckit.taskstoissues`." in prompt
    assert "Do not create a second Agent Task Issue." in prompt
    assert "Do not create the approved-spec Issue comment." in prompt
    assert "Stop after opening the specification review PR for human review." in prompt
    assert "Do not merge the PR." in prompt
    assert ISSUE_BODY_SECRET not in prompt


def test_prompt_contains_no_instruction_to_implement() -> None:
    prompt = build_prompt(18)
    assert "Implement GitHub Issue" not in prompt
    assert "implement this Issue" not in prompt
    assert "complete task specification" not in prompt
    assert "/speckit.implement" in prompt
    assert "Do not run `/speckit.implement`." in prompt
    assert prompt.index("Do not implement product or runtime code.") < prompt.index("Expected workflow:")


def test_agent_id_is_deterministic_issue_specific_and_distinct_from_implementation() -> None:
    first = build_agent_id(18)
    second = build_agent_id(18)
    other = build_agent_id(19)
    implementation = agent_dispatch.build_agent_id(18)
    assert first == second
    assert first != other
    assert first != implementation
    assert first.startswith("bc-")
    assert first == f"bc-{uuid.uuid5(uuid.NAMESPACE_URL, f'{REPOSITORY_URL}/issues/18/spec-agent')}"


def test_created_cursor_response_returns_safe_metadata() -> None:
    agent_id = build_agent_id(18)
    body = json.dumps(
        {
            "agent": {
                "id": agent_id,
                "url": f"https://cursor.com/agents/{agent_id}",
            },
            "run": {"id": "run-00000000-0000-0000-0000-000000000001"},
            "error": {"message": SECRET},
        }
    )
    result = interpret_cursor_create_response(18, agent_id, HttpResponse(201, body))
    payload = json.dumps(result.to_json_dict())
    assert result.outcome == "created"
    assert result.issue_number == 18
    assert result.agent_id == agent_id
    assert result.run_id == "run-00000000-0000-0000-0000-000000000001"
    assert SECRET not in payload
    assert "prompt" not in payload
    assert ISSUE_BODY_SECRET not in payload


def test_duplicate_cursor_conflict_fails_closed() -> None:
    agent_id = build_agent_id(18)
    body = json.dumps({"error": {"code": AGENT_ID_CONFLICT, "message": SECRET}})
    with pytest.raises(SpecDispatchError, match="already dispatched") as exc_info:
        interpret_cursor_create_response(18, agent_id, HttpResponse(409, body))
    assert "not creating another agent" in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


def test_unparseable_conflict_fails_closed_without_payload() -> None:
    with pytest.raises(SpecDispatchError, match=r"Cursor API returned HTTP 409$") as exc_info:
        interpret_cursor_create_response(18, build_agent_id(18), HttpResponse(409, f"conflict {SECRET}"))
    assert SECRET not in str(exc_info.value)
    assert "already dispatched" not in str(exc_info.value)


def test_cursor_http_error_fails_without_payload() -> None:
    with pytest.raises(SpecDispatchError, match=r"Cursor API returned HTTP 500$") as exc_info:
        interpret_cursor_create_response(18, build_agent_id(18), HttpResponse(500, json.dumps({"error": SECRET})))
    assert SECRET not in str(exc_info.value)


def test_submit_does_not_call_cursor_without_api_key() -> None:
    calls: list[tuple[str, dict[str, str], bytes]] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        calls.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    with pytest.raises(SpecDispatchError, match="CURSOR_API_KEY is not set"):
        submit_create_agent(18, build_create_agent_request(18), "", post=_post)
    assert calls == []


def test_submit_posts_expected_request_and_hides_secret() -> None:
    request = build_create_agent_request(18)
    seen: list[tuple[str, dict[str, str], bytes]] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        seen.append((url, headers, body))
        return HttpResponse(
            201,
            json.dumps(
                {
                    "agent": {"id": request["agentId"], "url": f"https://cursor.com/agents/{request['agentId']}"},
                    "run": {"id": "run-1"},
                }
            ),
        )

    result = submit_create_agent(18, request, SECRET, post=_post)
    assert result.outcome == "created"
    assert seen[0][0] == CURSOR_AGENTS_URL
    assert json.loads(seen[0][2].decode("utf-8")) == request
    assert SECRET not in json.dumps(result.to_json_dict())
    assert SECRET not in seen[0][2].decode("utf-8")
    assert ISSUE_BODY_SECRET not in seen[0][2].decode("utf-8")
    assert any(value.startswith("Basic ") for value in seen[0][1].values())
    assert SECRET not in "".join(seen[0][1].values())


def test_duplicate_submit_is_rejected_without_a_second_create() -> None:
    request = build_create_agent_request(18)
    statuses = [201, 409]
    created = 0

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        status = statuses.pop(0)
        if status == 201:
            nonlocal created
            created += 1
            return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-1"}}))
        return HttpResponse(409, json.dumps({"error": {"code": AGENT_ID_CONFLICT, "message": SECRET}}))

    first = submit_create_agent(18, request, SECRET, post=_post)
    with pytest.raises(SpecDispatchError, match="already dispatched") as exc_info:
        submit_create_agent(18, request, SECRET, post=_post)
    assert first.outcome == "created"
    assert created == 1
    assert SECRET not in first.message
    assert SECRET not in str(exc_info.value)


def test_cli_parse_issue() -> None:
    stdout = StringIO()
    assert main(["parse-issue", "--issue", "18"], stdout=stdout) == 0
    assert stdout.getvalue() == "18\n"


def test_cli_parse_issue_rejects_malformed(capsys: pytest.CaptureFixture[str]) -> None:
    stdout = StringIO()
    assert main(["parse-issue", "--issue", "0"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "positive integer" in captured.err


def test_cli_plan() -> None:
    stdout = StringIO()
    assert main(["plan", "--issue-json", _issue_json()], stdout=stdout) == 0
    plan = json.loads(stdout.getvalue())
    assert plan["issue_number"] == 18
    assert plan["request"]["autoCreatePR"] is False
    assert plan["request"]["repos"][0]["startingRef"] == "main"
    assert plan["request"]["name"] == "Spec Agent Issue #18"
    assert "model" not in plan["request"]
    assert ISSUE_BODY_SECRET not in stdout.getvalue()
    assert SECRET not in stdout.getvalue()


def test_cli_plan_rejects_pull_request_without_calling_cursor(capsys: pytest.CaptureFixture[str]) -> None:
    stdout = StringIO()
    assert main(["plan", "--issue-json", _issue_json(pull_request=True)], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "pull request" in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_cli_submit_created(monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_create_agent_request(18)

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-9"}}))

    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["submit", "--issue", "18", "--request-json", json.dumps(request)], stdout=stdout) == 0
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "created"
    assert result["run_id"] == "run-9"
    assert SECRET not in stdout.getvalue()


def test_cli_submit_missing_key_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    stdout = StringIO()
    assert (
        main(["submit", "--issue", "18", "--request-json", json.dumps(build_create_agent_request(18))], stdout=stdout)
        == 1
    )
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "CURSOR_API_KEY is not set" in captured.err
    assert SECRET not in captured.err


def test_cli_dispatch_uses_rest_issue_and_posts_once(monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_create_agent_request(18)
    api = _ScriptedGitHubApi([_ok_issue()])
    posts: list[bytes] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers
        posts.append(body)
        return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-2"}}))

    monkeypatch.setattr(agent_spec_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    monkeypatch.delenv(DISPATCH_REF_ENV, raising=False)
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", OWNER_REPO], stdout=stdout) == 0
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "created"
    assert api.paths == [f"repos/{OWNER_REPO}/issues/18"]
    assert json.loads(posts[0].decode("utf-8")) == request
    assert ISSUE_BODY_SECRET not in stdout.getvalue()
    assert SECRET not in stdout.getvalue()


def test_cli_dispatch_rejects_non_main_actions_ref(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    monkeypatch.setenv(DISPATCH_REF_ENV, "refs/heads/cursor/issue-66-5f18")
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", OWNER_REPO], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "must run from main" in captured.err
    assert SECRET not in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_cli_dispatch_rejects_wrong_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", "other/repo"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "operates only on" in captured.err
    assert SECRET not in captured.err


def test_cli_dispatch_does_not_post_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = _ScriptedGitHubApi([_ok_issue(labels=("needs:design",))])
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_spec_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", OWNER_REPO], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "no risk:* label" in captured.err
    assert SECRET not in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_cli_dispatch_rejects_closed_issue(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    api = _ScriptedGitHubApi([_ok_issue(state="closed")])
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_spec_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", OWNER_REPO], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "is closed" in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_rest_read_failure_does_not_plan_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = _ScriptedGitHubApi([_http_error(404, body=SECRET)])
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_spec_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_spec_dispatch, "post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--issue", "18", "--repo", OWNER_REPO], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "HTTP 404" in captured.err
    assert SECRET not in captured.err


def test_cli_rejects_invalid_issue_json_without_contents(capsys: pytest.CaptureFixture[str]) -> None:
    stdout = StringIO()
    assert main(["plan", "--issue-json", f'{{"prompt": "{SECRET}"'], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert SECRET not in captured.err
    assert "prompt" not in captured.err


def test_bool_issue_number_is_rejected() -> None:
    payload = _issue_mapping()
    payload["number"] = True
    with pytest.raises(SpecDispatchError, match="positive integer"):
        spec_issue_from_mapping(payload, "issue")


def test_null_issue_body_is_empty_string() -> None:
    payload = _issue_mapping()
    payload["body"] = None
    issue = spec_issue_from_mapping(payload, "issue")
    assert issue.body == ""


def test_workflow_is_dedicated_manual_and_least_privilege() -> None:
    workflow = Path(".github/workflows/agent-spec-dispatch.yml").read_text(encoding="utf-8")
    dispatch = Path(".github/workflows/agent-dispatch.yml").read_text(encoding="utf-8")
    approved = Path(".github/workflows/agent-spec-approved.yml").read_text(encoding="utf-8")
    lifecycle = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    rework = Path(".github/workflows/agent-rework.yml").read_text(encoding="utf-8")
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "issue_number:" in workflow
    assert "type: number" in workflow
    on_block = workflow.split("on:", 1)[1].split("jobs:", 1)[0]
    assert "issues:" not in on_block
    assert "pull_request:" not in workflow
    assert "labeled" not in workflow
    assert "needs:design" not in on_block
    assert "agent_spec_dispatch.py dispatch" in workflow
    assert 'dispatch --issue "${{ github.event.inputs.issue_number }}"' in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "environment: capt-cursor" in workflow
    assert "ref: main" in workflow
    assert "CAPT_SPEC_DISPATCH_REF" in workflow
    assert "secrets.CURSOR_API_KEY" in workflow
    assert "api.cursor.com" not in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "agent-spec-dispatch-${{ github.event.inputs.issue_number }}" in workflow
    assert "agent:ready" not in workflow
    assert "workflow_dispatch" not in dispatch
    assert "agent_spec_dispatch.py" not in dispatch
    assert "agent_spec_dispatch.py" not in approved
    assert "agent_spec_dispatch.py" not in lifecycle
    assert "agent_spec_dispatch.py" not in rework
    assert "agent_spec_dispatch.py" not in ci
    assert "CURSOR_API_KEY" not in approved
    assert "CURSOR_API_KEY" not in lifecycle
    assert "CURSOR_API_KEY" not in ci
    assert "labeled" in dispatch
    assert "github.event.label.name == 'agent:ready'" in dispatch
    assert "agent_spec.py classify" in approved
    assert "agent_spec.py handoff" in approved


def test_implementation_dispatcher_still_plans_ready_to_working() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ())
    assert plan.issue_add == ("agent:working",)
    assert plan.issue_remove == ("agent:ready",)
    assert "agent:ready" not in plan.issue_add
