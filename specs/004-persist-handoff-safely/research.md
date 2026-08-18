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

## Destination type and parent creation

- **Decision**: After `os.lstat`, the destination is eligible only when missing or when `stat.S_ISREG(st.st_mode)` is true. Any other mode is refused even with `--force`. Symlink and directory get specific messages; FIFO, socket, device, and every other non-regular mode share `path is not a regular file.` Do not create missing parents. A parent that is a symlink to a directory is allowed.
- **Rationale**: `--force` replacing a FIFO, socket, or device would clobber an unintended object. Enumerating special types is incomplete; the `lstat` mode is the closed predicate. `Path.is_file()` is unsafe here because it follows destination symlinks.
- **Alternatives considered**: `Path.resolve()` then write, `mkdir(parents=True)`, `--force` replacing through a symlink, treating FIFO/device as overwriteable files, and an enumerated special-type list. Rejected as symlink follow, implicit directories, redirectable overwrite, or an incomplete type list.

## Atomic publish

- **Decision**: Exclusive-create a sibling temporary file, write and `fsync`, then publish. **Publish is the commit.** Without `--force`, POSIX uses `os.link` (fails if dest exists) and Windows uses `os.rename` (fails if dest exists). After a successful exclusive `link`, `unlink(temp)` is cleanup, not publish: if unlink fails, dest already has the complete content via the new hard link, so the write succeeds and dest is not rolled back. With `--force`, confirm a regular file with non-following `lstat`, then on POSIX `open(..., O_WRONLY | O_NOFOLLOW)` plus `fstat`, then `os.replace`. Never write the destination in place.
- **Rationale**: In-place writes leave truncated files on a failed write. POSIX `os.rename` would replace an existing dest, so `link` is required there. Treating `link`+`unlink` as one all-or-nothing failure path contradicts the fact that `link` already published dest. `O_NOFOLLOW` catches a symlink that appeared after `lstat` before `replace` in sequential use. CaptureWriter already uses `O_CREAT|O_EXCL` for captures; handoff needs a complete-file publish rather than append.
- **Alternatives considered**: Direct `open(dest, "w")`; treating any exception after `link` as dest-unchanged; requiring a portable syscall that replaces only a regular file; `os.link` on Windows; adding `overwrite=` to `CaptureWriter`. Rejected as partial-write hazard, an unmeetable rollback, no portable type-enforcing replace, an unreliable Windows hard-link requirement, or a generic persistence API.

## Concurrent destination mutation

- **Decision**: The guaranteed contract is sequential use. CAPT does not promise to win a TOCTOU race against another process that swaps the destination path between the type check and publish. No portable single operation both replaces a regular file and refuses a concurrently installed symlink.
- **Rationale**: `os.replace` operates on the path. Holding an `O_NOFOLLOW` fd does not lock that path. Narrowing the race promise is honest; inventing a kernel-specific replace would expand scope.
- **Alternatives considered**: In-place write through `O_NOFOLLOW` (partial dest on crash) or Linux-only `renameat2` flags. Rejected as worse failure mode or non-portable scope.

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
