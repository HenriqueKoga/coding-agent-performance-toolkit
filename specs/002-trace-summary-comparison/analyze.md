# Analyze: Compare two trace summaries

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Coverage

| Spec requirement | Plan | Tasks |
| --- | --- | --- |
| Exactly two explicit capture inputs | Yes | T017-T019 |
| Reuse existing `summarize_capture()` | Yes | T019 |
| Fixed eight-metric comparison slots | Yes | T013-T016, T022-T024 |
| Observed zero distinct from unavailable telemetry | Yes | T003-T012 |
| Per-metric provider-neutral availability | Yes | T002-T012 |
| No numeric delta when either side is unavailable | Yes | T015-T016 |
| `delta = candidate - baseline` when comparable | Yes | T015 |
| No percentage delta in v1 | Yes | Notes / rendering contract |
| Equivalent text and JSON evidence | Yes | T021-T025 |
| No winner, score, significance, or recommendation | Yes | delivery constraints / Notes |
| Local-only and no persistence | Yes | T019, T027 |
| Existing trace-summary public schema/version unchanged | Yes | T011-T012, T027 |
| Bounded memory preserved | Yes | availability boundary / T010 |
| Synthetic tests and full validation | Yes | T003-T008, T017-T018, T022-T023, T028-T029 |

## Constitution

No conflicts identified after the availability amendment.

The original draft incorrectly assumed every integer zero in `TraceSummary` represented observed zero. Review identified that several current aggregation paths intentionally default missing telemetry to numeric zero. Treating those values as directly comparable would manufacture evidence, violating CAPT's deterministic-first principle.

The revised design remains local-first, deterministic, provider-neutral, privacy-allowlisted, and bounded-memory. It introduces no LLM, runtime dependency, database, service, generic experiment framework, or adapter change.

The only intentional internal expansion is fixed-size provider-neutral availability metadata needed to preserve evidence semantics. Existing `capt trace summarize` public text/JSON output and `TraceSummary.schema_version` remain unchanged.

## Source-of-truth check

The artifacts have distinct authority:

- `spec.md` is the behavioral contract and acceptance source of truth.
- `plan.md` is the technical design.
- `tasks.md` is implementation decomposition only.
- `analyze.md` is review evidence and is not normative.
- GitHub Issue #36 remains the operational lifecycle record.

No contradictory normative requirements remain across the three source artifacts.

## Review findings resolved

Four P1 review threads identified one shared design defect: availability had been lost before comparison.

The revised specification resolves the defect uniformly instead of adding special cases:

1. **Model requests**: metrics-only or no-usage captures no longer imply an observed request count of zero.
2. **Cost and tokens**: estimated cost, input tokens, and output tokens have independent availability; partial OTEL metric coverage cannot manufacture zeros for missing series.
3. **Tool metrics**: captures without tool-event coverage cannot report observed zero tool calls/failures, and result bytes require complete result-size evidence for counted calls.
4. **Compactions**: captures without relevant lifecycle/log coverage cannot report observed zero compactions.
5. **Comparison**: each of the eight slots remains present, but delta exists only when both baseline and candidate have observed evidence for that metric.
6. **Public compatibility**: availability is internal normalized evidence for this feature and must not alter existing trace-summary rendering or schema version.

This preserves the original product goal while preventing false before/after conclusions.

## Decisions resolved during specification

1. **Inputs**: exactly two explicit CAPT JSONL capture paths.
2. **CLI**: `capt trace compare BASELINE CANDIDATE` with `--format text|json`.
3. **Metrics**: exactly eight fixed comparison slots.
4. **Availability**: tracked independently per metric from normalized evidence, never inferred from numeric values.
5. **Delta**: signed absolute integer delta only when both sides are available.
6. **Unavailable state**: fixed slot remains present; unavailable values/delta are null/absent according to the explicit comparison schema.
7. **Percentages**: omitted from v1.
8. **Comparison model**: concrete immutable `TraceComparison` plus one small `MetricComparison`; no registry or experiment abstraction.
9. **Privacy**: no capture paths, identifiers, raw payloads, or provider-specific provenance in comparison output.

## Ambiguity

No `[NEEDS CLARIFICATION]` blocker remains.

Implementation must determine the exact existing accumulator location for each availability flag after inspecting normalized telemetry structures, but it may not weaken the behavioral rule: a metric is available only from positive evidence that the relevant telemetry was observed and complete enough for that aggregate.

If an exact availability condition cannot be established from normalized data without changing provider adapters or the capture schema, implementation must stop for human review rather than guess.

## Duplication

The detailed acceptance criteria should not be copied into Issue #36 after these artifacts are merged. The Issue should remain a thin operational envelope linking to this directory, carrying risk/lifecycle status, validation gate, and stop conditions.

Product/architecture/public-format docs added during implementation should document the resulting stable product contract, not restate the entire feature specification.

## Gaps

None block specification review.

One implementation stop condition remains intentionally explicit: if provider-neutral availability cannot be derived within existing normalized aggregation boundaries, do not introduce provider-specific comparison logic or silently fall back to numeric zero.

## Readiness

The specification is ready for human review after addressing the P1 availability feedback.

After the specification branch is approved and merged:

1. reduce Issue #36 to the operational envelope referencing `specs/002-trace-summary-comparison/`;
2. retain exactly one `risk:medium` label;
3. keep `needs:human-review` until the human explicitly approves implementation;
4. then apply `agent:ready` to dispatch Cursor through the existing lifecycle.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.