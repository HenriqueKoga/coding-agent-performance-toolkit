# Research: Persist compact trace handoff safely

**Feature**: `004-persist-handoff-safely`

**Date**: 2026-08-18

This Phase 0 note records choices the spec already pins. There are no remaining `[NEEDS CLARIFICATION]` items.

## Option names

- **Decision**: `--output PATH` plus `--force`. No short `-o`. `--force` is invalid without `--output`.
- **Rationale**: `capt trace collect claude-code` already uses `--output` for an explicit local path. Matching that name keeps the CLI vocabulary small. `--force` is the explicit overwrite action required by the Issue; exclusive-create-only would leave no in-CLI way to regenerate a named handoff file.
- **Alternatives considered**: `--file`, `--to`, stdout redirection only, and exclusive-create without `--force`. Rejected as a second vocabulary, as the problem this slice solves, or as a missing regeneration path.

## Stdout when writing a file

- **Decision**: Successful `--output` writes the handoff body only to the file. Stdout stays empty. Exit code 0 is success.
- **Rationale**: Printing the path would risk absolute-path disclosure. Printing the body twice is noisy for agent consumers. The operator already named the file.
- **Alternatives considered**: Echo the body, or print `Wrote {path}`. Rejected for duplication and path leakage. Collect still prints capture paths because it creates timestamped files the operator did not fully name; that does not apply here.

## Byte identity

- **Decision**: File bytes equal the current stdout representation for the same capture and `--format`, including the trailing newline.
- **Rationale**: The Issue requires semantic identity with the selected representation and JSON v1 unchanged. Byte identity is testable and avoids a second renderer.
- **Alternatives considered**: Pretty-printed files, omitted trailing newline, or a different JSON encoding. Rejected as a silent contract fork.

## Destination symlink and parent creation

- **Decision**: Refuse if the destination path is a symbolic link, including a dangling link, even with `--force`. Do not create missing parents. A parent that is a symlink to a directory is allowed.
- **Rationale**: Following a destination symlink would let `--force` clobber an unintended target. Creating parents is implicit persistence. A linked parent is a normal way to name a directory the operator already has.
- **Alternatives considered**: `Path.resolve()` then write, `mkdir(parents=True)`, and `--force` replacing through a symlink. Rejected as symlink follow, implicit directories, or redirectable overwrite.

## Atomic publish

- **Decision**: Exclusive-create a sibling temporary file, write and `fsync`, then exclusive publish. Without `--force`, POSIX uses `os.link` (fails if dest exists) and Windows uses `os.rename` (fails if dest exists). With `--force`, use `os.replace` only after a non-following `lstat` confirmed a regular file. Delete the temporary file on any failure. Never write the destination in place.
- **Rationale**: In-place writes leave truncated files on failure. POSIX `os.rename` would replace an existing dest, so `link` is required there. Windows `os.rename` already refuses an existing dest, so `os.replace` must not be used without `--force`. CaptureWriter already uses `O_CREAT|O_EXCL` for captures; handoff needs a complete-file publish rather than append, so copy the exclusive-create idea into a small helper instead of extending `CaptureWriter`.
- **Alternatives considered**: Direct `open(dest, "w")`, `tempfile.NamedTemporaryFile` in `/tmp` then rename across filesystems, `os.link` on Windows, or adding `overwrite=` to `CaptureWriter`. Rejected as partial-write hazard, non-atomic cross-device rename, an unreliable Windows hard-link requirement, or a generic persistence API.

## Permissions

- **Decision**: `0600` on the handoff file where POSIX supports it. Do not chmod the parent. Non-POSIX platforms skip the restriction rather than fail.
- **Rationale**: Matches capture-file privacy. Chmod of an operator-selected parent (for example a project directory) would be surprising and potentially harmful. Collect only chmod's the default captures directory, not a user `--output` parent (`restrict_directory=False`).
- **Alternatives considered**: `0644`, chmod parent `0700`, or failing on Windows. Rejected as too open, too invasive, or an unnecessary platform failure.

## Error text versus collect

- **Decision**: Handoff file errors are basename-only or pathless fixed reasons. Do not reuse `CaptureStorageError` messages that interpolate `resolved`.
- **Rationale**: Collect `--output` currently prints `Capture file already exists: {resolved}`. Handoff is an agent-facing artifact and the Issue forbids absolute-path leakage. Existing collect errors stay unchanged.
- **Alternatives considered**: Sharing `CaptureStorageError` or sanitizing collect in this slice. Rejected as a leak or as out-of-scope collect behavior change.

## README scope

- **Decision**: Audit `README.md` against the Typer command surface. Add compare and handoff. Correct insight/status contradictions. Update the README roadmap so shipped insight/compare/handoff items are not future-only. Point at `docs/summary-format.md` instead of copying schemas. Update stdout-only sentences in product, architecture, and summary-format docs because they would otherwise be false.
- **Rationale**: The Issue names README explicitly and forbids a marketing rewrite. Architecture/product stdout-only claims are contract docs that this additive CLI option makes wrong; leaving them would recreate the drift this slice is fixing.
- **Alternatives considered**: README-only with stale architecture sentences, or rewriting principles/privacy/non-goals. Rejected as leftover contradiction or as out-of-scope redesign.

## Unresolved items

None. Human review of this specification is still required before Issue #58 is reduced to an operational envelope pointing at these artifacts and receives `agent:ready`.
