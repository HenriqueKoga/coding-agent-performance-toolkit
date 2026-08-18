# Implementation Plan: Export compact trace handoff

**Branch**: `003-compact-trace-handoff` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/003-compact-trace-handoff/spec.md`

**Note**: Specification-phase plan only. Implementation enters the existing GitHub lifecycle through Issue #37 after human approval; do not run `/speckit.implement`.

## Summary

Add `capt trace handoff CAPTURE` as a local deterministic export command. One explicit CAPT JSONL capture is summarized through the existing bounded-memory path. A pure transformation copies a compact allowlist from that immutable `TraceSummary` into `TraceHandoff`. Text and JSON rendering expose only that allowlist. JSON is the canonical structured contract; text is the default CLI format. Existing summarize and compare contracts stay unchanged.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. No new package. Spec Kit is not a runtime dependency.

**Storage**: Local JSONL capture input; stdout only. No handoff persistence.

**Testing**: `uv run pytest` with synthetic fixtures

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Streaming and bounded memory; do not materialize entire captures. Handoff construction reads the finished summary only.

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM, no invented narrative

**Scale/Scope**: Single-capture extract of existing summary evidence

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Local-first: no outbound user-data path, no public bind
- [x] Deterministic-first: evidence is observed facts, not model judgment
- [x] Privacy: no payloads, identifiers, absolute paths, or real fixtures
- [x] Provider-neutral core; vendor mapping stays in adapters
- [x] Streaming / bounded memory preserved
- [x] No required LLM or model API in core
- [x] Public commands and versioned schemas remain compatible, or a version change is explicit
- [x] No premature registry, ABC, plugin system, or generic framework
- [x] Human approval identified for scope, dependencies, schema, or lifecycle risk
- [x] Implementation will enter GitHub as a manual Agent Task Issue, not via `/speckit.implement`

## CAPT design notes

- **Privacy impact**: potential, contained by an explicit compact allowlist. Output may include safe filename, capture source, integer aggregates, `usage_source`, nullable success-rate basis points, and existing insight evidence (including already-allowlisted tool names). No prompts, responses, tool content, source code, secrets, identifiers, or absolute paths.
- **Deterministic evidence**: copied summary aggregates and existing insight findings only. No intent, TODOs, recommendations, or root cause.
- **Bounded-memory impact**: no new accumulator state. One immutable compact DTO built from the finished summary.
- **Provider neutrality**: `handoff_from_summary(TraceSummary)` in the trace domain. No adapter change.
- **Compatibility**: additive `capt trace handoff` and a new handoff JSON v1 schema. Existing summary and comparison schemas/commands unchanged.
- **Validation**: full AGENTS.md set plus synthetic handoff smoke tests and privacy-exclusion tests.
- **Out of scope**: prompts/responses, intent reconstruction, source snapshots, TODOs, LLM, Context Ledger, checkpoints, resume/injection, `--latest`, `--output`, Markdown, generic artifact framework, databases, network, new dependencies.
- **Human decisions**: stop if useful output would require prompts, responses, source-code capture, remote storage, or model inference. Do not apply `agent:ready` or risk labels from Spec Kit.

## Project Structure

### Documentation (this feature)

```text
specs/003-compact-trace-handoff/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/handoff-json-v1.md
├── checklists/requirements.md
├── tasks.md
└── analyze.md
```

### Source Code (repository root)

```text
src/coding_agent_performance/
    cli.py
    adapters/claude_code/
    trace/
        cli.py
        summary.py
        report.py
        insights.py
        handoff.py          # new pure transformation
        rendering.py
        comparison.py       # unchanged public contract
docs/
    product.md
    architecture.md
    summary-format.md
    development.md
tests/
    test_handoff.py         # new
    test_trace_cli.py
    test_rendering.py
    test_insights.py
```

**Structure Decision**: Extend the existing `trace` package. Add one concrete module for the pure summary-to-handoff transform. Do not add an `artifacts/` package, registry, or exporter framework.

## Core handoff boundary

Prefer `src/coding_agent_performance/trace/handoff.py` with one concrete repeated invariant:

```python
HANDOFF_SCHEMA_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class HandoffCapture:
    source: str
    file: str


@dataclass(frozen=True, slots=True)
class HandoffTokens:
    input: int
    output: int


@dataclass(frozen=True, slots=True)
class HandoffModelUsage:
    usage_source: UsageSource
    requests: int
    errors: int
    refusals: int
    estimated_cost_usd_micros: int
    tokens: HandoffTokens


@dataclass(frozen=True, slots=True)
class HandoffTools:
    calls: int
    successes: int
    failures: int
    result_bytes: int
    success_rate_bps: int | None


