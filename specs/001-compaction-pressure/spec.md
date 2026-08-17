# Feature Specification: Detect compaction pressure

**Feature Branch**: `001-compaction-pressure`

**Created**: 2026-08-17

**Status**: Pilot specification (not implemented in this adoption)

**Input**: Detect compaction pressure from existing provider-neutral session aggregates using one deterministic threshold.

**Operational Issue**: [#34](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/34) already records this feature as a GitHub Agent Task. This directory is the Spec Kit pilot for that idea. It does not implement the feature and does not change Issue labels.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See compaction pressure on a summarized capture (Priority: P1)

A developer summarizes a local CAPT capture and wants to know whether the session showed compaction pressure. The summary already counts `sessions.compactions`. When that count meets a single explicit threshold, the summary includes one deterministic finding that reports only the observed count. When the count is below the threshold, no finding appears.

**Why this priority**: Compaction is an existing Understand-theme signal. The count is already aggregated, so this is the smallest useful insight increment.

**Independent Test**: Summarize synthetic captures with 0, 1, 2, and more than 2 compactions and compare text and JSON insight output.

**Acceptance Scenarios**:

1. **Given** a capture whose session aggregate has 0 or 1 compaction, **When** the capture is summarized, **Then** no compaction-pressure finding is emitted.
2. **Given** a capture whose session aggregate has 2 or more compactions, **When** the capture is summarized, **Then** one finding reports only the observed compaction count.
3. **Given** a capture that already has tool-insight findings, **When** compaction pressure is also present, **Then** existing tool insights and summary metrics remain unchanged and the new finding appears beside them.

### Edge Cases

- Zero sessions or zero compactions produces no finding.
- Exactly one compaction is below threshold and produces no finding.
- Exactly two compactions produces a finding.
- Counts above two produce the same finding shape with the larger observed count.
- The finding must not claim that compaction is bad, estimate context-window use, or recommend a next action.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST derive the finding only from the existing provider-neutral `sessions.compactions` aggregate.
- **FR-002**: CAPT MUST use one explicit deterministic threshold. Prefer `>= 2` if that matches current telemetry semantics.
- **FR-003**: Below threshold MUST emit no finding; at or above threshold MUST emit a finding.
- **FR-004**: Finding evidence MUST contain only the observed compaction count.
- **FR-005**: Text and JSON outputs MUST expose equivalent evidence.
- **FR-006**: Existing tool insights and summary metrics MUST remain unchanged.
- **FR-007**: The finding MUST state observed compaction pressure only. It MUST NOT infer root cause, quality degradation, or recommendations.

### Key Entities

- **CompactionPressure finding**: Allowlisted insight with the observed compaction count. No session identifiers, paths, or payloads.

## CAPT constraints *(mandatory)*

### Privacy

- Only the aggregate compaction count may appear.
- No identifiers, absolute paths, prompts, responses, or tool content.
- Fixtures and this specification use synthetic counts only.

### Deterministic evidence

- Evidence is the integer `sessions.compactions` compared to a fixed threshold.
- Do not infer why compaction happened or whether it harmed the session.

### Bounded memory

- Reuse the existing incremental session counter. Do not retain extra payload data or parse raw transcripts.

### Provider neutrality

- Use provider-neutral session aggregates only. No new Claude Code-specific mapping.

### Compatibility

- Additive insight field on the existing summary schema.
- Existing tool insight fields stay compatible.

### Out of scope

- Per-compaction timing or sequence analysis
- Context-window estimation
- Root-cause analysis
- Recommendations
- Configurable thresholds
- Severity or scoring
- Cross-capture comparison
- Generic insight framework
- Feature implementation in the Spec Kit adoption task
- Development-pipeline changes

### Validation

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Plus deterministic tests for zero, below threshold, threshold, above threshold, coexistence with existing insights, rendering, JSON, and privacy.

### Human decisions

- Stop if compaction semantics require raw provider transcript inspection or a schema redesign.
- Spec Kit must not mark this work `agent:ready` or apply lifecycle/risk labels.
- Implementation enters the existing GitHub lifecycle through Issue #34 or a later Agent Task Issue created by hand.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can predict the finding from the compaction count and the documented threshold without running a model.
- **SC-002**: Text and JSON show the same count or the same absence of a finding.
- **SC-003**: Summaries of synthetic captures never include identifiers, paths, or payloads.

## Assumptions

- `sessions.compactions` already counts normalized compaction lifecycle events.
- Threshold `>= 2` is compatible with current telemetry semantics.
- Issue #31 insight consolidation has already landed, so this feature can reuse the existing Insights pattern.
- This Spec Kit directory is a pilot. Implementation is a separate Agent Task.
