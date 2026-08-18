# Research: Export compact trace handoff

**Feature**: `003-compact-trace-handoff`

**Date**: 2026-08-18

This Phase 0 note records v1 choices that the spec already pins. There are no remaining `[NEEDS CLARIFICATION]` items.

## Command name and input arity

- **Decision**: `capt trace handoff CAPTURE` with exactly one explicit JSONL path.
- **Rationale**: The operational Issue asks for a read-only export under the existing `trace` namespace. `handoff` names the Preserve Context artifact without implying a generic export framework. Explicit path matches `trace compare` and the Issue's "one explicit capture input" wording.
- **Alternatives considered**: `trace export`, `trace export-handoff`, and `--latest`. Rejected because they either suggest a generic artifact framework or add discovery beyond v1.

## Compact evidence set

- **Decision**: Allowlist identity (`source`, filename), the five existing session counters, a scalar model-usage subset including `usage_source`, a scalar tool subset including `success_rate_bps`, and the existing insights object.
- **Rationale**: The Issue asks for a deliberately small set of already-safe evidence. Session/tool/model totals plus insights are enough for another agent to see what happened without re-reading the capture. `usage_source` keeps token/cost totals interpretable. Insights stay byte-compatible with summarize findings so this feature cannot invent new semantics.
- **Alternatives considered**: Emitting the full `TraceSummary`, adding `by_model` / `by_name` breakdowns, or omitting insights. Rejected as too large, still large, or missing the Issue's required insight inclusion.

## JSON versus text

- **Decision**: JSON is the canonical structured contract. Text is the default CLI format via existing `--format text|json`. Markdown is out of v1.
- **Rationale**: Summarize and compare already use that flag. JSON remains mandatory and exact; text must agree on evidence values.
- **Alternatives considered**: JSON-only output, Markdown as a third format, or JSON as the CLI default. Rejected as inconsistent with current CLI conventions or as extra surface area.

## File output

- **Decision**: Stdout only in v1. No `--output`.
- **Rationale**: The Issue requires stdout by default and treats dedicated file output as optional. Collect already has a refuse-if-exists `--output` for captures; adding a second write path for a new artifact would expand persistence surface without a unique need. Operators can redirect stdout.
- **Alternatives considered**: `--output PATH` refused when the file exists, or overwrite-with-`--force`. Deferred; either would be a later additive CLI change.

## Domain boundary

- **Decision**: Pure function from `TraceSummary` to an immutable `TraceHandoff` in `trace/handoff.py`. Rendering consumes only `TraceHandoff`.
- **Rationale**: ADR 0005 keeps analysis on immutable summary evidence. The Issue requires core construction to be a transformation of the provider-neutral summary, not CLI-only filtering.
- **Alternatives considered**: Rendering a subset of `TraceSummary` directly, or introducing an artifact registry. Rejected as CLI-only logic or a premature framework.

## Capture source allowlist

- **Decision**: Keep `capture.source` in v1, but map it through a closed allowlist in `handoff_from_summary()`. V1 members: `claude-code`. Any other string becomes `unknown`. Never echo the raw summary source when it is outside the list.
- **Rationale**: Envelope `source` is currently any non-empty string. Calling that field "safe" without mapping would let a prompt, identifier, or secret into an agent-facing artifact. `unknown` already appears as the empty-source snapshot fallback. Omitting the key would break the fixed JSON contract.
- **Alternatives considered**: Omitting `source`; importing the Claude Code adapter `SOURCE` constant; changing CaptureReader. Rejected as either dropping Issue-requested identity, coupling the domain to an adapter, or changing existing summarize/compare behavior.

## Handoff error mapping

- **Decision**: Call `summarize_capture()` from the handoff command, then map `CaptureError`/`OSError` to payload-free stderr. Do not reuse `summarize_or_fail()` for handoff. Do not change `CaptureError` or summarize/compare errors.
- **Rationale**: `CaptureError` currently interpolates unsupported `schema_version` into the message. Reusing that helper would violate FR-013 for an agent-facing command. Sanitizing globally would change existing summarize/compare output.
- **Alternatives considered**: Changing `capture.py` error text; documenting the leak as acceptable. Rejected as a compatibility change or a privacy hole.

## Unresolved items

None. Human review is still required before Issue #37 receives `agent:ready`.
