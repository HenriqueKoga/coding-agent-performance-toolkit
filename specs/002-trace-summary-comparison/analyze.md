# Analyze: Compare two trace summaries

**Date**: 2026-08-18

**Artifacts**: `spec.md`, `plan.md`, `tasks.md`

**Constitution**: `.specify/memory/constitution.md`

This is a read-only consistency assessment of the proposed specification artifacts. It does not implement the feature and does not change Issue lifecycle labels.

## Coverage

| Spec requirement | Plan | Tasks |
| --- | --- | --- |
| Exactly two explicit capture inputs | Yes | T019-T023 |
| Reuse existing `summarize_capture()` | Yes | T022-T023 |
| Same-file inputs use one immutable snapshot | Yes | T020, T023 |
| Fixed eight-metric comparison slots | Yes | T015-T018, T026-T029 |
| Observed zero distinct from unavailable telemetry where coverage can prove zero | Yes | T003-T014 |
| `model_requests` with zero API-request events is unavailable in v1 | Yes | T004, T009, T019 |
| Per-metric provider-neutral availability | Yes | T002-T014 |
| API usage field presence preserved through normalization | Yes | T003, T010 |
| Tool-failure completeness requires valid success status for every counted tool event | Yes | T006, T010, T012 |
| No numeric delta when either side is unavailable | Yes | T017-T018 |
| `delta = candidate - baseline` when comparable | Yes | T017 |
| Complete mandatory JSON v1 contract | Yes | T026-T029 |
| Equivalent text and JSON evidence | Yes | T025-T030 |
| Existing trace-summary public schema/version unchanged | Yes | T013-T014, T033 |
| Bounded memory preserved | Yes | availability boundary / T012 |
| Synthetic tests and full validation | Yes | T003-T009, T019-T021, T026-T028, T034-T035 |

## Constitution

No conflicts identified after review amendments.

The original draft incorrectly assumed every integer zero in `TraceSummary` represented observed zero. Review established that several aggregation paths default missing telemetry to numeric zero. Treating those values as directly comparable would manufacture deterministic evidence.

A later review identified that API-request normalization itself currently erases presence for some usage attributes by coercing absent/invalid values to zero. The revised specification therefore explicitly approves narrow additive provider-adapter metadata that preserves presence/absence of already-supported API request cost/input/output attributes in the normalized provider-neutral record. This is not approval for new telemetry mappings or provider-specific comparison logic.

The same completeness problem exists for tool failures: current normalization deliberately turns a missing or invalid `success` attribute into `success=True` for established summary behavior. Tool-event coverage can therefore prove that tool calls were observed, but cannot by itself prove a complete failure count. The revised design preserves success-status validity as additive internal evidence, leaves existing success coercion intact, and marks the comparison failure slot unavailable if any counted tool event lacks valid status evidence.

A subsequent review exposed a second-order contradiction: the revised success criteria and task list still required an observed zero for every slot, but `model_requests` has no independent zero-request coverage signal in the current telemetry contract. In v1, at least one normalized API-request event makes `model_requests` available with a positive count; zero API-request events means unavailable, not observed zero. The specification now states that explicitly and limits observed-zero assertions to metrics with affirmative coverage capable of proving zero.

Another review identified that summarizing the same mutable capture twice can create false non-zero deltas if events are appended between reads. Filesystem-identical inputs therefore reuse one immutable summary snapshot.

Finally, review found the comparison JSON contract underspecified. The revised plan makes the entire v1 structure normative: `schema_version: 1`, exactly two top-level keys, exactly eight ordered metric keys, and exactly four ordered fields per metric slot.

The design remains local-first, deterministic, provider-neutral at the domain/comparison boundary, privacy-allowlisted, and bounded-memory. It introduces no LLM, runtime dependency, database, service, generic experiment framework, or broader adapter redesign.

## Source-of-truth check

- `spec.md`: behavioral authority
- `plan.md`: technical design, including the normative JSON v1 schema
- `tasks.md`: implementation decomposition
- `analyze.md`: review evidence only
- Issue #36: operational lifecycle record

No contradictory normative requirements remain.

## Review findings resolved

### Metric availability and normalization presence

The revised design resolves the zero-vs-unavailable problem without inventing negative evidence:

1. request count requires at least one observed normalized API-request event; no request event means unavailable in v1, not observed zero;
2. cost/input/output token availability is independent per metric;
3. existing API request cost/input/output normalization preserves field presence so missing attributes cannot become indistinguishable zeros;
4. tool calls require tool-event coverage, while tool failures additionally require valid success status for every counted tool event;
5. tool result bytes require complete result-size evidence for counted calls;
6. compactions require relevant lifecycle/log coverage;
7. observed zero is valid only for metrics whose telemetry supplies affirmative coverage proving zero rather than mere event absence;
8. if either side is unavailable, the fixed comparison slot remains present but has `available=false` and null numeric fields;
9. existing `trace summarize` public rendering/schema version remains unchanged.

The provider-adapter approval is deliberately narrow: preserve information already present at the adapter boundary for API usage and tool-success validity, without changing existing coerced values or summary behavior. New provider telemetry mappings still require human review. Introducing a new signal solely to prove zero model requests is outside v1.

### Same-file snapshot consistency

When baseline and candidate resolve to the same filesystem object:

1. summarize that object exactly once;
2. reuse the same immutable summary for both sides;
3. do not rely on path-string equality alone;
4. keep resolved absolute paths out of output and errors.

### Comparison JSON v1

The public JSON contract is fully specified and testable:

1. top-level keys: `schema_version`, `metrics`;
2. `schema_version` is integer `1`;
3. `metrics` contains exactly the eight documented snake_case keys in fixed order;
4. each metric contains exactly `available`, `baseline`, `candidate`, `delta` in fixed order;
5. available slots use integers; unavailable slots use `null` for all three numeric fields;
6. no additional metadata is part of v1.

## Ambiguity

No `[NEEDS CLARIFICATION]` blocker remains.

Implementation may choose exact names for internal normalized presence fields and availability DTOs to match current conventions, but it may not weaken field-presence semantics, invent zero coverage from event absence, alter the normative JSON layout, or infer availability from numeric values.

## Gaps

None block specification review.

## Readiness

The specification is ready for human review after addressing availability, normalization presence, zero-request semantics, same-file snapshot consistency, and the JSON contract.

After merge:

1. reduce Issue #36 to the operational envelope referencing `specs/002-trace-summary-comparison/`;
2. retain exactly one `risk:medium` label;
3. keep `needs:human-review` until explicit human approval;
4. then apply `agent:ready` to dispatch Cursor.

Do not run `/speckit.implement` or `/speckit.taskstoissues`.
