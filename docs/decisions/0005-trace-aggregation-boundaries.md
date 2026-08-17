# ADR 0005: Trace aggregation boundaries

- Status: Accepted
- Date: 2026-08-17
- Decision owners: Project maintainers

## Context

Trace aggregation grew by adding mutable state containers and methods on `IncrementalSummarizer`. That shape still works, but session, usage, tool, metric, and coverage invariants are easier to evolve when the state that owns them also owns the operations that maintain them.

The next roadmap items add more analysis on top of the same summary path. A framework, registry, or one-class-per-rule design would add indirection before a second consumer exists.

## Decision

Keep `IncrementalSummarizer` as the public orchestration entry point.

Colocate mutable aggregation state with its behavior in concrete accumulators for capture, session, usage, tool, metric, and coverage concerns.

Keep finished report values as immutable DTOs. Accumulators emit those snapshots; they do not become the report.

Give deterministic insight computation a single `InsightAnalyzer` that reads provider-neutral immutable evidence and returns `Insights`. Keep individual rules as small stateless functions. Do not create one class per rule.

Keep rendering as a presentation layer over the finished summary.

Do not introduce a DI container, accumulator base class, generic registry, or an `aggregation/` package split until the current modules are no longer a clear home for the work.

## Consequences

### Positive

- Invariant-preserving logic sits next to the state it mutates.
- Later insight and comparison work can extend stable accumulator and analyzer boundaries.
- Public CLI, schemas, and output semantics stay unchanged.

### Negative

- Callers must go through the summarizer or an accumulator snapshot rather than mutating shared private state from many methods.
- Cross-cutting fallbacks, such as usage from events versus metrics, still require explicit orchestration.

## Alternatives considered

- Leaving all mutation on `IncrementalSummarizer`. Rejected because the next analysis features would keep enlarging one class.
- An accumulator ABC, registry, or plugin dispatcher. Rejected as a hypothetical framework.
- One class per insight rule. Rejected because the current rules are small, stateless, and share one evidence type.

## Follow-up

Add new insight rules through `InsightAnalyzer` and stateless detectors. Extract an `aggregation/` package only if a single accumulators module becomes too large for the work it contains.
