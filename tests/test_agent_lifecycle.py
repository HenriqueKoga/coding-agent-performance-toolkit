import json
import subprocess
from io import StringIO
from pathlib import Path

import pytest

import agent_lifecycle
from agent_lifecycle import (
    GitHubApiResponse,
    LifecycleError,
    LifecyclePlan,
    github_http_status_from_stderr,
    is_retryable_github_http_status,
    main,
    parse_linked_issue_number,
    plan_lifecycle,
    read_issue_label_names,
)

SECRET = "developer@example.invalid"


def _event_file(tmp_path: Path, action: str, body: str) -> Path:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps({"action": action, "pull_request": {"number": 9, "body": body, "labels": []}}),
        encoding="utf-8",
    )
    return path


def test_parse_closes_line_from_template() -> None:
    body = "## Linked task\n\nCloses #8\n\n## Summary\n"
    assert parse_linked_issue_number(body) == 8


def test_parse_closes_line_is_idempotent_for_duplicate_same_issue() -> None:
    assert parse_linked_issue_number("Closes #10\nCloses #10\n") == 10


def test_parse_rejects_missing_link_without_body() -> None:
    with pytest.raises(LifecycleError, match="does not contain a supported Closes") as exc_info:
        parse_linked_issue_number(f"## Summary\nsecret {SECRET}\nFixes #8\ncloses #8\nCloses: #8\n")
    assert SECRET not in str(exc_info.value)
    assert "Fixes" not in str(exc_info.value)


def test_parse_rejects_placeholder_and_zero() -> None:
    with pytest.raises(LifecycleError, match="does not contain a supported Closes"):
        parse_linked_issue_number("Closes #\nCloses #0\n")


def test_parse_rejects_ambiguous_links() -> None:
    with pytest.raises(LifecycleError, match="multiple Closes #<issue> links: #8, #10") as exc_info:
        parse_linked_issue_number("Closes #8\nCloses #10\n")
    assert SECRET not in str(exc_info.value)


def test_parse_ignores_inline_and_natural_language_references() -> None:
    with pytest.raises(LifecycleError, match="does not contain a supported Closes"):
        parse_linked_issue_number("This Closes #8 in passing.\nSee issue 8.\n")


def test_opened_ready_issue_moves_to_working_and_copies_risk() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ())
    assert plan == LifecyclePlan(
        issue_number=8,
        issue_add=("agent:working",),
        issue_remove=("agent:ready",),
        pr_add=("risk:low",),
        message="Issue #8 agent:ready -> agent:working; copy risk:low to the pull request",
    )
    assert "agent:ready" not in plan.issue_add


def test_ready_for_review_moves_working_issue_to_human_review() -> None:
    plan = plan_lifecycle("ready_for_review", 8, ("agent:working", "risk:low"), ("risk:low",))
    assert plan.issue_add == ("needs:human-review",)
    assert plan.issue_remove == ("agent:working",)
    assert plan.pr_add == ()
    assert plan.noop is False


def test_opened_without_risk_does_not_plan_mutation() -> None:
    with pytest.raises(LifecycleError, match="Issue #8 has no risk:\\* label"):
        plan_lifecycle("opened", 8, ("agent:ready",), ())


def test_opened_with_multiple_risks_does_not_plan_mutation() -> None:
    with pytest.raises(LifecycleError, match="multiple risk:\\* labels: risk:low, risk:medium"):
        plan_lifecycle("opened", 8, ("agent:ready", "risk:low", "risk:medium"), ())


def test_unexpected_lifecycle_state_does_not_plan_mutation() -> None:
    opened = plan_lifecycle("opened", 8, ("needs:design", "risk:low"), ())
    assert opened.noop is True
    assert "needs:design" in opened.message
    ready = plan_lifecycle("ready_for_review", 8, ("agent:ready", "risk:low"), ())
    assert ready.noop is True
    assert "agent:ready" in ready.message
    with pytest.raises(LifecycleError, match="multiple lifecycle labels: needs:human-review, agent:ready"):
        plan_lifecycle("opened", 8, ("agent:ready", "needs:human-review", "risk:low"), ())


