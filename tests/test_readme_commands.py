from pathlib import Path

README = Path("README.md").read_text(encoding="utf-8")


def test_readme_documents_compare_handoff_and_file_output() -> None:
    assert "capt trace compare" in README
    assert "capt trace handoff" in README
    assert "--output" in README
    assert "--force" in README


def test_readme_does_not_claim_insights_are_absent() -> None:
    lowered = README.lower()
    assert "does not yet produce performance insights" not in lowered
    assert "or generate insights" not in lowered
    assert "does **not** inspect Claude Code transcripts, persist data in a database, score sessions, or generate insights" not in README
