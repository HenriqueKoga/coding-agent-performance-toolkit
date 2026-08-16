# ADR 0004: Vendor adapters at the edge

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Project maintainers

## Context

Claude Code is the first supported source. Other coding agents may follow, but their official interfaces will differ.

A generic provider framework would force an abstraction before a second implementation exists.

## Decision

Keep vendor-specific parsing and names in adapters.

Domain records and reports stay provider-neutral.

The collector and OTLP decoder do not know Claude Code event names.

Do not add an ABC, registry, or plugin framework before a second concrete need exists.

## Consequences

### Positive

- The core stays less coupled to one vendor.
- A later provider can be added without rewriting storage or reports.

### Negative

- Some duplication may be tolerated until a second adapter proves a shared shape.
- Abstractions will be extracted from real implementations, not designed first.

## Alternatives considered

- A provider plugin marketplace. Rejected as premature platform work.
- Putting Claude Code names in the collector or decoder. Rejected because it couples ingestion to one vendor.

## Follow-up

Extract shared adapter interfaces only after a second official source exists and the duplication is real.