def test_retried_opened_event_is_idempotent() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:working", "risk:low"), ("risk:low",))
    assert plan.noop is True
    assert plan.issue_add == ()
    assert plan.issue_remove == ()
    assert plan.pr_add == ()
    assert "agent:ready" not in plan.issue_add


def test_retried_opened_event_completes_missing_pr_risk_copy() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:working", "risk:low"), ())
    assert plan.issue_add == ()
    assert plan.issue_remove == ()
    assert plan.pr_add == ("risk:low",)


def test_retried_ready_for_review_event_is_idempotent() -> None:
    plan = plan_lifecycle("ready_for_review", 8, ("needs:human-review", "risk:medium"), ("risk:medium",))
    assert plan.noop is True
    assert plan.pr_add == ()
    assert "agent:ready" not in plan.issue_add


def test_ready_for_review_does_not_change_existing_pr_risk() -> None:
    plan = plan_lifecycle("ready_for_review", 8, ("agent:working", "risk:high"), ("risk:high",))
    assert plan.pr_add == ()
    assert "risk:high" in plan.message


def test_conflicting_pr_risk_does_not_plan_mutation() -> None:
    with pytest.raises(LifecycleError, match="already has risk:high; refusing to replace"):
        plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ("risk:high",))


def test_cli_parse_link_and_plan(tmp_path: Path) -> None:
    event = _event_file(tmp_path, "opened", f"## Linked task\n\nCloses #8\n\nsecret {SECRET}\n")
    stdout = StringIO()
    assert main(["parse-link", "--event-file", str(event)], stdout=stdout) == 0
    assert stdout.getvalue() == "8\n"

    stdout = StringIO()
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--issue-labels-json",
                '["agent:ready", "risk:low"]',
                "--pr-labels-json",
                "[]",
            ],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["issue_number"] == 8
    assert plan["issue_add"] == ["agent:working"]
    assert plan["issue_remove"] == ["agent:ready"]
    assert plan["pr_add"] == ["risk:low"]
    assert plan["noop"] is False
    assert SECRET not in stdout.getvalue()


def test_cli_missing_link_fails_without_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, "opened", f"secret {SECRET}\n")
    assert main(["parse-link", "--event-file", str(event)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert SECRET not in captured.err


def test_cli_rejects_invalid_event_json_without_contents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "event.json"
    path.write_text(f'{{"prompt": "{SECRET}"', encoding="utf-8")
    assert main(["parse-link", "--event-file", str(path)]) == 1
    captured = capsys.readouterr()
    assert SECRET not in captured.err
    assert "prompt" not in captured.err


def test_cli_rejects_invalid_label_json_without_contents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, "opened", "Closes #8\n")
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--issue-labels-json",
                f'{{"token": "{SECRET}"',
                "--pr-labels-json",
                "[]",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert SECRET not in captured.err


def test_load_event_null_body_has_no_link(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"action": "opened", "pull_request": {"body": None}}), encoding="utf-8")
    event = agent_lifecycle.load_pull_request_event(path)
    with pytest.raises(LifecycleError, match="does not contain a supported Closes"):
        parse_linked_issue_number(event.body)


def test_load_event_rejects_unsupported_action(tmp_path: Path) -> None:
    event = _event_file(tmp_path, "synchronize", "Closes #8\n")
    with pytest.raises(LifecycleError, match="not a supported pull_request lifecycle event"):
        agent_lifecycle.load_pull_request_event(event)


def test_plan_json_never_adds_agent_ready() -> None:
    plan = plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ())
    assert "agent:ready" not in plan.issue_add
    assert plan.to_json_dict()["issue_add"] == ["agent:working"]


