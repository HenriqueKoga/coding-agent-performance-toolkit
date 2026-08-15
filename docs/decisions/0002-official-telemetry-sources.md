# ADR 0002: Official telemetry sources

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Project maintainers

## Context

Coding agents store rich session history in vendor-specific files. Those formats can change without notice and often contain prompts, responses, and workspace paths.

CAPT needs a source of activity data that can be documented, tested, and kept at arm's length from private transcripts.

## Decision

Use official, documented interfaces as integration contracts.

Claude Code is collected through OpenTelemetry HTTP/JSON.

Do not read internal transcripts under `~/.claude/projects`.

Unstable internal formats are not integration contracts.

## Consequences

### Positive

- Less risk of breakage when a vendor changes private files.
- The integration can be described and tested from public documentation.

### Negative

- Available fields are limited to official telemetry.
- Content and identity in those envelopes remain sensitive.

## Alternatives considered

- Parsing `~/.claude/projects` transcripts. Rejected because the format is unofficial and contains prompt and response content.
- Scraping terminal output. Rejected because it is brittle and hard to keep private.

## Follow-up

Future adapters may use different official mechanisms. Each adapter must document its source and privacy risks.
