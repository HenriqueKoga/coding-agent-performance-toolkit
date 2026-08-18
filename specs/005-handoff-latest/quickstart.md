# Quickstart: Support `--latest` for trace handoff

Specification-phase validation guide. Do not implement from this file during the Spec Agent pass.

## Prerequisites

- Python 3.14 and `uv`
- Existing `capt trace handoff` explicit-path path, including `--format`, `--output`, and `--force`
- Existing `capt trace summarize --latest` selection behavior
- Synthetic captures and temporary directories only

## Command under test

```text
capt trace handoff [CAPTURE] [--latest] [--format text|json] [--output PATH] [--force]
```

## Scenarios

1. **Explicit path unchanged**: run text, JSON, and `--output` on `tests/fixtures/claude_code/synthetic-capture.jsonl` without `--latest`. Behavior matches today's command.
2. **Latest text**: seed a temporary default capture directory with older and newer synthetic `.jsonl` files. `capt trace handoff --latest` stdout matches `capt trace handoff` on the newer file and matches the file `capt trace summarize --latest` would choose.
3. **Latest JSON**: `--latest --format json` matches an explicit-path JSON run of that newest file, including v1 field order.
4. **Latest file output**: `--latest --output PATH` writes byte-identical content to a stdout `--latest` run of the same format. `--latest --output PATH --force` replaces a regular file using current writer rules.
5. **Selector refusals**: `CAPTURE` plus `--latest`, neither selector, extra positional paths, and `--latest` with an empty or missing default directory all exit non-zero with the contract strings. No traceback, no absolute path, no payload.
6. **Privacy**: synthetic prompt/path/payload markers in the selected capture must not appear in stdout, file output, or stderr. Discovery errors must not include the default directory absolute path.
7. **README / help**: `capt trace handoff --help` includes `--latest`. README no longer says `--latest` is unsupported on handoff.

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

Use additional synthetic fixture paths and a monkeypatched default capture directory from the implementation tests. Do not use real captures. Assert that absolute machine paths do **not** leak.
