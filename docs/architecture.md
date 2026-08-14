# Architecture

## Goals

The Coding Agent Performance Toolkit (CAPT) is a local-first, provider-agnostic CLI. It exists to help developers measure and improve coding-agent efficiency: context usage, redundant work, and long-running task continuity.

CAPT is not a coding agent. Core features must work without an LLM API key, a hosted model, or a network round-trip to a vendor.

## Architectural principles

- Local-first: run on the user's machine and keep data there.
- Provider-agnostic: no core dependency on a single agent vendor.
- Deterministic-first: prefer inspectable, repeatable analysis over model-generated judgment.
- No model or LLM API dependency for core functionality.
- Session data and source code are sensitive by default.
- No data is sent externally.
- Vendor-specific adapters stay isolated from domain logic.
- Future outputs should be concise, structured, and useful to both humans and agents.
- Avoid premature abstractions.
- Implement only what the current feature needs.
- Use idiomatic, modern, strongly typed Python 3.14.

## System boundaries

In scope today:

- CLI entry points (`capt` and `python -m coding_agent_performance`)
- Environment diagnostics for Python, Git, Claude Code, and Codex
- A loopback-only OTLP HTTP/JSON receiver for Claude Code logs and metrics
- Versioned JSONL envelopes on the local filesystem

Out of scope today:

- Normalization of `resourceLogs` / `resourceMetrics`, session analysis, and insights
- Reading Claude Code transcripts under `~/.claude/projects`
- Databases, remote HTTP APIs, public network binds, TLS, gRPC, and protobuf
- MCP, embeddings, semantic search, and Context Ledger
- Telemetry from CAPT itself, plugins, and provider registries

Cursor is intentionally omitted from diagnostics because it does not provide a stable CLI needed for this check.

Remote services and public HTTP APIs remain out of scope. The OTLP receiver is a local, ephemeral ingestion boundary: it binds only to `127.0.0.1`, has no authentication surface for the internet, and is not a product API.

## Current architecture

```text
Claude Code
    -> OTLP HTTP/JSON on loopback
    -> CAPT local receiver
    -> versioned raw envelope
    -> local JSONL file
```

Package layout:

```text
src/coding_agent_performance/
    cli.py                         Top-level Typer app
    diagnostics.py                 Environment checks
    adapters/claude_code/telemetry.py   Export settings and shell snippet
    trace/cli.py                   `capt trace` rendering and errors
    trace/collector.py             OTLP HTTP/JSON receiver
    trace/storage.py               Exclusive JSONL capture writer
```

The Claude Code adapter knows only how to describe official export configuration. It does not start Claude Code, edit `~/.claude/settings.json`, or parse events.

The collector does not know Claude Code. It accepts `POST /v1/logs` and `POST /v1/metrics`, persists the JSON object as received, and counts successful batches. It does not interpret OTLP resource attributes.

Storage writes one compact JSON line per HTTP request. Inner log records and metric data points stay nested inside `payload` until a later normalization PR.

Diagnostics still use only the standard library. Collection uses the standard library HTTP server plus `platformdirs` for the user state directory.

## Future architecture

Later work should grow incrementally around a local domain model, not around vendor APIs.

Likely shape, kept high-level on purpose:

1. **Ingestion.** Isolated adapters configure or read vendor-specific sources and emit raw captures. The Claude Code path is OTLP HTTP/JSON; other agents may differ.
2. **Normalization.** A provider-independent layer turns raw envelopes into a shared session/trace model. That layer does not live inside the HTTP receiver.
3. **Domain.** Deterministic analysis operates on the normalized model: redundant calls, loops, oversized outputs, and later a Context Ledger.
4. **Search.** Code search optimized for LLM consumption, still local.
5. **Output.** Concise structured reports for humans and agents.

Vendor adapters must remain at the edge. The collector, storage format, and future domain types should not import Claude Code-specific event names.

Packages are created only when they have a real implementation. There is no generic provider registry in this version.

## Why not Django, PostgreSQL, Docker, or remote services

This is a local developer CLI. A web framework, a server database, containers, and hosted APIs would add operational cost before there is a product need. SQLite or other local storage can be considered later if persistence becomes necessary. Until then, JSONL files and in-memory counters are enough.

The local OTLP receiver does not change that decision. It is not a web product, not a daemon, and not an externally reachable service.

Remote services would also conflict with the privacy rule: session data and source code must not leave the machine.

## Local-first strategy

- Prefer the filesystem and local processes over servers.
- Keep the default workflow offline.
- Treat network access as an explicit exception. The collector listens on loopback only and makes no outbound requests.
- Isolate vendor-specific export configuration so removing or replacing an adapter does not rewrite storage or future domain logic.

## Sensitive-data policy

Traces, prompts, diffs, logs, captures, and repository contents are confidential by default.

- Do not read agent session files from `~/.claude/projects`.
- Do not upload, phone home, or emit telemetry from CAPT.
- Do not commit real traces, prompts, corporate logs, or unsanitized source snippets.
- Do not print OTLP payloads in the terminal.
- Keep user prompts, assistant responses, tool details, and tool content disabled in the suggested Claude Code snippet.
- Captures may still contain session identifiers, model names, account identity, working directories, tool names, and token/cost metrics. Treat them as sensitive.
- Test fixtures must be synthetic.

## Splitting into other repositories

Keep CAPT in one repository until a boundary is forced by real use. Consider a split only when at least one of these is true:

- A component has an independent release cycle or a different audience.
- Vendor adapters become large enough that they slow down core development.
- A library needs to be reused by another tool without pulling in the CLI.

Until then, a single Python package with a small public CLI is the simpler and more honest design.
