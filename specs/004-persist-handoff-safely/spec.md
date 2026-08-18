# Feature Specification: Persist compact trace handoff safely

**Feature Branch**: `004-persist-handoff-safely`

**Created**: 2026-08-18

**Status**: Draft for human review

**Input**: Add an explicit local file-output option to `capt trace handoff` so the existing compact text or JSON representation can be persisted with safe, deterministic write semantics, while stdout remains the default. Audit and update the user-facing README so it matches the current public CLI, including compare, handoff, and the new file-output behavior.

**Operational Issue**: [#58](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/58) is the existing operational Agent Task. After this specification PR is reviewed and merged, #58 will be reduced to an operational envelope pointing to the approved Spec Kit artifacts. A human may then apply `agent:ready`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persist a compact handoff to an explicit local file (Priority: P1)

A developer has one local CAPT JSONL capture and wants the existing compact handoff as a file they can pass to another local agent or tool. They do not want to rely on shell redirection, and they do not want CAPT to invent a handoff directory, history, or default output path.

When they name an output file that does not already exist, CAPT writes exactly the same text or JSON representation that stdout would have produced for that capture and format. Stdout stays empty of handoff content. If they omit the file option, stdout behavior is unchanged.

**Why this priority**: This is the next Preserve Context slice. The compact extract already exists; the missing piece is a safe, explicit way to keep it as a local file.

**Independent Test**: Run `capt trace handoff` on synthetic captures with and without `--output` and with `--format text` and `--format json`. Confirm stdout is unchanged when `--output` is absent, file bytes match the selected stdout representation when `--output` is present, and successful file writes emit no handoff body on stdout.

**Acceptance Scenarios**:

1. **Given** one valid explicit CAPT JSONL capture and no `--output`, **When** `capt trace handoff` is run, **Then** CAPT prints the existing compact handoff to stdout and does not create a handoff file.
2. **Given** the same capture and `--format json` without `--output`, **When** the command is run, **Then** JSON v1 is written to stdout exactly as today.
3. **Given** a destination path that does not exist and whose parent directory already exists, **When** `--output PATH` is used, **Then** CAPT writes the selected text or JSON representation to that path and prints no handoff body to stdout.
4. **Given** the same capture, format, and a successful file write, **When** the file bytes are compared with a stdout run that omits `--output`, **Then** the persisted content is byte-identical to that stdout representation, including the trailing newline.
5. **Given** two runs with the same capture, format, and a new output path each time, **When** both succeed, **Then** the two files are byte-identical.

### User Story 2 - Refuse unsafe writes and overwrite only when asked (Priority: P2)

A developer naming a handoff file must not silently replace an existing file, follow a symbolic link, write into a directory or special file, leave a truncated final file, or learn absolute paths or capture contents from an error. If they intentionally replace a regular file, they pass an explicit `--force` together with `--output`.

**Why this priority**: File output is only useful if it cannot clobber or leak by default. Overwrite is independently testable once create-if-absent works.

**Independent Test**: Attempt writes against existing files, directories, symbolic links, POSIX FIFOs, missing parents, and failed writes. Confirm refusal by default, `--force` replacement of a regular file, unchanged destinations after failed publish, restricted permissions where the platform supports them, and concise path-free payload-free errors.

**Acceptance Scenarios**:

1. **Given** `--output` pointing at an existing regular file and no `--force`, **When** the command is run, **Then** CAPT exits non-zero, leaves that file unchanged, and does not write a partial replacement.
2. **Given** `--output` pointing at an existing regular file and `--force`, **When** the command is run, **Then** CAPT replaces that file with the complete selected handoff representation and does not follow or replace a symbolic link, directory, FIFO, or other non-regular path.
3. **Given** `--force` without `--output`, **When** the command is run, **Then** CAPT exits non-zero and does not write a file.
4. **Given** `--output` whose parent directory is missing, whose parent is not a directory, whose path is a directory, whose path is a symbolic link, or whose path is a POSIX FIFO, **When** the command is run, **Then** CAPT exits non-zero, does not create missing parents, and leaves the destination unchanged, even if `--force` is present.
5. **Given** a publish that fails after a temporary sibling file was created, **When** the command exits, **Then** that temporary file is gone and the final destination is either absent or still the previous complete file.

### User Story 3 - Keep the README aligned with the public CLI (Priority: P3)

A new user reading the repository README should see the commands they can actually run today, including `capt trace compare` and `capt trace handoff`, and should not be told that CAPT cannot produce deterministic insights after that capability has already shipped.

**Why this priority**: File output is easy to miss if the README still describes an older stdout-only, insight-less CLI. Documentation can be reviewed independently of write-safety tests.

**Independent Test**: Diff the README command and capability claims against the current Typer command surface (`capt --help`, `capt trace --help`, and each public command's `--help`) plus this specification's `--output`/`--force` contract.

**Acceptance Scenarios**:

1. **Given** the current public CLI, **When** the README command list is audited, **Then** it documents `capt trace compare BASELINE CANDIDATE` with `--format text|json`.
2. **Given** this feature's CLI contract, **When** the README handoff section is read, **Then** it documents `capt trace handoff CAPTURE` with `--format text|json`, default stdout, `--output PATH`, and `--force`.
3. **Given** already-shipped deterministic insight, comparison, and handoff behavior, **When** the README introduction, "What this version includes", and similar status claims are read, **Then** they no longer contradict those capabilities.
4. **Given** a reader who needs schemas or ADRs, **When** they follow README links, **Then** they are pointed at existing docs rather than a copied JSON schema or duplicated specification.

### Edge Cases

- `--output` is omitted: stdout text/JSON behavior, including trailing newline, remains unchanged.
- `--output` is present: stdout contains no handoff body on success; exit code 0 is the success signal.
- `--output` names a new file in an existing parent directory.
- `--output` names an existing regular file without `--force`: refuse.
- `--output` names an existing regular file with `--force`: replace atomically with the complete new content.
- `--force` is passed without `--output`: refuse.
- Destination path is a symbolic link, including a dangling link: refuse, even with `--force`.
- Destination path is a directory: refuse, even with `--force`.
- Destination path is a FIFO, Unix socket, device, or any other existing non-regular object: refuse, even with `--force`. The destination is left unchanged.
- Parent directory is missing: refuse; do not create it.
- Parent path exists but is not a directory: refuse.
- Parent directory is a symbolic link to a directory: allowed; only the final path component is refused when it is not a missing path or a regular file.
- Publish fails (destination exists without `--force`, type refused, permissions, disk): destination is unchanged, the sibling temporary file is removed, no partial final artifact remains.
- Publish succeeds and later temp cleanup fails: destination already holds the complete new handoff and MUST NOT be rolled back. Temp unlink is then best-effort.
- A concurrent process that replaces the destination path between the type check and publish is outside the guaranteed contract. Sequential use is what this slice promises.
- Output path uses `~` expansion the same way other CAPT path options already do.
- Output path `-` is an ordinary filename, not a stdout synonym.
- `--latest` remains invalid on `capt trace handoff`.
- Capture-path errors keep the existing handoff payload-free mapping; file-write errors use their own concise reasons and must not interpolate envelope fields, payloads, or absolute paths.
- Restricted POSIX file mode `0600` is applied to a newly created or replaced handoff file where the platform supports it; missing that support is not a failure.
- Parent directory permissions are not changed.
- Writing `--output` onto the input capture path is treated like any other existing file: refused unless `--force`.
- README must not document internal Python functions, experimental collector internals beyond the existing public `capt trace collect claude-code` command, or unshipped Context Ledger behavior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: CAPT MUST keep `capt trace handoff CAPTURE` with exactly one explicit capture-path argument. Stdout MUST remain the default when no file-output option is supplied. Existing `--format text|json` behavior MUST remain, with `text` as the default.
- **FR-002**: CAPT MUST add an explicit `--output PATH` option. The path is always operator-selected. CAPT MUST NOT invent a default handoff directory, filename, history, discovery flag, or Context Ledger location.
- **FR-003**: When `--output` is absent, CAPT MUST emit the same stdout text or JSON bytes as the current command, including trailing newline handling. It MUST NOT create a handoff file.
- **FR-004**: When `--output` is present and the write succeeds, CAPT MUST persist the selected representation and MUST NOT print the handoff body to stdout.
- **FR-005**: Persisted content MUST be byte-identical to the stdout representation that the same capture and `--format` would produce without `--output`, including the trailing newline. JSON v1 field order, values, and allowlist MUST remain unchanged.
- **FR-006**: CAPT MUST NOT silently overwrite an existing path. If the destination already exists as a regular file and `--force` is absent, the command MUST fail and leave that file unchanged.
- **FR-007**: CAPT MUST accept `--force` only together with `--output`. `--force` without `--output` MUST fail. `--force` MAY replace an existing regular file only. `--force` MUST NOT replace a symbolic link, directory, FIFO, Unix socket, device, or any other existing non-regular path.
- **FR-008**: CAPT MUST refuse a destination whose parent is missing or is not a directory. It MUST NOT create parent directories.
- **FR-009**: CAPT MUST refuse a destination that exists and is not a regular file, including a symbolic link (dangling included), directory, FIFO, Unix socket, or device, even when `--force` is present. Existence and type checks MUST NOT follow the destination path. A missing path is the only destination that may be created without `--force`.
- **FR-010**: File creation MUST use exclusive local semantics. The complete representation is written to a sibling temporary file in the same parent directory, then published onto the destination. **Publish is the commit.** If publish fails, CAPT MUST remove that temporary file and MUST leave the destination either absent or still the previous complete file. If publish succeeds, the destination MUST contain the complete representation; a later failure to unlink the temporary file MUST NOT roll back the destination and MUST NOT turn a completed write into a user-visible failure. The destination MUST NOT retain a truncated or partially written handoff after a failed publish. This slice does not promise to win a TOCTOU race against another process mutating the destination path between the type check and publish; sequential use is the guaranteed contract.
- **FR-011**: Newly created or replaced handoff files MUST use restricted permissions `0600` where the platform supports that mode. CAPT MUST NOT chmod the parent directory. Inability to apply a POSIX-only mode on a non-POSIX platform MUST NOT fail a successful write.
- **FR-012**: File-write and option-combination errors MUST exit non-zero with concise stderr, no traceback, no payload contents, no interpolated envelope fields, and no absolute path. A filename basename MAY appear. Capture-input errors MUST keep the existing handoff-specific mapping already established for this command.
- **FR-013**: Handoff construction MUST remain a deterministic transformation of the finished provider-neutral summary. File output MUST NOT broaden the compact allowlist, weaken text sanitization, or re-read raw capture payloads.
- **FR-014**: No new runtime dependency, generic exporter, artifact registry, persistence abstraction, database, service, or remote storage MAY be introduced. Prefer a small handoff-specific write helper over a new framework. Existing capture-storage exclusive-create patterns MAY be reused as concrete logic, not generalized into a shared persistence layer unless a later human decision says otherwise.
- **FR-015**: Existing `capt trace summarize`, `compare`, `list`, `collect`, `capt doctor`, and provider adapter behavior MUST remain unchanged. Handoff JSON v1 MUST remain unchanged. `--latest` MUST remain unsupported on handoff.
- **FR-016**: The README MUST be audited against the actual public Typer command surface and MUST document `capt trace compare BASELINE CANDIDATE` and `capt trace handoff CAPTURE` with their current format behavior plus this feature's `--output`/`--force` contract.
- **FR-017**: README introduction, "What this version includes", "Current commands", and similar user-facing status claims MUST be corrected where they contradict already-shipped deterministic insights, comparison, or handoff. The change MUST stay concise and MUST NOT copy full JSON schemas, ADRs, or this specification into the README.
- **FR-018**: README MUST NOT document internal or non-command Python functions as public CLI. The Typer command surface is the authority for which commands belong in the README.

### Key Entities

- **HandoffFileTarget**: An operator-selected local destination for one handoff representation. It has an explicit path and an overwrite intent that is false unless `--force` is present with `--output`. It is not a ledger entry, capture, or discovered artifact.
- **HandoffFileWrite**: The result of attempting to persist one complete text or JSON representation. Success means the destination contains the full byte-identical representation and stdout has no handoff body. Failed publish means the destination is unchanged and the sibling temporary file is removed. Success with a later temp-unlink miss still counts as success: the destination is complete and is not rolled back.

## CAPT constraints *(mandatory)*

### Privacy

- File output contains only the existing compact handoff allowlist. It MUST NOT add identifiers, absolute input paths, prompts, responses, tool payloads, source code, secrets, or raw envelope fields.
- Error text MAY include a destination basename and a fixed reason. It MUST NOT include absolute paths, parent directories, payload contents, or interpolated envelope values such as `schema_version`.
- Restricted file permissions reduce accidental sharing of an agent-facing artifact; they do not change the allowlist.
- Tests, fixtures, README examples, and this specification use synthetic paths and data only.

### Deterministic evidence

- The persisted file is the same evidence extract already defined by the compact handoff. This feature does not add metrics, insights, scores, recommendations, or narrative.
- Byte identity with stdout is the determinism contract for a given capture and format.
- Overwrite, symlink, and parent-directory decisions are operator actions or refusals, not inferred intent.

### Bounded memory

- Capture summarization stays on the existing incremental path.
- Handoff construction still reads the finished immutable summary only.
- Rendering still produces one compact text or JSON string. File output writes that string; it MUST NOT materialize raw envelopes or retain extra copies of the capture.

### Provider neutrality

- File output is a local I/O concern around the existing provider-neutral `TraceHandoff`.
- No adapter change is required. No vendor-specific output path is introduced.

### Compatibility

- Additive CLI options on `capt trace handoff`: `--output` and `--force`.
- Default stdout behavior is preserved.
- Handoff JSON v1, summary JSON, comparison JSON, and other public commands are unchanged.
- No new report fields.

### Out of scope

- Context Ledger persistence or history
- Checkpoints or automatic resume/injection into Cursor, Claude Code, Codex, or another agent
- `--latest` or other capture discovery on handoff
- Multiple output files or export bundles
- Markdown as a new handoff format
- Changing handoff JSON v1 or adding evidence fields
- Capturing prompts, responses, source code, tool payloads, identifiers, or invented narrative
- Remote storage, sync, database, web service, network API, or cloud integration
- Generic artifact/export framework or a shared persistence hierarchy
- Creating missing parent directories
- Treating `-` as stdout
- Broad README redesign, badges, marketing rewrite, or unrelated documentation cleanup
- Changes to GitHub lifecycle, Cursor dispatch, Codex rework, or Spec Kit workflow
- `/speckit.implement` or `/speckit.taskstoissues` in this specification phase
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
uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl
uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl --format json
```

Plus focused checks covering:

- stdout unchanged when `--output` is absent, for text and JSON
- text and JSON file output
- byte identity between stdout representation and persisted representation
- refusal to overwrite by default
- `--force` replacement of a regular file only
- `--force` without `--output`
- symlink, existing directory, POSIX FIFO or other non-regular dest, missing parent, and non-directory parent, including with `--force`
- no partial final artifact after failed publish
- leftover temp after successful publish does not roll back the destination
- restricted `0600` permissions where POSIX supports them
- no sensitive/raw capture content or absolute paths in files or errors
- README command/capability audit against the actual public Typer surface

### Human decisions

- Human approval is required before Issue #58 receives `agent:ready`. Spec Kit must not apply that label.
- This specification pins `--output PATH`, `--force` only with `--output`, byte-identical file content, silent stdout on successful file write, refuse-if-exists by default, refuse every existing non-regular destination even with `--force`, no parent-directory creation, sibling temporary file plus exclusive or `--force` publish, publish-as-commit with best-effort temp cleanup, sequential type-check guarantees rather than TOCTOU-proof races, POSIX `0600` on the handoff file, and a focused README synchronization.
- Stop for human review if implementation would require changing handoff JSON v1, implicit persistence or Context Ledger semantics, remote storage or network behavior, a new runtime dependency, a generic artifact/persistence framework, `--latest` or broader capture discovery, changing summarize/compare/handoff contracts beyond these additive options, or README scope beyond current public behavior.
- Spec Kit must not apply lifecycle or risk labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can predict the file bytes from a stdout run of the same capture and format; they match exactly.
- **SC-002**: Omitting `--output` leaves stdout behavior indistinguishable from the current command.
- **SC-003**: An existing regular file is unchanged unless the operator passed both `--output` and `--force`. An existing non-regular destination remains unchanged even with `--force`.
- **SC-004**: After a failed publish, the destination is not a truncated handoff and no sibling temporary file remains. After a successful publish, the destination is complete even if temp cleanup later fails.
- **SC-005**: Successful file output and file-write errors contain no absolute paths, prompts, responses, tool payloads, or raw envelope values.
- **SC-006**: Where the platform supports POSIX modes, a written handoff file is not group- or world-readable (`0600`).
- **SC-007**: A new user can find `capt trace compare` and `capt trace handoff` in the README, including file output, without being told that deterministic insights do not exist.

## Assumptions

- Issue #37 / PR #57 already shipped stdout-only `capt trace handoff` with JSON v1 and payload-free capture-input errors. This slice adds file output around that command; it does not reopen the compact allowlist.
- `--output` is the option name because `capt trace collect claude-code` already uses it for an explicit local path. That collect path remains a capture-writer concern and is not merged with handoff writes.
- Silent stdout on successful `--output` is the agent-friendly contract: the operator already supplied the path, and printing it would risk absolute-path disclosure.
- Creating missing parents would be implicit persistence and is therefore refused.
- `--force` is included because regenerating a named handoff file is an expected local workflow; exclusive-create-only would leave no in-CLI replacement path.
- Destination symbolic links, directories, FIFOs, sockets, devices, and other non-regular existing paths are refused even with `--force` so overwrite cannot be redirected onto an unintended object.
- A parent directory that is itself a symlink to a directory is acceptable; the hazard called out by the Issue is the destination path.
- Publish is the commit. `os.link` then `unlink(temp)` on POSIX without `--force` may leave a leftover temp if unlink fails after dest is already published; that leftover must not roll back dest or fail the command.
- A concurrent mutator of the destination path between `lstat` and publish is outside this slice's guarantee. Sequential operator use is the contract.
- CaptureWriter exclusive-create, `0600`, and cleanup-on-failure are useful concrete patterns. Copying those ideas into a small handoff-specific helper is enough; promoting them into a generic writer is not.
- README examples may use synthetic relative paths such as `path/to/capture.jsonl` and `handoff.json`. They must not use real captures, account names, or absolute machine paths.
- `docs/product.md`, `docs/architecture.md`, and `docs/summary-format.md` currently say handoff is stdout-only. Implementation must update those sentences so they do not contradict this additive behavior, without turning this task into a broad documentation rewrite.
