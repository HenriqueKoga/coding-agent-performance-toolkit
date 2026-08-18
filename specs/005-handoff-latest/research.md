# Research: Support `--latest` for trace handoff

**Feature**: `005-handoff-latest`

**Date**: 2026-08-18

This Phase 0 note records choices the spec already pins. There are no remaining `[NEEDS CLARIFICATION]` items.

## Selector shape

- **Decision**: Optional positional `CAPTURE` plus `--latest`, matching `capt trace summarize`. Exactly one selector is required.
- **Rationale**: Operators already know this pair. The Issue forbids implicit latest and forbids a second discovery dialect.
- **Alternatives considered**: Keep `CAPTURE` required and add `--latest` as an error; a `--capture PATH` flag; always defaulting to latest. Rejected as a trap, a second path vocabulary, or implicit selection.

## Shared discovery path

- **Decision**: Call existing `latest_capture(default_captures_dir())`. Extract `resolve_summarize_capture()` into a small shared `resolve_capture_selection()` in `trace/cli.py` used by summarize and handoff. Do not change eligibility or ordering in `storage.py`.
- **Rationale**: The Issue requires the selected capture to match summarize under the same storage state and forbids a handoff-specific discovery subsystem. A four-line helper in the CLI module is the smallest concrete extraction.
- **Alternatives considered**: Copy the scan into `handoff.py`; have handoff call `list_captures()[0]`; add a discovery package/ABC. Rejected as a second algorithm, extra materialization, or a generic framework.

## Error strings

- **Decision**: Reuse summarize's selector strings and `LatestCaptureError` text. Keep handoff's `Provide exactly one capture path.` for extra positionals and `Provide --output with --force.` for writer misuse. Keep `handoff_capture_or_fail()` after selection.
- **Rationale**: Same choice should read the same. Capture-input sanitization on handoff is stricter than summarize and must not be lost.
- **Alternatives considered**: New handoff-only selector messages, or routing selected-capture errors through `summarize_or_fail()`. Rejected as dialect drift or as leaking `schema_version`.

## JSON and file output

- **Decision**: After selection, call the current render/write path with no format fork. `--latest --format json`, `--output`, and `--force` are combinations, not new features.
- **Rationale**: Issue acceptance criteria require unchanged JSON v1 and writer safety.
- **Alternatives considered**: A latest-only JSON envelope or a default output filename derived from the capture. Rejected as a schema change or implicit persistence.

## Compare and other commands

- **Decision**: Do not add `--latest` to compare, collect, list, or doctor. Sharing a helper does not require those commands to grow a flag.
- **Rationale**: Compare needs two explicit paths. The Issue puts other-command `--latest` out of scope unless an existing shared primitive requires it. The primitive does not.
- **Alternatives considered**: `capt trace compare --latest` as baseline. Rejected as a second product increment.

## Historical specs

- **Decision**: Leave `003-compact-trace-handoff` and `004-persist-handoff-safely` unchanged. This later spec is the approved `--latest` exception for handoff.
- **Rationale**: Those artifacts are the contracts for extract content and file safety. Rewriting them would mix historical slice scope with this increment.
- **Alternatives considered**: Patch FR-015 in 004 to allow `--latest`. Rejected as revisionist history; 005 is the additive record.

## Documentation

- **Decision**: Update README, architecture, product, and summary-format sentences that currently say handoff is explicit-path only and that `--latest` is unsupported.
- **Rationale**: After implementation those sentences would be false. The persist-handoff slice already established that contract docs must track additive CLI flags.
- **Alternatives considered**: Spec-only with stale README. Rejected because `--help` and README would disagree.

## Unresolved items

None. Human review of this specification is still required before Issue #63 receives `agent:ready`. The Issue body stays the original brief.
