# Feature Specification: Compare two trace summaries

**Feature Branch**: `002-trace-summary-comparison`

**Created**: 2026-08-17

**Status**: Draft for human review

**Input**: Compare two explicit CAPT captures locally and report deterministic before/after deltas from existing summary aggregates.

**Operational Issue**: [#36](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/36) is the GitHub Agent Task for implementation after this specification is approved and merged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare a baseline and candidate capture (Priority: P1)

A developer has two CAPT JSONL captures representing a baseline run and a candidate run after a workflow change. They want a compact deterministic comparison of stable aggregate metrics without a score, model judgment, or remote service.

**Why this priority**: This is the first minimal Improve-theme capability: users can inspect whether concrete observed metrics moved after a workflow change while retaining control over interpretation.

**Independent Test**: Run `capt trace compare <baseline.jsonl> <candidate.jsonl>` on synthetic captures with known aggregates and verify the text and JSON baseline/candidate/delta values.

**Acceptance Scenarios**:

1. **Given** two valid captures with identical allowlisted metrics, **When** they are compared, **Then** every reported delta is `0`.
2. **Given** a candidate with higher and lower metric values than the baseline, **When** compared, **Then** signed absolute deltas preserve direction exactly (`candidate - baseline`).
3. **Given** a baseline metric of zero, **When** the candidate is non-zero, **Then** the absolute delta remains deterministic and no percentage, NaN, or Infinity is produced.
4. **Given** two captures from providers supported by the same provider-neutral summary contract, **When** compared, **Then** comparison uses only normalized summary aggregates.

### User Story 2 - Consume the same comparison as JSON (Priority: P2)

A developer or local script wants the comparison as structured JSON with the same metric values and ordering semantics as text output.

**Independent Test**: Run the same synthetic pair with `--format json` and assert the structured metric data equals the text report evidence.

**Acceptance Scenarios**:

1. **Given** a valid comparison, **When** `--format json` is used, **Then** JSON contains only the allowlisted comparison contract.
2. **Given** identical inputs, **When** comparison is repeated, **Then** the serialized field order and numeric values are stable.

### Edge Cases

- Either input path is missing, unreadable, or not a valid CAPT capture.
- One or both captures contain zero tool calls, zero model requests, zero tokens, zero cost, or zero compactions.
- Baseline is greater than candidate, producing a negative delta.
- Candidate is greater than baseline, producing a positive delta.
- Baseline and candidate are the same file; the command remains valid and produces zero deltas.
- Input absolute paths must not be echoed in successful output or error text.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST add `capt trace compare BASELINE CANDIDATE` with exactly two explicit CAPT JSONL capture-path arguments for v1.
- **FR-002**: CAPT MUST summarize each input through the existing capture summarization path rather than duplicate OTLP decoding, normalization, or aggregation logic.
- **FR-003**: CAPT MUST compare exactly this initial metric allowlist, in this stable order:
  1. total tool calls (`tools.calls`)
  2. tool failures (`tools.failures`)
  3. cumulative tool result bytes (`tools.result_bytes`)
  4. model requests (`model_usage.requests`)
  5. estimated cost in USD micros (`model_usage.estimated_cost_usd_micros`)
  6. input tokens (`model_usage.tokens.input`)
  7. output tokens (`model_usage.tokens.output`)
  8. session compactions (`sessions.compactions`)
- **FR-004**: Each metric MUST report an integer `baseline`, integer `candidate`, and signed integer `delta`, where `delta = candidate - baseline`.
- **FR-005**: V1 MUST NOT report percentage deltas. This avoids separate zero-baseline semantics and keeps the public contract minimal.
- **FR-006**: Text and JSON MUST expose equivalent comparison evidence.
- **FR-007**: CAPT MUST NOT declare a winner, overall regression/improvement, quality score, significance, or recommendation.
- **FR-008**: Comparison MUST be provider-neutral and operate on immutable `TraceSummary` data after each capture has been summarized.
- **FR-009**: Comparison MUST remain local-only and read-only; it MUST NOT persist comparison state or send data externally.
- **FR-010**: Invalid input MUST exit non-zero with concise error text, no traceback, no payload contents, and no absolute path disclosure.
- **FR-011**: Existing `trace summarize`, `trace list`, collection, summary schema, and insight behavior MUST remain unchanged.

### Key Entities

- **MetricDelta**: One allowlisted metric comparison containing a stable metric key plus baseline, candidate, and signed absolute delta.
- **TraceComparison**: Immutable provider-neutral comparison result containing the fixed ordered metric set. It does not contain capture paths, provider-specific payloads, scores, or recommendations.

## CAPT constraints *(mandatory)*

### Privacy

- Successful output may contain only fixed metric names and aggregate integer values.
- Do not emit capture paths, session identifiers, prompts, responses, tool arguments/results, model payloads, or raw telemetry.
- Input-error messages may use a safe basename if necessary, consistent with current summarization errors, but must never include an absolute path or payload content.
- Tests and fixtures remain synthetic.

### Deterministic evidence

- Evidence is limited to the eight existing integer summary aggregates listed in FR-003.
- Delta is exact integer subtraction (`candidate - baseline`).
- No percentage delta, winner, score, quality inference, root cause, or recommendation is part of v1.

### Bounded memory

- Summarize each capture with the existing incremental summarizer.
- Do not retain raw records/events after summarization.
- Holding two finished immutable `TraceSummary` objects plus one small fixed-size comparison result is acceptable and bounded independently of capture size.

### Provider neutrality

- The comparison layer consumes only `TraceSummary`.
- No new Claude Code-specific mapping or provider branch is permitted in comparison logic.

### Compatibility

- Adds one public CLI command and a new comparison output contract.
- Does not modify the existing trace summary schema or capture schema.
- JSON comparison fields must be explicitly allowlisted and stable.

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

Plus focused CLI/text/JSON tests using deterministic synthetic baseline/candidate captures.

### Human decisions

- Human approval is required before the operational Issue receives `agent:ready`.
- Stop for human review if implementation requires changing `TraceSummary`, the capture schema, provider adapters, persistence, a new runtime dependency, or a generic experiment framework.
- Spec Kit must not apply lifecycle or risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given any two valid summaries, a reviewer can reproduce every comparison value using only the eight documented aggregate fields and integer subtraction.
- **SC-002**: Text and JSON expose the same eight metrics, baseline values, candidate values, and deltas.
- **SC-003**: Comparison memory usage does not scale with raw capture size beyond the existing bounded summarization behavior.
- **SC-004**: Successful comparison output contains no input paths, identifiers, or raw payload content.

## Assumptions

- `TraceSummary` remains the canonical immutable result of capture summarization.
- Existing `summarize_capture(Path)` can independently summarize both explicit inputs.
- Estimated cost is already represented deterministically as integer USD micros.
- Eight fixed metrics are sufficient for the first Improve slice; future metrics require a separate specification.