# Product

CAPT is a local-first CLI that helps developers understand and improve how coding agents use time, tokens and cost, context, tools, searches, and reasoning or execution cycles.

CAPT is not a coding agent. It observes and summarizes agent work. It does not replace Claude Code, Codex, Cursor, or any other client.

See [architecture.md](architecture.md) for system structure and [development.md](development.md) for how to change the project.

## Problem

Coding-agent sessions are expensive and hard to inspect from inside the session.

Common failures include:

- Little visibility into cost, duration, and token use
- Redundant tool calls and searches
- Tools used in an inefficient order
- Oversized tool results that consume context
- Lost context on long-running tasks
- Difficulty comparing two approaches to the same job
- Over-reliance on the model to evaluate its own work

Developers need local, explainable evidence. They should not have to send session data to another model to learn what happened.

## Target users

- Individual developers who use coding agents every day
- Engineering teams that want consistent local practices
- People responsible for developer productivity
- Maintainers of tools and integrations for coding agents

CAPT is a developer tool. It is not a workplace surveillance product and must not be used to monitor individual employee productivity.

## Jobs to be done

- Collect coding-agent activity with a safe local configuration
- Summarize a session without sending data to a model
- Identify waste and problematic patterns
- Produce compact context so another agent can continue a task
- Improve searches and tool results for LLM consumption
- Compare runs and see whether a workflow change helped

## Value proposition

CAPT aims to make agent work more efficient, cheaper, and easier to continue.

It should reduce token, cost, and context waste while keeping analysis explainable. The core stays portable across models and clients, keeps data local, and produces structured output that both humans and agents can consume.

## Product principles

- **Local-first.** Analysis runs on the user's machine.
- **Provider-agnostic.** The product is not tied to one vendor.
- **Deterministic-first.** Inspectable rules come before model judgment.
- **Privacy by default.** Session data and source code stay confidential.
- **Explainable evidence.** Claims should point to counts, timings, or other observed facts.
- **Useful without an API key.** Core features work offline.
- **Structured output.** Humans and agents should be able to parse the same reports.
- **Incremental delivery.** Ship one useful slice at a time.
- **No premature platform.** Do not build marketplaces, plugins, or remote infrastructure before there is a proven need.

## Current capabilities

After the telemetry-summary work, CAPT can:

- Run `capt doctor` for local environment checks
- Collect Claude Code logs and metrics through a loopback OTLP HTTP/JSON receiver
- Store versioned JSONL capture envelopes
- Validate those envelopes in streaming mode
- Decode OTLP HTTP/JSON
- Normalize Claude Code telemetry through an allowlist
- Print deterministic text and JSON summaries
- Detect repeated tool calls, repeated failed tool calls, high cumulative tool result volume, and dominant tool usage from those summaries
- List eligible local capture files without reading their contents

This version does not score sessions, emit recommendations, compare captures, or call a model.

## Product direction

These are themes, not a schedule or delivery promise.

### Observe

Capture sessions. Produce summaries. Report cost, tokens, duration, and tool use.

### Understand

Add deterministic insight rules for loops, redundant calls, failures, oversized outputs, compactions, and subagent use.

### Improve

Recommend changes from evidence. Compare before and after. Evaluate workflows.

### Preserve context

Keep a Context Ledger, checkpoints, compact handoffs, and a way to resume long tasks.

### Improve retrieval

Search code in a form that agents can use: compact results, ranking, and grouping suited to LLMs.

## Non-goals

- Replacing coding agents
- Depending on a model in the core
- Storing data in a remote service
- Monitoring individual employee productivity
- Capturing prompts and responses by default
- Reading unstable internal transcript formats
- Creating a plugin marketplace
- Adding a web app, Django, PostgreSQL, or remote infrastructure without a validated need

## Success indicators

Do not treat these as numeric targets.

Useful signals include:

- Time needed to get a useful diagnosis
- Amount of identifiable waste
- Fewer tool calls or less context after a recommendation
- Quality and size of handoffs
- Share of analysis that can be explained from evidence
- Number of providers supported without coupling the core
- Absence of data leaks

## Product boundaries

The core may produce deterministic evidence and, later, deterministic recommendations.

LLM integrations may exist later as an optional layer. They must not become a requirement for core features.

Any remote capability must be opt-in.

Persistence or a service is allowed only when a real query or workflow cannot be served by local files and in-memory analysis.
