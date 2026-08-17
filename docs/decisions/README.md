# Architecture decisions

Architecture Decision Records (ADRs) capture durable choices and their trade-offs.

An ADR is not implementation documentation. It records why a boundary exists, not how every module works.

Do not rewrite an accepted ADR to hide an old decision. If the project changes course, add a new ADR that supersedes the previous one.

Allowed statuses:

- **Proposed:** under discussion
- **Accepted:** in force
- **Superseded:** replaced by a later ADR
- **Rejected:** considered and not adopted

See [architecture.md](../architecture.md) for the current system structure.

## Current decisions

| Number | Decision | Status |
| --- | --- | --- |
| [0001](0001-local-first-deterministic-core.md) | Local-first deterministic core | Accepted |
| [0002](0002-official-telemetry-sources.md) | Official telemetry sources | Accepted |
| [0003](0003-versioned-jsonl-captures.md) | Versioned JSONL captures | Accepted |
| [0004](0004-vendor-adapters-at-the-edge.md) | Vendor adapters at the edge | Accepted |
| [0005](0005-trace-aggregation-boundaries.md) | Trace aggregation boundaries | Accepted |

## When to create an ADR

Create an ADR for:

- An architectural boundary change
- A new persistence model
- A network dependency
- Introducing an LLM into the product
- An incompatible schema change
- A new framework
- A new extensibility strategy
- A security or privacy decision
- A choice that is hard to reverse

Do not create an ADR for local refactors, bug fixes, or trivial details.

Copy [0000-template.md](0000-template.md) when adding a new record.
