---
description: "Task list for persist compact trace handoff safely"
---

# Tasks: Persist compact trace handoff safely

**Input**: Design documents from `/specs/004-persist-handoff-safely/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/handoff-file-output.md`, `quickstart.md`

**Tests**: Required. Synthetic fixtures and temporary directories only.

**Organization**: Build the exclusive file writer first, then stdout-compatible `--output`, then overwrite/symlink safety, then README audit. Implementation remains on existing Issue #58 after this specification is reviewed and merged. Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g. US1, US2, US3)
- Include exact file paths in descriptions

## CAPT delivery constraints

- [x] Tasks stay inside the spec's out-of-scope boundary
- [x] Tests use synthetic fixtures only
- [x] No runtime dependency, LLM, network, or persistence-framework task
- [x] Public schema/command changes are explicit: additive `--output`/`--force` on `capt trace handoff`; JSON v1 unchanged
- [x] Privacy allowlist and payload-free errors are preserved
- [x] Streaming / bounded memory is preserved
- [x] Final delivery uses the repository Agent Task issue template, a human-applied `risk:*` label, and human `agent:ready`
- [x] Spec Kit does not apply lifecycle or risk labels

## Phase 1: Setup

**Purpose**: Confirm the existing package layout; do not scaffold a new project.

- [ ] T001 Inspect `src/coding_agent_performance/trace/cli.py`, `src/coding_agent_performance/trace/handoff.py`, `src/coding_agent_performance/trace/rendering.py`, `src/coding_agent_performance/trace/storage.py`, `tests/test_handoff.py`, `README.md`, `docs/product.md`, `docs/architecture.md`, `docs/summary-format.md`, and `specs/003-compact-trace-handoff/contracts/handoff-json-v1.md`

---

## Phase 2: Foundational

**Purpose**: Small exclusive handoff file writer that user stories can call without changing JSON v1.

**Checkpoint**: `write_handoff_file()` can be unit-tested without CLI rendering

- [ ] T002 Add failing unit tests in `tests/test_handoff_output.py` for creating a new file with complete synthetic content, POSIX `0600` where `os.name == "posix"`, and cleanup of a sibling temporary file after a forced write failure
- [ ] T003 Implement `HandoffOutputError` and `write_handoff_file(path, content, *, overwrite)` in `src/coding_agent_performance/trace/handoff_output.py` using `~` expansion and a non-following destination `lstat`; do not call `Path.resolve()` on the destination
- [ ] T004 Implement parent-directory checks in `src/coding_agent_performance/trace/handoff_output.py`: parent must exist and be a directory; do not `mkdir`; do not chmod the parent; emit the contract messages from `specs/004-persist-handoff-safely/contracts/handoff-file-output.md`
- [ ] T005 Implement exclusive sibling-temp create (`O_CREAT|O_EXCL`), UTF-8 write, flush, `fsync`, POSIX `chmod 0o600`, exclusive no-overwrite publish (`os.link` on POSIX, `os.rename` on Windows; never `os.replace` in that branch), and `os.replace` only when `overwrite=True` in `src/coding_agent_performance/trace/handoff_output.py`; `unlink` the temp on any failure
- [ ] T006 Assert in `tests/test_handoff_output.py` that destination symlinks (including dangling) and directories fail even when `overwrite=True`, that an existing regular file fails when `overwrite=False` with `Handoff file already exists: {basename}`, and that no absolute path appears in `HandoffOutputError` messages

---

## Phase 3: User Story 1 - Persist a compact handoff to an explicit local file (Priority: P1)

**Goal**: `--output PATH` writes the existing text or JSON representation; omitting it leaves stdout unchanged.

**Independent Test**: Compare stdout-only runs with file runs on synthetic captures for both formats.

### Tests

- [ ] T007 [P] [US1] Add CLI tests in `tests/test_handoff.py` proving text and JSON stdout without `--output` remain identical to current behavior and create no extra files
- [ ] T008 [P] [US1] Add CLI tests in `tests/test_handoff.py` that write `--output` for `--format text` and `--format json` into a temporary directory and assert file bytes equal a stdout run of the same capture and format, including the trailing newline, and that the file run's stdout has no handoff body

### Implementation

- [ ] T009 [US1] Add `--output` to `capt trace handoff` in `src/coding_agent_performance/trace/cli.py`; render once with existing `render_handoff_text` / `render_handoff_json`; write to stdout when `--output` is omitted; call `write_handoff_file(..., overwrite=False)` when present
- [ ] T010 [US1] Map `HandoffOutputError` to stderr and exit 1 in `src/coding_agent_performance/trace/cli.py` without a traceback, without changing `handoff_capture_or_fail()`, and without broadening `handoff_from_summary()`

**Checkpoint**: Create-if-absent file output is independently testable

---

## Phase 4: User Story 2 - Refuse unsafe writes and overwrite only when asked (Priority: P2)

**Goal**: Existing files, destination symlinks, directories, and missing parents fail closed; `--force` replaces a regular file only.

**Independent Test**: Exercise the contract table in `specs/004-persist-handoff-safely/contracts/handoff-file-output.md` through the CLI.

