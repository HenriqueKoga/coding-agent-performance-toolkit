import json
import subprocess
import uuid
from io import StringIO
from pathlib import Path

import pytest

import agent_dispatch
from agent_dispatch import (
    AGENT_ID_CONFLICT,
    CURSOR_AGENTS_URL,
    OWNER_REPO,
    REPOSITORY_URL,
    STARTING_REF,
    DispatchError,
    HttpResponse,
    build_agent_id,
    build_create_agent_request,
    build_prompt,
    dispatch_issue_from_mapping,
    interpret_cursor_create_response,
    load_labeled_issue_event,
    main,
    plan_dispatch,
    read_dispatch_issue,
    submit_create_agent,
    validate_dispatch_preconditions,
)
from agent_lifecycle import GitHubApiResponse, plan_lifecycle

SECRET = "cursor-test-key-invalid"
ISSUE_BODY_SECRET = "developer@example.invalid"


def _issue_mapping(
    *,
    number: int = 18,
    state: str = "open",
    title: str = "Implement dispatch",
    body: str = f"secret {ISSUE_BODY_SECRET}",
    labels: tuple[str, ...] = ("agent:ready", "risk:low"),
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


def _event_file(
    tmp_path: Path,
    *,
    action: str = "labeled",
    added_label: str = "agent:ready",
    issue: dict[str, object] | None = None,
    sender_type: str | None = "User",
) -> Path:
    path = tmp_path / "event.json"
    payload: dict[str, object] = {
        "action": action,
        "label": {"name": added_label},
        "issue": _issue_mapping() if issue is None else issue,
    }
    if sender_type is not None:
        payload["sender"] = {"type": sender_type}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _issue_json(
    *,
    number: int = 18,
    state: str = "open",
    title: str = "Implement dispatch",
    body: str = f"secret {ISSUE_BODY_SECRET}",
    labels: tuple[str, ...] = ("agent:ready", "risk:low"),
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
    labels: tuple[str, ...] = ("agent:ready", "risk:low"),
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
        stderr=f"gh: HTTP {status}: Server Error (https://api.github.com/repos/owner/repo/issues/18)",
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


def test_open_ready_issue_with_one_risk_plans_one_request() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(), "issue")
    plan = plan_dispatch("agent:ready", issue)
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


def test_different_added_label_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(labels=("agent:ready", "risk:low")), "issue")
    with pytest.raises(DispatchError, match="added label is agent:ready"):
        plan_dispatch("risk:low", issue)


def test_pull_request_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(pull_request=True), "issue")
    with pytest.raises(DispatchError, match="is a pull request"):
        validate_dispatch_preconditions("agent:ready", issue)


def test_missing_risk_label_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(labels=("agent:ready",)), "issue")
    with pytest.raises(DispatchError, match="has no risk:\\* label"):
        plan_dispatch("agent:ready", issue)


def test_multiple_risk_labels_do_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(
        _issue_mapping(labels=("agent:ready", "risk:low", "risk:medium")),
        "issue",
    )
    with pytest.raises(DispatchError, match="multiple risk:\\* labels: risk:low, risk:medium"):
        plan_dispatch("agent:ready", issue)


def test_missing_lifecycle_label_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(labels=("risk:low",)), "issue")
    with pytest.raises(DispatchError, match="has no lifecycle label"):
        plan_dispatch("agent:ready", issue)


def test_conflicting_lifecycle_labels_do_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(
        _issue_mapping(labels=("agent:ready", "agent:working", "risk:low")),
        "issue",
    )
    with pytest.raises(DispatchError, match="multiple lifecycle labels: agent:ready, agent:working"):
        plan_dispatch("agent:ready", issue)


def test_unexpected_lifecycle_label_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(labels=("needs:design", "risk:low")), "issue")
    with pytest.raises(DispatchError, match="lifecycle is needs:design"):
        plan_dispatch("agent:ready", issue)


def test_closed_issue_does_not_plan_dispatch() -> None:
    issue = dispatch_issue_from_mapping(_issue_mapping(state="closed"), "issue")
    with pytest.raises(DispatchError, match="is closed"):
        plan_dispatch("agent:ready", issue)


