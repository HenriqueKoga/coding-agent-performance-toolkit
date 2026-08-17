# Tasks: Detect compaction pressure

**Input**: Design documents from `/specs/001-compaction-pressure/`

**Prerequisites**: plan.md, spec.md

**Tests**: Required. Synthetic fixtures only.

**Organization**: One user story. After analyze, implementation stays on the existing GitHub Agent Task Issue #34. Do not run `/speckit.implement`. Do not run `/speckit.taskstoissues`.

## CAPT delivery constraints

- [x] Tasks stay inside the spec's out-of-scope boundary
- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence task
- [x] Public schema/command changes are explicit and documented
- [x] Privacy allowlist and payload-free errors are preserved
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses the repository Agent Task issue template, a human-applied `risk:*` label, and human `agent:ready`
- [x] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm the existing insight path.

- [ ] T001 Inspect `src/coding_agent_performance/trace/report.py`, `insights.py`, `rendering.py`, and `docs/summary-format.md` for the current Insights pattern

---

## Phase 2: Foundational

**Purpose**: Add the allowlisted finding type before detection or rendering.

- [ ] T002 Add an immutable compaction-pressure finding DTO and field on `Insights` in `src/coding_agent_performance/trace/report.py`

**Checkpoint**: User story work can begin

---

## Phase 3: User Story 1 - See compaction pressure on a summarized capture (Priority: P1)

**Goal**: Emit a deterministic finding from `sessions.compactions` when the count meets the threshold.

**Independent Test**: Synthetic captures with 0, 1, 2, and greater counts produce the specified text and JSON evidence.

### Tests

- [ ] T003 [P] [US1] Add failing insight tests in `tests/test_insights.py` for zero, below threshold, threshold, above threshold, and coexistence with existing tool insights
- [ ] T004 [P] [US1] Add failing rendering and JSON tests in `tests/test_rendering.py` and `tests/test_summary.py`

### Implementation

- [ ] T005 [US1] Detect compaction pressure from `SessionStats.compactions` in `src/coding_agent_performance/trace/insights.py`
- [ ] T006 [US1] Allowlist the finding in `src/coding_agent_performance/trace/rendering.py` for text and JSON
- [ ] T007 [US1] Document the field in `docs/summary-format.md` and mention the rule in `docs/architecture.md` and `docs/product.md`

**Checkpoint**: Story is independently testable

---

## Phase 4: Polish

- [ ] T008 [P] Confirm fixtures remain synthetic and output omits identifiers, paths, and payloads
- [ ] T009 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, and `uv run pytest`

---

## Notes

- Prefer the existing Issue #34 as the single Agent Task for implementation
- `/speckit.taskstoissues` cannot populate the Agent Task template, required risk classification, or human `agent:ready` gate
- Do not implement these tasks as part of the Spec Kit adoption (Issue #42)
