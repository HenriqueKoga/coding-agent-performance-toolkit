import json
from collections.abc import Sequence
from io import StringIO
from pathlib import Path

import pytest

import agent_spec
from agent_lifecycle import (
    LIFECYCLE_OPT_OUT_MARKER,
    GitHubApiResponse,
    LifecycleError,
    has_lifecycle_opt_out,
    parse_linked_issue_number,
)
from agent_spec import (
    AGENT_READY,
    CANONICAL_ARTIFACTS,
    GITHUB_ACTIONS_BOT_LOGIN,
    GITHUB_ACTIONS_BOT_TYPE,
    NEEDS_DESIGN,
    NEEDS_HUMAN_REVIEW,
    SpecApprovalError,
    SpecMetadata,
    apply_comment,
    apply_issue_labels,
    build_approved_comment,
    classify_spec_event,
    comments_from_mapping,
    load_merged_pull_request_event,
    main,
    parse_approved_spec,
    parse_spec_metadata,
    plan_spec_handoff,
    read_issue_comments,
    related_issue_numbers,
    require_related_issue_agreement,
    resolve_approved_spec,
    skipped_plan,
    validate_canonical_artifacts,
)

SECRET = "developer@example.invalid"
SPEC_PATH = "specs/004-persist-handoff-safely/spec.md"
FEATURE_DIR = "specs/004-persist-handoff-safely"


def _spec_body(
    *,
    issue: str = "58",
    spec: str = SPEC_PATH,
    related: str | None = "Related to #58",
    extra_block: str = "",
    opt_out: bool = True,
) -> str:
    opt_out_line = f"{LIFECYCLE_OPT_OUT_MARKER}\n" if opt_out else ""
    related_line = f"{related}\n" if related is not None else ""
    extra = f"\n{extra_block}\n" if extra_block else ""
    return (
        "## Linked task\n\n"
        f"{opt_out_line}"
        f"<!-- capt-spec:v1\n"
        f"issue: {issue}\n"
        f"spec: {spec}\n"
        "-->\n"
        f"{extra}"
        f"{related_line}"
        f"secret {SECRET}\n"
    )