def test_prompt_contains_required_contract() -> None:
    issue_number = 18
    prompt = build_prompt(issue_number)
    assert f"Issue #{issue_number}" in prompt
    assert OWNER_REPO in prompt
    assert "AGENTS.md" in prompt
    assert "relevant repository documentation" in prompt
    assert "complete task specification" in prompt
    assert "Do not expand scope." in prompt
    assert "Do not mutate lifecycle or risk labels." in prompt
    assert "Draft Pull Request" in prompt
    assert f"`Closes #{issue_number}`" in prompt
    assert "Do not mark the PR ready for review" in prompt
    assert "Do not merge the PR." in prompt
    assert ISSUE_BODY_SECRET not in prompt


def test_agent_id_is_deterministic_and_issue_specific() -> None:
    first = build_agent_id(18)
    second = build_agent_id(18)
    other = build_agent_id(19)
    assert first == second
    assert first != other
    assert first.startswith("bc-")
    assert first == f"bc-{uuid.uuid5(uuid.NAMESPACE_URL, f'{REPOSITORY_URL}/issues/18')}"


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


def test_duplicate_cursor_conflict_is_already_dispatched() -> None:
    agent_id = build_agent_id(18)
    body = json.dumps({"error": {"code": AGENT_ID_CONFLICT, "message": SECRET}})
    result = interpret_cursor_create_response(18, agent_id, HttpResponse(409, body))
    assert result.outcome == "already_dispatched"
    assert result.agent_id == agent_id
    assert result.run_id is None
    assert "already dispatched" in result.message
    assert "not creating another agent" in result.message
    assert SECRET not in result.message


def test_unparseable_conflict_fails_closed_without_payload() -> None:
    with pytest.raises(DispatchError, match=r"Cursor API returned HTTP 409$") as exc_info:
        interpret_cursor_create_response(18, build_agent_id(18), HttpResponse(409, f"conflict {SECRET}"))
    assert SECRET not in str(exc_info.value)
    assert "already dispatched" not in str(exc_info.value)


def test_conflict_without_error_code_fails_closed_without_payload() -> None:
    with pytest.raises(DispatchError, match=r"Cursor API returned HTTP 409$") as exc_info:
        interpret_cursor_create_response(
            18,
            build_agent_id(18),
            HttpResponse(409, json.dumps({"error": {"message": SECRET}})),
        )
    assert SECRET not in str(exc_info.value)
    assert "already dispatched" not in str(exc_info.value)


def test_unexpected_conflict_code_fails_without_payload() -> None:
    with pytest.raises(DispatchError, match=r"Cursor API returned HTTP 409 \(agent_busy\)$") as exc_info:
        interpret_cursor_create_response(
            18,
            build_agent_id(18),
            HttpResponse(409, json.dumps({"error": {"code": "agent_busy", "message": SECRET}})),
        )
    assert SECRET not in str(exc_info.value)


def test_cursor_http_error_fails_without_payload() -> None:
    with pytest.raises(DispatchError, match=r"Cursor API returned HTTP 500$") as exc_info:
        interpret_cursor_create_response(18, build_agent_id(18), HttpResponse(500, json.dumps({"error": SECRET})))
    assert SECRET not in str(exc_info.value)


def test_submit_does_not_call_cursor_without_api_key() -> None:
    calls: list[tuple[str, dict[str, str], bytes]] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        calls.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    with pytest.raises(DispatchError, match="CURSOR_API_KEY is not set"):
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
    assert any(value.startswith("Basic ") for value in seen[0][1].values())
    assert SECRET not in "".join(seen[0][1].values())


def test_duplicate_submit_does_not_look_like_a_second_create() -> None:
    request = build_create_agent_request(18)
    statuses = [201, 409]
    outcomes: list[str] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        status = statuses.pop(0)
        if status == 201:
            return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-1"}}))
        return HttpResponse(409, json.dumps({"error": {"code": AGENT_ID_CONFLICT, "message": SECRET}}))

    first = submit_create_agent(18, request, SECRET, post=_post)
    second = submit_create_agent(18, request, SECRET, post=_post)
    outcomes.extend([first.outcome, second.outcome])
    assert outcomes == ["created", "already_dispatched"]
    assert first.agent_id == second.agent_id
    assert SECRET not in first.message
    assert SECRET not in second.message


