# Implementation Plan: Support `--latest` for trace handoff

**Branch**: `005-handoff-latest` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-handoff-latest/spec.md`

**Note**: Specification-phase plan only. Issue #63 is the existing operational Agent Task. Its body remains the original feature brief. After this specification is reviewed and merged, automation records the approved artifacts; a human may then apply `agent:ready`. Do not run `/speckit.implement`. Do not rewrite Issue #63.

## Summary

Add `--latest` to `capt trace handoff` so the command can resolve the newest eligible local capture using the same discovery path as `capt trace summarize --latest`. Explicit `CAPTURE` stays valid. The two selectors are mutually exclusive. After a capture is selected, the existing compact-handoff transform, JSON v1 renderer, and safe `--output`/`--force` writer run unchanged.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. Reuse `latest_capture()` and `default_captures_dir()` from `trace/storage.py`. No new package. Spec Kit is not a runtime dependency.

**Storage**: Local default capture directory already used by summarize/list. No new capture store, handoff directory, or ledger.

**Testing**: `uv run pytest` with synthetic fixtures and temporary capture directories

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Keep the existing `--latest` running-maximum scan. Do not materialize entire captures to choose one file. After selection, keep streaming summarization.

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM, no generic discovery framework

**Scale/Scope**: Single-capture handoff plus reuse of existing latest-selection

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Local-first: no outbound user-data path, no public bind
- [x] Deterministic-first: evidence is observed facts, not model judgment
- [x] Privacy: no payloads, identifiers, absolute paths, or real fixtures
- [x] Provider-neutral core; vendor mapping stays in adapters
- [x] Streaming / bounded memory preserved
- [x] No required LLM or model API in core
- [x] Public commands and versioned schemas remain compatible, or a version change is explicit
- [x] No premature registry, ABC, plugin system, or generic framework
- [x] Human approval identified for scope, dependencies, schema, or lifecycle risk
- [x] Implementation will enter GitHub through existing Issue #63 after human `agent:ready`, not via `/speckit.implement`

## CAPT design notes

- **Privacy impact**: none beyond existing handoff. `--latest` chooses an already-local file. Output stays on the compact allowlist. Selector and discovery errors reuse path-free summarize messages; capture-input errors keep the handoff mapping.
- **Deterministic evidence**: selection uses the existing newest-eligible `.jsonl` order. The extract is unchanged.
- **Bounded-memory impact**: reuse `_select_latest_capture()`'s single running maximum. Do not scan through `list_captures()` just to take `[0]`.
- **Provider neutrality**: filesystem selection in the default capture directory; no adapter change.
- **Compatibility**: additive `--latest` on `capt trace handoff`. Explicit path, JSON v1, and writer safety unchanged. Compare still has no `--latest`.
- **Validation**: full AGENTS.md set plus selector, agreement-with-summarize, JSON identity, file-output, and privacy tests.
- **Out of scope**: implicit latest, compare `--latest`, global ordering change, JSON v1 changes, Markdown, Context Ledger, remote discovery, generic framework, new runtime dependency.
- **Human decisions**: stop if global "latest" meaning, JSON v1, implicit selection, a new dependency, network discovery, or a generic abstraction would be required. Do not apply `agent:ready` or risk labels from Spec Kit.

## Project Structure

### Documentation (this feature)

```text
specs/005-handoff-latest/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/handoff-latest-selection.md
├── checklists/requirements.md
├── tasks.md
└── analyze.md
```

Handoff JSON v1 remains [specs/003-compact-trace-handoff/contracts/handoff-json-v1.md](../003-compact-trace-handoff/contracts/handoff-json-v1.md). File output remains [specs/004-persist-handoff-safely/contracts/handoff-file-output.md](../004-persist-handoff-safely/contracts/handoff-file-output.md). This feature does not copy or version those schemas.

### Source Code (repository root)

```text
src/coding_agent_performance/
    cli.py
    adapters/claude_code/          # unchanged
    trace/
        cli.py                     # optional CAPTURE, --latest, shared selector
        storage.py                 # reuse latest_capture(); do not fork ordering
        handoff.py                 # unchanged pure transform
        handoff_output.py          # unchanged writer
        rendering.py               # unchanged text/JSON
