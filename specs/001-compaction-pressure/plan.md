# Implementation Plan: Detect compaction pressure

**Branch**: `001-compaction-pressure` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-compaction-pressure/spec.md`

**Note**: Pilot plan only. This adoption does not implement the feature or run `/speckit.implement`.

## Summary

Add one deterministic insight that reports compaction pressure when `sessions.compactions` meets a fixed threshold (prefer `>= 2`). Reuse the existing Insights pattern, allowlist rendering, and provider-neutral session aggregate. Do not parse transcripts or add payload state.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. No new package. Spec Kit is not a runtime dependency.

**Storage**: Existing local JSONL captures and in-memory session counters

**Testing**: `uv run pytest` with synthetic fixtures

**Target Platform**: Local CLI

**Project Type**: local-first CLI

**Performance Goals**: Keep the current incremental summarizer. No extra per-event payload retention.

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM

**Scale/Scope**: Single-capture summary insight

## Constitution Check

- [x] Local-first: no outbound user-data path, no public bind
- [x] Deterministic-first: evidence is the observed compaction count
- [x] Privacy: only the aggregate count is allowlisted
- [x] Provider-neutral core; no new adapter mapping
- [x] Streaming / bounded memory preserved
- [x] No required LLM or model API in core
- [x] Public commands remain compatible; summary JSON gains an additive allowlisted insight field
- [x] No premature registry, ABC, plugin system, or generic framework
- [x] Human approval: stop if transcript inspection or schema redesign is required
- [x] Implementation will enter GitHub as a manual Agent Task Issue, not via `/speckit.implement`

## CAPT design notes

- **Privacy impact**: potential, because summaries already process telemetry. Only the integer compaction count may be added to the allowlist.
- **Deterministic evidence**: `sessions.compactions >= 2` (preferred) emits `{ compaction_count: N }`.
- **Bounded-memory impact**: none beyond the existing `compactions` counter in the incremental session aggregator.
- **Provider neutrality**: consume `SessionStats.compactions` in `trace/insights.py`; do not add Claude Code event names.
- **Compatibility**: additive `insights.compaction_pressure` (or equivalent allowlisted field) on summary schema version 1. Existing tool insights stay unchanged.
- **Validation**: full project validation plus boundary, rendering, JSON, coexistence, and privacy tests.
- **Out of scope**: timing, context-window estimates, recommendations, configurable thresholds, scoring, comparison, generic insight framework, and implementation in Issue #42.
- **Human decisions**: if current compaction semantics are not represented by `sessions.compactions`, stop for review.

## Project Structure

### Documentation (this feature)

```text
specs/001-compaction-pressure/
├── spec.md
├── plan.md
├── tasks.md
└── analyze.md
```

No separate research, data-model, contracts, or quickstart files. The existing session aggregate and Insights DTO are sufficient.

### Source Code (repository root)

```text
src/coding_agent_performance/trace/report.py
src/coding_agent_performance/trace/insights.py
src/coding_agent_performance/trace/aggregation.py
src/coding_agent_performance/trace/rendering.py
docs/summary-format.md
docs/architecture.md
docs/product.md
tests/test_insights.py
tests/test_rendering.py
tests/test_summary.py
tests/helpers/synthetic_capture.py
```

**Structure Decision**: Extend the existing trace insight and summary path. Do not add a new package or insight framework.

## Complexity Tracking

No constitution violations.