def test_load_labeled_event(tmp_path: Path) -> None:
    event = load_labeled_issue_event(_event_file(tmp_path))
    assert event.added_label == "agent:ready"
    assert event.sender_type == "User"
    assert event.issue.number == 18
    assert event.issue.state == "open"
    assert event.issue.title == "Implement dispatch"
    assert ISSUE_BODY_SECRET in event.issue.body
    assert event.issue.is_pull_request is False
    assert "agent:ready" in event.issue.labels
    assert "risk:low" in event.issue.labels


def test_load_event_rejects_unsupported_action(tmp_path: Path) -> None:
    event = _event_file(tmp_path, action="unlabeled")
    with pytest.raises(DispatchError, match="not a supported issues labeled event"):
        load_labeled_issue_event(event)


def test_bot_sender_does_not_dispatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, sender_type="Bot")
    with pytest.raises(DispatchError, match=r"sender type is Bot; dispatch requires User"):
        load_labeled_issue_event(event)
    stdout = StringIO()
    assert main(["parse-event", "--event-file", str(event)], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "dispatch requires User" in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_bot_sender_error_omits_login(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "action": "labeled",
                "label": {"name": "agent:ready"},
                "sender": {"type": "Bot", "login": SECRET},
                "issue": _issue_mapping(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DispatchError, match=r"sender type is Bot; dispatch requires User") as exc_info:
        load_labeled_issue_event(path)
    assert SECRET not in str(exc_info.value)


def test_missing_sender_does_not_dispatch(tmp_path: Path) -> None:
    event = _event_file(tmp_path, sender_type=None)
    with pytest.raises(DispatchError, match="sender is missing"):
        load_labeled_issue_event(event)


def test_cli_plan_and_parse_event(tmp_path: Path) -> None:
    event = _event_file(tmp_path)
    stdout = StringIO()
    assert main(["parse-event", "--event-file", str(event)], stdout=stdout) == 0
    assert stdout.getvalue() == "18\n"

    stdout = StringIO()
    assert (
        main(
            ["plan", "--event-file", str(event), "--issue-json", _issue_json()],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["issue_number"] == 18
    assert plan["request"]["autoCreatePR"] is False
    assert plan["request"]["repos"][0]["startingRef"] == "main"
    assert "model" not in plan["request"]
    assert ISSUE_BODY_SECRET not in stdout.getvalue()
    assert SECRET not in stdout.getvalue()


def test_cli_plan_rejects_pull_request_without_calling_cursor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path, issue=_issue_mapping(pull_request=True))
    stdout = StringIO()
    assert (
        main(
            ["plan", "--event-file", str(event), "--issue-json", _issue_json(pull_request=True)],
            stdout=stdout,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "pull request" in captured.err
    assert ISSUE_BODY_SECRET not in captured.err


def test_cli_parse_event_rejects_other_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, added_label="risk:low")
    stdout = StringIO()
    assert main(["parse-event", "--event-file", str(event)], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "agent:ready" in captured.err


def test_cli_submit_created(monkeypatch: pytest.MonkeyPatch) -> None:
    request = build_create_agent_request(18)

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers, body
        return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-9"}}))

    monkeypatch.setattr(agent_dispatch, "_post_json", _post)
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


def test_cli_dispatch_uses_rest_issue_and_posts_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event_file(tmp_path)
    request = build_create_agent_request(18)
    api = _ScriptedGitHubApi([_ok_issue()])
    posts: list[bytes] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        del url, headers
        posts.append(body)
        return HttpResponse(201, json.dumps({"agent": {"id": request["agentId"]}, "run": {"id": "run-2"}}))

    monkeypatch.setattr(agent_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_dispatch, "_post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--event-file", str(event), "--repo", "owner/repo"], stdout=stdout) == 0
    result = json.loads(stdout.getvalue())
    assert result["outcome"] == "created"
    assert api.paths == ["repos/owner/repo/issues/18"]
    assert json.loads(posts[0].decode("utf-8")) == request
    assert ISSUE_BODY_SECRET not in stdout.getvalue()
    assert SECRET not in stdout.getvalue()


def test_cli_dispatch_does_not_post_when_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path)
    api = _ScriptedGitHubApi([_ok_issue(labels=("agent:ready",))])
    posts: list[object] = []

    def _post(url: str, headers: dict[str, str], body: bytes) -> HttpResponse:
        posts.append((url, headers, body))
        raise AssertionError("Cursor API must not be called")

    monkeypatch.setattr(agent_dispatch, "_run_gh_api", api)
    monkeypatch.setattr(agent_dispatch, "_post_json", _post)
    monkeypatch.setenv("CURSOR_API_KEY", SECRET)
    stdout = StringIO()
    assert main(["dispatch", "--event-file", str(event), "--repo", "owner/repo"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert posts == []
    assert "no risk:* label" in captured.err
    assert SECRET not in captured.err


def test_rest_read_retries_503_then_succeeds() -> None:
    api = _ScriptedGitHubApi([_http_error(503, body=SECRET), _ok_issue()])
    issue = read_dispatch_issue("owner/repo", 18, run_api=api, sleep=api.sleep, notify=api.notify)
    assert issue.number == 18
    assert issue.labels == ("agent:ready", "risk:low")
    assert api.paths == ["repos/owner/repo/issues/18", "repos/owner/repo/issues/18"]
    assert SECRET not in "".join(api.notes)


def test_rest_read_failure_does_not_plan_dispatch() -> None:
    api = _ScriptedGitHubApi([_http_error(404, body=SECRET)])
    with pytest.raises(DispatchError, match="HTTP 404") as exc_info:
        read_dispatch_issue("owner/repo", 18, run_api=api, sleep=api.sleep)
    assert SECRET not in str(exc_info.value)


def test_default_runner_uses_gh_api_rest_path(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        recorded.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=_issue_json(), stderr="")

    monkeypatch.setattr(agent_dispatch.subprocess, "run", _fake_run)
    issue = read_dispatch_issue("owner/repo", 18, sleep=lambda _: None)
    assert recorded == [["gh", "api", "repos/owner/repo/issues/18"]]
    assert issue.number == 18


def test_workflow_is_dedicated_and_least_privilege() -> None:
    workflow = Path(".github/workflows/agent-dispatch.yml").read_text(encoding="utf-8")
    lifecycle = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "on:\n  issues:" in workflow
    assert "labeled" in workflow
    assert "github.event.label.name == 'agent:ready'" in workflow
    assert "github.event.sender.type == 'User'" in workflow
    assert "secrets.CURSOR_API_KEY" in workflow
    assert "api.cursor.com" not in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "agent_dispatch.py dispatch" in workflow
    assert "CURSOR_API_KEY" not in lifecycle
    assert "agent-dispatch" not in lifecycle
    assert "api.cursor.com" not in lifecycle
    assert "CURSOR_API_KEY" not in ci
    assert "agent-dispatch" not in ci
    assert "labeled" not in lifecycle


def test_lifecycle_semantics_file_still_plans_ready_to_working() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ())
    assert plan.issue_add == ("agent:working",)
    assert plan.issue_remove == ("agent:ready",)
    assert "agent:ready" not in plan.issue_add


def test_cli_rejects_invalid_event_json_without_contents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "event.json"
    path.write_text(f'{{"prompt": "{SECRET}"', encoding="utf-8")
    stdout = StringIO()
    assert main(["parse-event", "--event-file", str(path)], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert SECRET not in captured.err
    assert "prompt" not in captured.err


def test_bool_issue_number_is_rejected() -> None:
    payload = _issue_mapping()
    payload["number"] = True
    with pytest.raises(DispatchError, match="positive integer"):
        dispatch_issue_from_mapping(payload, "issue")


def test_null_issue_body_is_empty_string() -> None:
    payload = _issue_mapping()
    payload["body"] = None
    issue = dispatch_issue_from_mapping(payload, "issue")
    assert issue.body == ""
    assert issue.title == "Implement dispatch"
