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

CAPT currently inspects the local runtime, not agent sessions.

In scope today:

- CLI entry points (`capt` and `python -m coding_agent_performance`)
- Environment diagnostics for Python, Git, Claude Code, and Codex

Out of scope today:

- Trace import, normalization, or analysis
- Persistence, databases, and HTTP APIs
- Agent adapters, MCP, embeddings, semantic search, and Context Ledger
- Reading agent config or session files
- Telemetry, plugins, and remote services

Cursor is intentionally omitted from diagnostics because it does not provide a stable CLI needed for this check.

## Current architecture

The first version is a small installable Python package:

```text
src/coding_agent_performance/
    cli.py            Typer application and command rendering
    diagnostics.py    Environment checks and report data
    __main__.py       `python -m coding_agent_performance`
```

`diagnostics.py` collects typed results. `cli.py` renders them. Collection does not print, and rendering does not probe the environment. That split keeps the checks testable without exercising Typer internals or the machine's real tooling.

Diagnostics use only the standard library: `sys.version_info`, `shutil.which`, and `subprocess.run` with a short timeout, captured output, and no `shell=True`. Python 3.14+ and Git are essential. Claude Code and Codex are optional; a missing optional tool is a warning, not a failure.

## Future architecture

Later work should grow incrementally around a local domain model, not around vendor APIs.

Likely shape, kept high-level on purpose:

1. **Ingestion.** Isolated adapters read vendor-specific session artifacts and emit a normalized trace representation.
2. **Domain.** Deterministic analysis operates on that normalized model: redundant calls, loops, oversized outputs, and later a Context Ledger.
3. **Search.** Code search optimized for LLM consumption, still local and independent of a hosted embedding service unless a later design explicitly justifies it.
4. **Output.** Concise structured reports for humans and agents.

Vendor adapters must remain at the edge. Domain types, analysis, and CLI commands should not import Claude Code, Codex, or Cursor-specific formats.

Packages such as `trace`, `context`, `search`, and `adapters` will be created only when they have a real implementation.

## Why not Django, PostgreSQL, Docker, or remote services

This is a local developer CLI. A web framework, a server database, containers, and hosted APIs would add operational cost before there is a product need. SQLite or other local storage can be considered later if persistence becomes necessary. Until then, files on disk and in-memory data structures are enough.

Remote services would also conflict with the privacy rule: session data and source code must not leave the machine.

## Local-first strategy

- Prefer the filesystem and local processes over servers.
- Keep the default workflow offline.
- Treat network access as an explicit, later exception, never as a hidden dependency of core commands.
- Isolate any future vendor-specific reader so removing or replacing it does not rewrite the domain.

## Sensitive-data policy

Traces, prompts, diffs, logs, and repository contents are confidential by default.

- Do not read agent session files until a dedicated, reviewed ingestion feature exists.
- Do not upload, phone home, or emit telemetry.
- Do not commit real traces, prompts, corporate logs, or unsanitized source snippets.
- Future sample fixtures must be synthetic or explicitly sanitized.

## Splitting into other repositories

Keep CAPT in one repository until a boundary is forced by real use. Consider a split only when at least one of these is true:

- A component has an independent release cycle or a different audience.
- Vendor adapters become large enough that they slow down core development.
- A library needs to be reused by another tool without pulling in the CLI.

Until then, a single Python package with a small public CLI is the simpler and more honest design.
