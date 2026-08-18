# Data Model: Persist compact trace handoff safely

**Feature**: `004-persist-handoff-safely`

This slice does not change `TraceHandoff` or handoff JSON v1. It adds a write intent around an already-rendered representation.

## HandoffFileTarget

Operator-selected destination for one handoff representation.

| Field | Type | Notes |
| --- | --- | --- |
| `path` | local path | Explicit `--output` value after `~` expansion. Not resolved; destination symlinks are not followed. |
| `overwrite` | `bool` | True only when `--force` is present together with `--output`. |

Validation:

- `path` is required for any file write.
- `overwrite` true without `path` is invalid at the CLI (`Provide --output with --force.`).
- The object is not persisted, listed, or discovered later.

## HandoffFileWrite

Outcome of publishing one complete UTF-8 representation to `HandoffFileTarget`.

| Field | Type | Notes |
| --- | --- | --- |
| `content` | `str` | Exact stdout representation including trailing newline |
| `destination` | final path | After a successful exclusive publish or atomic replace |

Validation:

- Success: destination contains `content` bytes in full; stdout has no handoff body.
- Failure: destination is unchanged (missing or previous complete file); sibling temporary file is absent.
- Destination type at publish time must be missing or, with `overwrite`, a regular file. Symbolic links and directories are never valid destinations.

No state machine beyond fail-closed checks before publish. No ledger history.

## Relationships

```text
TraceSummary
    -> handoff_from_summary()          # unchanged
    -> TraceHandoff                    # unchanged
    -> render text or JSON string      # unchanged contract
           ├─ stdout (default)
           └─ write_handoff_file()     # this feature
                 ├─ HandoffFileTarget
                 └─ sibling temp then atomic publish
```

`CaptureWriter` remains the JSONL capture appender. It is not a parent type of this write.
