# Data Model: Support `--latest` for trace handoff

**Feature**: `005-handoff-latest`

This slice does not change `TraceHandoff`, handoff JSON v1, or `HandoffFileTarget`. It adds a selection choice in front of the existing extract.

## CaptureSelection

Operator choice of exactly one capture selector.

| Field | Type | Notes |
| --- | --- | --- |
| `capture` | local path or absent | Explicit positional `CAPTURE` |
| `latest` | `bool` | True only when `--latest` is passed |

Validation:

- `capture` present and `latest` true is invalid (`Provide either a capture path or --latest, not both.`).
- `capture` absent and `latest` false is invalid (`Provide a capture path or --latest.`).
- More than one positional capture path is invalid (`Provide exactly one capture path.`).
- The object is not persisted. It is not a ledger entry.

## SelectedCapture

The single local eligible CAPT JSONL file after selection.

| Field | Type | Notes |
| --- | --- | --- |
| `path` | local path | Explicit `CAPTURE`, or `latest_capture(default_captures_dir())` |

Validation:

- For `--latest`, eligibility and ordering are the existing summarize/list rules: `.jsonl`, not a symlink, file in the default capture directory, newest `mtime_ns`, descending filename on ties.
- Missing directory, non-directory, unreadable directory, or no eligible files raise the existing `LatestCaptureError` messages.
- After selection, the file is summarized through the existing handoff capture-input path.

No new state machine. No stored "latest" pointer.

## Relationships

```text
CaptureSelection
    -> resolve_capture_selection()     # shared with summarize
           ├─ explicit CAPTURE
           └─ latest_capture(default_captures_dir())
    -> SelectedCapture
    -> summarize_capture()             # existing bounded path
    -> handoff_from_summary()          # unchanged
    -> TraceHandoff                    # unchanged
    -> render text or JSON             # unchanged
           ├─ stdout (default)
           └─ write_handoff_file()     # unchanged
```

`list_captures()` remains the listing path. `--latest` must not depend on materializing that listing.
