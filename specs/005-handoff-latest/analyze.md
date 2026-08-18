# Analyze: Support `--latest` for trace handoff

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Supporting**: `research.md`, `data-model.md`, `contracts/handoff-latest-selection.md`, `quickstart.md`, `checklists/requirements.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature, does not rewrite Issue #63, and does not change Issue lifecycle labels.

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | --- | --- | --- | --- | --- |
| D1 | Duplication | LOW | `spec.md`, `plan.md`, `contracts/handoff-latest-selection.md` | The selector error table appears in three files. | Keep the contract file as the implementation checklist. Spec and plan should stay aligned with those exact strings. |
| A1 | Ambiguity | LOW | `plan.md` extra-argument handling | After `--latest` becomes a real option, Typer extra-args behavior may change from the current unknown-option trap. | T007 already requires extra positional paths to keep `Provide exactly one capture path.` Implement that check explicitly rather than relying on leftover `ctx.args` behavior. |
| U1 | Underspecification | LOW | historical `004` contract | `specs/004-persist-handoff-safely/contracts/handoff-file-output.md` still says `--latest` is not part of the command. | Leave 004 historical. Implementers should read `005` as the later CLI shape and 004 as the unchanged writer safety contract. |
| I1 | Inconsistency | LOW | `spec.md` FR-016 vs `003`/`004` | Earlier handoff specs forbade `--latest`; this increment allows it on handoff only. | This is an intentional later exception, recorded in Assumptions. Do not patch 003/004 FR text. |

No CRITICAL or HIGH findings.

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
| --- | --- | --- | --- |
| FR-001 explicit `--latest` selector | Yes | T004, T005, T006 | Not implied when both selectors are absent |
| FR-002 explicit `CAPTURE` unchanged | Yes | T005, T006, T018 | Including `--format` / `--output` / `--force` |
| FR-003 mutually exclusive selectors | Yes | T002, T011 | Exact summarize string |
| FR-004 neither selector refused | Yes | T002, T011 | Exact summarize string |
| FR-005 reuse summarize/list discovery | Yes | T003, T013 | `latest_capture()` only; no handoff scan |
| FR-006 same file as summarize `--latest` | Yes | T004, T013 | Includes tie-break and symlink exclusion |
| FR-007 `--latest --format json`; JSON v1 unchanged | Yes | T008, T010, T018 | |
| FR-008 `--latest --output PATH` | Yes | T009, T010 | Byte identity with selected stdout |
| FR-009 `--latest --output PATH --force` | Yes | T009, T010 | Non-regular destinations still refused |
| FR-010 text rendering unchanged | Yes | T004, T005 | Apart from which capture is selected |
| FR-011 extra positional paths | Yes | T007, T011 | |
| FR-012 latest and capture-input errors | Yes | T003, T012, T006 | `handoff_capture_or_fail()` after selection |
| FR-013 no new payload/path exposure | Yes | T004, T012, T014 | |
| FR-014 other commands unchanged; compare has no `--latest` | Yes | T014, T018 | |
| FR-015 smallest shared helper; no framework | Yes | T003, T010, T018 | Helper stays in `trace/cli.py` |
| FR-016 README/docs match additive CLI | Yes | T015, T016, T017 | |
| SC-001 `--latest` text matches explicit path | Yes | T004 | |
| SC-002 summarize and handoff select the same file | Yes | T013 | |
| SC-003 mixed or missing selectors fail closed | Yes | T011 | |
| SC-004 JSON identical for either selector | Yes | T008 | |
| SC-005 file bytes and writer safety | Yes | T009 | |
| SC-006 no paths/payloads in output or errors | Yes | T012, T014 | |
| SC-007 help and README document `--latest` | Yes | T005, T015, T017 | |
| US1 latest text handoff | Yes | T004–T007 | |
| US2 JSON and file output combinations | Yes | T008–T010 | |
| US3 fail-closed selection and agreement | Yes | T011–T014 | |
| Smoke help/explicit path/JSON | Yes | T019 | |

**Constitution Alignment Issues:** none

**Unmapped Tasks:** T001 is setup inspection. T019 is validation delivery work required by AGENTS.md, not orphaned product scope. T002 is a summarize regression net around the helper extraction.

**Metrics:**

- Total Requirements: 16 functional + 7 success criteria
- Total Tasks: 19
- Coverage % (requirements with >=1 task): 100%
- Ambiguity Count: 1 (LOW)
- Duplication Count: 1 (LOW)
- Critical Issues Count: 0

## Constitution

No conflicts identified.

The design remains local-first: `--latest` reads the existing default capture directory and does not send data off-machine. Deterministic evidence is unchanged; selection is the observed newest eligible file, and the handoff is the existing compact extract. Privacy stays allowlisted, with selector errors reused from summarize so discovery does not grow a leaky dialect. Provider-neutral `TraceHandoff` is untouched. Bounded memory is preserved because latest selection keeps a single running maximum rather than materializing a listing or raw envelopes.

The shared helper is a concrete extraction of `resolve_summarize_capture()` in `trace/cli.py`. It does not become a discovery registry, does not change `latest_capture()` ordering, and adds no runtime dependency or LLM.

Human approval remains the gate: after merge, automation may index these artifacts on Issue #63, and a human may apply `agent:ready`. Spec Kit does not apply `agent:ready` or `risk:*`. The Issue body stays the original brief.

## Next Actions

No CRITICAL or HIGH issues. The specification is consistent enough for human review of this specification-only PR.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.

If a reviewer rejects a pinned default (especially reuse of summarize error strings or leaving 003/004 historical), update `spec.md` first, then `plan.md`/`tasks.md`, and re-run this analysis.

## Remediation

No remediation edits are required for the LOW findings. They are implementer notes, not blockers.
