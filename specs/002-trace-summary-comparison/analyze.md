# Analyze: Compare two trace summaries

**Date**: 2026-08-17

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Coverage

| Spec requirement | Plan | Tasks |
| --- | --- | --- |
| Exactly two explicit capture inputs | Yes | T005, T007 |
| Reuse existing `summarize_capture()` | Yes | T007 |
| Fixed eight-metric allowlist | Yes | T002-T004, T010-T012 |
| `delta = candidate - baseline` | Yes | T004 |
| No percentage delta in v1 | Yes | Notes / rendering contract |
| Equivalent text and JSON evidence | Yes | T009-T013 |
| No winner, score, significance, or recommendation | Yes | delivery constraints / Notes |
| Provider-neutral comparison over `TraceSummary` | Yes | T003, T015 |
| Local-only and no persistence | Yes | T007, T015 |
| Concise privacy-safe invalid-input errors | Yes | T006, T008 |
| Existing summary/capture/insight contracts unchanged | Yes | T008, T015 |
| Bounded memory preserved | Yes | design notes / T015 |
| Synthetic tests and full validation | Yes | T005-T006, T010-T011, T016-T017 |

## Constitution

No conflicts identified.

The proposed design remains local-first, deterministic, provider-neutral, privacy-allowlisted, and bounded-memory. It introduces no LLM, runtime dependency, database, service, generic experiment framework, or adapter change.

The new public surface is explicit: one additive CLI command plus a separate comparison JSON contract. Existing `TraceSummary.schema_version` is not changed by this feature.

## Source-of-truth check

The artifacts intentionally have distinct authority:

- `spec.md` is the behavioral contract and acceptance source of truth.
- `plan.md` is the approved technical design for satisfying the spec.
- `tasks.md` is implementation decomposition only.
- `analyze.md` is review evidence and is not normative.
- GitHub Issue #36 should contain lifecycle/risk/operational information and references to these artifacts, not duplicate their detailed requirements.

No contradictory normative requirements were found across the three source artifacts.

## Decisions resolved during specification

The previous Issue left several implementation choices open. This specification resolves them to keep v1 narrow:

1. **Inputs**: compare exactly two explicit CAPT JSONL capture paths, not precomputed summaries and not `--latest` discovery.
2. **CLI**: `capt trace compare BASELINE CANDIDATE` with the existing `--format text|json` convention.
3. **Metrics**: exactly eight existing stable integer aggregates, with fixed ordering.
4. **Delta**: signed absolute integer delta only, defined as `candidate - baseline`.
5. **Percentages**: omitted from v1, eliminating zero-baseline percentage semantics.
6. **Comparison model**: a concrete immutable `TraceComparison` plus a small shared `MetricDelta`; no registry or experiment abstraction.
7. **Privacy**: comparison output never includes input paths; errors remain basename-only if a filename is needed.

These decisions are compatible with the existing Issue intent and reduce ambiguity rather than expand scope.

## Ambiguity

No `[NEEDS CLARIFICATION]` blocker remains.

Implementation may choose the exact placement/name of focused rendering test files to match the current test organization. It may also minimally extract existing capture-error mapping if concrete duplication appears when adding the second summary call. Neither choice changes behavior or architecture.

## Duplication

The detailed acceptance criteria should not be copied into Issue #36 after these artifacts are merged. The Issue should become an operational envelope linking to this directory, carrying risk/lifecycle status, validation gate, and stop conditions.

Product/architecture/public-format docs added during implementation should document the resulting stable product contract, not restate the entire feature specification.

## Gaps

None that block specification review.

One process prerequisite remains: these artifacts must be reviewed and merged to `main` before Issue #36 receives `agent:ready`, because the implementation agent starts from `main` and must be able to read the approved source-of-truth specification.

## Readiness

The specification is ready for human review.

After the specification branch is approved and merged:

1. reduce Issue #36 to the operational envelope that references `specs/002-trace-summary-comparison/`;
2. retain exactly one `risk:medium` label;
3. keep `needs:human-review` until the human explicitly approves implementation;
4. then apply `agent:ready` to dispatch Cursor through the existing lifecycle.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.