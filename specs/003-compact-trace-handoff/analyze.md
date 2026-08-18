# Analyze: Export compact trace handoff

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Supporting**: `research.md`, `data-model.md`, `contracts/handoff-json-v1.md`, `quickstart.md`, `checklists/requirements.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | --- | --- | --- | --- | --- |
| D1 | Duplication | LOW | `plan.md`, `contracts/handoff-json-v1.md` | The mandatory JSON v1 example and key order appear in both files. | Keep both identical. `plan.md` remains the spec-facing technical contract; the contracts file is the implementation checklist target. Do not let them drift. |
| A1 | Ambiguity | LOW | `plan.md` Rendering | Aggregate text layout (headings, spacing) is not byte-specified; insight lines must reuse existing summarize wording. | Treat text as evidence-agreement, not a second schema. JSON remains the canonical structured contract. |
| U1 | Underspecification | LOW | `tasks.md` T014 | Text rendering of `usage_source` could use the raw enum or the existing summarize labels. | Use existing summarize labels for the same enum so text cannot invent a third vocabulary. Values must still match JSON. |

No CRITICAL or HIGH findings.

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
| --- | --- | --- | --- |
| FR-001 one explicit `capt trace handoff CAPTURE` | Yes | T009, T010, T012 | Unexpected `--latest`/`--output` covered by T010 |
| FR-002 reuse existing summarization/insights | Yes | T001, T012 | Uses `summarize_capture()`, not a second parser |
| FR-003 pure summary-to-handoff transform | Yes | T002-T005, T012 | Domain module before CLI |
| FR-004 compact evidence allowlist | Yes | T004, T014, T016, T019 | Matches data-model and JSON contract |
| FR-005 independent `schema_version` 1 | Yes | T006, T016 | |
| FR-006 filename; allowlisted source; counts not content | Yes | T008, T018, T024 | Arbitrary source maps to `unknown` |
| FR-007 copy insights unchanged | Yes | T005, T009, T014 | |
| FR-008 no invented narrative | Yes | T011, T014 | |
| FR-009 JSON canonical; text default | Yes | T014-T020 | |
| FR-010 deterministic output | Yes | T017 | |
| FR-011 stdout only | Yes | T013, T010 | No `--output` |
| FR-012 local read-only | Yes | T012, T013, T023 | No persistence or network task |
| FR-013 payload-free path-free errors | Yes | T010, T012 | Handoff-specific mapping; no `summarize_or_fail()` |
| FR-014 existing summarize/compare unchanged | Yes | T015, T022, T023 | Includes existing error text |
| FR-015 exact JSON v1, no extra fields | Yes | T016, T017, T019 | |
| SC-001 predict fields from summary plus source mapping | Yes | T002-T008 | Source is allowlisted, not raw |
| SC-002 text/JSON evidence agreement | Yes | T018 | |
| SC-003 no paths, payloads, narrative, or raw source | Yes | T008, T010, T011, T018, T024 | |
| SC-004 repeated output identical | Yes | T017 | |
| SC-005 bounded memory | Yes | T003, T004 | No new accumulators |
| SC-006 existing public contracts unchanged | Yes | T022, T023 | |
| SC-007 one mandatory JSON v1 schema | Yes | T016, T019, T021 | |
| US1 compact text handoff | Yes | T009-T015 | |
| US2 canonical JSON | Yes | T016-T020 | |
| Smoke text/JSON invocations | Yes | T025 | `tests/fixtures/claude_code/synthetic-capture.jsonl` |

**Constitution Alignment Issues:** none

**Unmapped Tasks:** T001 is setup inspection and T021/T025 are documentation and validation. They are required delivery work, not orphaned product scope.

**Metrics:**

- Total Requirements: 15 functional + 7 success criteria
- Total Tasks: 25
- Coverage % (requirements with >=1 task): 100%
- Ambiguity Count: 1 (LOW)
- Duplication Count: 1 (LOW)
- Critical Issues Count: 0

## Constitution

No conflicts identified.

The design remains local-first, deterministic, provider-neutral, privacy-allowlisted, and bounded-memory. It introduces no LLM, runtime dependency, database, service, or generic artifact framework. It does not capture prompts or responses, reconstruct intent, or persist a Context Ledger.

The compact allowlist is smaller than `TraceSummary` on purpose. Copying the full summary would violate the Issue's "deliberately small set" requirement and would make the handoff a second summary schema rather than a Preserve Context extract.

Insight findings are copied, not rewritten. That keeps deterministic evidence explainable from existing summarize rules and avoids invented semantics.

Stdout-only v1 avoids a new write path. Dedicated `--output` would be an additive later command change with refuse-if-exists semantics, not a silent overwrite.

Capture `source` is sanitized in the handoff layer rather than trusted as already-safe. Envelope `source` is currently any non-empty string; echoing it would leak into an agent-facing artifact. Mapping through `{claude-code}` / `unknown` does not import the Claude Code adapter and does not change summarize output.

Handoff errors are mapped locally so unsupported `schema_version` cannot appear on stderr. `summarize_or_fail()` is not reused. Capture reader and summarize/compare error text stay unchanged.

## Source-of-truth check

- `spec.md`: behavioral authority
- `plan.md`: technical design, including the normative JSON v1 schema
- `contracts/handoff-json-v1.md`: the same JSON v1 schema for implementation tests
- `tasks.md`: implementation decomposition
- `analyze.md`: review evidence only
- Issue #37: operational lifecycle record

No contradictory normative requirements remain. The JSON examples in `plan.md` and `contracts/handoff-json-v1.md` currently match.

## Review findings resolved

Codex review on the specification PR identified three gaps. The revised artifacts pin them:

1. `capture.source` is no longer treated as inherently safe. V1 emits only `claude-code` or `unknown`.
2. Handoff CLI errors must not interpolate envelope field values, including `schema_version`. Implementation uses `summarize_capture()` plus a handoff-specific mapper, not `summarize_or_fail()`.
3. Delivery validation includes successful text and JSON smoke invocations against `tests/fixtures/claude_code/synthetic-capture.jsonl`.

## Ambiguity

No `[NEEDS CLARIFICATION]` blocker remains.

Implementation may choose exact class names inside `handoff.py` to match current conventions, but it may not widen the allowlist, dump `TraceSummary` as JSON, add `--latest`/`--output`, emit Markdown, invent narrative fields, echo arbitrary sources, print envelope field values on stderr, or change summarize/compare contracts.

## Gaps

None block specification review.

The LOW text-layout and `usage_source` label notes do not change the JSON contract or acceptance criteria.

## Readiness

The specification is ready for human review after addressing source allowlisting, handoff error sanitization, and smoke-command coverage.

After merge:

1. reduce Issue #37 to the operational envelope referencing `specs/003-compact-trace-handoff/`;
2. retain exactly one `risk:medium` label;
3. keep `needs:human-review` until explicit human approval;
4. then apply `agent:ready` to dispatch Cursor.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.

## Next Actions

- LOW findings only: keep the specification-only review PR.
- Do not run `/speckit.implement`.
- Do not run `/speckit.taskstoissues`.
- Do not mutate Issue #37 labels from this specification pass.