### Tests

- [ ] T011 [P] [US2] Add CLI tests in `tests/test_handoff.py` for refuse-overwrite without `--force`, `--force` replacement of a regular file, and `--force` without `--output` printing `Provide --output with --force.`
- [ ] T012 [P] [US2] Add CLI tests in `tests/test_handoff.py` for destination symlink, destination directory, missing parent, and non-directory parent; assert non-zero exit, unchanged destination, no created parents, no leftover sibling temp, no traceback, and no absolute path on stderr

### Implementation

- [ ] T013 [US2] Add `--force` to `capt trace handoff` in `src/coding_agent_performance/trace/cli.py`, reject `--force` without `--output`, and pass `overwrite=force` into `write_handoff_file()` in `src/coding_agent_performance/trace/handoff_output.py`
- [ ] T014 [US2] Confirm in `tests/test_handoff.py` that `--latest` remains invalid, extra capture arguments still fail, capture-input errors stay payload-free, and file output of a capture containing synthetic prompt/path/payload markers does not leak those strings into the file or stderr

**Checkpoint**: Safety contract is independently testable

---

## Phase 5: User Story 3 - Keep the README aligned with the public CLI (Priority: P3)

**Goal**: README documents compare, handoff, and file output, and no longer contradicts shipped insights.

**Independent Test**: Diff README claims against Typer `--help` and this contract.

### Tests

- [ ] T015 [P] [US3] Add focused assertions in `tests/test_readme_commands.py` that `README.md` documents `capt trace compare`, `capt trace handoff`, `--output`, and `--force`, and that it no longer claims this version does not produce insights

### Implementation

- [ ] T016 [US3] Audit `README.md` against `src/coding_agent_performance/cli.py` and `src/coding_agent_performance/trace/cli.py`; add concise compare and handoff sections (text/JSON, default stdout, `--output`, `--force`) using synthetic relative paths only
- [ ] T017 [US3] Correct README introduction, "What this version includes", "Current commands", and roadmap wording in `README.md` so shipped insight, comparison, and handoff capabilities are not described as absent or future-only; do not copy JSON schemas or rewrite unrelated sections

**Checkpoint**: README can be reviewed against the public CLI without running file-write tests

---

## Phase 6: Polish

- [ ] T018 [P] Replace stdout-only handoff claims with optional explicit `--output` in `docs/product.md`, `docs/architecture.md`, `docs/summary-format.md`, and `docs/development.md` without duplicating this specification or changing JSON v1
- [ ] T019 [P] Confirm in `tests/test_handoff.py` or existing tests that `capt trace summarize`, `capt trace compare`, collect, list, and doctor behavior is unchanged and that handoff JSON v1 key order is unchanged
- [ ] T020 [P] Confirm no adapter, collector, capture-schema, insight-threshold, comparison-schema, or `CaptureWriter` API generalization in `src/coding_agent_performance/adapters/claude_code/`, `src/coding_agent_performance/trace/capture.py`, `src/coding_agent_performance/trace/insights.py`, `src/coding_agent_performance/trace/comparison.py`, and `src/coding_agent_performance/trace/storage.py`
- [ ] T021 Run `uv sync --frozen --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest`, `uv build --clear`, `git diff --check`, smoke `uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl`, the same command with `--format json`, and a synthetic `--output` write into a temporary path

## Dependencies

```text
T001
  -> T002 -> T003 -> T004 -> T005 -> T006
  -> T007, T008 (after T006)
  -> T009 -> T010
  -> T011, T012 (after T010)
  -> T013 -> T014
  -> T015, T016, T017 (README can start after T001; keep after CLI flags exist so the documented contract matches code)
  -> T018, T019, T020
  -> T021
```

User Story 1 depends on the foundational writer. User Story 2 depends on User Story 1 CLI wiring so `--output` already exists. User Story 3 is documentation and can be drafted in parallel after flags are pinned, then checked against the implemented help text.

## Parallel execution examples

- After T006: T007 and T008 can proceed in parallel.
- After T010: T011 and T012 can proceed in parallel.
- After T014: T015 can proceed in parallel with T016/T017 drafting, then T018–T020.

## Implementation strategy

MVP is Phase 2 plus User Story 1: explicit `--output` create-if-absent with byte-identical text/JSON. User Story 2 then locks overwrite and symlink safety, including `--force`. User Story 3 synchronizes README. Do not add `--latest`, Markdown, parent-directory creation, JSON v1 fields, or a generic writer framework.

## Notes

- Issue #58 is the existing operational Agent Task. After this specification review PR is merged, #58 is reduced to an operational envelope pointing at these artifacts. A human may then apply `agent:ready`.
- Do not change handoff JSON v1 or the compact allowlist.
- Do not reuse `CaptureWriter` or `CaptureStorageError`.
- Do not print absolute paths on success or failure.
- Do not follow destination symlinks.
- Do not create missing parent directories.
- Do not chmod operator-selected parent directories.
- `/speckit.taskstoissues` and `/speckit.implement` are not part of the CAPT production lifecycle.
