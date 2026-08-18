# Implementation Plan: Compare two trace summaries

**Branch**: `002-trace-summary-comparison` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/002-trace-summary-comparison/spec.md`

**Note**: Specification-phase plan only. Implementation enters the existing GitHub lifecycle through Issue #36 after human approval; do not run `/speckit.implement`.

## Summary

Add `capt trace compare BASELINE CANDIDATE` as a local deterministic comparison command. Each distinct capture is summarized through the existing bounded-memory path. Normalization and aggregation preserve fixed-size provider-neutral availability for the eight comparison metrics so missing telemetry is never treated as observed zero. A pure comparison layer produces eight fixed slots and text/JSON rendering exposes only allowlisted evidence.

If baseline and candidate resolve to the same filesystem object, summarize it exactly once and reuse that immutable snapshot for both sides. This preserves the explicit same-file zero-delta guarantee even if the capture is still being appended concurrently.

## Technical Context

- Python 3.14
- Existing CAPT runtime only; no new package
- Local JSONL inputs; no comparison persistence
- Synthetic tests with `uv run pytest`
- Fixed-size availability/comparison state

## Constitution Check

- [x] Local-first; no outbound data
- [x] Deterministic-first; unavailable telemetry is not converted into evidence
- [x] Privacy allowlist; no paths, identifiers, payloads, or provider-specific provenance in output
- [x] Provider-neutral normalized/domain availability
- [x] Bounded-memory summarization preserved
- [x] Existing trace-summary public schema/version remains unchanged
- [x] No LLM, registry, plugin system, experiment framework, or new dependency
- [x] Human approval required before `agent:ready`

## Availability boundary

The current final numeric aggregates cannot always distinguish observed zero from missing telemetry. Add the smallest fixed-size provider-neutral availability state required by the eight slots during existing normalization/aggregation.

For API request usage fields, the current normalizer loses presence by coercing absent/invalid cost/input/output attributes to integer zero. This feature explicitly permits the narrow additive change needed to preserve whether each already-supported field was present and valid before aggregation. Do not add new provider telemetry mappings or provider-specific comparison behavior.

Preferred summary-side shape:

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

Exact naming may follow existing normalized-record/report/accumulator conventions. Do not use a dict, registry, dynamic discovery, or provider-specific comparison structure.

Availability rules:

- `model_requests`: only when request-count evidence is observed; metrics-only/no-usage fallback must not imply zero.
- cost/input/output tokens: independently available only when their own evidence is observed sufficiently for a complete aggregate; API-event normalization must preserve per-field presence rather than erase it into zero.
- tool calls/failures: only with observed tool-event telemetry coverage.
- tool result bytes: only when tool coverage exists and result-size evidence is complete for counted calls.
- compactions: only with relevant normalized lifecycle/log telemetry coverage.

Existing `trace summarize` rendering must ignore this internal metadata so its public contract remains unchanged.

## Core comparison boundary

Prefer `src/coding_agent_performance/trace/comparison.py` with one concrete repeated invariant:

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

Both sides available -> integer values and `delta = candidate - baseline`.

Either side unavailable -> fixed slot remains present, `available=False`, and `baseline`, `candidate`, and `delta` are all `None`. Never substitute zero for unavailable evidence.

## CLI orchestration

Add:

```text
capt trace compare BASELINE CANDIDATE [--format text|json]
```

The command should:

1. receive two explicit `Path` arguments;
2. determine whether both paths resolve to the same filesystem object without exposing resolved absolute paths in output;
3. if they are the same object, call `summarize_capture()` once and reuse that immutable summary for baseline and candidate;
4. otherwise summarize each input independently through existing `summarize_capture()`;
5. call the pure comparison function;
6. render text or JSON;
7. map input/OSError failures to concise non-zero errors without traceback or absolute-path disclosure.

Use standard filesystem identity semantics suitable for existing platform support (`Path.samefile()` or an equivalently safe approach) while handling nonexistent/unreadable inputs through the established error path. Do not compare path strings only, because aliases/symlinks may reference the same object.

If summarize error handling would otherwise be meaningfully duplicated, extract only a small local helper that preserves existing behavior.

## Rendering

Text and JSON consume only `TraceComparison` and preserve fixed metric order.

### Mandatory comparison JSON v1 contract

The public JSON shape is normative, not illustrative. `schema_version` MUST be integer `1`. The only top-level keys are `schema_version` and `metrics`, in that order. `metrics` MUST contain exactly these eight keys, in this order:

1. `tool_calls`
2. `tool_failures`
3. `tool_result_bytes`
4. `model_requests`
5. `estimated_cost_usd_micros`
6. `input_tokens`
7. `output_tokens`
8. `session_compactions`

Every metric object MUST contain exactly `available`, `baseline`, `candidate`, and `delta`, in that order. When `available` is `true`, the three numeric fields are integers. When `available` is `false`, all three numeric fields are JSON `null`.

Complete v1 example:

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

No provider provenance, paths, identifiers, percentages, scores, recommendations, or additional metadata may be added to comparison JSON v1. The comparison schema version is independent from `TraceSummary.schema_version`.

## Expected implementation touch points

```text
src/coding_agent_performance/providers/claude_code/normalizer.py  # narrow presence preservation only
normalized event/domain model used by model-request aggregation
src/coding_agent_performance/trace/report.py
src/coding_agent_performance/trace/summary.py
src/coding_agent_performance/trace/comparison.py
src/coding_agent_performance/trace/cli.py
src/coding_agent_performance/trace/rendering.py
existing accumulator modules as required
docs/product.md
docs/architecture.md
docs/summary-format.md
tests/test_comparison.py
existing normalizer/CLI/summary tests
```

Keep availability state inside existing normalization/accumulator responsibilities. No package-level architecture change.

## Validation

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build --clear
git diff --check
```

Focused validation must cover API-field presence preservation, observed-zero versus unavailable telemetry, partial coverage, mixed availability, same-file snapshot reuse, aliases/symlinks where portable, the exact JSON v1 contract, text/JSON agreement, privacy, and unchanged existing trace-summary rendering.

## Complexity Tracking

The intentional scope increase from the initial draft is limited to fixed-size internal availability metadata, narrow preservation of presence for already-supported normalized API usage fields, and same-file snapshot reuse. These are required to prevent false deterministic evidence; none changes the existing trace-summary public schema.