def test_cli_refuses_plan_that_adds_agent_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event_file(tmp_path, "opened", "Closes #8\n")

    def _bad_plan(
        action: object,
        issue_number: int,
        issue_labels: object,
        pr_labels: object,
    ) -> LifecyclePlan:
        del action, issue_labels, pr_labels
        return LifecyclePlan(issue_number, ("agent:ready",), (), (), "bad")

    monkeypatch.setattr(agent_lifecycle, "plan_lifecycle", _bad_plan)
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--issue-labels-json",
                '["agent:ready", "risk:low"]',
                "--pr-labels-json",
                "[]",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refusing to add agent:ready automatically" in captured.err


def test_opened_without_lifecycle_label_does_not_plan_mutation() -> None:
    plan = plan_lifecycle("opened", 8, ("risk:low",), ())
    assert plan.noop is True
    assert "absent" in plan.message
    assert plan.issue_add == ()


def test_ready_for_review_without_lifecycle_label_does_not_plan_mutation() -> None:
    plan = plan_lifecycle("ready_for_review", 10, ("risk:low",), ())
    assert plan.noop is True
    assert plan.issue_add == ()
    assert plan.issue_remove == ()
    assert plan.pr_add == ()
    assert "absent" in plan.message
    assert "agent:working" in plan.message


def test_multiple_pr_risk_labels_do_not_plan_mutation() -> None:
    with pytest.raises(LifecycleError, match="pull request has multiple risk:\\* labels"):
        plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ("risk:low", "risk:high"))


def test_parse_accepts_crlf_and_surrounding_whitespace() -> None:
    assert parse_linked_issue_number("## Linked task\r\n\r\n  Closes #12  \r\n") == 12


def test_cli_ready_for_review_without_lifecycle_is_noop(tmp_path: Path) -> None:
    event = _event_file(tmp_path, "ready_for_review", "Closes #10\n")
    stdout = StringIO()
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--issue-labels-json",
                '["risk:low"]',
                "--pr-labels-json",
                "[]",
            ],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["issue_add"] == []
    assert plan["issue_remove"] == []
    assert plan["pr_add"] == []
    assert plan["noop"] is True
    assert "absent" in plan["message"]


def test_cli_rejects_non_string_label_items(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, "ready_for_review", "Closes #8\n")
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--issue-labels-json",
                "[1]",
                "--pr-labels-json",
                "[]",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "JSON array of strings" in captured.err


def test_load_event_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(LifecycleError, match="must be a JSON object"):
        agent_lifecycle.load_pull_request_event(path)


def test_load_event_rejects_non_string_body(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"action": "opened", "pull_request": {"body": 12}}), encoding="utf-8")
    with pytest.raises(LifecycleError, match="pull request body is not a string"):
        agent_lifecycle.load_pull_request_event(path)


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


def _issue_payload(*names: str) -> str:
    return json.dumps({"number": 8, "labels": [{"name": name, "color": "ededed"} for name in names]})


def _ok_response(*names: str) -> GitHubApiResponse:
    return GitHubApiResponse(returncode=0, stdout=_issue_payload(*names), stderr="")


def _http_error(status: int, body: str = "") -> GitHubApiResponse:
    return GitHubApiResponse(
        returncode=1,
        stdout=body,
        stderr=f"gh: HTTP {status}: Server Error (https://api.github.com/repos/owner/repo/issues/8)",
    )


def _read_labels(api: _ScriptedGitHubApi, issue_number: int = 8) -> tuple[str, ...]:
    return read_issue_label_names(
        "owner/repo",
        issue_number,
        run_api=api,
        sleep=api.sleep,
        notify=api.notify,
    )


def test_retryable_github_http_status_is_only_transient_5xx() -> None:
    for status in (500, 502, 503, 504):
        assert is_retryable_github_http_status(status) is True
    for status in (None, 200, 400, 401, 403, 404, 408, 409, 422, 429, 501):
        assert is_retryable_github_http_status(status) is False


