# Analyze: Persist compact trace handoff safely

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Supporting**: `research.md`, `data-model.md`, `contracts/handoff-file-output.md`, `quickstart.md`, `checklists/requirements.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | --- | --- | --- | --- | --- |
| D1 | Duplication | LOW | `spec.md`, `plan.md`, `contracts/handoff-file-output.md` | The `--output`/`--force` error table appears in three files. | Keep the contract file as the implementation checklist. Spec and plan should stay aligned with those exact strings. |
| A1 | Ambiguity | LOW | `plan.md` CLI orchestration | Text stdout still uses `typer.echo` while JSON uses `sys.stdout.write`. File identity is defined as matching those existing stdout bytes. | Do not invent a third newline convention. Tests must compare file bytes to a real stdout run, not to a reconstructed string that skips `typer.echo`. |
| U1 | Underspecification | LOW | `tasks.md` T015 | README assertions check command names and insight-contradiction phrases, not every optional flag already documented for collect/list/summarize. | Keep T015 focused on compare/handoff/file-output plus insight-status fixes. T016 still audits the full Typer surface by hand. |

No CRITICAL or HIGH findings.

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
| --- | --- | --- | --- |
| FR-001 stdout default; `--format` unchanged | Yes | T007, T009, T019 | |
| FR-002 explicit `--output PATH` | Yes | T008, T009 | No default directory or discovery |
| FR-003 omit `--output`: stdout, no file | Yes | T007 | |
| FR-004 `--output` success: file, empty stdout | Yes | T008, T009 | |
| FR-005 byte identity including newline | Yes | T008 | Compared to a stdout run |
| FR-006 refuse existing regular file | Yes | T006, T011 | |
| FR-007 `--force` only with `--output`; regular file only | Yes | T011, T013 | |
| FR-008 missing/non-directory parent; no mkdir | Yes | T004, T012 | |
| FR-009 destination symlink refused even with `--force` | Yes | T006, T012 | Includes dangling |
| FR-010 sibling temp, exclusive/atomic publish, cleanup | Yes | T002, T005, T012 | POSIX `link`, Windows `rename`, `--force` uses `replace` |
| FR-011 POSIX `0600`; no parent chmod | Yes | T002, T004, T005 | |
| FR-012 concise path-free payload-free errors | Yes | T006, T010, T012, T014 | Basename allowed |
| FR-013 no allowlist broadening | Yes | T010, T014, T019 | `handoff_from_summary()` unchanged |
| FR-014 no generic persistence/new dependency | Yes | T003, T020 | New module is handoff-specific |
| FR-015 other commands and JSON v1 unchanged; no `--latest` | Yes | T014, T019, T020 | |
| FR-016 README compare + handoff + file output | Yes | T015, T016 | |
| FR-017 README status/insight contradictions | Yes | T015, T017 | |
| FR-018 Typer surface is README authority | Yes | T016 | |
| SC-001 file bytes predictable from stdout | Yes | T008 | |
| SC-002 omitting `--output` indistinguishable | Yes | T007 | |
| SC-003 existing file unchanged without `--force` | Yes | T006, T011 | |
| SC-004 no truncated dest or leftover temp | Yes | T002, T005, T012 | |
| SC-005 no paths/payloads in file or errors | Yes | T006, T012, T014 | |
| SC-006 POSIX `0600` | Yes | T002, T005 | |
| SC-007 README compare/handoff/insights | Yes | T015, T016, T017 | |
| US1 persist to explicit file | Yes | T007–T010 | |
| US2 unsafe-write refusal and `--force` | Yes | T011–T014 | |
| US3 README alignment | Yes | T015–T017 | |
| Smoke stdout/JSON/`--output` | Yes | T021 | |

**Constitution Alignment Issues:** none

**Unmapped Tasks:** T001 is setup inspection. T018 and T021 are contract-doc and validation delivery work required by AGENTS.md, not orphaned product scope.

**Metrics:**

- Total Requirements: 18 functional + 7 success criteria
- Total Tasks: 21
- Coverage % (requirements with >=1 task): 100%
- Ambiguity Count: 1 (LOW)
- Duplication Count: 1 (LOW)
- Critical Issues Count: 0

## Constitution

No conflicts identified.

The design remains local-first: the operator names a local path, and nothing is sent off-machine. Deterministic evidence is unchanged; the file is the existing compact extract. Privacy stays allowlisted, with stricter path-free file-write errors than collect's current resolved-path collision message. Provider-neutral `TraceHandoff` is untouched. Bounded memory is preserved because only the already-rendered string is written.

The new module is a concrete handoff writer. It does not become a generic artifact registry, does not extend `CaptureWriter` into a persistence framework, and adds no runtime dependency or LLM.

Human approval remains the gate: after merge, Issue #58 is reduced to an operational envelope pointing at these artifacts, and a human may apply `agent:ready`. Spec Kit does not apply `agent:ready` or `risk:*`.

## Cross-artifact consistency

- Spec, plan, and contract agree on `--output`, `--force` only with `--output`, byte-identical files, silent stdout on successful file write, refuse destination symlinks, no parent creation, and POSIX `0600`.
- JSON v1 is explicitly not versioned here; tasks forbid `handoff.py` allowlist changes.
- README work is bounded to current public Typer commands plus contradiction fixes. Product/architecture/summary-format stdout-only sentences are updated because they would otherwise become false.
- Issue #58 is the existing operational Agent Task. This specification PR does not dispatch implementation, mutate #58, or apply `agent:ready`.

## Next actions

No CRITICAL or HIGH issues. The specification is ready for a specification-only review PR.

Do not run `/speckit.implement` or `/speckit.taskstoissues`. After human merge, #58 remains the operational Agent Task and is reduced to an envelope pointing at these artifacts. A human may then apply `agent:ready`.

## Remediation

No required edits. Optional later polish: keep the three error tables identical if any message string changes during implementation review.
