# Implementation Plan: Compare two trace summaries

**Branch**: `002-trace-summary-comparison` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-trace-summary-comparison/spec.md`

**Note**: Specification-phase plan only. Implementation enters the existing GitHub lifecycle through Issue #36 after human approval; do not run `/speckit.implement`.

## Summary

Add `capt trace compare BASELINE CANDIDATE` as a local deterministic comparison command. Each capture is summarized independently through the existing bounded-memory `summarize_capture()` path. A small provider-neutral comparison layer consumes the two immutable `TraceSummary` values and produces fixed ordered integer deltas for eight allowlisted metrics. Rendering remains text/JSON presentation only.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. No new package.

**Storage**: Existing local JSONL captures; no comparison persistence

**Testing**: `uv run pytest` with synthetic capture fixtures

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Preserve incremental bounded-memory summarization for each input; comparison state is fixed-size

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM

**Scale/Scope**: Exactly two explicit capture inputs per invocation

## Constitution Check

- [x] Local-first: no outbound user-data path or public bind
- [x] Deterministic-first: comparison is exact integer evidence
- [x] Privacy: comparison result excludes payloads, identifiers, and paths
- [x] Provider-neutral core; no adapter changes planned
- [x] Streaming / bounded memory preserved for both inputs
- [x] No required LLM or model API in core
- [x] Existing public commands/schemas stay compatible; one additive command/output contract is explicit
- [x] No registry, ABC, plugin system, or experiment framework
- [x] Human approval required before `agent:ready`
- [x] Implementation will enter GitHub through existing Issue #36, not `/speckit.implement`

## CAPT design notes

- **Privacy impact**: potential because two user-selected local paths are read. Do not serialize those paths in comparison output; errors stay basename-only where a file reference is necessary.
- **Deterministic evidence**: eight integer fields from `TraceSummary`; `delta = candidate - baseline`; no percentage in v1.
- **Bounded-memory impact**: two immutable summaries plus one fixed-size comparison object. No raw record retention.
- **Provider neutrality**: comparison module accepts `TraceSummary` only. Input providers are irrelevant once normalized.
- **Compatibility**: new `capt trace compare` command. Existing summary schema_version and rendering remain unchanged.
- **Validation**: full repository checks plus CLI and pure comparison unit tests.
- **Out of scope**: summary-JSON inputs, latest discovery, configurable metric lists, percentages, scores, recommendations, experiments, persistence.
- **Human decisions**: stop if implementation requires changing the summary schema/provider normalization or introducing a generic comparison framework.

## Proposed design

### Core comparison boundary

Create a small provider-neutral module, preferably:

```text
src/coding_agent_performance/trace/comparison.py
```

It owns only immutable comparison DTOs and the deterministic transformation from two `TraceSummary` objects.

Preferred shape:

```python
@dataclass(frozen=True, slots=True)
class MetricDelta:
    baseline: int
    candidate: int
    delta: int

@dataclass(frozen=True, slots=True)
class TraceComparison:
    tool_calls: MetricDelta
    tool_failures: MetricDelta
    tool_result_bytes: MetricDelta
    model_requests: MetricDelta
    estimated_cost_usd_micros: MetricDelta
    input_tokens: MetricDelta
    output_tokens: MetricDelta
    session_compactions: MetricDelta


def compare_summaries(baseline: TraceSummary, candidate: TraceSummary) -> TraceComparison: ...
```

A single small `MetricDelta` abstraction is justified because the exact same invariant (`baseline`, `candidate`, `candidate - baseline`) applies to all eight current metrics. Do not introduce metric registries, generic schemas, protocols, plugin systems, or dynamic field discovery.

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

If current summarize error handling would otherwise be copied substantially, extract only a small local helper that preserves current behavior for `summarize` and `compare`. Do not refactor unrelated CLI behavior.

### Rendering

Keep presentation in `trace/rendering.py` or a focused comparison renderer adjacent to existing rendering if that is clearer after inspection. Rendering must consume `TraceComparison`, never raw captures or provider records.

Text order and JSON field order follow the fixed metric order in the spec.

Suggested JSON contract:

```json
{
  "schema_version": 1,
  "metrics": {
    "tool_calls": {"baseline": 10, "candidate": 8, "delta": -2},
    "tool_failures": {"baseline": 2, "candidate": 1, "delta": -1},
    "tool_result_bytes": {"baseline": 1000, "candidate": 1200, "delta": 200},
    "model_requests": {"baseline": 5, "candidate": 4, "delta": -1},
    "estimated_cost_usd_micros": {"baseline": 300000, "candidate": 250000, "delta": -50000},
    "input_tokens": {"baseline": 2000, "candidate": 1800, "delta": -200},
    "output_tokens": {"baseline": 900, "candidate": 950, "delta": 50},
    "session_compactions": {"baseline": 2, "candidate": 1, "delta": -1}
  }
}
```

The comparison schema version is independent from the existing `TraceSummary.schema_version`; do not modify the summary version just to add this command.

## Project Structure

### Documentation (this feature)

```text
specs/002-trace-summary-comparison/
├── spec.md
├── plan.md
├── tasks.md
└── analyze.md
```

No research/data-model/contracts/quickstart files are necessary: current repository code and the fixed JSON contract are sufficient.

### Source Code (repository root)

Expected concrete files after implementation review:

```text
src/coding_agent_performance/trace/comparison.py
src/coding_agent_performance/trace/cli.py
src/coding_agent_performance/trace/rendering.py
docs/product.md
docs/architecture.md
docs/summary-format.md
tests/test_comparison.py
tests/test_cli.py
```

Existing test file names may be reused if the repository already has more focused CLI/rendering test modules. Do not create duplicate test organization solely to match this plan.

**Structure Decision**: Add one cohesive pure comparison module and extend existing CLI/rendering boundaries. No package-level architecture change.

## Complexity Tracking

No constitution violations.