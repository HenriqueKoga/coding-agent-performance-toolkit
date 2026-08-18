# Quickstart: Persist compact trace handoff safely

Specification-phase validation guide. Do not implement from this file during the Spec Agent pass.

## Prerequisites

- Python 3.14 and `uv`
- Existing `capt trace handoff` stdout path
- Synthetic captures and temporary directories only

## Command under test

```text
capt trace handoff CAPTURE [--format text|json] [--output PATH] [--force]
```

## Scenarios

1. **Stdout unchanged**: run text and JSON without `--output` on `tests/fixtures/claude_code/synthetic-capture.jsonl`. Output matches today's command and creates no extra file.
2. **File identity**: write `--output` for text and JSON into a new file under a temporary directory. File bytes equal a stdout run of the same capture and format. Stdout of the file run has no handoff body.
3. **Refuse overwrite**: write once, then write again to the same path without `--force`. Second run exits non-zero; first file is unchanged.
4. **Explicit overwrite**: repeat with `--force` against a regular file. File becomes the new complete representation. `0600` holds on POSIX.
5. **Unsafe destinations**: destination symlink, directory, missing parent, `--force` without `--output`. All fail closed. No parent directories are created. No leftover `.capt-tmp-` sibling remains.
6. **Privacy**: synthetic prompt/path/payload markers in the capture must not appear in the file, stdout, or stderr. File-write errors must not include absolute paths.
7. **README audit**: README documents compare and handoff, including `--output`/`--force`, and no longer claims insights are absent. Public command list matches Typer `--help`.

## Expected validation

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build --clear
git diff --check
uv run capt trace handoff --help
uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl
uv run capt trace handoff tests/fixtures/claude_code/synthetic-capture.jsonl --format json
```

Use additional synthetic fixture paths and temporary output files from the implementation tests, not real captures or absolute machine paths in assertions beyond checking that those paths do **not** leak.
