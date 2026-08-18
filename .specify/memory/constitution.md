# CAPT Constitution

Durable product and engineering principles for the Coding Agent Performance Toolkit.

This file is the specification-layer source of truth for principles and architectural constraints. It does not replace operational agent instructions.

| Concern | Canonical source |
| --- | --- |
| Product and engineering principles | This constitution |
| Operational agent instructions, validation, Git/PR/lifecycle, human approval gates | [AGENTS.md](../../AGENTS.md) |
| Durable architectural decisions | [docs/decisions/](../../docs/decisions/README.md) |
| Current system structure | [docs/architecture.md](../../docs/architecture.md) |
| Product intent | [docs/product.md](../../docs/product.md) |
| Spec Kit usage in this repository | [docs/spec-kit.md](../../docs/spec-kit.md) |

Do not copy these principles into `AGENTS.md`. Link here instead.

## Core Principles

### I. Local-first

CAPT runs on the user's machine. Session data, source code, captures, and analysis stay local by default.

Do not send user data externally. Do not add remote persistence, hosted analysis, or a public network bind. Telemetry receivers bind to `127.0.0.1` only. Network access is an explicit exception, not a default.

### II. Deterministic-first analysis

Prefer inspectable, repeatable rules over model-generated judgment.

Insights and summaries must point to counts, timings, or other observed facts. Do not score quality, emit recommendations, or infer root cause unless a later accepted specification explicitly adds that behavior.

### III. Privacy by default

Traces, prompts, diffs, logs, captures, and repository contents are confidential.

- Do not read unofficial agent transcripts such as `~/.claude/projects`.
- Do not upload, phone home, or emit telemetry from CAPT.
- Do not print OTLP payloads, prompts, responses, tool inputs, or tool content.
- Summaries select fields through an explicit allowlist.
- Error messages name files and line numbers, never payloads.
- Absolute paths do not appear in summaries.
- Test fixtures and specification examples use synthetic data only.
- Do not commit prompts, responses, real traces, corporate logs, secrets, or private source.

### IV. Provider-neutral core

The core is not tied to one coding-agent vendor. Domain records, reports, storage, and generic OTLP decoding stay provider-neutral.

Vendor-specific names, export settings, and allowlist mapping belong in adapters at the edge. The collector and generic OTLP decoder do not import Claude Code event names.

### V. Vendor adapters at the edge

Keep vendor-specific parsing isolated. Do not invent a generic provider framework, registry, ABC, plugin system, or marketplace without a proven second implementation and an accepted decision.

Official, documented interfaces are the integration contract. Unstable internal formats are not.

### VI. Bounded-memory and streaming processing

Prefer streaming and incremental analysis. Do not load an entire capture or raw attribute map when a single-pass or bounded structure is enough.

Readers enforce line limits. Summarizers keep small duration lists and series state. New features must not require unbounded materialization of envelopes or payloads.

### VII. No required LLM or model dependency in the core

Core features must work without an LLM, hosted model, or API key.

Model-based features may exist later only as an optional layer after an accepted decision. Spec Kit itself is development tooling; it is not a CAPT runtime dependency and does not authorize adding a model API to the product.

### VIII. Compatibility and public-contract discipline

Preserve public commands and versioned schemas.

Incompatible changes need a new version. Readers may ignore unknown fields when that is safe. Never reuse an existing field for a new meaning. New report fields appear only through an explicit allowlist.

### IX. Synthetic fixtures for sensitive telemetry

Tests, examples, and specification artifacts use synthetic fixtures only.

Do not paste captures into issues, pull requests, or Spec Kit documents. Do not use real session identifiers, prompts, tool payloads, or corporate paths as examples.

### X. No premature generic frameworks

Follow existing project patterns. Prefer explicit code, composition, and small typed values.

Do not add `utils.py`, `helpers.py`, factories, registries, ABCs, or protocols without a concrete consumer. Do not create packages, persistence, or remote services before a real query or workflow requires them.

### XI. Human approval for scope and risk

A human owns readiness, risk classification, scope expansion, and merge.

Stop and ask before expanding scope, introducing a runtime dependency, changing a public command or versioned schema incompatibly, adding network access, persistence, or an LLM, publishing a release, changing CI, secrets, or repository settings, using destructive Git commands, or merging a pull request.

Spec Kit must not apply `agent:ready`, `agent:working`, `needs:human-review`, or `risk:*` labels. Only a human may apply `agent:ready`.

## Engineering constraints

- Use Python 3.14.
- Manage the project with `uv`.
- Keep the CLI on Typer.
- Write modern, idiomatic, strongly typed Python.
- Prefer immutable domain values and `@dataclass(slots=True)` for data-focused types.
- Keep CLI, domain, adapters, parsing, and rendering separate.
- Do not add Spec Kit or `specify-cli` as a CAPT application or runtime dependency.

## Specification and execution split

Spec Kit improves specification quality. It does not replace the GitHub/Cursor/Codex execution lifecycle.

```text
Roadmap / product idea
        ↓
Spec Agent (pinned Spec Kit)
  constitution? → specify → clarify? → plan → tasks → analyze.md
        ↓
specification-only review PR
        ↓
human review / merge
        ↓
manual GitHub Agent Task Issue
        ↓
human: agent:ready
        ↓
existing Cursor / CI / Codex lifecycle
```

`/speckit.implement` is not the production implementation path in this pilot. `/speckit.taskstoissues` is not an automatic bridge into the CAPT issue lifecycle. The Spec Agent stops after the specification review PR. See [docs/spec-kit.md](../../docs/spec-kit.md).

## Governance

- This constitution is canonical for durable principles. `AGENTS.md` is canonical for operational procedure.
- Accepted ADRs remain in force. Do not silently supersede an ADR here.
- If documentation conflicts with established public behavior or tests, treat it as documentation drift and stop before changing behavior.
- Amendments require a pull request and human approval.
- Do not weaken privacy, local-first, deterministic-first, provider-boundary, compatibility, or human-approval rules to make a specification or tool fit.

**Version**: 1.0.1 | **Ratified**: 2026-08-17 | **Last Amended**: 2026-08-18