docs/
    product.md
    architecture.md
    summary-format.md
    development.md
README.md
tests/
    test_handoff.py
    test_summary_cli.py            # agreement tests may share fixtures, not change summarize
    test_readme_commands.py
    test_trace_cli.py
```

**Structure Decision**: Extend `trace/cli.py`. Extract the smallest concrete shared selector from `resolve_summarize_capture()` so summarize and handoff call the same function. Do not add `utils.py`, a discovery package, or methods on `CaptureWriter`.

## CLI contract

```text
capt trace handoff [CAPTURE] [--latest] [--format text|json] [--output PATH] [--force]
```

| Input | Required | Default | Notes |
| --- | --- | --- | --- |
| `CAPTURE` | exactly one of `CAPTURE` or `--latest` | | Explicit CAPT JSONL path |
| `--latest` | exactly one of `CAPTURE` or `--latest` | false | Newest eligible file in the default capture directory |
| `--format` | no | `text` | Unchanged |
| `--output PATH` | no | absent | Unchanged writer |
| `--force` | no | false | Unchanged; still requires `--output` |

Help text for `--latest` MUST describe selecting the newest capture in the default capture directory, matching summarize's meaning.

Drop the current "unknown option" trap that treats `--latest` as extra args. After `--latest` is a real option, extra positional capture paths still fail with `Provide exactly one capture path.`

## Capture selection

Reuse, do not fork:

1. `default_captures_dir()`
2. `latest_capture(directory)`
3. Eligibility: `.jsonl`, not a symlink, is a file, no nested scan
4. Order: highest `mtime_ns`, then descending filename
5. Errors: existing `LatestCaptureError` strings

Implementation shape in `src/coding_agent_performance/trace/cli.py`:

- Keep summarize's current selector behavior byte-for-byte for its public errors.
- Rename or generalize `resolve_summarize_capture(capture, *, latest)` into a small shared function used by summarize and handoff. Suggested name: `resolve_capture_selection`. Stay in `cli.py`.
- Handoff command: `capture: Path | None = None` plus `--latest: bool = False`, then `selected = resolve_capture_selection(capture, latest=latest)`, then the existing transform/render/write path.
- Do not change `handoff_from_summary()`, `write_handoff_file()`, JSON v1, or `latest_capture()` ordering.

Summarize MUST keep calling the same helper so the two commands cannot drift.

## Error contract

Selector errors (before any capture is read):

| Condition | stderr | Exit |
| --- | --- | --- |
| `CAPTURE` and `--latest` | `Provide either a capture path or --latest, not both.` | 1 |
| neither selector | `Provide a capture path or --latest.` | 1 |
| extra positional capture paths | `Provide exactly one capture path.` | 1 |
| `--latest` and `LatestCaptureError` | existing `str(exc)` from storage | 1 |
| `--force` without `--output` | `Provide --output with --force.` | 1 |

After a capture is selected, `handoff_capture_or_fail()` remains the capture-input mapper. Do not route handoff capture errors through `summarize_or_fail()`.

No traceback. No absolute path. No payload.

## Documentation

Update sentences that currently say handoff requires exactly one explicit path and that `--latest` is not supported:

- `README.md` handoff section: accept `CAPTURE` or `--latest`, not both; keep `--format` / `--output` / `--force`
- `docs/architecture.md`: handoff selection matches summarize `--latest`
- `docs/product.md` and `docs/summary-format.md`: one explicit capture or `--latest`
- `docs/development.md` only if a smoke example should show `--latest`

Do not rewrite `specs/003-*` or `specs/004-*`. Those slices remain historical; this increment is the later exception for handoff.

## Constitution Check (post-design)

- Local-first: default capture directory on the user's machine only.
- Deterministic-first: reuse observed mtime/filename order; no inferred capture.
- Privacy: allowlist unchanged; discovery errors remain path-free.
- Provider-neutral: no adapter work.
- Bounded memory: running-maximum scan reused.
- No LLM.
- Compatibility: additive CLI flag; JSON v1 unchanged.
- No generic discovery framework.
- Human `agent:ready` remains the implementation gate.

No constitution violations. Complexity Tracking is empty.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