@dataclass(frozen=True, slots=True)
class TraceHandoff:
    schema_version: int
    capture: HandoffCapture
    sessions: SessionStats
    model_usage: HandoffModelUsage
    tools: HandoffTools
    insights: Insights
```

Exact names may follow existing module conventions. Do not use a dict, registry, dynamic field discovery, or dataclass-as-JSON dumping for the public contract.

`handoff_from_summary(summary: TraceSummary) -> TraceHandoff` copies:

- `capture.source` and `capture.file` only
- the existing `sessions` value
- scalar model-usage fields listed above, including `tokens.input` / `tokens.output` and excluding cache tokens, durations, and breakdowns
- scalar tool fields listed above, including `success_rate_bps`, and excluding `input_bytes`, durations, and `by_name`
- the existing `insights` value unchanged

It MUST NOT copy activity, coverage, comparison availability, envelopes, batch counts, or received-at timestamps.

## CLI orchestration

Add:

```text
capt trace handoff CAPTURE [--format text|json]
```

The command should:

1. require exactly one explicit `Path` argument;
2. call existing `summarize_or_fail()` / `summarize_capture()`;
3. call `handoff_from_summary()`;
4. render text or JSON;
5. write JSON to stdout with a trailing newline, matching summarize/compare JSON;
6. map input/OSError failures to concise non-zero errors without traceback or absolute-path disclosure.

Do not add `--latest`. Do not add `--output`. Do not accept two capture paths.

Reuse existing `OutputFormat` and summarize error mapping. If help text on `trace_app` currently lists collect/list/summarize/compare, update it to include handoff without changing those commands.

## Rendering

Text and JSON consume only `TraceHandoff`.

JSON MUST match [contracts/handoff-json-v1.md](./contracts/handoff-json-v1.md) exactly: key order, types, `null` versus empty-array insight shapes, and no extra fields. Build the dict through an explicit allowlist. Do not serialize dataclasses dynamically.

Text MUST report the same identity, aggregate values, success-rate nullability, and insight presence/absence as JSON. It MUST NOT add narrative, recommendations, or sections for out-of-allowlist summary fields. Reuse existing insight line wording where that wording already exists in summarize text, so insight evidence cannot drift.

### Mandatory handoff JSON v1 contract

The public JSON shape is normative. `schema_version` MUST be integer `1`. The only top-level keys are `schema_version`, `capture`, `sessions`, `model_usage`, `tools`, and `insights`, in that order.

Complete v1 example (synthetic):

```json
{
  "schema_version": 1,
  "capture": {
    "source": "claude-code",
    "file": "synthetic-session.jsonl"
  },
  "sessions": {
    "count": 1,
    "prompts": 4,
    "assistant_responses": 4,
    "compactions": 2,
    "subagents_completed": 0
  },
  "model_usage": {
    "usage_source": "api_request_events",
    "requests": 6,
    "errors": 0,
    "refusals": 0,
    "estimated_cost_usd_micros": 123456,
    "tokens": {
      "input": 8000,
      "output": 2500
    }
  },
  "tools": {
    "calls": 12,
    "successes": 10,
    "failures": 2,
    "result_bytes": 4096,
    "success_rate_bps": 8333
  },
  "insights": {
    "repeated_tool_calls": [
      {
        "tool_name": "Read",
        "call_count": 5
      }
    ],
    "repeated_failed_tool_calls": [],
    "high_tool_result_volume": [],
    "high_tool_failure_rate": [],
    "dominant_tool": {
      "tool_name": "Read",
      "call_count": 8,
      "total_calls": 12,
      "share_percent": 66
    },
    "compaction_pressure": {
      "compaction_count": 2
    },
    "subagent_usage": null
  }
}
```

No provider provenance, paths, identifiers, scores, recommendations, TODOs, or additional metadata may be added to handoff JSON v1. The handoff schema version is independent from `TraceSummary.schema_version`.

## Expected implementation touch points

```text
src/coding_agent_performance/trace/handoff.py
src/coding_agent_performance/trace/cli.py
src/coding_agent_performance/trace/rendering.py
docs/product.md
docs/architecture.md
docs/summary-format.md
docs/development.md
tests/test_handoff.py
existing CLI/rendering/insight tests as needed for compatibility
```

No normalizer, collector, capture-schema, comparison, or insight-rule changes.

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

Focused validation must cover the exact JSON v1 contract, empty/minimal traces, insight copy versus summarize, `success_rate_bps` nullability, text/JSON agreement, privacy exclusions, CLI errors, stdout-only behavior, and unchanged existing summarize/compare rendering.

## Complexity Tracking

No constitution violations. The only new types are the compact handoff DTOs required to keep the public artifact smaller than `TraceSummary` without making rendering the source of truth.
