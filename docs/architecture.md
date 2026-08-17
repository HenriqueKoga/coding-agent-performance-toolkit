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
- Read-only listing of eligible local captures
- Streaming validation of those envelopes
- OTLP HTTP/JSON decoding
- Claude Code allowlist normalization
- Incremental, deterministic text and JSON summaries
- Deterministic insight rules for repeated tool calls, repeated failed tool calls, high cumulative tool result volume, and dominant tool usage

Out of scope today:

- Additional insight rules (loops, oversized individual outputs, compactions, subagent analysis)
- Recommendations, scores, and capture comparison
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
    -> CaptureReader
    -> OTLP decoder
    -> Claude Code normalizer
    -> incremental summarizer
    -> insight computation
    -> text or JSON renderer
```

Package layout:

```text
src/coding_agent_performance/
    cli.py                              Top-level Typer app
    diagnostics.py                      Environment checks
    adapters/claude_code/telemetry.py   Export settings and shell snippet
    adapters/claude_code/normalizer.py  Allowlist mapping onto domain records
    trace/cli.py                        `capt trace` arguments, errors, and exit codes
    trace/collector.py                  OTLP HTTP/JSON receiver
    trace/storage.py                    Exclusive JSONL capture writer, listing, and latest-capture selection
    trace/capture.py                    Shared envelope schema and streaming reader
    trace/json_codec.py                 Strict JSON parsing for collector and reader
    trace/otel.py                       Generic OTLP HTTP/JSON decoder
    trace/records.py                    Provider-neutral normalized records
    trace/report.py                     Immutable summary DTOs
    trace/cost.py                       Safe USD to microdollar conversion
    trace/aggregation.py                Incremental summarizer and statistics
    trace/insights.py                   Deterministic insight rules
    trace/summary.py                    Capture-to-summary use case
    trace/rendering.py                  Allowlist JSON dict plus text/JSON summary and capture-list output
