# Tasks: Export compact trace handoff

**Input**: Design documents from `/specs/003-compact-trace-handoff/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/handoff-json-v1.md`, `quickstart.md`

**Tests**: Required. Synthetic fixtures only.

**Organization**: Build the pure summary-to-handoff transform first, then text CLI, then canonical JSON. Implementation stays on existing GitHub Agent Task Issue #37. Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g. US1, US2)
- Include exact file paths in descriptions

## CAPT delivery constraints

- [x] Tasks stay inside the spec's out-of-scope boundary
- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence task
- [x] Public schema/command changes are explicit: additive `capt trace handoff` plus handoff JSON v1
- [x] Existing summarize and compare schemas stay unchanged
- [x] Privacy allowlist and payload-free errors are preserved
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses the repository Agent Task issue template, a human-applied `risk:*` label, and human `agent:ready`
- [x] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm the existing package layout; do not scaffold a new project.

- [ ] T001 Inspect `src/coding_agent_performance/trace/report.py`, `src/coding_agent_performance/trace/summary.py`, `src/coding_agent_performance/trace/insights.py`, `src/coding_agent_performance/trace/cli.py`, `src/coding_agent_performance/trace/rendering.py`, `src/coding_agent_performance/trace/comparison.py`, `docs/summary-format.md`, `tests/test_comparison.py`, `tests/test_insights.py`, and `tests/test_trace_cli.py`

---

## Phase 2: Foundational

**Purpose**: Immutable compact extract that all user stories consume.

**Checkpoint**: `handoff_from_summary()` can be unit-tested without CLI rendering

- [ ] T002 Add failing unit tests for `TraceHandoff` construction in `tests/test_handoff.py` using synthetic `TraceSummary` values, including empty/minimal summaries and summaries with insight findings
- [ ] T003 Implement compact DTOs and `handoff_from_summary()` in `src/coding_agent_performance/trace/handoff.py` per `plan.md` and `data-model.md`; reuse existing `SessionStats` and `Insights`
- [ ] T004 Copy only FR-004 allowlisted fields from `TraceSummary` in `src/coding_agent_performance/trace/handoff.py`; omit activity, coverage, comparison availability, envelopes, timestamps, cache tokens, durations, `by_model`, `by_name`, and `input_bytes`
- [ ] T005 Copy `insights` unchanged in `src/coding_agent_performance/trace/handoff.py` and assert in `tests/test_handoff.py` that findings match the source summary object-for-object
- [ ] T006 Set `schema_version` to `1` in `src/coding_agent_performance/trace/handoff.py` independently from `TraceSummary.schema_version`
- [ ] T007 Assert in `tests/test_handoff.py` that `tools.success_rate_bps` is `None` when `calls == 0` and equals the summary property otherwise
- [ ] T008 Assert in `tests/test_handoff.py` that `capture.file` is the summary filename only, prompt/assistant fields remain integer counts, `claude-code` sources are preserved, and an arbitrary synthetic source string is mapped to `unknown` without appearing in the handoff

---

## Phase 3: User Story 1 - Export a compact evidence handoff (Priority: P1)

**Goal**: `capt trace handoff CAPTURE` prints a compact text handoff to stdout from one explicit capture.

**Independent Test**: Run the command on synthetic captures with no insights and with insights; verify stdout evidence and CLI errors.

### Tests

- [ ] T009 [P] [US1] Add CLI success tests in `tests/test_handoff.py` for one explicit synthetic capture covering empty/minimal traces and traces with insight findings
- [ ] T010 [P] [US1] Add CLI error tests in `tests/test_handoff.py` for missing path, unreadable path, invalid capture, extra arguments, unexpected `--latest` or `--output`, and an envelope whose `schema_version` is a distinctive synthetic marker string; assert non-zero exit, no traceback, no payloads, no absolute-path disclosure, and that the marker string is absent from stderr
- [ ] T011 [P] [US1] Add tests in `tests/test_handoff.py` proving text output contains no goals, decisions, TODOs, recommendations, or next-action section

### Implementation

- [ ] T012 [US1] Add `capt trace handoff CAPTURE` in `src/coding_agent_performance/trace/cli.py` using existing `summarize_capture()` and `handoff_from_summary()`; map `CaptureError`/`OSError` through a handoff-specific payload-free helper and do not reuse `summarize_or_fail()`
- [ ] T013 [US1] Keep the command stdout-only in `src/coding_agent_performance/trace/cli.py`; do not add `--latest` or `--output`
- [ ] T014 [US1] Add deterministic text rendering of `TraceHandoff` in `src/coding_agent_performance/trace/rendering.py` that reports only allowlisted identity, aggregates, success-rate nullability, and existing insight line wording
- [ ] T015 [US1] Update `trace_app` help in `src/coding_agent_performance/trace/cli.py` to mention handoff without changing collect, list, summarize, or compare behavior

