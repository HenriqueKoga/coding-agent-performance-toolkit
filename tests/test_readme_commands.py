from pathlib import Path

README = Path("README.md").read_text(encoding="utf-8")


def test_readme_documents_compare_handoff_and_file_output() -> None:
    assert "capt trace compare" in README
    assert "capt trace handoff" in README
    assert "capt trace handoff --latest" in README
    assert "--output" in README
    assert "--force" in README
    handoff_section = README.split("## Export a compact handoff", 1)[1].split("## ", 1)[0]
    assert "--latest" in handoff_section
    assert "--latest` is not supported" not in handoff_section
    compare_section = README.split("`capt trace compare`", 1)[1].split("## ", 1)[0]
    assert "--latest` is not supported" in compare_section


def test_readme_does_not_claim_insights_are_absent() -> None:
    lowered = README.lower()
    assert "does not yet produce performance insights" not in lowered
    assert "or generate insights" not in lowered
