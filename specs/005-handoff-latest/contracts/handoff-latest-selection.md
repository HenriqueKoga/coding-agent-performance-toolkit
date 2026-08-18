# Handoff latest-capture selection

Public CLI contract for selecting a capture on `capt trace handoff`.

This contract does not change handoff JSON v1. The structured document remains [handoff-json-v1.md](../../003-compact-trace-handoff/contracts/handoff-json-v1.md). File output remains [handoff-file-output.md](../../004-persist-handoff-safely/contracts/handoff-file-output.md).

## Command

```text
capt trace handoff [CAPTURE] [--latest] [--format text|json] [--output PATH] [--force]
```

| Input | Required | Default | Notes |
| --- | --- | --- | --- |
| `CAPTURE` | exactly one of `CAPTURE` or `--latest` | | Explicit CAPT JSONL path |
| `--latest` | exactly one of `CAPTURE` or `--latest` | false | Newest eligible `.jsonl` in the default capture directory |
| `--format` | no | `text` | Unchanged from 003/004 |
| `--output PATH` | no | absent | Unchanged from 004 |
| `--force` | no | false | Unchanged from 004; valid only with `--output` |

`-` is still an ordinary `--output` filename, not stdout.

## Selection

`--latest` MUST select the same file that `capt trace summarize --latest` would select under the same default capture directory state.

Canonical rules (already implemented for summarize/list; do not fork):

- Default directory is the existing CAPT captures directory.
- Eligible entries are `.jsonl` files in that directory, not symbolic links, not nested paths.
- Newest wins by modification time nanoseconds.
- Equal timestamps break ties by descending filename.
- `--latest` keeps a single running maximum; it does not require building the full listing.

## Selector errors

| Condition | stderr | Exit |
| --- | --- | --- |
| `CAPTURE` and `--latest` | `Provide either a capture path or --latest, not both.` | 1 |
| neither `CAPTURE` nor `--latest` | `Provide a capture path or --latest.` | 1 |
| extra positional capture paths | `Provide exactly one capture path.` | 1 |
| `--latest` and missing default directory | `Default capture directory does not exist.` | 1 |
| `--latest` and default path is not a directory | `Default capture path is not a directory.` | 1 |
| `--latest` and no eligible files | `No capture files found in the default capture directory.` | 1 |
| `--latest` and directory read failure | `Could not read default capture directory: {detail}` | 1 |

`{detail}` is an `OSError` reason, not a path. Messages MUST NOT include absolute paths, payloads, or envelope fields. No traceback.

After a capture is selected, invalid-capture errors keep the existing handoff mapping from `004-persist-handoff-safely` / `003-compact-trace-handoff`.

## Success

Once a capture is selected, the remainder of the command is the current handoff:

- default stdout text or JSON v1
- `--output` / `--force` safety unchanged
- JSON field order and values identical to an explicit-path run of that same file
- text rendering identical to an explicit-path run of that same file

## Out of this contract

- Implicit latest without `--latest`
- Changing global latest ordering
- `--latest` on compare or other commands
- Markdown, JSON v1 field changes, Context Ledger, remote discovery
