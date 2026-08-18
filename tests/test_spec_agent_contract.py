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
    assert section.index("Create a focused branch") < section.index(
        "opens a specification-only review PR"
    )
