# Tasks: Compare two trace summaries

**Input**: Design documents from `/specs/002-trace-summary-comparison/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required. Synthetic fixtures only.

**Organization**: One primary comparison story plus structured-output coverage. After analyze, implementation stays on existing GitHub Agent Task Issue #36. Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## CAPT delivery constraints

- [x] Tasks stay inside the spec's out-of-scope boundary
- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence task
- [x] New public command/output contract is explicit
- [x] Privacy allowlist and payload-free errors are preserved
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses Issue #36 with human-applied risk and `agent:ready`
- [x] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm current summary, CLI, rendering, and error boundaries before adding comparison.

- [ ] T001 Inspect `src/coding_agent_performance/trace/report.py`, `summary.py`, `cli.py`, `rendering.py`, relevant summary-format docs, and existing CLI/rendering tests

---

## Phase 2: Foundational comparison model

**Purpose**: Define the fixed immutable comparison contract and pure transformation.

- [ ] T002 Add focused failing unit tests for `MetricDelta`/`TraceComparison` and the eight-metric allowlist in `tests/test_comparison.py` or the repository's closest existing test module
- [ ] T003 Implement immutable comparison DTOs and `compare_summaries()` in `src/coding_agent_performance/trace/comparison.py`
- [ ] T004 Verify metric order is fixed and `delta == candidate - baseline` for identical/increase/decrease/zero scenarios

**Checkpoint**: Two immutable `TraceSummary` values can be compared without CLI, provider, or rendering dependencies

---

## Phase 3: User Story 1 - Compare explicit captures (Priority: P1)

**Goal**: Add a local CLI command that compares two explicit capture paths through existing summarization.

**Independent Test**: Synthetic baseline/candidate captures produce the expected eight deterministic text deltas.

### Tests

- [ ] T005 [P] [US1] Add CLI tests for two valid explicit capture paths, identical runs, increases, decreases, and zero values
- [ ] T006 [P] [US1] Add CLI error tests for missing/unreadable/invalid baseline and candidate inputs, asserting non-zero exit, no traceback, no payloads, and no absolute-path disclosure

### Implementation

- [ ] T007 [US1] Add `capt trace compare BASELINE CANDIDATE` to `src/coding_agent_performance/trace/cli.py` using existing `summarize_capture()` for each input
- [ ] T008 [US1] Reuse or minimally extract existing summarize error mapping only if needed to avoid meaningful duplication; preserve existing `trace summarize` behavior exactly
- [ ] T009 [US1] Add deterministic text comparison rendering in the existing rendering boundary with the fixed metric order

**Checkpoint**: `capt trace compare baseline.jsonl candidate.jsonl` is independently usable and local-only

---

## Phase 4: User Story 2 - Structured JSON comparison (Priority: P2)

**Goal**: Expose the same comparison evidence as a stable allowlisted JSON contract.

**Independent Test**: `--format json` returns the same eight baseline/candidate/delta values as text evidence.

### Tests

- [ ] T010 [P] [US2] Add JSON serialization tests for schema version, fixed field order, exact values, negative/positive/zero deltas, and repeated deterministic serialization
- [ ] T011 [P] [US2] Add text/JSON agreement and privacy tests ensuring successful output omits capture paths, identifiers, and raw telemetry content

### Implementation

- [ ] T012 [US2] Add JSON rendering for `TraceComparison` using the explicit allowlist from `plan.md`; do not serialize dataclasses dynamically or discover metrics at runtime
- [ ] T013 [US2] Wire the existing `--format text|json` pattern into `trace compare`

**Checkpoint**: Text and JSON are semantically equivalent and deterministic

---

## Phase 5: Documentation and validation

- [ ] T014 [P] Document `capt trace compare` and its eight metrics in `docs/product.md`, `docs/architecture.md`, and the appropriate public output/summary-format documentation without duplicating the full feature spec
- [ ] T015 [P] Confirm no existing summary schema/version, insight semantics, provider adapters, or capture contracts changed
- [ ] T016 [P] Confirm all fixtures/examples are synthetic and comparison output/error messages remain allowlisted
- [ ] T017 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, and `git diff --check`

---

## Notes

- Issue #36 is the single operational implementation task after specification approval.
- The spec is the behavioral source of truth; the plan is the technical design; this file is the work decomposition; `analyze.md` is review evidence only.
- Do not add percentage deltas in v1.
- Do not introduce a metric registry, generic experiment abstraction, protocol hierarchy, or provider-specific comparison path.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.