# Tasks: Compare two trace summaries

**Input**: Design documents from `/specs/002-trace-summary-comparison/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required. Synthetic fixtures only.

**Organization**: Preserve observed-vs-unavailable semantics first, then add comparison and rendering. Implementation stays on existing GitHub Agent Task Issue #36. Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## CAPT delivery constraints

- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence task
- [x] Existing trace-summary public text/JSON schema stays unchanged
- [x] New comparison JSON v1 contract is exact and allowlisted
- [x] Missing telemetry is never converted into observed zero
- [x] Availability state remains provider-neutral and fixed-size
- [x] Narrow normalization-field presence preservation is explicitly approved
- [x] Same-file inputs reuse one immutable summary snapshot
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses Issue #36 with human-applied risk and `agent:ready`

## Phase 1: Inspect current evidence boundaries

- [ ] T001 Inspect `report.py`, `summary.py`, current accumulators, normalized event/metric models, `providers/claude_code/normalizer.py`, `cli.py`, `rendering.py`, capture path handling, and tests that establish fallback/zero behavior
- [ ] T002 Identify the exact normalized evidence required to mark each of the eight metric slots available without numeric-value heuristics

---

## Phase 2: Preserve metric availability during normalization and aggregation

### Tests

- [ ] T003 Add normalizer tests proving missing/invalid API-request cost, input-token, and output-token fields remain distinguishable from explicit numeric zero without changing existing telemetry mappings
- [ ] T004 Add request-count availability tests across API-request events, OTEL-metric fallback, and no-usage captures
- [ ] T005 Add independent availability tests for estimated cost, input tokens, and output tokens, including partial API-event attributes and partial OTEL metric series
- [ ] T006 Add tool calls/failures availability tests for log-backed versus metrics-only captures
- [ ] T007 Add tool-result-byte tests where one or more counted tool calls lack result-size evidence
- [ ] T008 Add compaction availability tests for lifecycle/log-backed versus metrics-only captures
- [ ] T009 Assert observed numeric zero remains available while missing telemetry remains unavailable

### Implementation

- [ ] T010 Preserve per-field presence for already-supported API-request cost/input/output fields in the normalized provider-neutral record; do not add new telemetry mappings or provider-specific comparison logic
- [ ] T011 Add the smallest immutable provider-neutral availability DTO/fields needed for the eight slots
- [ ] T012 Extend existing accumulators with fixed-size availability/completeness state; do not retain raw records or introduce a registry
- [ ] T013 Attach availability to the internal immutable summary domain result while keeping existing `trace summarize` renderers/schema version unchanged
- [ ] T014 Add compatibility tests proving current trace-summary text/JSON output is unchanged

---

## Phase 3: Foundational comparison model

- [ ] T015 Add failing unit tests for the fixed `MetricComparison`/`TraceComparison` contract
- [ ] T016 Implement immutable comparison DTOs and pure `compare_summaries()`
- [ ] T017 Verify fixed order and `delta == candidate - baseline` only when both sides are available
- [ ] T018 Verify either-side unavailability yields an explicit unavailable slot with `baseline`, `candidate`, and `delta` all absent/null

---

## Phase 4: User Story 1 - Compare explicit captures (Priority: P1)

### Tests

- [ ] T019 [P] [US1] Add CLI tests for identical, increased, decreased, observed-zero, and mixed-availability metrics
- [ ] T020 [P] [US1] Add same-file tests proving one summary snapshot is reused, including an alias/symlink case where portable; the result must not depend on a second read of a concurrently changing capture
- [ ] T021 [P] [US1] Add CLI error tests for missing/unreadable/invalid inputs, asserting non-zero exit, no traceback, no payloads, and no absolute-path disclosure

### Implementation

- [ ] T022 [US1] Add `capt trace compare BASELINE CANDIDATE` using existing `summarize_capture()` for each distinct input
- [ ] T023 [US1] Detect when both inputs resolve to the same filesystem object and summarize it exactly once; reuse that immutable summary for both sides
- [ ] T024 [US1] Reuse or minimally extract existing summarize error mapping only when needed; preserve current `trace summarize` behavior
- [ ] T025 [US1] Add deterministic text rendering with fixed metric order and explicit unavailable state

---

## Phase 5: User Story 2 - Structured JSON comparison (Priority: P2)

### Tests

- [ ] T026 [P] [US2] Assert the exact normative JSON v1 contract from `plan.md`: top-level key order, `schema_version == 1`, `metrics` object, exact eight metric keys/order, exact per-slot keys/order, integer values when available, and all three nullable values when unavailable
- [ ] T027 [P] [US2] Add repeated deterministic serialization tests and reject/guard against accidental extra top-level or metric fields
- [ ] T028 [P] [US2] Add text/JSON agreement and privacy tests ensuring output omits capture paths, identifiers, provider provenance, and raw telemetry

### Implementation

- [ ] T029 [US2] Add explicit allowlisted JSON rendering matching the complete mandatory v1 shape in `plan.md`; do not serialize dataclasses dynamically or discover metrics at runtime
- [ ] T030 [US2] Wire the existing `--format text|json` pattern into `trace compare`

---

## Phase 6: Documentation and validation

- [ ] T031 [P] Document `capt trace compare`, the exact JSON v1 contract, eight fixed slots, unavailable semantics, and same-file snapshot behavior in product/architecture/public-format docs without duplicating the full feature spec
- [ ] T032 [P] Confirm the only provider-adapter change is narrow preservation of presence for already-supported API-request fields; no new provider mapping or provider-specific comparison behavior is introduced
- [ ] T033 [P] Confirm no existing summary JSON schema/version, insight semantics, or capture contracts changed
- [ ] T034 [P] Confirm all fixtures/examples are synthetic and comparison output/error messages remain allowlisted
- [ ] T035 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, and `git diff --check`

## Notes

- Issue #36 is the single operational implementation task after specification approval.
- Do not infer availability from numeric values.
- Do not erase normalized field presence into fallback zero when availability depends on it.
- Do not compare same-file inputs by summarizing the same mutable file twice.
- Do not deviate from the mandatory comparison JSON v1 layout without a new specification/schema version decision.
- Do not add percentages, scoring, recommendations, a metric registry, generic experiment abstraction, protocol hierarchy, or provider-specific comparison path.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.