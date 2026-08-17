# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach]

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only unless a human approves a new dependency. Spec Kit is not a runtime dependency.

**Storage**: Local versioned JSONL captures / in-memory summary state / N/A

**Testing**: `uv run pytest` with synthetic fixtures

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Streaming and bounded memory; do not materialize entire captures

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM

**Scale/Scope**: Single-capture analysis unless the spec says otherwise

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [ ] Local-first: no outbound user-data path, no public bind
- [ ] Deterministic-first: evidence is observed facts, not model judgment
- [ ] Privacy: no payloads, identifiers, absolute paths, or real fixtures
- [ ] Provider-neutral core; vendor mapping stays in adapters
- [ ] Streaming / bounded memory preserved
- [ ] No required LLM or model API in core
- [ ] Public commands and versioned schemas remain compatible, or a version change is explicit
- [ ] No premature registry, ABC, plugin system, or generic framework
- [ ] Human approval identified for scope, dependencies, schema, or lifecycle risk
- [ ] Implementation will enter GitHub as a manual Agent Task Issue, not via `/speckit.implement`

## CAPT design notes

- **Privacy impact**: [none / potential / confirmed] and the allowlist implication
- **Deterministic evidence**: [fields and thresholds]
- **Bounded-memory impact**: [what state is added]
- **Provider neutrality**: [core vs adapter]
- **Compatibility**: [schema/command effect]
- **Validation**: [commands that must pass]
- **Out of scope**: [carried from spec]
- **Human decisions**: [open questions that block implementation]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── spec.md
├── plan.md              # This file
├── research.md          # Optional; omit when existing code is sufficient
├── data-model.md        # Optional; omit when no new entities exist
├── quickstart.md        # Optional
├── contracts/           # Optional
├── tasks.md             # Created by /speckit.tasks
└── analyze.md           # Consistency report from /speckit.analyze
```

### Source Code (repository root)

Use the existing CAPT layout. Do not invent a new package tree.

```text
src/coding_agent_performance/
    cli.py
    adapters/claude_code/
    trace/
docs/
tests/
```

**Structure Decision**: Extend the existing package. Name the concrete files this feature will change.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., new abstraction] | [current need] | [why existing pattern is insufficient] |
