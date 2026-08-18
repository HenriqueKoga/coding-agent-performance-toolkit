# Analyze: Compare two trace summaries

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Coverage

| Spec requirement | Plan | Tasks |
| --- | --- | --- |
| Exactly two explicit capture inputs | Yes | T017-T021 |
| Reuse existing `summarize_capture()` | Yes | T020-T021 |
| Same-file inputs use one immutable snapshot | Yes | T018, T021 |
| Fixed eight-metric comparison slots | Yes | T013-T016, T024-T026 |
| Observed zero distinct from unavailable telemetry | Yes | T003-T012 |
| Per-metric provider-neutral availability | Yes | T002-T012 |
| No numeric delta when either side is unavailable | Yes | T015-T016 |
| `delta = candidate - baseline` when comparable | Yes | T015 |
| No percentage delta in v1 | Yes | Notes / rendering contract |
| Equivalent text and JSON evidence | Yes | T023-T027 |
| Existing trace-summary public schema/version unchanged | Yes | T011-T012, T029 |
| Bounded memory preserved | Yes | availability boundary / T010 |
| Synthetic tests and full validation | Yes | T003-T008, T017-T019, T024-T025, T030-T031 |

## Constitution

No conflicts identified after review amendments.

The original draft incorrectly assumed every integer zero in `TraceSummary` represented observed zero. Review established that several aggregation paths default missing telemetry to numeric zero. Treating those values as directly comparable would manufacture deterministic evidence.

A later review also identified that summarizing the same mutable capture twice can create false non-zero deltas if events are appended between reads. The revised plan therefore requires filesystem-identical inputs to reuse one immutable summary snapshot.

The design remains local-first, deterministic, provider-neutral, privacy-allowlisted, and bounded-memory. It introduces no LLM, runtime dependency, database, service, generic experiment framework, or adapter change.

## Source-of-truth check

- `spec.md`: behavioral authority
- `plan.md`: technical design
- `tasks.md`: implementation decomposition
- `analyze.md`: review evidence only
- Issue #36: operational lifecycle record

No contradictory normative requirements remain.

## Review findings resolved

Five review threads exposed two underlying correctness requirements.

### Metric availability

Four P1 threads showed that missing telemetry can currently appear as numeric zero. The revised design resolves this uniformly:

1. request count requires observed request-count evidence;
2. cost/input/output token availability is independent per metric;
3. tool calls/failures require tool-event coverage;
4. tool result bytes require complete result-size evidence for counted calls;
5. compactions require relevant lifecycle/log coverage;
6. if either side is unavailable, the fixed comparison slot remains present but has no numeric delta;
7. existing `trace summarize` public rendering/schema version remains unchanged.

### Same-file snapshot consistency

One P2 thread showed that two sequential reads of the same actively growing capture can differ. The revised technical contract requires:

1. determine whether baseline and candidate resolve to the same filesystem object;
2. summarize that object exactly once;
3. reuse the same immutable summary for both sides;
4. do not rely on path-string equality alone, so aliases/symlinks are handled correctly where supported;
5. keep resolved absolute paths out of output and errors.

This preserves the explicit same-file zero-delta guarantee without requiring captures to be globally immutable.

## Ambiguity

No `[NEEDS CLARIFICATION]` blocker remains.

Implementation must establish exact availability conditions from normalized evidence within existing aggregation boundaries. It may not weaken the behavioral rule or infer availability from numeric values.

If provider-neutral availability cannot be derived without changing provider adapters or the capture schema, implementation must stop for human review rather than guess.

## Gaps

None block specification review.

## Readiness

The specification is ready for human review after addressing the availability and same-file snapshot feedback.

After merge:

1. reduce Issue #36 to the operational envelope referencing `specs/002-trace-summary-comparison/`;
2. retain exactly one `risk:medium` label;
3. keep `needs:human-review` until explicit human approval;
4. then apply `agent:ready` to dispatch Cursor.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.