# Implementation Plan: Persist compact trace handoff safely

**Branch**: `004-persist-handoff-safely` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-persist-handoff-safely/spec.md`

**Note**: Specification-phase plan only. Issue #58 is the existing operational Agent Task. After this specification is reviewed and merged, #58 is reduced to an operational envelope pointing at these artifacts; a human may then apply `agent:ready`. Do not run `/speckit.implement`.

## Summary

Add `--output PATH` and `--force` to the existing `capt trace handoff` command so the current text or JSON representation can be written to an explicit local file. Stdout remains the default. File bytes are identical to that stdout representation. Writes use exclusive sibling-temp plus atomic replace, refuse destination symlinks and silent overwrite, and keep payload-free path-free errors. Audit the README against the actual Typer surface so compare, handoff, insights, and this file-output contract are documented without a documentation rewrite.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Existing CAPT runtime only. Standard library file I/O. No new package. Spec Kit is not a runtime dependency.

**Storage**: Local operator-selected file for one complete handoff representation. No handoff directory, history, or ledger. Capture JSONL storage is unchanged.

**Testing**: `uv run pytest` with synthetic fixtures and temporary directories

**Target Platform**: Local CLI (Linux/macOS/Windows)

**Project Type**: local-first CLI

**Performance Goals**: Streaming and bounded memory; do not materialize entire captures. File output writes the already-rendered compact string only.

**Constraints**: Local-first, deterministic-first, privacy allowlist, provider-neutral core, no required LLM, no generic persistence framework

**Scale/Scope**: Single-capture handoff plus focused README synchronization

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Local-first: no outbound user-data path, no public bind
- [x] Deterministic-first: evidence is observed facts, not model judgment
- [x] Privacy: no payloads, identifiers, absolute paths, or real fixtures
- [x] Provider-neutral core; vendor mapping stays in adapters
- [x] Streaming / bounded memory preserved
- [x] No required LLM or model API in core
- [x] Public commands and versioned schemas remain compatible, or a version change is explicit
- [x] No premature registry, ABC, plugin system, or generic framework
- [x] Human approval identified for scope, dependencies, schema, or lifecycle risk
- [x] Implementation will enter GitHub as a manual Agent Task Issue, not via `/speckit.implement`

## CAPT design notes

- **Privacy impact**: potential, contained. The file contains only the existing compact handoff allowlist. Errors may include a destination basename and a fixed reason, never an absolute path, parent path, payload, or envelope field. POSIX `0600` on the created file reduces accidental sharing and does not expand the allowlist.
- **Deterministic evidence**: unchanged extract. File output copies rendered stdout bytes; it does not add metrics or narrative.
- **Bounded-memory impact**: no new accumulator state. One rendered string is written through a sibling temporary file.
- **Provider neutrality**: write helper consumes `str` content already rendered from `TraceHandoff`. No adapter change.
- **Compatibility**: additive `--output` and `--force` on `capt trace handoff`. Default stdout, JSON v1, and other public commands unchanged.
- **Validation**: full AGENTS.md set plus file-write, overwrite, symlink, permission, privacy, stdout-identity, and README-audit tests.
- **Out of scope**: Context Ledger, `--latest`, Markdown, JSON v1 changes, parent-directory creation, generic writer framework, remote storage, README redesign, Spec Kit/lifecycle changes.
- **Human decisions**: stop if JSON v1, implicit persistence, network, a new dependency, a generic framework, `--latest`, or README scope beyond current public CLI would be required. Do not apply `agent:ready` or risk labels from Spec Kit.

## Project Structure

### Documentation (this feature)

```text
specs/004-persist-handoff-safely/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/handoff-file-output.md
├── checklists/requirements.md
├── tasks.md
└── analyze.md
```

Handoff JSON v1 remains the contract in `specs/003-compact-trace-handoff/contracts/handoff-json-v1.md` and `docs/summary-format.md`. This feature does not version or copy that schema.

### Source Code (repository root)

```text
src/coding_agent_performance/
    cli.py
    adapters/claude_code/
    trace/
        cli.py                 # add --output/--force; keep stdout default
        handoff.py             # unchanged pure transform
        handoff_output.py      # new small exclusive file writer
        rendering.py           # reuse existing text/JSON renderers
        storage.py             # capture writer unchanged; do not generalize
docs/
    product.md
    architecture.md
    summary-format.md
    development.md
README.md
tests/
    test_handoff.py
    test_handoff_output.py
    test_trace_cli.py
```

**Structure Decision**: Extend the existing `trace` package. Add one concrete module for the handoff file write. Do not add an `artifacts/` package, a generic `atomic_write` framework, or methods on `CaptureWriter`.

## CLI contract

```text
capt trace handoff CAPTURE [--format text|json] [--output PATH] [--force]
```

- `CAPTURE` remains required and explicit.
- `--format` is unchanged: `text` default, `json` canonical structured form.
- `--output` is optional. Absent: current stdout behavior, no file created.
- `--output` present and write succeeds: destination receives the selected representation; stdout has no handoff body.
- `--force` is valid only with `--output`.
- `--latest` remains invalid.
- No short `-o`. Collect already uses long `--output` only.

Successful file content is the exact string currently produced for stdout, including the trailing newline that `typer.echo` (text) and `sys.stdout.write(..., "\n")` (JSON) already emit.

## File-write helper

Prefer `src/coding_agent_performance/trace/handoff_output.py` with a small exception and one function:

```python
class HandoffOutputError(Exception):
    """Expected failure while persisting a handoff file."""


