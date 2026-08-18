# Implementation Plan: Compare two trace summaries

**Branch**: `002-trace-summary-comparison` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-trace-summary-comparison/spec.md`

**Note**: Specification-phase plan only. Implementation enters the existing GitHub lifecycle through Issue #36 after human approval; do not run `/speckit.implement`.

## Summary

Add `capt trace compare BASELINE CANDIDATE` as a local deterministic comparison command. Each capture is summarized independently through the existing bounded-memory path. Aggregation must preserve fixed-size provider-neutral availability for the eight comparison metrics so missing telemetry is never treated as observed zero. A small comparison layer consumes immutable summary values plus that availability and produces eight fixed comparison slots. Rendering remains text/JSON presentation only.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. No new package.

**Storage**: Existing local JSONL captures; no comparison persistence

**Testing**: `uv run pytest` with synthetic capture fixtures

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Preserve incremental bounded-memory summarization for each input; availability and comparison state are fixed-size

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM

**Scale/Scope**: Exactly two explicit capture inputs per invocation

## Constitution Check

- [x] Local-first: no outbound user-data path or public bind
- [x] Deterministic-first: unavailable telemetry is not converted into evidence
- [x] Privacy: comparison result excludes payloads, identifiers, paths, and provider-specific provenance
- [x] Provider-neutral core; no adapter changes planned
- [x] Streaming / bounded memory preserved for both inputs
- [x] No required LLM or model API in core
- [x] Existing trace-summary public schema/version stays compatible
- [x] No registry, ABC, plugin system, or experiment framework
- [x] Human approval required before `agent:ready`
- [x] Implementation will enter GitHub through existing Issue #36, not `/speckit.implement`

## CAPT design notes

- **Privacy impact**: two user-selected local paths are read. Do not serialize those paths; errors stay basename-only where necessary.
- **Deterministic evidence**: each of the eight slots has explicit availability; `delta = candidate - baseline` only when both sides are available.
- **Bounded-memory impact**: availability uses fixed-size flags/counters in existing accumulators; no raw record retention.
- **Provider neutrality**: provider adapters continue to normalize records; availability is derived in provider-neutral aggregation.
- **Compatibility**: new `capt trace compare` command. Existing `trace summarize` text/JSON and `TraceSummary.schema_version` remain unchanged.
- **Validation**: full repository checks plus focused availability, CLI, and rendering tests.
- **Out of scope**: summary-JSON inputs, latest discovery, configurable metric lists, percentages, scores, recommendations, experiments, persistence.

## Proposed design

### Availability boundary

The current final numeric aggregates are insufficient to distinguish observed zero from missing telemetry. Add the smallest provider-neutral availability state needed by the eight comparison metrics during existing aggregation.

Preferred shape is an immutable fixed-size value attached to the internal summary domain model, for example:

```python
@dataclass(frozen=True, slots=True)
class ComparisonAvailability:
    tool_calls: bool
    tool_failures: bool
    tool_result_bytes: bool
    model_requests: bool
    estimated_cost_usd_micros: bool
    input_tokens: bool
    output_tokens: bool
    session_compactions: bool
```

Exact naming may follow existing report/accumulator conventions. Do not implement this as a dict, registry, dynamic field discovery, or provider-specific structure.

Availability must be produced from normalized evidence, not from `value != 0`. The implementation must cover these semantics:

- `model_requests`: available only when request-count evidence is actually observed; metrics-only/no-usage fallback must not imply zero requests.
- `estimated_cost_usd_micros`, `input_tokens`, `output_tokens`: independently available only when the relevant API-event field or OTEL metric series is observed sufficiently to produce a complete aggregate.
- `tool_calls` and `tool_failures`: available only when tool-event telemetry coverage is observed; metrics-only captures must not imply zero tool activity.
- `tool_result_bytes`: available only when tool-event coverage exists and required result-size evidence is complete for the counted calls.
- `session_compactions`: available only when the relevant normalized lifecycle/log telemetry coverage is observed; metrics-only captures must not imply zero compactions.

The existing `trace summarize` renderer must continue to ignore this internal availability metadata so its public output/schema version remains unchanged.

### Core comparison boundary

Create a small provider-neutral module, preferably:

```text
src/coding_agent_performance/trace/comparison.py
```

Preferred result shape:

```python
@dataclass(frozen=True, slots=True)
class MetricComparison:
    available: bool
    baseline: int | None
    candidate: int | None
    delta: int | None


