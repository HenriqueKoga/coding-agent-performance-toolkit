# Coding Agent Performance Toolkit (CAPT)

Local-first toolkit for measuring and improving coding-agent performance, context usage, and developer workflows.

> **Early-stage project.** CAPT is in pre-alpha. This repository currently provides project scaffolding, a small CLI, and local environment diagnostics. Trace import, analysis, and optimization features are not implemented yet.

## Why CAPT exists

Coding agents such as Claude Code, Codex, and Cursor can spend tokens, context, and time on redundant tool calls, loops, and oversized outputs. Those costs are hard to see from inside a single session.

CAPT is intended to become a local, vendor-independent CLI that helps developers inspect agent sessions, find waste, and keep long-running work coherent. It is not a new coding agent, and its core features will not depend on an LLM API key or a hosted model.

## Principles

- **Local-first.** Analysis runs on your machine. Session data and source code stay local.
- **Provider-agnostic.** The product is independent of any single coding-agent vendor.
- **Deterministic-first.** Core behavior should be explainable and repeatable without a model in the loop.
- **No model or LLM API dependency** for core functionality.
- **Sensitive by default.** Traces, prompts, and code are treated as confidential. CAPT must not send them anywhere.

## What this version includes

- An installable Python 3.14 package managed with `uv`
- The `capt` CLI with `--help`, `--version`, and `doctor`
- Local environment checks for Python, Git, Claude Code, and Codex
- Linting, formatting, type checking, tests, and CI

This version does **not** import traces, analyze sessions, persist data, or integrate with coding agents beyond checking whether their CLIs are installed.

## Quickstart

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/HenriqueKoga/coding-agent-performance-toolkit.git
cd coding-agent-performance-toolkit
uv sync
```

## Current commands

```bash
uv run capt --help
uv run capt --version
uv run capt doctor
```

`capt doctor` checks essential tools (Python 3.14+ and Git) and optional coding-agent CLIs (Claude Code and Codex). Missing optional tools produce warnings and do not fail the command. Cursor is not checked yet because it does not expose a stable CLI for this diagnosis.

You can also run:

```bash
uv run python -m coding_agent_performance --help
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Roadmap

Planned incrementally, without dates or delivery promises:

1. Import and normalize coding-agent traces
2. Deterministic session analysis
3. Detection of redundant calls, loops, and oversized outputs
4. A Context Ledger for long-running task continuity
5. Code search shaped for LLM consumption
6. Isolated adapters for specific coding agents

## Non-goals

- Replacing Claude Code, Codex, Cursor, or any other coding agent
- Requiring an LLM API key or hosted model for core features
- Sending session data, prompts, or source code to remote services
- Building a generic plugin marketplace or provider framework in the first iterations
- Shipping Django, PostgreSQL, Docker, HTTP APIs, or a web UI as part of the local-first core

## Privacy and security

CAPT is designed to run locally. Do not assume that future commands sanitize data for you.

Never add traces, prompts, source code, logs, or other corporate data to this repository without sanitization. Treat session files and workspace contents as sensitive by default. This project must not phone home, collect telemetry, or upload your data.

## License

Licensed under the [Apache License 2.0](LICENSE).
