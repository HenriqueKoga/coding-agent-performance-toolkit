import json
from io import StringIO
from pathlib import Path

import pytest

import agent_lifecycle
from agent_lifecycle import LifecycleError, LifecyclePlan, main, parse_linked_issue_number, plan_lifecycle

SECRET = "developer@example.invalid"


def _event_file(tmp_path: Path, action: str, body: str, *, draft: bool = False) -> Path:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "action": action,
                "pull_request": {"number": 9, "body": body, "labels": [], "draft": draft},
            }
        ),
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


def test_load_event_maps_synchronize_using_draft_state(tmp_path: Path) -> None:
    draft = _event_file(tmp_path, "synchronize", "Closes #8\n", draft=True)
    assert agent_lifecycle.load_pull_request_event(draft).action == "opened"
    ready = tmp_path / "ready.json"
    ready.write_text(
        json.dumps(
            {
                "action": "synchronize",
                "pull_request": {"number": 9, "body": "Closes #8\n", "labels": [], "draft": False},
            }
        ),
        encoding="utf-8",
    )
    assert agent_lifecycle.load_pull_request_event(ready).action == "ready_for_review"


def test_load_event_rejects_unsupported_action(tmp_path: Path) -> None:
    event = _event_file(tmp_path, "edited", "Closes #8\n")
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


def test_ready_for_review_without_lifecycle_label_adds_human_review() -> None:
    plan = plan_lifecycle("ready_for_review", 10, ("risk:low",), ())
    assert plan.issue_add == ("needs:human-review",)
    assert plan.issue_remove == ()
    assert plan.pr_add == ("risk:low",)
    assert "agent:ready" not in plan.issue_add


def test_multiple_pr_risk_labels_do_not_plan_mutation() -> None:
    with pytest.raises(LifecycleError, match="pull request has multiple risk:\\* labels"):
        plan_lifecycle("opened", 8, ("agent:ready", "risk:low"), ("risk:low", "risk:high"))


def test_parse_accepts_crlf_and_surrounding_whitespace() -> None:
    assert parse_linked_issue_number("## Linked task\r\n\r\n  Closes #12  \r\n") == 12


def test_cli_ready_for_review_with_only_risk_label(tmp_path: Path) -> None:
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
    assert plan["issue_add"] == ["needs:human-review"]
    assert plan["issue_remove"] == []
    assert plan["pr_add"] == ["risk:low"]
    assert plan["noop"] is False


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