```

The Claude Code adapter knows official export configuration and how to map Claude Code log and metric names onto small domain records. It does not start Claude Code, edit `~/.claude/settings.json`, or keep prompt, response, or tool content.

The collector does not know Claude Code. It accepts `POST /v1/logs` and `POST /v1/metrics`, persists the JSON object as received, and counts successful batches. It does not interpret OTLP resource attributes.

Storage writes one compact JSON line per HTTP request. The reader validates those envelopes in streaming mode and never loads the whole file. `capt trace list` scans the default capture directory for eligible `.jsonl` files and prints filename, size in bytes, and UTC modification time without opening capture contents. Optional `--limit` prints a prefix of that newest-first listing. `capt trace summarize` accepts an explicit path or `--latest`, which selects the newest eligible `.jsonl` file in the default capture directory without following symbolic links. Listing and `--latest` share the same eligibility and newest-first ordering rules. `--latest` keeps a single running maximum; listing materializes the ordered set.

The OTLP decoder understands `AnyValue`, `resourceLogs`, and `resourceMetrics` only. It does not import the Claude Code adapter.

Normalization is allowlist-based. Session and prompt identifiers may exist in memory for counting and deduplication. They never appear in the summary DTO, text output, or JSON output.

The summarizer is incremental. It keeps small duration lists for percentiles and metric series state for cumulative versus delta resolution. It does not materialize every envelope or raw attribute map.

Text and JSON renderers consume the finished DTO only. JSON is written with `allow_nan=False`.

Diagnostics still use only the standard library. Collection uses the standard library HTTP server plus `platformdirs` for the user state directory. Summary uses only the standard library.

## Capture reader

`CaptureReader` opens the file in binary mode and reads one line at a time, with a 16 MiB line limit so an oversized envelope is rejected before it is fully decoded as text.

Each line must be UTF-8 JSON with `schema_version == 1`, a timezone-aware `received_at`, a non-empty `source`, `signal` of `logs` or `metrics`, and a JSON object payload. Logs require `resourceLogs`; metrics require `resourceMetrics`. A file cannot mix sources. Unknown envelope fields are ignored.

Errors name the file and line number and never include the line or payload.

## OTLP decoder

The decoder walks OTLP JSON:

```text
resourceLogs -> resource.attributes -> scopeLogs -> logRecords -> attributes
resourceMetrics -> resource.attributes -> scopeMetrics -> metrics -> sum|gauge dataPoints
```

`AnyValue` supports `stringValue`, `boolValue`, `intValue` (including the JSON string form of `int64`), `doubleValue`, `bytesValue`, `arrayValue`, and `kvlistValue`. JSON strings inside attributes are not parsed. `bytesValue` is kept opaque and is not decoded as text. Histograms, exponential histograms, and summaries are counted as unsupported.

Event names come from `event.name`, then `eventName`, then a textual body that clearly names a `claude_code.*` event. The body is discarded after naming.

## Claude Code normalizer

The normalizer is the only vendor-specific mapping. There is no provider ABC, registry, or plugin system.

It emits small immutable records: model request, model request error, tool execution, user prompt, assistant response, activity measurement, and named lifecycle events. Unknown events and metrics are counted by name.

Cost prefers `cost_usd_micros`. If that field is absent, `cost_usd` is converted with `Decimal` and stored as an integer number of USD micros. The two fields are never added together.

## Provider-neutral records

Domain records live in `trace/records.py`. They carry only the fields required for aggregation. After normalization, the full OTLP attribute map is gone. The finished report lives in `trace/report.py` and does not contain mutable maps.

## Incremental summarizer

`api_request` events are the preferred source for tokens, cost, duration, model, and query source. If any remain after deduplication, token and cost metrics are ignored for those totals. Otherwise the summarizer falls back to `claude_code.token.usage` and `claude_code.cost.usage`.

Log records are deduplicated when `session.id`, `event.sequence`, and the event name are all present. Metric points are deduplicated by series identity and timestamp.

For `sum` metrics:

- `DELTA`: unique datapoints are added
- `CUMULATIVE`: each series keeps the datapoint with the latest `timeUnixNano`
- Series identity is metric name, relevant attributes, and `startTimeUnixNano`
- Missing or unknown temporality uses the latest datapoint and records a coverage warning

Gauges keep the latest datapoint per series. Counter resets are new series because `startTimeUnixNano` changes. CAPT does not use `max(value)` as a substitute for time, because counters can restart.

Percentiles use nearest-rank: `index = ceil(percentile * count) - 1`.

## Why not SQLite

JSONL plus in-memory series state is enough for a single-file summary. A database would add schema management, another sensitive store, and no current query that the incremental pass cannot answer. SQLite can be reconsidered if later features need durable multi-capture queries.

## Future architecture

Later work should grow incrementally around the local domain model, not around vendor APIs.

Likely shape, kept high-level on purpose:

1. **Ingestion.** Isolated adapters configure or read vendor-specific sources and emit raw captures. The Claude Code path is OTLP HTTP/JSON; other agents may differ.
2. **Normalization.** A provider-independent layer turns raw envelopes into shared records. That layer does not live inside the HTTP receiver.
3. **Domain.** Deterministic insight rules operate on summaries and normalized records. Repeated tool calls, repeated failed tool calls, high cumulative tool result volume, and dominant tool usage are implemented. Future rules may detect loops, redundant calls, oversized individual outputs, and later support a Context Ledger.
4. **Search.** Code search optimized for LLM consumption, still local.
5. **Output.** Concise structured reports for humans and agents.

Insight rules remain small, deterministic, and explainable. Vendor adapters must remain at the edge. The collector, storage format, OTLP decoder, and domain types should not import Claude Code-specific event names except through the adapter.

Packages are created only when they have a real implementation. There is no generic provider registry in this version.

## Why not Django, PostgreSQL, Docker, or remote services

This is a local developer CLI. A web framework, a server database, containers, and hosted APIs would add operational cost before there is a product need.

The local OTLP receiver does not change that decision. It is not a web product, not a daemon, and not an externally reachable service.

Remote services would also conflict with the privacy rule: session data and source code must not leave the machine.

## Local-first strategy

- Prefer the filesystem and local processes over servers.
- Keep the default workflow offline.
- Treat network access as an explicit exception. The collector listens on loopback only and makes no outbound requests.
- Isolate vendor-specific export configuration so removing or replacing an adapter does not rewrite storage or domain logic.

## Sensitive-data policy

Traces, prompts, diffs, logs, captures, and repository contents are confidential by default.

- Do not read agent session files from `~/.claude/projects`.
- Do not upload, phone home, or emit telemetry from CAPT.
- Do not commit real traces, prompts, corporate logs, or unsanitized source snippets.
- Do not print OTLP payloads in the terminal.
- Keep user prompts, assistant responses, tool details, and tool content disabled in the suggested Claude Code snippet.
- Captures may still contain session identifiers, model names, account identity, working directories, tool names, and token/cost metrics. Treat them as sensitive.
- Summaries select fields through an allowlist and omit identifiers and content.
- Test fixtures must be synthetic.

## Splitting into other repositories

Keep CAPT in one repository until a boundary is forced by real use. Consider a split only when at least one of these is true:

- A component has an independent release cycle or a different audience.
- Vendor adapters become large enough that they slow down core development.
- A library needs to be reused by another tool without pulling in the CLI.

Until then, a single Python package with a small public CLI is the simpler and more honest design.

## Architecture decisions

Durable choices and trade-offs live in [decisions/README.md](decisions/README.md). This document describes the current structure; it does not replace those records.
