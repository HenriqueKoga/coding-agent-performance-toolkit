---
description: "Task list for support --latest for trace handoff"
---

# Tasks: Support `--latest` for trace handoff

**Input**: Design documents from `/specs/005-handoff-latest/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/handoff-latest-selection.md`, `quickstart.md`

**Tests**: Required. Synthetic fixtures and temporary capture directories only.

**Organization**: Extract the shared selector first so summarize cannot drift, then add `--latest` text handoff, then JSON/file-output combinations, then fail-closed selector cases. Implementation remains on existing Issue #63 after this specification is reviewed and merged. Do not run `/speckit.implement` or `/speckit.taskstoissues`. Do not rewrite Issue #63.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g. US1, US2, US3)
- Include exact file paths in descriptions

## CAPT delivery constraints

- [x] Tasks stay inside the spec's out-of-scope boundary
- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or discovery-framework task
- [x] Public schema/command changes are explicit: additive `--latest` on `capt trace handoff`; JSON v1 unchanged
- [x] Privacy allowlist and payload-free errors are preserved
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses the repository Agent Task issue template, a human-applied `risk:*` label, and human `agent:ready`
- [x] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm the existing package layout; do not scaffold a new project.

- [ ] T001 Inspect `src/coding_agent_performance/trace/cli.py`, `src/coding_agent_performance/trace/storage.py`, `src/coding_agent_performance/trace/handoff.py`, `src/coding_agent_performance/trace/handoff_output.py`, `tests/test_handoff.py`, `tests/test_summary_cli.py`, `README.md`, `docs/architecture.md`, `docs/product.md`, `docs/summary-format.md`, `specs/003-compact-trace-handoff/contracts/handoff-json-v1.md`, and `specs/004-persist-handoff-safely/contracts/handoff-file-output.md`

---

## Phase 2: Foundational

**Purpose**: One shared capture selector so handoff cannot invent a second latest algorithm.

**Checkpoint**: Summarize `--latest` public behavior is unchanged and both commands can call the same helper

- [ ] T002 Keep `tests/test_summary_cli.py` covering path plus `--latest`, neither selector, newest mtime, descending-filename tie-break, and symlink exclusion; add a case there only if extracting the helper would leave one of those summarize behaviors untested
- [ ] T003 Extract `resolve_summarize_capture()` into `resolve_capture_selection(capture, *, latest)` in `src/coding_agent_performance/trace/cli.py`; keep summarize calling it; keep `latest_capture(default_captures_dir())` as the only latest implementation; do not change `storage.py` ordering or add a discovery module

---

## Phase 3: User Story 1 - Handoff the latest local capture (Priority: P1)

**Goal**: `capt trace handoff --latest` prints the existing compact text handoff for the newest eligible capture. Explicit `CAPTURE` still works.

**Independent Test**: Seed two synthetic captures, run `--latest`, and compare stdout with an explicit-path run of the newer file.

### Tests

- [ ] T004 [P] [US1] Add CLI tests in `tests/test_handoff.py` that `--latest` text stdout matches `capt trace handoff` on the newest seeded capture, does not mention the older filename, and does not print absolute paths
- [ ] T005 [P] [US1] Add CLI tests in `tests/test_handoff.py` that explicit `CAPTURE` without `--latest` still matches current text handoff and that `capt trace handoff --help` documents `--latest`

### Implementation

- [ ] T006 [US1] Make `CAPTURE` optional and add `--latest` on `handoff` in `src/coding_agent_performance/trace/cli.py`; resolve with `resolve_capture_selection()`; then keep `handoff_capture_or_fail()`, `handoff_from_summary()`, and existing text rendering
- [ ] T007 [US1] Stop treating `--latest` as an unknown extra argument in `src/coding_agent_performance/trace/cli.py`; extra positional capture paths MUST still print `Provide exactly one capture path.`

**Checkpoint**: `--latest` text handoff is independently testable

---

## Phase 4: User Story 2 - Keep JSON and safe file output while selecting `--latest` (Priority: P2)

**Goal**: `--latest` combines with `--format json`, `--output`, and `--force` without changing JSON v1 or writer safety.

**Independent Test**: Compare `--latest` JSON/file runs with explicit-path runs of the selected file.

### Tests

- [ ] T008 [P] [US2] Add CLI tests in `tests/test_handoff.py` that `--latest --format json` matches an explicit-path JSON run of the selected capture, including v1 key order and values
- [ ] T009 [P] [US2] Add CLI tests in `tests/test_handoff.py` that `--latest --output PATH` writes byte-identical file content to a `--latest` stdout run, prints no handoff body, and that `--latest --output PATH --force` replaces a regular file while still refusing symlink/directory destinations

