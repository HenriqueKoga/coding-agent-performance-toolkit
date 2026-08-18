# Feature Specification: Compare two trace summaries

**Feature Branch**: `002-trace-summary-comparison`

**Created**: 2026-08-17

**Status**: Draft for human review

**Input**: Compare two explicit CAPT captures locally and report deterministic before/after deltas from normalized summary aggregates without treating missing telemetry as observed zero.

**Operational Issue**: [#36](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/36) is the GitHub Agent Task for implementation after this specification is approved and merged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare a baseline and candidate capture (Priority: P1)

A developer has two CAPT JSONL captures representing a baseline run and a candidate run after a workflow change. They want a compact deterministic comparison of stable aggregate metrics without a score, model judgment, or remote service.

**Why this priority**: This is the first minimal Improve-theme capability: users can inspect whether concrete observed metrics moved after a workflow change while retaining control over interpretation.

**Independent Test**: Run `capt trace compare <baseline.jsonl> <candidate.jsonl>` on synthetic captures with known aggregates and availability metadata and verify the text and JSON values.

**Acceptance Scenarios**:

1. **Given** two captures where an allowlisted metric is observed on both sides with the same value, **When** they are compared, **Then** that metric reports a delta of `0`.
2. **Given** a candidate with higher and lower observed metric values than the baseline, **When** compared, **Then** signed absolute deltas preserve direction exactly (`candidate - baseline`).
3. **Given** an observed baseline value of zero, **When** the observed candidate is non-zero, **Then** the absolute delta remains deterministic and no percentage, NaN, or Infinity is produced.
4. **Given** a metric whose telemetry is unavailable on either side, **When** compared, **Then** CAPT MUST mark that metric unavailable and MUST NOT manufacture a numeric delta from a default zero.
5. **Given** two captures from providers supported by the same provider-neutral summary contract, **When** compared, **Then** comparison uses only normalized summary values plus normalized metric-availability metadata.

### User Story 2 - Consume the same comparison as JSON (Priority: P2)

A developer or local script wants the comparison as structured JSON with the same metric values and availability semantics as text output.

**Independent Test**: Run the same synthetic pair with `--format json` and assert the structured metric data equals the text report evidence.

**Acceptance Scenarios**:

1. **Given** a valid comparison, **When** `--format json` is used, **Then** JSON contains exactly the versioned allowlisted comparison contract defined in this specification and `plan.md`.
2. **Given** identical inputs, **When** comparison is repeated, **Then** serialized field order, availability state, and numeric values are stable.

### Edge Cases

- Either input path is missing, unreadable, or not a valid CAPT capture.
- A metric has an observed value of zero on one or both captures.
- A metric is unavailable because its telemetry family, series, event, or required attribute was not observed.
- One capture has metric availability while the other does not.
- Baseline is greater than candidate, producing a negative delta.
- Candidate is greater than baseline, producing a positive delta.
- Baseline and candidate are the same file; observed metrics produce zero deltas and unavailable metrics remain unavailable.
- Input absolute paths must not be echoed in successful output or error text.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST add `capt trace compare BASELINE CANDIDATE` with exactly two explicit CAPT JSONL capture-path arguments for v1.
- **FR-002**: CAPT MUST summarize each input through the existing capture summarization path rather than duplicate OTLP decoding, normalization, or aggregation logic.
- **FR-003**: CAPT MUST expose exactly this initial comparison metric allowlist, in this stable order:
  1. total tool calls (`tools.calls`)
  2. tool failures (`tools.failures`)
  3. cumulative tool result bytes (`tools.result_bytes`)
  4. model requests (`model_usage.requests`)
  5. estimated cost in USD micros (`model_usage.estimated_cost_usd_micros`)
  6. input tokens (`model_usage.tokens.input`)
  7. output tokens (`model_usage.tokens.output`)
  8. session compactions (`sessions.compactions`)
- **FR-004**: For each metric, CAPT MUST preserve whether the value is actually observed/available; absence of telemetry MUST NOT be represented as an observed zero for comparison purposes.
- **FR-005**: When a metric is available on both baseline and candidate, it MUST report integer `baseline`, integer `candidate`, and signed integer `delta`, where `delta = candidate - baseline`.
- **FR-006**: When a metric is unavailable on either side, the comparison slot MUST remain present but MUST be explicitly unavailable; its `baseline`, `candidate`, and `delta` MUST be `null` in JSON and MUST NOT be computed from fallback zeros.
- **FR-007**: Availability MUST be tracked per metric, not inferred from the final numeric value. In particular:
  - model request availability MUST distinguish API-request-event evidence from metric-only/no-usage captures;
  - estimated cost, input tokens, and output tokens MUST be independently available only when their own source data is observed;
  - the normalization boundary MUST preserve per-field presence for API request cost/input/output attributes instead of coercing missing/invalid values into indistinguishable observed zeros;
  - tool calls/failures MUST distinguish observed tool-event coverage from captures without tool telemetry;
  - tool result bytes MUST be unavailable if the required result-size evidence is incomplete for counted tool calls;
  - session compactions MUST distinguish observed lifecycle/log coverage from captures where compaction telemetry was not captured.
- **FR-008**: V1 MUST NOT report percentage deltas.
- **FR-009**: Text and JSON MUST expose equivalent metric availability and comparison evidence.
- **FR-010**: CAPT MUST NOT declare a winner, overall regression/improvement, quality score, significance, or recommendation.
- **FR-011**: Comparison MUST be provider-neutral and operate on immutable normalized summary data plus provider-neutral availability metadata after each capture has been summarized.
- **FR-012**: Comparison MUST remain local-only and read-only; it MUST NOT persist comparison state or send data externally.
- **FR-013**: Invalid input MUST exit non-zero with concise error text, no traceback, no payload contents, and no absolute path disclosure.
- **FR-014**: Existing `trace summarize`, `trace list`, collection, summary JSON schema/version, and insight behavior MUST remain unchanged.
- **FR-015**: The implementation MAY add provider-neutral internal availability metadata to normalized event/domain records and the immutable summary domain model, but existing `trace summarize` text/JSON rendering MUST NOT expose that metadata or change its public schema in this feature.
- **FR-016**: The comparison JSON contract MUST use `schema_version: 1`, a top-level `metrics` object, and exactly the eight snake_case metric keys from FR-003 as defined in `plan.md`; no additional top-level or per-metric fields are permitted in v1.

### Key Entities

- **MetricAvailability**: Provider-neutral internal evidence stating whether one allowlisted aggregate is observed and safe to compare. It must be produced from normalized aggregation evidence, not from `value != 0`.
- **MetricComparison**: One fixed comparison slot containing availability plus nullable baseline/candidate/delta values. Numeric values are present only when the metric is comparable on both sides.
- **TraceComparison**: Immutable provider-neutral result containing the fixed ordered eight metric slots. It does not contain capture paths, provider-specific payloads, scores, or recommendations.

## CAPT constraints *(mandatory)*

### Privacy

- Successful output may contain only fixed metric names, availability state, and allowlisted aggregate integer values.
- Do not emit capture paths, session identifiers, prompts, responses, tool arguments/results, model payloads, raw telemetry, or provider-specific provenance strings.
- Input-error messages may use a safe basename if necessary, consistent with current summarization errors, but must never include an absolute path or payload content.
- Tests and fixtures remain synthetic.

### Deterministic evidence

- Evidence is limited to the eight allowlisted aggregates plus boolean/provider-neutral availability needed to avoid false zero comparisons.
- Availability is derived from whether the relevant normalized telemetry evidence was observed and complete enough for that metric.
- A numeric zero is comparable only when availability is true for that side.
- Delta is exact integer subtraction (`candidate - baseline`) only when both sides are available.
- No percentage delta, winner, score, quality inference, root cause, or recommendation is part of v1.

### Bounded memory

- Summarize each capture with the existing incremental summarizer.
- Availability tracking must be fixed-size accumulator state; do not retain raw records/events after summarization.
- Holding two finished immutable summaries plus one small fixed-size comparison result is acceptable and bounded independently of capture size.

### Provider neutrality

- Availability semantics belong to normalized evidence and aggregation, not provider-specific comparison code.
- A provider adapter MAY preserve presence/absence of fields already present in its telemetry when that information is otherwise lost during normalization; the normalized representation MUST remain provider-neutral.
- The comparison layer consumes only normalized immutable summary values and provider-neutral availability metadata.
- No new Claude Code-specific branch is permitted in comparison logic.

### Compatibility

- Adds one public CLI command and a new comparison output contract.
- Existing trace summary JSON schema/version and capture schema remain unchanged.
- Additive internal normalized/domain fields for availability are permitted only if existing summary rendering remains compatible.
- JSON comparison fields are explicitly allowlisted and stable.

### Out of scope

- Comparing precomputed summary JSON files
- `--latest` or automatic baseline/candidate discovery
- Percentage deltas
- Better/worse labels, winner selection, scoring, significance, recommendations
- Multi-run aggregation or experiments
- Historical storage or dashboards
- CI regression gates
- Configurable metric sets or thresholds
- Provider-specific comparison behavior
- Generic experiment/comparison plugin framework
- Exposing provider-specific provenance in comparison output
- Changing the existing trace-summary public schema/version
- New runtime dependencies, LLMs, databases, or external services

### Validation

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build --clear
git diff --check
```

Plus focused tests covering observed zero versus unavailable telemetry for all eight comparison slots, mixed availability between baseline/candidate, normalization-field presence, same-file snapshot reuse, and deterministic text/JSON rendering.

### Human decisions

- Human approval is required before the operational Issue receives `agent:ready`.
- This specification explicitly approves the **narrow additive normalization change** required to preserve presence/absence of existing API-request cost/input/output fields, plus provider-neutral internal availability metadata required to distinguish observed zero from missing telemetry. It does not approve provider-specific comparison logic, new telemetry mappings, or broader adapter redesign.
- Existing trace-summary public rendering/schema must remain unchanged.
- Stop for human review if implementation requires changing the capture schema, adding new provider telemetry mappings beyond preserving existing field presence, changing existing trace-summary public output/schema version, persistence, a new runtime dependency, or a generic experiment framework.
- Spec Kit must not apply lifecycle or risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: No allowlisted metric produces a numeric delta when either side lacks evidence that the metric was observed.
- **SC-002**: An observed zero remains distinguishable from unavailable telemetry for every allowlisted metric.
- **SC-003**: Text and JSON expose the same eight metric slots, availability states, and comparable numeric values.
- **SC-004**: Comparison memory usage does not scale with raw capture size beyond the existing bounded summarization behavior.
- **SC-005**: Successful comparison output contains no input paths, identifiers, raw payload content, or provider-specific provenance.
- **SC-006**: Existing `capt trace summarize` public text/JSON contract and schema version remain unchanged.
- **SC-007**: The comparison JSON output is reproducibly described by one mandatory v1 schema with no implementation-defined field layout.

## Assumptions

- `TraceSummary` remains the canonical immutable result of capture summarization and may gain internal provider-neutral availability metadata without changing its existing rendered schema.
- Existing normalized request records may gain additive presence metadata for fields already parsed from telemetry.
- Existing `summarize_capture(Path)` can independently summarize both explicit inputs.
- Availability can be accumulated incrementally using fixed-size state alongside existing counters.
- Estimated cost remains represented deterministically as integer USD micros when observed.
- Eight fixed metric slots are sufficient for the first Improve slice; future metrics require a separate specification.