**Checkpoint**: Story is independently testable with default text output

---

## Phase 4: User Story 2 - Consume the same handoff as JSON (Priority: P2)

**Goal**: `--format json` emits the mandatory v1 contract and agrees with text evidence.

**Independent Test**: Compare JSON to `contracts/handoff-json-v1.md` and to text values for the same synthetic captures.

### Tests

- [ ] T016 [P] [US2] Assert the exact JSON v1 contract from `specs/003-compact-trace-handoff/contracts/handoff-json-v1.md` and `plan.md` in `tests/test_handoff.py`: top-level key order, `schema_version == 1`, nested key order, integer values, `success_rate_bps` nullability, empty-array versus `null` insights
- [ ] T017 [P] [US2] Add repeated deterministic serialization tests in `tests/test_handoff.py` and reject extra top-level or nested fields
- [ ] T018 [P] [US2] Add text/JSON agreement tests in `tests/test_handoff.py` for identity, aggregates, insight presence/absence, allowlisted/`unknown` source, and privacy exclusions against synthetic payload/path/prompt/source strings

### Implementation

- [ ] T019 [US2] Add explicit allowlisted JSON rendering in `src/coding_agent_performance/trace/rendering.py` matching `contracts/handoff-json-v1.md`; do not serialize dataclasses dynamically
- [ ] T020 [US2] Wire existing `--format text|json` into `capt trace handoff` in `src/coding_agent_performance/trace/cli.py`, defaulting to text and writing JSON with a trailing newline

**Checkpoint**: JSON is the canonical structured representation and text agrees

---

## Phase 5: Polish

- [ ] T021 [P] Document `capt trace handoff`, stdout-only behavior, and the exact JSON v1 contract in `docs/product.md`, `docs/architecture.md`, `docs/summary-format.md`, and `docs/development.md` without duplicating the full feature spec
- [ ] T022 [P] Confirm in `tests/test_handoff.py` or existing summary/comparison tests that `capt trace summarize` and `capt trace compare` public text/JSON output is unchanged
- [ ] T023 [P] Confirm no adapter, collector, capture-schema, insight-threshold, or comparison-schema changes in `src/coding_agent_performance/adapters/claude_code/`, `src/coding_agent_performance/trace/capture.py`, `src/coding_agent_performance/trace/insights.py`, and `src/coding_agent_performance/trace/comparison.py`
- [ ] T024 [P] Confirm all fixtures/examples are synthetic and that handoff stdout/stderr cannot contain prompt, tool-payload, secret, absolute-path, arbitrary-source, or envelope `schema_version` marker strings from those fixtures
- [ ] T025 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, `git diff --check`, and smoke `uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl` plus the same command with `--format json`

## Dependencies

```text
T001
  -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008
  -> T009, T010, T011 (after T008)
  -> T012 -> T013 -> T014 -> T015
  -> T016, T017, T018 (after T015)
  -> T019 -> T020
  -> T021, T022, T023, T024
  -> T025
```

User Story 1 depends on the foundational extract. User Story 2 depends on User Story 1 CLI wiring so `--format` can share one command. Foundational tests can run before CLI work.

## Parallel execution examples

- After T008: T009, T010, and T011 can proceed in parallel.
- After T015: T016, T017, and T018 can proceed in parallel.
- After T020: T021 through T024 can proceed in parallel.

## Implementation strategy

MVP is Phase 2 plus User Story 1: one explicit capture produces a compact text evidence handoff. User Story 2 then freezes the canonical JSON contract. Do not ship JSON-only without text, and do not add `--output`, `--latest`, Markdown, or narrative fields.

## Notes

- Issue #37 is the single operational implementation task after specification approval.
- Do not invent goals, decisions, TODOs, or source-code context.
- Do not copy the full `TraceSummary` into JSON and call it compact.
- Do not echo arbitrary envelope `source` or `schema_version` values.
- Do not reuse `summarize_or_fail()` for handoff.
- Do not change insight thresholds or recompute findings.
- Do not add a generic artifact framework, registry, or `artifacts/` package.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.
