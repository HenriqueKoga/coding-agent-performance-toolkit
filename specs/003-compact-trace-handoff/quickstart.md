# Quickstart: Export compact trace handoff

Specification-phase validation guide. Do not implement from this file during the Spec Agent pass.

## Prerequisites

- Python 3.14 and `uv`
- Existing `capt trace summarize` path
- Synthetic captures only

## Command under test

```text
capt trace handoff CAPTURE [--format text|json]
```

## Scenarios

1. **Minimal capture**: summarize and handoff a synthetic capture with no sessions, tools, or model usage. JSON still has every v1 key. `tools.success_rate_bps` is `null`. All insight arrays are empty and singleton insights are `null`. No goals or TODOs appear.
2. **Insight capture**: use a synthetic capture that already produces repeated-tool, compaction-pressure, or other summarize findings. Handoff insights must match summarize insights field-for-field.
3. **Determinism**: run the same command twice for `text` and twice for `json`. Outputs are identical.
4. **Privacy**: fixtures that contain synthetic prompt/tool/path strings in raw envelopes must not leak those strings into handoff stdout or stderr. An arbitrary envelope `source` becomes `unknown`. An unsupported `schema_version` marker string must not appear on stderr.
5. **Errors**: missing file, invalid capture, missing argument, and unsupported schema_version exit non-zero with no traceback, payload, interpolated envelope value, or absolute path.
6. **Compatibility**: `capt trace summarize` and `capt trace compare` output for the same fixtures remains unchanged.

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

The text and JSON smoke invocations must succeed against that synthetic fixture and must not print prompt, tool-payload, identifier, or absolute-path strings from the capture. Use additional synthetic fixture paths from the implementation tests, not real captures.