@dataclass(frozen=True, slots=True)
class TraceComparison:
    tool_calls: MetricComparison
    tool_failures: MetricComparison
    tool_result_bytes: MetricComparison
    model_requests: MetricComparison
    estimated_cost_usd_micros: MetricComparison
    input_tokens: MetricComparison
    output_tokens: MetricComparison
    session_compactions: MetricComparison
```

For each slot:

- both sides available -> `available=True`, integer baseline/candidate, exact integer delta;
- either side unavailable -> `available=False`, `delta=None`; use `None` for unavailable side values and never substitute zero.

A single small `MetricComparison` abstraction is justified because the same invariant applies to all eight fixed slots. Do not introduce metric registries, generic schemas, protocols, plugin systems, or dynamic field discovery.

### CLI orchestration

Extend `src/coding_agent_performance/trace/cli.py` with:

```text
capt trace compare BASELINE CANDIDATE [--format text|json]
```

The command should:

1. receive two explicit `Path` arguments;
2. summarize baseline through existing `summarize_capture()`;
3. summarize candidate through existing `summarize_capture()`;
4. call the pure comparison function;
5. render text or JSON;
6. map capture/OSError failures to concise non-zero CLI errors without tracebacks.

If current summarize error handling would otherwise be copied substantially, extract only a small local helper that preserves current behavior for `summarize` and `compare`.

### Rendering

Rendering consumes `TraceComparison`, never raw captures or provider records. Text and JSON preserve the fixed metric order and explicitly distinguish unavailable slots.

Suggested JSON contract:

```json
{
  "schema_version": 1,
  "metrics": {
    "tool_calls": {"available": true, "baseline": 10, "candidate": 8, "delta": -2},
    "tool_failures": {"available": true, "baseline": 2, "candidate": 1, "delta": -1},
    "tool_result_bytes": {"available": false, "baseline": null, "candidate": null, "delta": null},
    "model_requests": {"available": true, "baseline": 5, "candidate": 4, "delta": -1},
    "estimated_cost_usd_micros": {"available": true, "baseline": 300000, "candidate": 250000, "delta": -50000},
    "input_tokens": {"available": true, "baseline": 2000, "candidate": 1800, "delta": -200},
    "output_tokens": {"available": true, "baseline": 900, "candidate": 950, "delta": 50},
    "session_compactions": {"available": false, "baseline": null, "candidate": null, "delta": null}
  }
}
```

The comparison schema version is independent from `TraceSummary.schema_version`.

## Project Structure

Expected implementation touch points after inspection:

```text
src/coding_agent_performance/trace/report.py
src/coding_agent_performance/trace/summary.py
src/coding_agent_performance/trace/comparison.py
src/coding_agent_performance/trace/cli.py
src/coding_agent_performance/trace/rendering.py
docs/product.md
docs/architecture.md
docs/summary-format.md
tests/test_comparison.py
tests/test_cli.py
```

Accumulator modules may also change where availability must be recorded. Keep those changes local to existing accumulator responsibilities.

**Structure Decision**: Extend existing accumulator/domain boundaries with fixed-size availability and add one cohesive pure comparison module. No package-level architecture change.

## Complexity Tracking

The only intentional scope increase from the original draft is additive internal availability metadata required to prevent false evidence. Existing public trace-summary schema and behavior remain unchanged.