def _event_file(
    tmp_path: Path,
    body: str,
    *,
    action: str = "closed",
    number: int = 56,
    merged: bool = True,
    base_ref: str = "main",
) -> Path:
    path = tmp_path / "event.json"
    payload: dict[str, object] = {
        "action": action,
        "pull_request": {
            "number": number,
            "merged": merged,
            "body": body,
            "base": {"ref": base_ref},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_artifacts(root: Path, spec_path: str = SPEC_PATH) -> None:
    feature_dir = root / Path(spec_path).parent
    feature_dir.mkdir(parents=True, exist_ok=True)
    for name in CANONICAL_ARTIFACTS:
        (feature_dir / name).write_text(f"# synthetic {name}\n", encoding="utf-8")


def _approved_comment(issue_number: int = 58, pull_request_number: int = 56, spec: str = SPEC_PATH) -> str:
    return build_approved_comment(SpecMetadata(issue_number=issue_number, spec_path=spec), pull_request_number)


def _comment_payload(
    comment_id: int,
    body: str,
    *,
    login: str = GITHUB_ACTIONS_BOT_LOGIN,
    user_type: str = GITHUB_ACTIONS_BOT_TYPE,
) -> dict[str, object]:
    return {"id": comment_id, "user": {"login": login, "type": user_type}, "body": body}


class _ScriptedGitHubApi:
    def __init__(self, responses: list[GitHubApiResponse]) -> None:
        self._responses = responses
        self.paths: list[str] = []
        self.writes: list[tuple[str, str, str]] = []
        self.commands: list[tuple[str, ...]] = []
        self.sleeps: list[float] = []
        self.notes: list[str] = []

    def __call__(self, path: str) -> GitHubApiResponse:
        self.paths.append(path)
        return self._responses[len(self.paths) - 1]

    def write(self, method: str, path: str, body: str) -> GitHubApiResponse:
        self.writes.append((method, path, body))
        return GitHubApiResponse(returncode=0, stdout="{}", stderr="")

    def command(self, args: Sequence[str]) -> GitHubApiResponse:
        self.commands.append(tuple(args))
        return GitHubApiResponse(returncode=0, stdout="", stderr="")

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def notify(self, message: str) -> None:
        self.notes.append(message)


def test_valid_capt_spec_metadata_is_parsed() -> None:
    metadata = parse_spec_metadata(_spec_body())
    assert metadata == SpecMetadata(issue_number=58, spec_path=SPEC_PATH)
    assert metadata.feature_dir == FEATURE_DIR
    assert metadata.artifact_path("plan.md") == f"{FEATURE_DIR}/plan.md"


def test_capt_spec_coexists_with_lifecycle_opt_out_and_related_to() -> None:
    body = _spec_body()
    assert has_lifecycle_opt_out(body) is True
    with pytest.raises(LifecycleError, match="opts out of Agent Task lifecycle"):
        parse_linked_issue_number(body)
    metadata = parse_spec_metadata(body)
    assert metadata is not None
    require_related_issue_agreement(body, metadata)
    assert related_issue_numbers(body) == (58,)
    assert SECRET not in metadata.spec_path


def test_missing_capt_spec_metadata_is_none_and_does_not_infer_specs() -> None:
    body = f"{LIFECYCLE_OPT_OUT_MARKER}\nRelated to #36\nSee specs/002-trace-summary-comparison/spec.md\n"
    assert parse_spec_metadata(body) is None
    assert related_issue_numbers(body) == (36,)


def test_duplicate_metadata_blocks_fail_closed() -> None:
    body = _spec_body(extra_block=("<!-- capt-spec:v1\nissue: 58\nspec: specs/004-persist-handoff-safely/spec.md\n-->"))
    with pytest.raises(SpecApprovalError, match="duplicate capt-spec metadata") as exc_info:
        parse_spec_metadata(body)
    assert SECRET not in str(exc_info.value)
    assert "58" not in str(exc_info.value)


def test_malformed_and_unsupported_versions_fail_closed() -> None:
    for version in ("", "v2", "V1", "v1 extra", "1"):
        body = f"{LIFECYCLE_OPT_OUT_MARKER}\n<!-- capt-spec:{version}\nissue: 58\nspec: {SPEC_PATH}\n-->\n"
        with pytest.raises(SpecApprovalError, match="unsupported or malformed capt-spec"):
            parse_spec_metadata(body)


def test_missing_invalid_and_conflicting_fields_fail_closed() -> None:
    with pytest.raises(SpecApprovalError, match="missing required capt-spec metadata fields"):
        parse_spec_metadata("<!-- capt-spec:v1\nissue: 58\n-->\n")
    with pytest.raises(SpecApprovalError, match="capt-spec issue is missing or invalid"):
        parse_spec_metadata(f"<!-- capt-spec:v1\nissue: 0\nspec: {SPEC_PATH}\n-->\n")
    with pytest.raises(SpecApprovalError, match="capt-spec issue is missing or invalid"):
        parse_spec_metadata(f"<!-- capt-spec:v1\nissue: #58\nspec: {SPEC_PATH}\n-->\n")
    with pytest.raises(SpecApprovalError, match="unsupported capt-spec metadata fields"):
        parse_spec_metadata(f"<!-- capt-spec:v1\nissue: 58\nspec: {SPEC_PATH}\nowner: capt\n-->\n")
    with pytest.raises(SpecApprovalError, match="conflicting fields"):
        parse_spec_metadata(f"<!-- capt-spec:v1\nissue: 58\nissue: 59\nspec: {SPEC_PATH}\n-->\n")


def test_inline_or_backticked_metadata_is_ignored() -> None:
    body = (
        f"Use `<!-- capt-spec:v1` on its own lines.\n"
        f"Do not write <!-- capt-spec:v1 issue: 58 spec: {SPEC_PATH} --> inline.\n"
        f"{LIFECYCLE_OPT_OUT_MARKER}\nRelated to #58\n"
    )
    assert parse_spec_metadata(body) is None


def test_related_issue_mismatch_fails_closed() -> None:
    body = _spec_body(related="Related to #36")
    metadata = parse_spec_metadata(body)
    assert metadata is not None
    with pytest.raises(SpecApprovalError, match="does not match Related to"):
        require_related_issue_agreement(body, metadata)


def test_multiple_related_issue_links_fail_when_metadata_is_present() -> None:
    body = _spec_body(related="Related to #58\nRelated to #36")
    metadata = parse_spec_metadata(body)
    assert metadata is not None
    with pytest.raises(SpecApprovalError, match="multiple Related to"):
        require_related_issue_agreement(body, metadata)


def test_invalid_spec_paths_fail_closed() -> None:
    for spec in (
        "spec.md",
        "docs/spec.md",
        "specs/spec.md",
        "specs/004-persist-handoff-safely/plan.md",
        "specs/004-persist-handoff-safely/nested/spec.md",
        "/specs/004-persist-handoff-safely/spec.md",
        "specs/../secret/spec.md",
        "specs\\\\004-persist-handoff-safely\\\\spec.md",
        "SPECS/004-persist-handoff-safely/spec.md",
    ):
        with pytest.raises(SpecApprovalError, match=r"canonical specs/<feature>/spec.md path"):
            parse_spec_metadata(_spec_body(spec=spec))


def test_missing_canonical_artifacts_fail_closed(tmp_path: Path) -> None:
    metadata = SpecMetadata(issue_number=58, spec_path=SPEC_PATH)
    feature_dir = tmp_path / FEATURE_DIR
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
    (feature_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    with pytest.raises(SpecApprovalError, match="missing required canonical artifacts"):
        validate_canonical_artifacts(tmp_path, metadata)


def test_symlink_artifacts_are_rejected(tmp_path: Path) -> None:
    metadata = SpecMetadata(issue_number=58, spec_path=SPEC_PATH)
    _write_artifacts(tmp_path)
    analyze = tmp_path / FEATURE_DIR / "analyze.md"
    analyze.unlink()
    analyze.symlink_to(tmp_path / FEATURE_DIR / "spec.md")
    with pytest.raises(SpecApprovalError, match="missing required canonical artifacts"):
        validate_canonical_artifacts(tmp_path, metadata)


def test_valid_artifacts_pass(tmp_path: Path) -> None:
    metadata = SpecMetadata(issue_number=58, spec_path=SPEC_PATH)
    _write_artifacts(tmp_path)
    validate_canonical_artifacts(tmp_path, metadata)


def test_unmerged_or_implementation_pr_skips_without_selecting_specs(tmp_path: Path) -> None:
    unmerged = load_merged_pull_request_event(_event_file(tmp_path, _spec_body(), merged=False))
    assert classify_spec_event(unmerged) is None
    plan = skipped_plan(unmerged)
    assert plan.outcome == "skipped"
    assert plan.mutate_issue_body is False
    assert plan.issue_add == ()
    assert "was not merged" in plan.message

    implementation = load_merged_pull_request_event(_event_file(tmp_path, "## Linked task\n\nCloses #8\n", number=9))
    assert classify_spec_event(implementation) is None
    assert "not a specification lifecycle opt-out" in skipped_plan(implementation).message


def test_opted_out_pr_without_metadata_skips_compatibly(tmp_path: Path) -> None:
    body = f"{LIFECYCLE_OPT_OUT_MARKER}\nRelated to #36\nSee {SPEC_PATH}\nsecret {SECRET}\n"
    event = load_merged_pull_request_event(_event_file(tmp_path, body))
    assert classify_spec_event(event) is None
    plan = skipped_plan(event)
    assert plan.outcome == "skipped"
    assert plan.spec_path is None
    assert "no capt-spec metadata" in plan.message
    assert "Issue body was not rewritten" in plan.message
    assert SECRET not in plan.message


def test_non_main_base_fails_when_metadata_is_present(tmp_path: Path) -> None:
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body(), base_ref="spec/004"))
    with pytest.raises(SpecApprovalError, match="base is not main"):
        classify_spec_event(event)


def test_valid_merge_plans_one_managed_comment_and_human_review(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    plan = plan_spec_handoff(event, metadata, (NEEDS_DESIGN, "risk:medium"), (), repo_root=tmp_path)
    assert plan.outcome == "created"
    assert plan.issue_number == 58
    assert plan.pull_request_number == 56
    assert plan.spec_path == SPEC_PATH
    assert plan.comment_action == "create"
    assert plan.existing_comment_id is None
    assert plan.issue_add == (NEEDS_HUMAN_REVIEW,)
    assert plan.issue_remove == (NEEDS_DESIGN,)
    assert plan.mutate_issue_body is False
    assert AGENT_READY not in plan.issue_add
    assert plan.comment_body is not None
    approved = parse_approved_spec(plan.comment_body)
    assert approved is not None
    assert approved.issue_number == 58
    assert approved.pull_request_number == 56
    assert approved.spec_path == SPEC_PATH
    assert "acceptance criteria" not in plan.comment_body.lower()
    assert SECRET not in plan.comment_body
    assert SECRET not in plan.message


def test_needs_human_review_issue_keeps_lifecycle_and_records_comment(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    plan = plan_spec_handoff(
        event,
        metadata,
        (NEEDS_HUMAN_REVIEW, "risk:medium"),
        (),
        repo_root=tmp_path,
    )
    assert plan.issue_add == ()
    assert plan.issue_remove == ()
    assert AGENT_READY not in plan.issue_add
    assert plan.outcome == "created"


def test_rerun_updates_the_same_comment_without_duplication(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    stale = "<!-- capt-spec-approved:v1\nissue: 58\npr: 56\nspec: " + SPEC_PATH + "\n-->\n\nstale\n"
    comments = comments_from_mapping(
        [
            _comment_payload(77, stale),
            _comment_payload(78, "human note about the spec", login="reviewer", user_type="User"),
        ],
        "comments",
    )
    plan = plan_spec_handoff(event, metadata, (NEEDS_HUMAN_REVIEW,), comments, repo_root=tmp_path)
    assert plan.outcome == "updated"
    assert plan.comment_action == "update"
    assert plan.existing_comment_id == 77
    assert plan.comment_body is not None
    assert plan.comment_body != stale
    unchanged = plan_spec_handoff(
        event,
        metadata,
        (NEEDS_HUMAN_REVIEW,),
        comments_from_mapping([_comment_payload(77, plan.comment_body)], "comments"),
        repo_root=tmp_path,
    )
    assert unchanged.outcome == "unchanged"
    assert unchanged.comment_action == "unchanged"
    assert unchanged.existing_comment_id == 77


def test_handoff_creates_instead_of_updating_a_forged_marker(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    forged = _approved_comment(pull_request_number=99, spec="specs/001-compaction-pressure/spec.md")
    comments = comments_from_mapping(
        [_comment_payload(77, forged, login="attacker", user_type="User")],
        "comments",
    )
    plan = plan_spec_handoff(event, metadata, (NEEDS_HUMAN_REVIEW,), comments, repo_root=tmp_path)
    assert plan.outcome == "created"
    assert plan.comment_action == "create"
    assert plan.existing_comment_id is None


def test_handoff_updates_trusted_comment_not_forged_marker(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    stale = "<!-- capt-spec-approved:v1\nissue: 58\npr: 56\nspec: " + SPEC_PATH + "\n-->\n\nstale\n"
    comments = comments_from_mapping(
        [
            _comment_payload(77, stale, login="attacker", user_type="User"),
            _comment_payload(88, stale),
        ],
        "comments",
    )
    plan = plan_spec_handoff(event, metadata, (NEEDS_HUMAN_REVIEW,), comments, repo_root=tmp_path)
    assert plan.outcome == "updated"
    assert plan.comment_action == "update"
    assert plan.existing_comment_id == 88


def test_duplicate_managed_comments_fail_closed(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = load_merged_pull_request_event(_event_file(tmp_path, _spec_body()))
    metadata = classify_spec_event(event)
    assert metadata is not None
    body = _approved_comment()
    comments = comments_from_mapping([_comment_payload(1, body), _comment_payload(2, body)], "comments")
    with pytest.raises(SpecApprovalError, match="multiple capt-spec-approved comments"):
        plan_spec_handoff(event, metadata, (NEEDS_HUMAN_REVIEW,), comments, repo_root=tmp_path)


def test_apply_comment_creates_then_patches_and_never_edits_issue_body() -> None:
    created = agent_spec.SpecHandoffPlan(
        outcome="created",
        issue_number=58,
        pull_request_number=56,
        spec_path=SPEC_PATH,
        comment_body=_approved_comment(),
        comment_action="create",
        existing_comment_id=None,
        issue_add=(),
        issue_remove=(),
        mutate_issue_body=False,
        message="created",
    )
    api = _ScriptedGitHubApi([])
    apply_comment("owner/repo", created, write_api=api.write)
    assert api.writes[0][0] == "POST"
    assert api.writes[0][1] == "repos/owner/repo/issues/58/comments"
    assert json.loads(api.writes[0][2]) == {"body": created.comment_body}

    updated = agent_spec.SpecHandoffPlan(
        outcome="updated",
        issue_number=58,
        pull_request_number=56,
        spec_path=SPEC_PATH,
        comment_body=_approved_comment(),
        comment_action="update",
        existing_comment_id=77,
        issue_add=(),
        issue_remove=(),
        mutate_issue_body=False,
        message="updated",
    )
    apply_comment("owner/repo", updated, write_api=api.write)
    assert api.writes[1][0] == "PATCH"
    assert api.writes[1][1] == "repos/owner/repo/issues/comments/77"
    assert all(not path.endswith("/issues/58") for _, path, _ in api.writes)

    unchanged = agent_spec.SpecHandoffPlan(
        outcome="unchanged",
        issue_number=58,
        pull_request_number=56,
        spec_path=SPEC_PATH,
        comment_body=_approved_comment(),
        comment_action="unchanged",
        existing_comment_id=77,
        issue_add=(),
        issue_remove=(),
        mutate_issue_body=False,
        message="unchanged",
    )
    apply_comment("owner/repo", unchanged, write_api=api.write)
    assert len(api.writes) == 2


def test_apply_issue_labels_never_includes_body_or_agent_ready() -> None:
    api = _ScriptedGitHubApi([])
    apply_issue_labels(58, (NEEDS_HUMAN_REVIEW,), (NEEDS_DESIGN,), run_command=api.command)
    assert api.commands == [
        ("gh", "issue", "edit", "58", "--add-label", NEEDS_HUMAN_REVIEW, "--remove-label", NEEDS_DESIGN)
    ]
    assert "--body" not in api.commands[0]
    with pytest.raises(SpecApprovalError, match="refusing to add agent:ready"):
        apply_issue_labels(58, (AGENT_READY,), (), run_command=api.command)
    assert len(api.commands) == 1


def test_resolve_approved_spec_compatibility_path_does_not_guess_directory() -> None:
    comments = comments_from_mapping(
        [_comment_payload(1, "please use specs/002-trace-summary-comparison/spec.md")],
        "comments",
    )
    assert resolve_approved_spec(58, comments) is None


def test_resolve_approved_spec_reads_managed_comment() -> None:
    comments = comments_from_mapping([_comment_payload(77, _approved_comment())], "comments")
    approved = resolve_approved_spec(58, comments)
    assert approved is not None
    assert approved.spec_path == SPEC_PATH
    assert approved.pull_request_number == 56


def test_forged_approved_spec_marker_is_ignored() -> None:
    forged_body = "<!-- capt-spec-approved:v1\nissue: 58\npr: 99\nspec: specs/001-compaction-pressure/spec.md\n-->\n"
    comments = comments_from_mapping(
        [_comment_payload(1, forged_body, login="attacker", user_type="User")],
        "comments",
    )
    assert resolve_approved_spec(58, comments) is None


def test_forged_approved_spec_marker_does_not_create_duplicates_or_redirect() -> None:
    genuine = _approved_comment()
    forged = "<!-- capt-spec-approved:v1\nissue: 58\npr: 99\nspec: specs/001-compaction-pressure/spec.md\n-->\n"
    comments = comments_from_mapping(
        [
            _comment_payload(1, forged, login="attacker", user_type="User"),
            _comment_payload(77, genuine),
        ],
        "comments",
    )
    approved = resolve_approved_spec(58, comments)
    assert approved is not None
    assert approved.pull_request_number == 56
    assert approved.spec_path == SPEC_PATH


def test_forged_malformed_marker_does_not_fail_closed() -> None:
    comments = comments_from_mapping(
        [
            _comment_payload(
                1,
                "<!-- capt-spec-approved:v2\nissue: 58\npr: 56\nspec: specs/001-compaction-pressure/spec.md\n-->\n",
                login="attacker",
                user_type="User",
            )
        ],
        "comments",
    )
    assert resolve_approved_spec(58, comments) is None


def test_github_actions_login_with_non_bot_type_is_ignored() -> None:
    comments = comments_from_mapping(
        [_comment_payload(77, _approved_comment(), user_type="User")],
        "comments",
    )
    assert resolve_approved_spec(58, comments) is None


def test_comments_without_author_fail_closed() -> None:
    with pytest.raises(SpecApprovalError, match="are invalid"):
        comments_from_mapping([{"id": 77, "body": _approved_comment()}], "comments")


def test_cli_plan_and_classify_for_valid_merge(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    event = _event_file(tmp_path, _spec_body())
    stdout = StringIO()
    assert main(["classify", "--event-file", str(event)], stdout=stdout) == 0
    classified = json.loads(stdout.getvalue())
    assert classified["handoff"] is True
    assert classified["issue_number"] == 58
    assert SECRET not in stdout.getvalue()

    stdout = StringIO()
    assert (
        main(
            [
                "plan",
                "--event-file",
                str(event),
                "--repo-root",
                str(tmp_path),
                "--issue-labels-json",
                json.dumps([NEEDS_DESIGN, "risk:medium"]),
                "--comments-json",
                "[]",
            ],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["outcome"] == "created"
    assert plan["mutate_issue_body"] is False
    assert AGENT_READY not in plan["issue_add"]
    assert plan["issue_add"] == [NEEDS_HUMAN_REVIEW]
    assert SECRET not in stdout.getvalue()


def test_cli_skips_opted_out_pr_without_metadata(tmp_path: Path) -> None:
    event = _event_file(tmp_path, f"{LIFECYCLE_OPT_OUT_MARKER}\nRelated to #36\nsecret {SECRET}\n")
    stdout = StringIO()
    assert main(["plan", "--event-file", str(event), "--repo-root", str(tmp_path)], stdout=stdout) == 0
    plan = json.loads(stdout.getvalue())
    assert plan["outcome"] == "skipped"
    assert plan["mutate_issue_body"] is False
    assert plan["spec_path"] is None
    assert SECRET not in stdout.getvalue()
    assert "36" not in stdout.getvalue()


def test_cli_invalid_metadata_fails_without_planning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = _event_file(tmp_path, _spec_body(issue="nope"))
    stdout = StringIO()
    assert main(["plan", "--event-file", str(event), "--repo-root", str(tmp_path)], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "capt-spec issue is missing or invalid" in captured.err
    assert SECRET not in captured.err


def test_cli_apply_comment_create(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[str, str, str]] = []

    def _write(method: str, path: str, body: str) -> GitHubApiResponse:
        writes.append((method, path, body))
        return GitHubApiResponse(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(agent_spec, "_run_gh_api_write", _write)
    plan = {
        "outcome": "created",
        "issue_number": 58,
        "pull_request_number": 56,
        "spec_path": SPEC_PATH,
        "comment_body": _approved_comment(),
        "comment_action": "create",
        "existing_comment_id": None,
        "issue_add": [],
        "issue_remove": [],
        "mutate_issue_body": False,
        "message": "created",
    }
    stdout = StringIO()
    assert main(["apply-comment", "--plan-json", json.dumps(plan), "--repo", "owner/repo"], stdout=stdout) == 0
    assert json.loads(stdout.getvalue()) == {"outcome": "created", "mutate_issue_body": False}
    assert writes[0][0] == "POST"
    assert writes[0][1] == "repos/owner/repo/issues/58/comments"


def test_cli_rejects_plan_that_would_rewrite_issue_body(capsys: pytest.CaptureFixture[str]) -> None:
    plan = {
        "outcome": "created",
        "issue_number": 58,
        "pull_request_number": 56,
        "spec_path": SPEC_PATH,
        "comment_body": _approved_comment(),
        "comment_action": "create",
        "existing_comment_id": None,
        "issue_add": [],
        "issue_remove": [],
        "mutate_issue_body": True,
        "message": "created",
    }
    stdout = StringIO()
    assert main(["apply-comment", "--plan-json", json.dumps(plan), "--repo", "owner/repo"], stdout=stdout) == 1
    captured = capsys.readouterr()
    assert stdout.getvalue() == ""
    assert "must not rewrite the Issue body" in captured.err


def test_cli_handoff_creates_comment_and_moves_design_to_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_artifacts(tmp_path)
    event = _event_file(tmp_path, _spec_body())
    api = _ScriptedGitHubApi(
        [
            GitHubApiResponse(
                returncode=0,
                stdout=json.dumps({"labels": [{"name": NEEDS_DESIGN}, {"name": "risk:medium"}]}),
                stderr="",
            ),
            GitHubApiResponse(returncode=0, stdout="[]", stderr=""),
        ]
    )
    writes: list[tuple[str, str, str]] = []
    commands: list[tuple[str, ...]] = []

    def _write(method: str, path: str, body: str) -> GitHubApiResponse:
        writes.append((method, path, body))
        return GitHubApiResponse(returncode=0, stdout="{}", stderr="")

    def _command(args: Sequence[str]) -> GitHubApiResponse:
        commands.append(tuple(args))
        return GitHubApiResponse(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(agent_spec, "_run_gh_api", api)
    monkeypatch.setattr("agent_lifecycle._run_gh_api", api)
    monkeypatch.setattr(agent_spec, "_run_gh_api_write", _write)
    monkeypatch.setattr(agent_spec, "_run_gh_command", _command)
    stdout = StringIO()
    assert (
        main(
            ["handoff", "--event-file", str(event), "--repo-root", str(tmp_path), "--repo", "owner/repo"],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["outcome"] == "created"
    assert plan["mutate_issue_body"] is False
    assert AGENT_READY not in plan["issue_add"]
    assert writes == [("POST", "repos/owner/repo/issues/58/comments", json.dumps({"body": plan["comment_body"]}))]
    assert commands == [
        ("gh", "issue", "edit", "58", "--add-label", NEEDS_HUMAN_REVIEW, "--remove-label", NEEDS_DESIGN)
    ]
    assert "--body" not in commands[0]
    assert api.paths == [
        "repos/owner/repo/issues/58",
        "repos/owner/repo/issues/58/comments?per_page=100&page=1",
    ]
    assert SECRET not in stdout.getvalue()


def test_cli_handoff_does_not_apply_agent_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_artifacts(tmp_path)
    event = _event_file(tmp_path, _spec_body())
    api = _ScriptedGitHubApi(
        [
            GitHubApiResponse(
                returncode=0,
                stdout=json.dumps({"labels": [{"name": NEEDS_HUMAN_REVIEW}, {"name": "risk:low"}]}),
                stderr="",
            ),
            GitHubApiResponse(returncode=0, stdout="[]", stderr=""),
        ]
    )
    commands: list[tuple[str, ...]] = []

    def _write(method: str, path: str, body: str) -> GitHubApiResponse:
        del method, path, body
        return GitHubApiResponse(returncode=0, stdout="{}", stderr="")

    def _command(args: Sequence[str]) -> GitHubApiResponse:
        commands.append(tuple(args))
        return GitHubApiResponse(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(agent_spec, "_run_gh_api", api)
    monkeypatch.setattr("agent_lifecycle._run_gh_api", api)
    monkeypatch.setattr(agent_spec, "_run_gh_api_write", _write)
    monkeypatch.setattr(agent_spec, "_run_gh_command", _command)
    stdout = StringIO()
    assert (
        main(
            ["handoff", "--event-file", str(event), "--repo-root", str(tmp_path), "--repo", "owner/repo"],
            stdout=stdout,
        )
        == 0
    )
    plan = json.loads(stdout.getvalue())
    assert plan["issue_add"] == []
    assert AGENT_READY not in plan["issue_add"]
    assert commands == []


def test_comment_read_retries_503_then_succeeds() -> None:
    api = _ScriptedGitHubApi(
        [
            GitHubApiResponse(returncode=1, stdout=SECRET, stderr="gh: HTTP 503: Server Error"),
            GitHubApiResponse(
                returncode=0,
                stdout=json.dumps([_comment_payload(77, _approved_comment())]),
                stderr="",
            ),
        ]
    )
    comments = read_issue_comments("owner/repo", 58, run_api=api, sleep=api.sleep, notify=api.notify)
    assert comments[0].comment_id == 77
    assert comments[0].user_login == GITHUB_ACTIONS_BOT_LOGIN
    assert comments[0].user_type == GITHUB_ACTIONS_BOT_TYPE
    assert api.sleeps == [2.0]
    assert SECRET not in "".join(api.notes)


def test_workflow_is_dedicated_and_does_not_rewrite_issue_bodies() -> None:
    workflow = Path(".github/workflows/agent-spec-approved.yml").read_text(encoding="utf-8")
    lifecycle = Path(".github/workflows/agent-lifecycle.yml").read_text(encoding="utf-8")
    dispatch = Path(".github/workflows/agent-dispatch.yml").read_text(encoding="utf-8")
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pull_request:" in workflow
    assert "closed" in workflow
    assert "github.event.pull_request.merged == true" in workflow
    assert "agent_spec.py handoff" in workflow
    assert "merge_commit_sha" in workflow
    assert "issues: write" in workflow
    assert "--body" not in workflow
    assert "agent:ready" not in workflow
    assert "CURSOR_API_KEY" not in workflow
    assert "api.cursor.com" not in workflow
    assert "agent-spec-approved" not in lifecycle
    assert "agent-spec-approved" not in dispatch
    assert "agent-spec-approved" not in ci
    assert "agent_spec.py" not in lifecycle
    assert "agent_spec.py" not in dispatch


def test_spec_review_template_includes_versioned_metadata_and_keeps_opt_out() -> None:
    template = Path(".github/spec-review-pull-request.md").read_text(encoding="utf-8")
    assert template.splitlines()[2] == LIFECYCLE_OPT_OUT_MARKER
    assert has_lifecycle_opt_out(template) is True
    with pytest.raises(LifecycleError, match="opts out of Agent Task lifecycle"):
        parse_linked_issue_number(template)
    with pytest.raises(SpecApprovalError, match="capt-spec issue is missing or invalid"):
        parse_spec_metadata(template)
    assert "<!-- capt-spec:v1" in template
    assert "Related to #<issue>" in template
