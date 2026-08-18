# Feature Specification: Export compact trace handoff

**Feature Branch**: `003-compact-trace-handoff`

**Created**: 2026-08-18

**Status**: Draft for human review

**Input**: Add a deterministic command that exports a compact, agent-readable handoff from one local CAPT capture using only existing allowlisted summary aggregates and insights, without capturing prompts or responses, inventing intent, or calling a model.

**Operational Issue**: [#37](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/37) is the GitHub Agent Task for implementation after this specification is approved and merged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Export a compact evidence handoff (Priority: P1)

A developer has one local CAPT JSONL capture from a long-running coding-agent session. They want a compact evidence handoff that another agent or a later local workflow can consume, without re-reading the capture, reconstructing intent, or sending data anywhere.

The handoff is an evidence extract, not a narrative. It reports only a small allowlisted subset of the existing summary: safe capture identity, key session/tool/model aggregates, and the deterministic insights already computed for that capture.

**Why this priority**: This is the first Preserve Context slice. It turns already-safe summary evidence into a smaller, machine-consumable artifact so a later optional layer or another coding agent can continue from facts rather than from invented goals or source-code context.

**Independent Test**: Run `capt trace handoff <capture.jsonl>` on synthetic captures covering empty/minimal traces, traces with no insight findings, and traces with one or more insight findings. Verify text output contains only the compact allowlisted evidence and matches the same values as JSON for those fields.

**Acceptance Scenarios**:

1. **Given** one valid explicit CAPT JSONL capture, **When** `capt trace handoff` is run, **Then** CAPT prints a compact handoff to stdout built only from the existing summary and insights for that capture.
2. **Given** a capture whose summary has no insight findings, **When** a handoff is exported, **Then** the handoff still includes the insights object with empty arrays and null findings, and it does not invent goals, decisions, TODOs, or next steps.
3. **Given** a capture whose summary has one or more insight findings, **When** a handoff is exported, **Then** those findings appear with the same allowlisted evidence fields already used by `capt trace summarize`.
4. **Given** the same capture file, **When** the handoff command is run twice, **Then** the output is byte-stable for the selected format.

### User Story 2 - Consume the same handoff as JSON (Priority: P2)

A developer or local script wants the compact handoff as structured JSON so another agent or tool can parse it without reading text layout.

JSON is the canonical structured representation. Text output is the human-readable counterpart required by existing CLI conventions.

**Why this priority**: Agent-readable consumption is the reason the artifact exists, but it is independently testable from the text command once the compact evidence set is defined.

**Independent Test**: Run the same synthetic captures with `--format json` and assert the exact v1 JSON contract, including field order, null versus empty-array insight shapes, and agreement with text evidence.

**Acceptance Scenarios**:

1. **Given** a valid handoff, **When** `--format json` is used, **Then** JSON contains exactly the versioned compact-handoff contract defined in this specification and `plan.md`.
2. **Given** identical inputs, **When** JSON export is repeated, **Then** serialized field order and values are stable.
3. **Given** a capture whose summary includes insight findings and one whose insights are all absent, **When** both are exported as JSON, **Then** present findings use the existing insight field shapes and absent findings remain empty arrays or `null` rather than omitted keys.

### Edge Cases

- The input path is missing, unreadable, or not a valid CAPT capture.
- The capture is valid but empty or minimal: no sessions, no tool calls, no model usage, and no insight findings.
- Insight arrays are empty and singleton insight fields are `null`; the insights object is still present.
- Tool success rate is `null` because there are no tool calls; the field remains present as `null` rather than `0`.
- Capture identity is the existing safe filename and source only; an absolute input path must not appear in successful output or error text.
- The command is invoked with no capture path, more than one capture path, or `--latest`.
- The operator redirects stdout to a file; v1 does not add a dedicated `--output` flag.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST add `capt trace handoff CAPTURE` with exactly one explicit CAPT JSONL capture-path argument for v1.
- **FR-002**: CAPT MUST summarize that input through the existing capture summarization and insight path rather than duplicate OTLP decoding, normalization, aggregation, or insight rules.
- **FR-003**: CAPT MUST produce the handoff as a deterministic transformation of the finished provider-neutral summary. The CLI MUST only select the capture, invoke that transformation, and render the result.
- **FR-004**: The handoff MUST contain exactly this compact evidence allowlist, in this stable order:
  1. `schema_version`
  2. capture identity: `source` and `file` only
  3. session aggregates: `count`, `prompts`, `assistant_responses`, `compactions`, `subagents_completed`
  4. model-usage aggregates: `usage_source`, `requests`, `errors`, `refusals`, `estimated_cost_usd_micros`, and `tokens.input` / `tokens.output`
  5. tool aggregates: `calls`, `successes`, `failures`, `result_bytes`, `success_rate_bps`
  6. insights: the existing insight findings object, using the same keys and per-finding fields already emitted by `capt trace summarize`
- **FR-005**: `schema_version` MUST be integer `1` and MUST be independent from the trace-summary schema version.
- **FR-006**: `capture.file` MUST remain a filename only. `sessions.prompts` and `sessions.assistant_responses` MUST remain integer counts. They MUST NEVER include prompt text, assistant text, or other content.
- **FR-007**: Insights MUST be copied from the existing summary findings. CAPT MUST NOT rephrase, score, rank, filter, or add narrative around those findings.
- **FR-008**: The handoff MUST NOT invent goals, decisions, TODOs, source-code context, recommendations, quality judgments, or a next-action section.
- **FR-009**: JSON MUST be the canonical structured representation. Text MUST expose the same evidence values and insight presence/absence as JSON. Text MUST follow the existing `--format text|json` CLI convention, with `text` as the default and `json` as the structured form. Markdown is not a v1 format.
- **FR-010**: Output MUST be deterministic for the same capture: stable field order, stable insight order already defined by summarization, and no non-deterministic timestamps or path materialization.
- **FR-011**: By default, CAPT MUST print the handoff to stdout. V1 MUST NOT add a file-output flag. Operators who need a file may redirect stdout.
- **FR-012**: The command MUST be local-only and read-only. It MUST NOT persist handoff state, bind a network port, or send data externally.
- **FR-013**: Invalid input MUST exit non-zero with concise error text, no traceback, no payload contents, and no absolute path disclosure.
- **FR-014**: Existing `trace summarize`, `trace compare`, `trace list`, collection, summary JSON schema/version, comparison JSON schema/version, and insight behavior MUST remain unchanged.
- **FR-015**: The handoff JSON contract MUST use exactly the top-level keys and nested allowlist defined in `plan.md`. No additional top-level or nested fields are permitted in v1, including activity, coverage, duration percentiles, cache-token totals, per-model breakdowns, per-tool `by_name` rows, envelope counts, received-at timestamps, comparison-availability metadata, identifiers, paths, payloads, or invented narrative fields.

### Key Entities

- **TraceHandoff**: Immutable provider-neutral compact evidence extract produced from one `TraceSummary`. It contains only the allowlisted identity, aggregate, and insight fields. It does not contain capture paths, prompt or response content, tool arguments or results, source code, scores, or recommendations.
- **HandoffInsights**: The existing summary insight findings, carried unchanged into the handoff. Empty arrays and `null` singleton findings remain explicit.

## CAPT constraints *(mandatory)*

### Privacy

- Successful output may contain only the compact allowlist in FR-004: safe capture `source` and filename, integer session/tool/model aggregates, `usage_source`, nullable tool success-rate basis points, and existing insight evidence fields (including already-allowlisted tool names).
- Do not emit capture paths, session identifiers, prompt text, assistant text, tool arguments/results, source-code snippets, error payloads, secrets, model payloads, raw telemetry, or provider-specific provenance beyond the existing `usage_source` enumeration.
- Input-error messages may use a safe basename if necessary, consistent with current summarization errors, but must never include an absolute path or payload content.
- Tests, fixtures, and this specification use synthetic data only.

### Deterministic evidence

- Every handoff field is copied from an existing observed summary aggregate or insight finding.
- `schema_version` is the handoff document version, not evidence.
- Do not infer user intent, root cause, quality, remaining work, or a recommended next action.
- Do not treat missing telemetry as a story about what the developer meant to do.
- Insight thresholds stay those already defined by summarization; this feature does not add or change thresholds.

### Bounded memory

- Summarize the capture with the existing incremental summarizer.
- Handoff construction reads the finished immutable summary only. It must not retain raw envelopes, attribute maps, or payloads.
- The handoff object is a fixed-shape extract plus already-bounded insight collections. It must not grow with capture size beyond those existing summary collections.

### Provider neutrality

- Handoff construction consumes the provider-neutral `TraceSummary` only.
- No new Claude Code-specific mapping, event name, or adapter branch is permitted.
- `usage_source` remains the existing provider-neutral enumeration already used by summaries.

### Compatibility

- Adds one public CLI command and a new handoff output contract with its own `schema_version`.
- Existing trace-summary and comparison JSON schemas/versions remain unchanged.
- New handoff JSON fields are explicitly allowlisted and stable.
- This feature does not version or extend the summary schema.

### Out of scope

- Capturing prompts or responses
- Reconstructing user intent or writing a session narrative
- Source-code snapshots or repository context
- Automatic TODO extraction
- LLM or model summarization
- Context Ledger persistence or history
- Checkpoint management
- Automatic resume or injection into Cursor, Claude Code, or Codex
- `--latest` or other capture discovery
- Dedicated file output / `--output`
- Markdown output
- Per-model, per-tool, activity, coverage, duration, cache-token, or timestamp fields beyond FR-004
- Changing insight thresholds or adding new insight rules
- Remote storage or sync
- Database
- Generic artifact/export framework
- Pipeline or lifecycle-workflow changes
- New runtime dependencies

### Validation

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build --clear
git diff --check
```

Plus focused tests covering deterministic JSON/text content, empty and minimal traces, insight inclusion and absence, privacy exclusions (sensitive/raw payload strings cannot appear), text/JSON agreement, CLI arity and input errors, and unchanged existing summarize/compare output.

### Human decisions

- Human approval is required before the operational Issue receives `agent:ready`.
- This specification pins the v1 compact allowlist, `capt trace handoff` command name, stdout-only output, and text-default / JSON-canonical format split. It does not approve prompts, responses, source-code capture, remote storage, persistence, a model API, `--latest`, dedicated file output, Markdown, or a generic artifact framework.
- Stop for human review if useful handoff output would require prompts, responses, source-code capture, remote storage, or model inference.
- Spec Kit must not apply lifecycle or risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can predict every handoff field from the existing summary of the same capture without running a model.
- **SC-002**: Text and JSON expose the same compact identity, aggregate values, and insight presence/absence.
- **SC-003**: Successful handoff output contains no input paths, identifiers, prompt or response content, tool payloads, source-code snippets, or invented narrative fields.
- **SC-004**: Repeating the command on the same capture produces identical output for a given format.
- **SC-005**: Handoff memory use does not scale with raw capture size beyond existing bounded summarization behavior.
- **SC-006**: Existing `capt trace summarize` and `capt trace compare` public text/JSON contracts and schema versions remain unchanged.
- **SC-007**: The handoff JSON output is described by one mandatory v1 schema with no implementation-defined extra fields.

## Assumptions

- Issue #36 comparison has already landed, so this feature can reuse `summarize_capture()` and existing insights without changing those contracts.
- `TraceSummary` remains the canonical immutable result of capture summarization.
- Copying existing insight findings into a smaller document is sufficient for the first Preserve Context slice; a later Context Ledger or resume workflow is a separate specification.
- Stdout redirection is sufficient file persistence for v1; a dedicated `--output` flag would be a later additive command change.
- Defaulting to `text` while documenting JSON as the canonical structured contract matches `summarize` and `compare` and does not make JSON optional.
- Eight-metric comparison availability metadata is internal to comparison and is not part of a handoff.
- The compact allowlist in FR-004 is the complete v1 evidence set; adding breakdowns or activity/coverage fields requires a new specification or schema version.
