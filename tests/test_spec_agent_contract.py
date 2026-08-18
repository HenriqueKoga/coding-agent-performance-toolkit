from pathlib import Path


def test_speckit_workflow_requires_analyze_before_spec_pr_handoff() -> None:
    workflow = Path(".specify/workflows/speckit/workflow.yml").read_text(encoding="utf-8")
    analyze_at = workflow.index("command: speckit.analyze")
    persist_at = workflow.index("Persist the approved report as specs/<feature>/analyze.md")
    handoff_at = workflow.index("Open a specification-only review PR from this branch")
    assert analyze_at < persist_at < handoff_at
    assert "command: speckit.implement" not in workflow


def test_development_workflow_creates_branch_before_specification_pr() -> None:
    text = Path("docs/development.md").read_text(encoding="utf-8")
    section = text[text.index("## Development workflow") : text.index("## Agent-assisted workflow")]
    assert section.index("Create a focused branch") < section.index("opens a specification-only review PR")
    assert "needs:design" in section
    assert "After that PR is reviewed, a human opens one Agent Task Issue" not in section


def test_spec_agent_docs_use_existing_issue_as_brief() -> None:
    spec_kit = Path("docs/spec-kit.md").read_text(encoding="utf-8")
    development = Path("docs/development.md").read_text(encoding="utf-8")
    constitution = Path(".specify/memory/constitution.md").read_text(encoding="utf-8")
    tasks = Path(".specify/templates/overrides/tasks-template.md").read_text(encoding="utf-8")
    assert "It is not a GitHub Issue." not in spec_kit
    assert "The operational input is an existing Agent Task Issue." in spec_kit
    assert spec_kit.index("Agent Task Issue in needs:design") < spec_kit.index(
        "manual workflow_dispatch Spec Agent from main"
    )
    assert "The Agent Task Issue already exists in `needs:design`" in development
    assert "manual GitHub Agent Task Issue (`needs:design`)" in constitution
    assert constitution.index("manual GitHub Agent Task Issue (`needs:design`)") < constitution.index(
        "Spec Agent (pinned Spec Kit) via manual workflow_dispatch from main"
    )
    assert "a human creates one GitHub Agent Task Issue by hand" not in tasks
    assert "Do not create a second GitHub Issue." in tasks
