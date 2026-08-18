# Feature Specification: Support `--latest` for trace handoff

**Feature Branch**: `005-handoff-latest`

**Created**: 2026-08-18

**Status**: Draft for human review

**Input**: Allow `capt trace handoff` to resolve the latest available local capture when the operator explicitly passes `--latest`, while preserving existing handoff text/JSON/file-output behavior and reusing the capture-discovery semantics already used by `capt trace summarize --latest`.

**Operational Issue**: [#63](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/63) is the existing operational Agent Task. Its body is the immutable original feature brief. After this specification PR is reviewed and merged, repository automation records the approved Spec Kit artifacts on that Issue. A human may then apply `agent:ready`. This specification does not rewrite the Issue body.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Handoff the latest local capture (Priority: P1)

A developer has several local CAPT captures and wants a compact evidence handoff of the newest one without copying a path from `capt trace list`. They already know `capt trace summarize --latest` and expect the same selection rule.

When they pass `--latest` and no capture path, CAPT selects that newest eligible local capture and prints the existing compact text handoff to stdout. Explicit `capt trace handoff CAPTURE` remains available and unchanged.

**Why this priority**: This is the missing capture-selection slice for handoff. Compact extract and safe file output already exist; operators should not need a second discovery ritual just to hand off the newest capture.

**Independent Test**: Seed a default capture directory with two synthetic `.jsonl` files of different ages. Run `capt trace handoff --latest` and compare stdout with `capt trace handoff` on the newer file. Confirm the older file is not selected and that an explicit path still works without `--latest`.

**Acceptance Scenarios**:

1. **Given** two eligible synthetic captures in the default capture directory, **When** `capt trace handoff --latest` is run, **Then** CAPT prints the existing compact text handoff for the same capture that `capt trace summarize --latest` would select under that storage state.
2. **Given** the same newest capture as an explicit path, **When** `capt trace handoff CAPTURE` is run without `--latest`, **Then** stdout matches today's explicit-path text handoff for that file.
3. **Given** an explicit capture path and no `--latest`, **When** the command is repeated, **Then** behavior is indistinguishable from the current command for that path, format, and file-output options.

---

### User Story 2 - Keep JSON and safe file output while selecting `--latest` (Priority: P2)

A developer who already uses `--format json`, `--output PATH`, and `--force` wants those options to work after selecting a capture with `--latest`. Discovery only chooses which local capture is transformed; it must not fork the handoff document or the writer.

**Why this priority**: Selection is useless if JSON v1 or file persistence silently change. This slice is independently testable once `--latest` can resolve a capture.

**Independent Test**: On a synthetic newest capture, compare `--latest` text/JSON/file runs with explicit-path runs of that same file. Confirm JSON v1 fields and order, file bytes, `--force` overwrite, and writer refusals remain the existing contracts.

**Acceptance Scenarios**:

1. **Given** an eligible newest capture, **When** `capt trace handoff --latest --format json` is run, **Then** JSON v1 is written to stdout with the same fields, order, and values that an explicit-path JSON run of that capture would produce.
2. **Given** a destination that does not exist, **When** `capt trace handoff --latest --output PATH` is used, **Then** the file receives the selected representation, stdout has no handoff body, and the bytes match an explicit-path `--output` run of that same capture and format.
3. **Given** an existing regular destination, **When** `--latest --output PATH --force` is used, **Then** CAPT replaces that regular file using the current explicit-overwrite behavior and still refuses symbolic links, directories, FIFOs, and other non-regular destinations.
4. **Given** `--latest` with `--output` omitted, **When** the command succeeds, **Then** stdout remains the default and no handoff file is created.

---

### User Story 3 - Reject ambiguous or empty selection with the same discovery rules (Priority: P3)

A developer who mixes an explicit path with `--latest`, omits both, or has no eligible captures must get concise deterministic guidance. They must not get a guessed capture, a second discovery algorithm, or a leak of payloads or absolute paths.

**Why this priority**: Fail-closed selection is what keeps `--latest` additive rather than implicit. Errors can be tested without changing successful handoff output.

**Independent Test**: Invoke handoff with both selectors, with neither, with extra capture arguments, and with a missing or empty default capture directory. Confirm non-zero exits, no traceback, no payload or absolute-path disclosure, and that `--latest` still uses the existing summarize/list eligibility and newest-first ordering, including filename tie-break and symlink exclusion.

**Acceptance Scenarios**:

1. **Given** an explicit `CAPTURE` and `--latest` together, **When** the command is run, **Then** CAPT exits non-zero, does not emit a handoff body, and prints concise guidance that the two selectors are mutually exclusive.
2. **Given** neither `CAPTURE` nor `--latest`, **When** the command is run, **Then** CAPT exits non-zero and prints concise guidance that one of those selectors is required. It MUST NOT silently choose the latest capture.
3. **Given** `--latest` and no eligible captures in the default capture directory, **When** the command is run, **Then** CAPT exits non-zero with the same class of concise directory/empty-directory failure already used by summarize `--latest`.
4. **Given** the same default capture directory state, **When** summarize `--latest` and handoff `--latest` both succeed, **Then** they select the same capture file. There is no documented reason for them to differ.

### Edge Cases

- Explicit `CAPTURE` without `--latest`: current handoff behavior, including `--format`, `--output`, `--force`, capture-input errors, and JSON v1.
- `--latest` without `CAPTURE`: select the newest eligible `.jsonl` in the default capture directory; then run the existing handoff transform and renderer.
- `CAPTURE` and `--latest` together: refuse. Do not prefer one selector.
- Neither `CAPTURE` nor `--latest`: refuse. Do not imply latest.
- Extra capture-path arguments: refuse. Handoff remains one selected capture.
- `--latest` with `--format json`: JSON v1 unchanged.
- `--latest` with `--output` / `--force`: existing writer safety unchanged.
- `--force` without `--output`: still invalid, including when `--latest` is present.
- Default capture directory missing, not a directory, unreadable, or empty of eligible files: fail closed.
- Equal modification timestamps: descending filename tie-break already used by summarize/list.
- Symbolic links, directories, nested files, and non-`.jsonl` entries in the default capture directory are not eligible, matching summarize/list.
- `--latest` does not follow capture-directory symbolic links as eligible captures.
- `--latest` is still unsupported on `capt trace compare` and is not added to other commands unless an existing shared primitive already requires it.
- Discovery errors MUST NOT print payloads, prompts, tool content, raw envelope fields, or absolute paths.
- After a capture is selected, invalid-capture errors keep the existing handoff payload-free mapping.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST accept `capt trace handoff --latest` as a valid way to select exactly one local capture. `--latest` MUST be explicit. CAPT MUST NOT select the latest capture when neither `CAPTURE` nor `--latest` is supplied.
- **FR-002**: CAPT MUST keep explicit `capt trace handoff CAPTURE` working. When `CAPTURE` is present and `--latest` is absent, handoff text, JSON, `--output`, and `--force` behavior MUST remain the current contracts from `003-compact-trace-handoff` and `004-persist-handoff-safely`.
- **FR-003**: Explicit `CAPTURE` and `--latest` MUST be mutually exclusive. Supplying both MUST exit non-zero, print `Provide either a capture path or --latest, not both.`, emit no handoff body, and write no handoff file.
- **FR-004**: Omitting both `CAPTURE` and `--latest` MUST exit non-zero and print `Provide a capture path or --latest.` CAPT MUST NOT invent a default capture.
- **FR-005**: `--latest` MUST reuse the existing canonical capture-discovery semantics already used by `capt trace summarize --latest` and `capt trace list`. Eligibility, default capture directory, newest-first ordering, equal-timestamp filename tie-break, and symlink exclusion MUST NOT be reimplemented as a handoff-specific discovery subsystem.
- **FR-006**: Under the same repository/local storage state, `capt trace handoff --latest` MUST select the same capture file that `capt trace summarize --latest` would select. This specification identifies no reason for those selectors to differ.
- **FR-007**: After a capture is selected, CAPT MUST run the existing compact-handoff transform and renderer. `--latest --format json` MUST be supported. Handoff JSON v1 fields, values, and ordering MUST NOT change.
- **FR-008**: `--latest --output PATH` MUST use the existing safe file-output semantics: byte-identical representation, no handoff body on successful stdout, refuse-if-exists without `--force`, refuse non-regular destinations, and no parent-directory creation.
- **FR-009**: `--latest --output PATH --force` MUST preserve the current explicit-overwrite behavior for an existing regular file and MUST NOT broaden writer permissions or destination types.
- **FR-010**: Existing text rendering MUST remain unchanged apart from which capture is selected through `--latest`. CAPT MUST NOT add narrative, recommendations, Markdown, or new evidence fields.
- **FR-011**: Extra capture-path arguments MUST still fail closed. When more than one positional capture path is supplied, CAPT MUST print `Provide exactly one capture path.`
- **FR-012**: `--latest` discovery failures MUST reuse the existing latest-capture failure text already used by summarize (`Default capture directory does not exist.`, `Default capture path is not a directory.`, `No capture files found in the default capture directory.`, and `Could not read default capture directory: {detail}`). After selection, capture-input errors MUST keep the existing handoff payload-free mapping.
- **FR-013**: Discovery and error handling MUST NOT newly expose raw prompts, responses, tool payloads, source code, secrets, envelope field values, or unnecessary absolute paths.
- **FR-014**: Existing `capt trace summarize`, `compare`, `collect`, `list`, capture storage, provider adapters, insights, summary schema, and comparison schema MUST remain unchanged. Compare MUST continue to reject `--latest`. No global change to what "latest" means is permitted.
- **FR-015**: No new runtime dependency, generic discovery/provider framework, remote/cloud capture lookup, database, or Context Ledger MAY be introduced. If a shared selector helper is needed, it MUST be the smallest concrete extraction of the existing summarize latest-selection path.
- **FR-016**: User-facing README and architecture/product sentences that currently say handoff requires exactly one explicit path and that `--latest` is not supported MUST be updated so they match this additive CLI. The change MUST stay concise and MUST NOT copy this specification or JSON schemas into the README.

### Key Entities

- **CaptureSelection**: The operator's choice of exactly one selector: an explicit capture path, or `--latest`. The two MUST NOT be combined. Neither selector means no selection.
- **SelectedCapture**: The single local eligible CAPT JSONL file that results from that choice. For `--latest`, it is the newest eligible file in the default capture directory according to the existing summarize/list rules. After selection, the existing `TraceHandoff` extract and optional file write apply unchanged.

## CAPT constraints *(mandatory)*

### Privacy

- `--latest` only chooses which already-local capture is transformed through the existing compact-handoff allowlist.
- Successful output may contain only the existing handoff allowlist: closed capture source, filename, integer aggregates, and existing insight evidence.
- Discovery MUST NOT read unofficial transcripts, follow capture symlinks as eligible files, or emit capture-directory absolute paths.
- Error text MAY include a capture or destination basename and a fixed reason. It MUST NOT include payloads, prompts, responses, tool content, interpolated envelope values, or absolute paths.
- Tests, fixtures, README examples, and this specification use synthetic data and synthetic relative paths only.

### Deterministic evidence

- Selection is an observed filesystem order already defined for summarize/list: newest eligible `.jsonl`, then descending filename on ties.
- The handoff document remains a deterministic extract of the selected capture's summary. This feature does not add metrics, insights, scores, or recommendations.
- CAPT MUST NOT infer which capture the operator "probably" wanted when selectors are missing or conflicting.

### Bounded memory

- `--latest` MUST keep the existing single running-maximum scan used by summarize. It MUST NOT materialize raw envelopes, payloads, or an unbounded extra listing in order to pick one file.
- After selection, summarization and handoff construction stay on the existing incremental path.
- File output still writes one already-rendered compact string.

### Provider neutrality

- Capture discovery is provider-neutral filesystem selection in the default capture directory.
- Handoff construction still consumes the provider-neutral summary extract. No adapter change is required.

### Compatibility

- Additive CLI behavior on `capt trace handoff`: optional `CAPTURE` plus `--latest`.
- Explicit `capt trace handoff CAPTURE` remains compatible.
- Handoff text output, JSON v1, and `--output` / `--force` semantics remain compatible.
- No new report fields. No schema version bump.
- Summarize `--latest` and list ordering remain the canonical definition of "latest".

### Out of scope

- Implicitly using the latest capture when neither `CAPTURE` nor `--latest` is supplied
- Adding `--latest` to commands that do not already support it, including `capt trace compare`, unless required by an existing shared primitive
- Changing how captures are ordered or what "latest" means globally
- Context Ledger, checkpoints, history, resume, or automatic agent-context injection
- New handoff formats such as Markdown
- Handoff JSON v1 changes
- Multiple capture selection or batch handoff
- Remote/cloud capture discovery
- Database or external service
- Generic discovery/provider framework
- New runtime dependency unless a concrete requirement cannot be satisfied with existing code and the standard library
- Broad CLI refactoring unrelated to the shared latest-capture path
- Rewriting `003-compact-trace-handoff` or `004-persist-handoff-safely` except by this later additive increment
- `/speckit.implement` or `/speckit.taskstoissues` in this specification phase
- Applying `agent:ready` or mutating Issue #63's body

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

Focused validation MUST cover at least:

- explicit `CAPTURE` continues to work
- `--latest` text handoff
- `--latest --format json`
- `--latest --output PATH`
- `--latest --output PATH --force`
- `CAPTURE` + `--latest` rejected
- neither `CAPTURE` nor `--latest` rejected
- no available captures produces concise deterministic failure
- latest selection agrees with the existing summarize/latest behavior
- handoff JSON v1 remains unchanged
- file-output bytes remain identical to the selected handoff representation
- privacy/sanitization and existing writer safety remain intact

### Human decisions

- Human approval is required before Issue #63 receives `agent:ready`. Spec Kit must not apply that label or rewrite the Issue body.
- This specification pins `--latest` as an explicit selector on `capt trace handoff`, mutual exclusion with `CAPTURE`, reuse of summarize/list latest semantics, unchanged JSON v1, and unchanged `--output`/`--force` safety.
- Stop for human review if specification or implementation would require changing the global meaning/order of "latest", changing handoff JSON v1, introducing implicit latest selection without `--latest`, a new runtime dependency, remote/network discovery, a generic discovery/persistence/provider abstraction, Context Ledger/history semantics, or changes outside the narrow handoff/latest integration.
- Spec Kit must not apply lifecycle or risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer who knows the newest eligible capture can predict the `--latest` text handoff: it matches an explicit-path handoff of that same file.
- **SC-002**: Under one storage state, summarize `--latest` and handoff `--latest` name the same selected file.
- **SC-003**: Mixing `CAPTURE` with `--latest`, or omitting both, fails closed and never emits a guessed handoff.
- **SC-004**: JSON v1 field order and values for a selected capture are identical whether that capture was named explicitly or chosen with `--latest`.
- **SC-005**: `--latest --output` file bytes are identical to the selected stdout representation; `--force` and unsafe-destination refusals still match the current writer contract.
- **SC-006**: Successful output and selector/discovery errors contain no absolute paths, prompts, responses, tool payloads, or raw envelope values.
- **SC-007**: A new user can learn from `--help` and the README that handoff accepts either an explicit path or `--latest`, not both.

## Assumptions

- Issue #37 / PR #57 shipped stdout compact handoff. Issue #58 / PR #60 shipped `--output`/`--force`. This slice adds capture selection around those contracts and does not reopen the compact allowlist or writer design.
- `capt trace summarize --latest` and `capt trace list` already define eligibility and newest-first order. Reusing that path satisfies the Issue requirement that the selected capture match summarize unless a documented reason requires a difference. No such reason is identified.
- Reusing summarize's selector error strings avoids a second CLI dialect for the same choice.
- Making `CAPTURE` optional on handoff, matching summarize, is an additive command change rather than an incompatible schema change.
- Specs `003-compact-trace-handoff` and `004-persist-handoff-safely` remain the contracts for extract content and file safety. Those documents forbade `--latest` for their slices; this later increment is the approved exception for handoff only.
- README and architecture sentences that currently say `--latest` is unsupported on handoff would become false after implementation and therefore must be updated in that implementation, without a documentation rewrite.
- Compare continues to require two explicit paths. Sharing a helper with summarize does not require adding `--latest` to compare.
- No `[NEEDS CLARIFICATION]` items remain. `/speckit-clarify` is not required unless a reviewer rejects a pinned default.
