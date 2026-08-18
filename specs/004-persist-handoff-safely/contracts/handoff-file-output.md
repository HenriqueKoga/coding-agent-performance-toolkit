# Handoff file output

Public CLI contract for persisting `capt trace handoff` to an explicit local file.

This contract does not change handoff JSON v1. The structured document remains [handoff-json-v1.md](../../003-compact-trace-handoff/contracts/handoff-json-v1.md).

## Command

```text
capt trace handoff CAPTURE [--format text|json] [--output PATH] [--force]
```

| Input | Required | Default | Notes |
| --- | --- | --- | --- |
| `CAPTURE` | yes | | Exactly one explicit CAPT JSONL path |
| `--format` | no | `text` | `text` or `json`; JSON remains the canonical structured form |
| `--output PATH` | no | absent | When absent, stdout-only behavior is unchanged |
| `--force` | no | false | Valid only with `--output` |

`--latest` is not part of this command. `-` is an ordinary output filename, not stdout.

## Success

### Stdout default

When `--output` is omitted, stdout bytes for `text` and `json` match the current command, including the trailing newline. No handoff file is created.

### File output

When `--output` is present and the write succeeds:

- the destination file contains the exact stdout representation that the same capture and `--format` would have produced without `--output`
- stdout contains no handoff body
- exit code is `0`
- on POSIX, the file mode is `0600`

Repeating a successful write to a new path produces byte-identical files for the same capture and format.

## Overwrite

| Destination | `--force` | Result |
| --- | --- | --- |
| missing regular path, parent exists | ignored | create |
| existing regular file | no | fail; file unchanged |
| existing regular file | yes | atomic replace with complete new content |
| symbolic link, including dangling | any | fail; target unchanged |
| directory | any | fail; directory unchanged |
| `--force` without `--output` | yes | fail; no file written |

Parent directories are not created. A parent that is a symlink to a directory is allowed. The destination path itself must not be a symlink.

## Failure messages

Exit code `1`. No traceback. No payload. No absolute path. Basename only when a file name is required.

| Condition | stderr |
| --- | --- |
| `--force` without `--output` | `Provide --output with --force.` |
| existing regular file, no `--force` | `Handoff file already exists: {basename}` |
| destination is a symbolic link | `Could not write handoff file: path is a symbolic link.` |
| destination is a directory | `Could not write handoff file: path is a directory.` |
| parent missing | `Could not write handoff file: parent directory does not exist.` |
| parent is not a directory | `Could not write handoff file: parent path is not a directory.` |
| other write `OSError` | `Could not write handoff file: {strerror}` with no path |

Capture-input errors keep the existing handoff mapping and are not redefined here.

## Publish mechanics

Implementation MUST:

1. inspect the destination with a non-following `lstat`
2. write the complete UTF-8 representation to an exclusive sibling temporary file in the same parent directory
3. `fsync` that temporary file
4. publish exclusively when `--force` is absent (`os.link` on POSIX, `os.rename` on Windows; both fail if the destination exists) or with `os.replace` when `--force` is present
5. remove the temporary file on any failure

The destination MUST NOT contain a truncated handoff after a failed write.

## Privacy

Successful file content is the existing compact allowlist only. Errors MUST NOT include absolute paths, parent directories, prompt or tool content, or interpolated envelope fields.
