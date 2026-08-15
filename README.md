# Coding Agent Performance Toolkit (CAPT)

Local-first toolkit for measuring and improving coding-agent performance, context usage, and developer workflows.

> **Early-stage project.** CAPT is in pre-alpha. This version can collect raw Claude Code OpenTelemetry envelopes locally and summarize them deterministically. It does not yet produce performance insights or recommendations.

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
- An experimental loopback OTLP HTTP/JSON collector for Claude Code
- Local JSONL capture files for raw logs and metrics envelopes
- Deterministic text and JSON summaries of those captures
- Linting, formatting, type checking, tests, and CI

This version does **not** inspect Claude Code transcripts, persist data in a database, score sessions, or generate insights.

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
uv run capt trace collect claude-code
uv run capt trace summarize path/to/capture.jsonl
```

`capt doctor` checks essential tools (Python 3.14+ and Git) and optional coding-agent CLIs (Claude Code and Codex). Missing optional tools produce warnings and do not fail the command. Cursor is not checked yet because it does not expose a stable CLI for this diagnosis.

You can also run:

```bash
uv run python -m coding_agent_performance --help
```

## Collect Claude Code telemetry

`capt trace collect claude-code` starts a **local, loopback-only** OTLP HTTP/JSON receiver. It is a CAPT ingestion boundary, not a generic OpenTelemetry Collector and not a network service.

Default listen address: `127.0.0.1:4318`.

1. In one terminal, start the collector:

```bash
uv run capt trace collect claude-code
```

2. In another terminal, export the variables printed by CAPT and start Claude Code. The printed snippet enables logs and metrics over `http/json` and keeps prompts, responses, tool details, and tool content disabled.

3. Use Claude Code as usual. CAPT stores each accepted OTLP request as one JSON line.

4. Press `Ctrl+C` in the collector terminal to stop. CAPT prints the capture path and the number of log and metric batches received.

Optional flags:

```bash
uv run capt trace collect claude-code --port 4319
uv run capt trace collect claude-code --output /path/to/capture.jsonl
```

`--output` is refused if the file already exists. CAPT does not start Claude Code, and it does not modify `~/.claude/settings.json` or your shell profile.

### Capture location

Without `--output`, captures are written under the user state directory from `platformdirs`. On Linux that is:

```text
~/.local/state/capt/captures/
```

Filenames look like `claude-code-20260814T220000Z-a1b2c3.jsonl`. Directories and files use restricted POSIX permissions where the OS supports them (`0700` / `0600`).

### Capture format

Each accepted POST becomes one compact JSON line. CAPT does not split or interpret the inner OTLP batch. A log envelope looks like:

```json
{"schema_version":1,"received_at":"2026-08-14T22:00:00.123456+00:00","source":"claude-code","signal":"logs","payload":{"resourceLogs":[]}}
```

Metrics use `"signal":"metrics"` and the received `resourceMetrics` object as `payload`.

## Summarize a capture

`capt trace summarize` reads a local JSONL capture, validates CAPT envelopes, decodes OTLP HTTP/JSON, and prints a deterministic summary. It does not call an LLM.

Tokens, cost, duration, and model totals come from `api_request` events when at least one is present. If a capture has no `api_request` events, CAPT falls back to `claude_code.token.usage` and `claude_code.cost.usage`. It never adds those two sources together.

The summary is an allowlist. Session, prompt, message, request, account, and organization identifiers are omitted. Prompt text, assistant text, errors, tool inputs, parameters, commands, and paths are omitted. The raw capture file remains sensitive and local.

```bash
uv run capt trace summarize ~/.local/state/capt/captures/example.jsonl

uv run capt trace summarize \
  ~/.local/state/capt/captures/example.jsonl \
  --format json
```

`--format text` is the default. `--format json` writes only JSON to stdout. See [docs/summary-format.md](docs/summary-format.md) for the pre-alpha JSON contract.

## Troubleshooting

- **Port already in use.** Choose another loopback port with `--port`, or stop the process bound to `4318`.
- **No events received.** Confirm the collector is still running, then start Claude Code in a second terminal with the printed `export` lines. Official Claude Code telemetry is opt-in via `CLAUDE_CODE_ENABLE_TELEMETRY=1`.
- **Managed settings.** Corporate or managed Claude Code settings can override local OTLP endpoints and protocols. If nothing arrives, check whether an administrator locked the exporter destination.
- **Export debugging.** `claude --debug` can help diagnose exporter errors. Use it only for diagnosis; do not paste debug logs that may contain identity or workspace details into public issues.
- **Never share a capture** without reviewing and sanitizing it first. Even with prompt and tool content disabled, envelopes can still include session ids, model names, Claude Code version, account identity, working directory, tool names, token counts, and cost metrics.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run capt trace collect claude-code --help
uv run capt trace summarize --help
```

## Roadmap

Planned incrementally, without dates or delivery promises:

1. Deterministic insight rules on top of summaries
2. Detection of redundant calls, loops, and oversized outputs
3. A Context Ledger for long-running task continuity
4. Code search shaped for LLM consumption
5. Isolated adapters for additional coding agents

## Non-goals

- Replacing Claude Code, Codex, Cursor, or any other coding agent
- Requiring an LLM API key or hosted model for core features
- Sending session data, prompts, or source code to remote services
- Building a generic plugin marketplace or provider framework in the first iterations
- Shipping Django, PostgreSQL, Docker, remote HTTP APIs, or a web UI as part of the local-first core

## Privacy and security

CAPT is designed to run locally. Do not assume that future commands sanitize data for you.

The collector binds only to `127.0.0.1`, does not log received payloads, and does not make outbound network requests. The printed Claude Code snippet keeps `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`, `OTEL_LOG_TOOL_DETAILS`, and `OTEL_LOG_TOOL_CONTENT` set to `0`. There is no flag in this version to enable those fields.

Summaries omit identifiers and content through an allowlist. The raw capture file is still sensitive; do not commit or share it.

Never add traces, prompts, source code, logs, or other corporate data to this repository without sanitization. Treat session files, captures, and workspace contents as sensitive by default. This project must not phone home, collect telemetry of its own, or upload your data.

## License

Licensed under the [Apache License 2.0](LICENSE).
