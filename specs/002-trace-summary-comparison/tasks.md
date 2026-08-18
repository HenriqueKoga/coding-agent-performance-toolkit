# Tasks: Compare two trace summaries

**Input**: Design documents from `/specs/002-trace-summary-comparison/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required. Synthetic fixtures only.

**Organization**: Preserve observed-vs-unavailable semantics first, then add comparison and rendering. Implementation stays on existing GitHub Agent Task Issue #36. Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## CAPT delivery constraints

- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence task
- [x] Existing trace-summary public text/JSON schema stays unchanged
- [x] New comparison contract is explicit and allowlisted
- [x] Missing telemetry is never converted into observed zero
- [x] Availability state remains provider-neutral and fixed-size
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses Issue #36 with human-applied risk and `agent:ready`

## Phase 1: Inspect current evidence boundaries

- [ ] T001 Inspect `report.py`, `summary.py`, all current accumulators, normalized event/metric models, `cli.py`, `rendering.py`, and tests that establish fallback/zero behavior
- [ ] T002 Identify the exact normalized evidence required to mark each of the eight metric slots available without using numeric-value heuristics

**Checkpoint**: Availability rules are mapped to existing normalized evidence before code changes.

---

## Phase 2: Preserve metric availability during aggregation

**Purpose**: Distinguish an observed zero from unavailable/incomplete telemetry using fixed-size provider-neutral state.

### Tests

- [ ] T003 Add focused failing tests for `model_requests` availability across API-request events, OTEL-metric fallback, and no-usage captures
- [ ] T004 Add independent availability tests for estimated cost, input tokens, and output tokens, including partial OTEL metric series
- [ ] T005 Add availability tests for tool calls/failures on log-backed versus metrics-only captures
- [ ] T006 Add tool-result-byte tests where one or more counted tool calls lack result-size evidence
- [ ] T007 Add session-compaction availability tests for lifecycle/log-backed versus metrics-only captures
- [ ] T008 Assert observed numeric zero remains available while missing telemetry remains unavailable

### Implementation

- [ ] T009 Add the smallest immutable provider-neutral availability DTO/fields needed for the eight slots
- [ ] T010 Extend existing accumulators with fixed-size availability/completeness state; do not retain raw records or introduce a registry
- [ ] T011 Attach availability to the internal immutable summary domain result while keeping existing `trace summarize` renderers/schema version unchanged
- [ ] T012 Add compatibility tests proving current trace-summary text/JSON output is unchanged by the internal metadata

**Checkpoint**: `TraceSummary` can distinguish observed zero from unavailable evidence for all eight comparison slots without changing its public rendered contract.

---

## Phase 3: Foundational comparison model

- [ ] T013 Add failing unit tests for the fixed `MetricComparison`/`TraceComparison` contract
- [ ] T014 Implement immutable comparison DTOs and pure `compare_summaries()` in `src/coding_agent_performance/trace/comparison.py`
- [ ] T015 Verify fixed order and `delta == candidate - baseline` only when both sides are available
- [ ] T016 Verify either-side unavailability yields an explicit unavailable slot and no numeric delta

**Checkpoint**: Two immutable summaries can be compared without CLI, provider, or rendering dependencies.

---

## Phase 4: User Story 1 - Compare explicit captures (Priority: P1)

### Tests

- [ ] T017 [P] [US1] Add CLI tests for two explicit captures with identical, increased, decreased, observed-zero, and mixed-availability metrics
- [ ] T018 [P] [US1] Add CLI error tests for missing/unreadable/invalid baseline and candidate inputs, asserting non-zero exit, no traceback, no payloads, and no absolute-path disclosure

### Implementation

- [ ] T019 [US1] Add `capt trace compare BASELINE CANDIDATE` using existing `summarize_capture()` for each input
- [ ] T020 [US1] Reuse or minimally extract existing summarize error mapping only when needed; preserve current `trace summarize` behavior
- [ ] T021 [US1] Add deterministic text comparison rendering with fixed metric order and explicit unavailable state

**Checkpoint**: `capt trace compare baseline.jsonl candidate.jsonl` is independently usable, local-only, and never fabricates deltas from unavailable telemetry.

---

## Phase 5: User Story 2 - Structured JSON comparison (Priority: P2)

### Tests

- [ ] T022 [P] [US2] Add JSON tests for schema version, fixed field order, available numeric slots, unavailable nullable slots, and deterministic serialization
- [ ] T023 [P] [US2] Add text/JSON agreement and privacy tests ensuring output omits capture paths, identifiers, provider provenance, and raw telemetry

### Implementation

- [ ] T024 [US2] Add explicit allowlisted JSON rendering; do not serialize dataclasses dynamically or discover metrics at runtime
- [ ] T025 [US2] Wire the existing `--format text|json` pattern into `trace compare`

---

## Phase 6: Documentation and validation

- [ ] T026 [P] Document `capt trace compare`, the eight fixed slots, and unavailable semantics in product/architecture/public-format docs without duplicating the full feature spec
- [ ] T027 [P] Confirm no existing summary JSON schema/version, insight semantics, provider adapters, or capture contracts changed
- [ ] T028 [P] Confirm all fixtures/examples are synthetic and comparison output/error messages remain allowlisted
- [ ] T029 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, and `git diff --check`

## Notes

- Issue #36 is the single operational implementation task after specification approval.
- The spec is behavioral authority; the plan is technical design; this file is work decomposition; `analyze.md` is review evidence only.
- Do not infer availability from `value == 0` or `value != 0`.
- Do not add percentages, scoring, recommendations, a metric registry, generic experiment abstraction, protocol hierarchy, or provider-specific comparison path.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.