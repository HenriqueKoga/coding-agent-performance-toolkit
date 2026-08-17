# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft

**Input**: User description: "$ARGUMENTS"

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST [specific capability]
- **FR-002**: System MUST [specific capability]

*Mark unclear requirements with `[NEEDS CLARIFICATION: ...]` and run `/speckit.clarify` before planning.*

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]

## CAPT constraints *(mandatory)*

Fill every item. These are specification gates, not implementation details.

### Privacy

- What identifiers, paths, payloads, prompts, or tool content could this feature expose?
- What allowlist fields, if any, may appear in text or JSON output?
- Confirm fixtures and examples are synthetic.

### Deterministic evidence

- What observed counts, timings, or other facts support a finding or summary field?
- What must not be inferred (root cause, quality, recommendations)?

### Bounded memory

- Does the feature keep streaming/incremental behavior?
- What new in-memory state is required, and why is it bounded?

### Provider neutrality

- Does the change stay in provider-neutral records/reports?
- If vendor-specific mapping is required, does it stay in an adapter?

### Compatibility

- Does this add, change, or version a public command or schema?
- Are new report fields allowlisted?

### Out of scope

- [Explicit non-goals for this increment]

### Validation

- [Exact commands and checks required before delivery]

### Human decisions

- [Decisions a person must make before or during implementation]
- Spec Kit must not mark the work `agent:ready` or apply lifecycle/risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: [Measurable, technology-agnostic outcome]
- **SC-002**: [Measurable, technology-agnostic outcome]

## Assumptions

- [Assumption about scope, existing behavior, or environment]