### Implementation

- [ ] T010 [US2] Keep `write_handoff_file()` and `--force` without `--output` handling unchanged in `src/coding_agent_performance/trace/cli.py` and `src/coding_agent_performance/trace/handoff_output.py`; do not add a latest-specific output filename or JSON envelope

**Checkpoint**: JSON and file output through `--latest` are independently testable

---

## Phase 5: User Story 3 - Reject ambiguous or empty selection with the same discovery rules (Priority: P3)

**Goal**: Conflicting or missing selectors fail closed. `--latest` agrees with summarize, including empty-directory errors, filename tie-break, and symlink exclusion.

**Independent Test**: Exercise the selector table in `specs/005-handoff-latest/contracts/handoff-latest-selection.md` and compare selected filenames with summarize.

### Tests

- [ ] T011 [P] [US3] Add CLI tests in `tests/test_handoff.py` for `CAPTURE` plus `--latest` (`Provide either a capture path or --latest, not both.`), neither selector (`Provide a capture path or --latest.`), and extra positional paths (`Provide exactly one capture path.`); assert exit 1, no traceback, no handoff body
- [ ] T012 [P] [US3] Add CLI tests in `tests/test_handoff.py` for `--latest` with a missing default directory, a non-directory, an empty directory, and a directory `OSError` using the existing `LatestCaptureError` strings; assert no absolute path on stderr
- [ ] T013 [US3] Add CLI tests in `tests/test_handoff.py` that under one monkeypatched default capture directory, handoff `--latest` and summarize `--latest` select the same file for newest mtime, equal-mtime filename tie-break, and symlink exclusion
- [ ] T014 [US3] Confirm in `tests/test_handoff.py` that synthetic prompt/path/payload markers in the selected capture do not appear in `--latest` stdout, JSON, `--output` files, or stderr, and that compare still rejects `--latest`

**Checkpoint**: Fail-closed selection and summarize agreement are independently testable

---

## Phase 6: Polish

- [ ] T015 [P] Update the handoff section in `README.md` so `capt trace handoff` accepts `CAPTURE` or `--latest`, not both, and still documents `--format`, `--output`, and `--force` with synthetic relative paths
- [ ] T016 [P] Replace explicit-path-only handoff claims in `docs/product.md`, `docs/architecture.md`, `docs/summary-format.md`, and `docs/development.md` if a smoke example is needed; do not copy this specification or change JSON v1
- [ ] T017 [P] Extend `tests/test_readme_commands.py` so README documents handoff `--latest` and no longer says `--latest` is not supported on handoff
- [ ] T018 [P] Confirm in existing tests that summarize, compare, collect, list, doctor, adapters, `handoff_from_summary()`, and JSON v1 key order are unchanged
- [ ] T019 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, `git diff --check`, smoke `uv run capt trace handoff --help`, `uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl`, and the same command with `--format json`

## Dependencies

```text
T001
  -> T002 -> T003
  -> T004, T005 (after T003)
  -> T006 -> T007
  -> T008, T009 (after T007)
  -> T010
  -> T011, T012 (after T007)
  -> T013 -> T014
  -> T015, T016, T017
  -> T018
  -> T019
```

User Story 1 depends on the shared selector. User Story 2 depends on User Story 1 CLI wiring so `--latest` already resolves a capture. User Story 3 can start after T007 because the helper already owns selector errors.

## Parallel execution examples

- After T003: T004 and T005 can proceed in parallel.
- After T007: T008, T009, T011, and T012 can proceed in parallel.
- After T014: T015, T016, and T017 can proceed in parallel.

## Implementation strategy

MVP is Phase 2 plus User Story 1: `--latest` text handoff that matches an explicit-path run of the newest eligible capture. User Story 2 then locks JSON v1 and file-output combinations. User Story 3 locks fail-closed selectors and summarize agreement. Do not add implicit latest, compare `--latest`, Markdown, JSON v1 fields, or a generic discovery framework.

## Notes

- Issue #63 is the existing operational Agent Task. After this specification review PR is merged, automation records the approved spec; the Issue body stays the original brief. A human may then apply `agent:ready`.
- Do not change `latest_capture()` eligibility or ordering.
- Do not change handoff JSON v1 or the compact allowlist.
- Do not invent a default handoff filename from `--latest`.
- Do not print absolute paths on success or failure.
- Do not rewrite `specs/003-compact-trace-handoff` or `specs/004-persist-handoff-safely`.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.
