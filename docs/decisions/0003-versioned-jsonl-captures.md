# ADR 0003: Versioned JSONL captures

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Project maintainers

## Context

The collector receives OTLP HTTP/JSON batches and must persist them locally for later summary. The first use case is a single-file, streaming read. There is no current query that requires a database.

## Decision

Each accepted OTLP request becomes one JSONL envelope.

The envelope includes `schema_version`.

Writes are exclusive and local.

The reader streams one line at a time and never loads the whole file.

Do not add a database until a real query requires one.

## Consequences

### Positive

- The format is simple, auditable, and portable.
- Streaming keeps memory use bounded.
- Incompatible changes can be versioned.

### Negative

- Capture files remain sensitive and must stay out of the repository.
- Queries across many captures are not optimized.

## Alternatives considered

- SQLite for every capture. Rejected because it adds schema management and another sensitive store before there is a multi-capture query.
- In-memory only. Rejected because users need a file they can summarize later.

## Follow-up

Revisit storage if later features need durable multi-capture queries. An incompatible envelope change requires a new schema version and should consider a new ADR.
