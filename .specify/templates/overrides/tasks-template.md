---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: CAPT features that change behavior include tests. Use synthetic fixtures only.

**Organization**: Tasks are grouped by user story. After `/speckit.analyze`, persist `analyze.md` and open a specification-only review PR. After that PR is reviewed, a human creates one GitHub Agent Task Issue by hand. Do not run `/speckit.implement` as the production path. Do not run `/speckit.taskstoissues` to create lifecycle issues.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- CAPT is a single Python package: `src/coding_agent_performance/`, `tests/`, `docs/`
- Paths shown below must use real repository paths from plan.md

<!--
  The /speckit.tasks command MUST replace sample tasks with actual tasks.
  Do not keep sample tasks in the generated tasks.md file.
-->

## CAPT delivery constraints

- [ ] Tasks stay inside the spec's out-of-scope boundary
- [ ] Tests use synthetic fixtures only
- [ ] No runtime dependency, LLM, network, or persistence task unless the spec already has human approval
- [ ] Public schema/command changes are explicit and documented
- [ ] Privacy allowlist and payload-free errors are preserved
- [ ] Streaming / bounded memory is preserved
- [ ] Final delivery uses the repository Agent Task issue template, a human-applied `risk:*` label, and human `agent:ready`
- [ ] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm the existing package layout; do not scaffold a new project.

- [ ] T001 Inspect the existing files named in plan.md

---

## Phase 2: Foundational

**Purpose**: Shared types or documentation contracts that block the user story.

- [ ] T002 [Foundational change, or delete this phase if none is required]

**Checkpoint**: User story work can begin

---

## Phase 3: User Story 1 - [Title] (Priority: P1)

**Goal**: [Brief description]

**Independent Test**: [How to verify]

### Tests

- [ ] T003 [P] [US1] Add failing tests in tests/[file].py

### Implementation

- [ ] T004 [US1] Implement the change in src/coding_agent_performance/[path]
- [ ] T005 [US1] Update docs/summary-format.md or other contract docs if output changes

**Checkpoint**: Story is independently testable

---

## Phase N: Polish

- [ ] TXXX [P] Documentation updates in docs/
- [ ] TXXX Run the required validation set from AGENTS.md

---

## Notes

- Prefer one Agent Task Issue for the feature after specification review, not one GitHub Issue per Spec Kit task
- `/speckit.taskstoissues` cannot populate the Agent Task template, required risk classification, or human `agent:ready` gate
- Do not implement from this file through `/speckit.implement` in the CAPT pilot