def test_github_http_status_from_stderr_ignores_payload() -> None:
    stderr = f"gh: HTTP 503: Server Error payload {SECRET}\n"
    assert github_http_status_from_stderr(stderr) == 503
    assert github_http_status_from_stderr("") is None
    assert github_http_status_from_stderr(f"payload {SECRET}") is None


def test_rest_read_succeeds_first_try() -> None:
    api = _ScriptedGitHubApi([_ok_response("agent:ready", "risk:low")])
    labels = _read_labels(api)
    assert labels == ("agent:ready", "risk:low")
    assert api.paths == ["repos/owner/repo/issues/8"]
    assert api.sleeps == []
    assert api.notes == []


def test_rest_read_retries_503_then_succeeds() -> None:
    api = _ScriptedGitHubApi(
        [
            _http_error(503, body=SECRET),
            _ok_response("agent:ready", "risk:low"),
        ]
    )
    labels = _read_labels(api)
    assert labels == ("agent:ready", "risk:low")
    assert api.paths == ["repos/owner/repo/issues/8", "repos/owner/repo/issues/8"]
    assert api.sleeps == [agent_lifecycle.GITHUB_REST_READ_RETRY_DELAY_SECONDS]
    assert api.notes == [
        "GitHub REST issue #8 read returned HTTP 503 "
        f"(attempt 1/{agent_lifecycle.GITHUB_REST_READ_MAX_ATTEMPTS}); retrying"
    ]
    assert SECRET not in "".join(api.notes)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_rest_read_exhausts_retryable_status(status: int) -> None:
    attempts = agent_lifecycle.GITHUB_REST_READ_MAX_ATTEMPTS
    api = _ScriptedGitHubApi([_http_error(status, body=SECRET)] * attempts)
    with pytest.raises(
        LifecycleError,
        match=f"GitHub REST issue #8 read failed with HTTP {status} after {attempts} attempts",
    ) as exc_info:
        _read_labels(api)
    assert len(api.paths) == attempts
    assert api.sleeps == [agent_lifecycle.GITHUB_REST_READ_RETRY_DELAY_SECONDS] * (attempts - 1)
    assert SECRET not in str(exc_info.value)
    assert "retrying" not in str(exc_info.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
def test_rest_read_non_retryable_status_fails_immediately(status: int) -> None:
    api = _ScriptedGitHubApi([_http_error(status, body=SECRET), _ok_response("agent:ready", "risk:low")])
    with pytest.raises(LifecycleError, match=rf"GitHub REST issue #8 read failed with HTTP {status}$") as exc_info:
        _read_labels(api)
    assert api.paths == ["repos/owner/repo/issues/8"]
    assert api.sleeps == []
    assert api.notes == []
    assert SECRET not in str(exc_info.value)
    assert "after" not in str(exc_info.value)


def test_rest_read_unknown_failure_fails_immediately() -> None:
    api = _ScriptedGitHubApi([GitHubApiResponse(returncode=1, stdout=SECRET, stderr=f"gh crashed {SECRET}")])
    with pytest.raises(LifecycleError, match=r"GitHub REST issue #8 read failed after 1 attempt$") as exc_info:
        _read_labels(api)
    assert api.paths == ["repos/owner/repo/issues/8"]
    assert api.sleeps == []
    assert SECRET not in str(exc_info.value)


def test_rest_labels_feed_existing_planner_unchanged() -> None:
    api = _ScriptedGitHubApi([_ok_response("agent:ready", "risk:low")])
    labels = _read_labels(api)
    plan = plan_lifecycle("opened", 8, labels, ())
    assert plan.issue_add == ("agent:working",)
    assert plan.issue_remove == ("agent:ready",)
    assert plan.pr_add == ("risk:low",)
    assert "agent:ready" not in plan.issue_add


def test_rest_read_failure_does_not_plan_mutation() -> None:
    api = _ScriptedGitHubApi([_http_error(404)])
    with pytest.raises(LifecycleError, match="HTTP 404"):
        _read_labels(api)


def test_default_runner_uses_gh_api_rest_path(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        recorded.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=_issue_payload("agent:ready", "risk:low"), stderr="")

    monkeypatch.setattr(agent_lifecycle.subprocess, "run", _fake_run)
    labels = read_issue_label_names("owner/repo", 8, sleep=lambda _: None)
    assert recorded == [["gh", "api", "repos/owner/repo/issues/8"]]
    assert labels == ("agent:ready", "risk:low")


def test_gh_unavailable_fails_immediately_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise OSError("gh missing")

    monkeypatch.setattr(agent_lifecycle.subprocess, "run", _raise_os_error)
    sleeps: list[float] = []
    with pytest.raises(LifecycleError, match="GitHub CLI is not available for REST issue read"):
        read_issue_label_names("owner/repo", 8, sleep=sleeps.append)
    assert sleeps == []


def test_cli_read_issue_labels_prints_planner_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_read(repository: str, issue_number: int, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        assert repository == "owner/repo"
        assert issue_number == 8
        return ("agent:ready", "risk:low")

    monkeypatch.setattr(agent_lifecycle, "read_issue_label_names", _fake_read)
    stdout = StringIO()
    assert main(["read-issue-labels", "--issue", "8", "--repo", "owner/repo"], stdout=stdout) == 0
    assert json.loads(stdout.getvalue()) == ["agent:ready", "risk:low"]
    assert SECRET not in stdout.getvalue()


def test_cli_read_issue_labels_uses_gh_repo_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, int]] = []

    def _fake_read(repository: str, issue_number: int, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        seen.append((repository, issue_number))
        return ("risk:low",)

    monkeypatch.setattr(agent_lifecycle, "read_issue_label_names", _fake_read)
    monkeypatch.setenv("GH_REPO", "owner/repo")
    stdout = StringIO()
    assert main(["read-issue-labels", "--issue", "8"], stdout=stdout) == 0
    assert seen == [("owner/repo", 8)]
    assert json.loads(stdout.getvalue()) == ["risk:low"]


def test_cli_read_issue_labels_failure_prints_no_labels(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail(repository: str, issue_number: int, **kwargs: object) -> tuple[str, ...]:
        del repository, issue_number, kwargs
        raise LifecycleError("GitHub REST issue #8 read failed with HTTP 503 after 3 attempts")

    monkeypatch.setattr(agent_lifecycle, "read_issue_label_names", _fail)
    stdout = StringIO()
    assert main(["read-issue-labels", "--issue", "8", "--repo", "owner/repo"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert captured.out == ""
    assert "HTTP 503" in captured.err
    assert "after 3 attempts" in captured.err
    assert SECRET not in captured.err


def test_cli_read_issue_labels_rejects_missing_repo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GH_REPO", raising=False)
    stdout = StringIO()
    assert main(["read-issue-labels", "--issue", "8"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "GH_REPO is not set" in captured.err


def test_rest_read_rejects_invalid_repository_before_calling_api() -> None:
    api = _ScriptedGitHubApi([_ok_response("risk:low")])
    with pytest.raises(LifecycleError, match="GitHub repository must be owner/repo"):
        read_issue_label_names("owner", 8, run_api=api, sleep=api.sleep)
    assert api.paths == []


def test_rest_read_rejects_invalid_success_payload_without_retry() -> None:
    api = _ScriptedGitHubApi([GitHubApiResponse(returncode=0, stdout=f'{{"message": "{SECRET}"}}', stderr="")])
    with pytest.raises(LifecycleError, match="missing labels") as exc_info:
        _read_labels(api)
    assert api.paths == ["repos/owner/repo/issues/8"]
    assert api.sleeps == []
    assert SECRET not in str(exc_info.value)


def test_workflow_uses_rest_issue_read_not_graphql() -> None:
    workflow = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    assert "gh issue view" not in workflow
    assert "read-issue-labels" in workflow
    assert "graphql" not in workflow.lower()
    assert "synchronize" not in workflow