def write_handoff_file(path: Path, content: str, *, overwrite: bool) -> None: ...
```

Behavior:

1. Expand `~`. Do **not** `resolve()` the destination; that would follow a destination symlink.
2. Inspect the destination with a non-following `lstat`:
   - symbolic link, including dangling: fail, even if `overwrite` is true
   - directory: fail, even if `overwrite` is true
   - regular file and `overwrite` is false: fail
   - missing: allowed
3. Parent must already exist and be a directory (`Path.is_dir()` may follow a parent symlink). Do not `mkdir`. Do not chmod the parent.
4. Create a sibling temporary file in that parent with `os.O_CREAT | os.O_EXCL | os.O_WRONLY` and mode `0o600` on POSIX (`0o666` masked by umask elsewhere).
5. Write UTF-8 `content`, flush, `fsync`, then `chmod` `0o600` on POSIX.
6. Publish without following the destination:
   - `overwrite` false: exclusive publish so an existing destination cannot be replaced. On POSIX, `os.link(temp, dest)` then `unlink(temp)` is sufficient because `link` fails if `dest` exists. On Windows, `os.rename(temp, dest)` is the equivalent because it fails when `dest` exists; do not call `os.replace` in this branch. If the destination exists at publish time, fail and remove `temp`.
   - `overwrite` true: `os.replace(temp, dest)` so a regular file is replaced atomically. Because step 2 already refused symlinks and directories, replace cannot be aimed at those types unless they appeared after the check; if the destination is no longer a regular file, fail closed and remove `temp` rather than following a symlink.
7. On any exception after the temporary file exists, `unlink` it (`missing_ok=True`) and leave the destination unchanged.

Error text is the exception message. Messages use a destination **basename** only when naming the file, never an absolute or parent path:

| Condition | Message |
| --- | --- |
| `--force` without `--output` | `Provide --output with --force.` |
| existing regular file, no `--force` | `Handoff file already exists: {basename}` |
| destination is a symbolic link | `Could not write handoff file: path is a symbolic link.` |
| destination is a directory | `Could not write handoff file: path is a directory.` |
| parent missing | `Could not write handoff file: parent directory does not exist.` |
| parent is not a directory | `Could not write handoff file: parent path is not a directory.` |
| other `OSError` | `Could not write handoff file: {strerror}` with no path |

Do not reuse `CaptureStorageError` or `CaptureWriter.create()`. Collect `--output` currently interpolates a resolved path on collision; handoff MUST NOT copy that leak.

## CLI orchestration

In `src/coding_agent_performance/trace/cli.py`:

1. Keep the existing one-capture argument, extra-arg rejection, `handoff_capture_or_fail()`, and `handoff_from_summary()`.
2. Add `--output` as `Path | None = None` and `--force` as `bool = False`.
3. If `force` and `output is None`, print `Provide --output with --force.` and exit 1.
4. Render text or JSON into a local `str` using the existing renderers plus the same trailing newline as today's stdout path.
5. If `output is None`, write that string to stdout exactly as today (`typer.echo` for text, `sys.stdout.write` for JSON).
6. If `output is not None`, call `write_handoff_file(output, content, overwrite=force)` and print nothing to stdout on success.
7. Map `HandoffOutputError` to stderr and exit 1. Do not print a traceback.

Capture-input errors stay on the existing handoff-specific mapper. Do not change summarize, compare, collect, list, or doctor.

## README and contract docs

Audit `README.md` against `src/coding_agent_performance/cli.py` and `src/coding_agent_performance/trace/cli.py` (Typer surface is the authority):

Public commands today:

- `capt --help`, `capt --version`, `capt doctor`
- `capt trace collect claude-code [--port] [--output]`
- `capt trace list [--limit]`
- `capt trace summarize [CAPTURE] [--latest] [--format text|json]`
- `capt trace compare BASELINE CANDIDATE [--format text|json]`
- `capt trace handoff CAPTURE [--format text|json]` plus this feature's `--output`/`--force`

README work, kept concise:

- Correct the early-stage blurb and "What this version includes" so they no longer claim CAPT does not produce insights after those rules have shipped.
- Add compare and handoff to "Current commands" and short usage sections modeled on summarize: synthetic relative paths, `--format`, and for handoff `--output` / `--force`.
- Do not paste JSON schemas; link `docs/summary-format.md` where a schema pointer is useful.
- Do not document internal Python functions.
- Adjust the README roadmap so shipped insight/compare/handoff capabilities are not listed as future-only. Do not add badges, rewrite principles, or expand privacy/non-goals beyond contradiction fixes.

Also update the current stdout-only sentences in `docs/product.md`, `docs/architecture.md`, and `docs/summary-format.md` so they mention optional explicit `--output` without duplicating this spec. `docs/development.md` already lists `capt trace handoff --help`; add `--output` only if that help line would otherwise be misleading.

## Expected implementation touch points

```text
src/coding_agent_performance/trace/handoff_output.py
src/coding_agent_performance/trace/cli.py
src/coding_agent_performance/trace/handoff.py          # no allowlist change
src/coding_agent_performance/trace/rendering.py        # reuse, no schema change
src/coding_agent_performance/trace/storage.py          # do not generalize CaptureWriter
README.md
docs/product.md
docs/architecture.md
docs/summary-format.md
docs/development.md
tests/test_handoff.py
tests/test_handoff_output.py
```

No normalizer, collector, capture-schema, comparison, insight-rule, or JSON v1 changes.

## Validation

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

Focused validation must cover stdout-unchanged default, text and JSON file bytes matching stdout, refuse-overwrite, `--force` regular-file replace, `--force` without `--output`, symlink/directory/missing-parent failures, no leftover temp or partial destination, POSIX `0600`, privacy exclusions, and README audit against the Typer surface.

## Complexity Tracking

No constitution violations. The new module is a concrete handoff file writer, not a generic persistence framework. CaptureWriter stays capture-specific.
