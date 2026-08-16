# ADR 0001: Local-first deterministic core

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Project maintainers

## Context

CAPT inspects coding-agent sessions that contain source code, prompts, paths, and account identity. Those sessions often run under corporate accounts that cannot send data to a hosted model.

The product needs to remain useful without an API key and without asking users to trust a remote analysis service.

## Decision

CAPT is a local CLI.

The core does not depend on an LLM or model API key.

Primary analysis is deterministic and inspectable.

Model-based features may exist later only as an optional layer.

The core does not send user telemetry to an external service.

## Consequences

### Positive

- Session data and source code stay on the user's machine.
- Results are repeatable and easier to review.
- The tool works for users who cannot use a vendor API key.

### Negative

- Early recommendations must be rule-based.
- Some semantic analysis will need an optional layer later, if it is justified.

## Alternatives considered

- A hosted analysis service. Rejected because it conflicts with privacy and local-first use.
- Requiring an LLM for summaries. Rejected because core features must work without a model.

## Follow-up

Keep optional model features out of the core until a later ADR accepts that boundary change.
