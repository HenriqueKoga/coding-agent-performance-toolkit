# Development

This guide covers setup, implementation, validation, and delivery.

Read [AGENTS.md](../AGENTS.md) for mandatory agent rules. Read [product.md](product.md) for intent and [architecture.md](architecture.md) for system structure.

## Prerequisites

- Python 3.14
- [uv](https://astral.sh/uv/)
- Git
- Claude Code, optional, for collector smoke tests

## Setup

```bash
git clone https://github.com/HenriqueKoga/coding-agent-performance-toolkit.git
cd coding-agent-performance-toolkit
uv sync --frozen --all-groups
```

## Common commands

```bash
uv run capt --help
uv run capt doctor
uv run capt trace collect claude-code --help
uv run capt trace list --help
uv run capt trace summarize --help
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Use `--help` commands to inspect the public CLI. Use `ruff format .` while editing and `ruff format --check .` before delivery. `ruff check` and `ty check` are required lint and type gates. `pytest` is the required test gate and enforces at least 90% coverage.

## Repository map

```text
src/coding_agent_performance/
    cli.py                 Top-level Typer app
    diagnostics.py         `capt doctor`
    adapters/claude_code/  Official export settings and allowlist normalizer
    trace/                 Collect, store, decode, summarize, and render
docs/                      Product, architecture, development, and ADRs
tests/                     Synthetic fixtures and focused tests
.github/                   Issue/PR templates, CI, Agent Task lifecycle, Cursor dispatch, and Codex rework
```

Related documents:

- [architecture.md](architecture.md)
- [product.md](product.md)
- [summary-format.md](summary-format.md)
- [decisions/README.md](decisions/README.md)

## Development workflow

1. Start from an up-to-date `main`.
2. Create a focused branch with a `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, or `chore/` prefix.
3. Read the documents relevant to the change.
4. Write or update tests first when behavior changes.
5. Implement incrementally.
6. Run targeted tests while developing.
7. Run the full validation set before delivery.
8. Review `git diff`.
9. Update documentation when contracts, architecture, or workflow change.
10. Open a pull request. Do not merge it automatically.

## Agent-assisted workflow

The same tool may play more than one role. Keep the handoffs explicit.

### Planning agent

Turns a goal into acceptance criteria. Names risks and out-of-scope items. Does not silently implement unapproved requirements.

### Implementation agent

Implements the smallest coherent change. Adds tests. Follows the plan and the project documents.

### Review agent

Reviews behavior, types, privacy, performance, tests, and documentation. Cites concrete evidence. Separates blockers from optional improvements.

### Human owner

Sets priorities. Approves scope changes. Decides trade-offs. Authorizes external or destructive actions. Approves the merge. A human is the only actor allowed to apply `agent:ready`.

### Repository lifecycle automation

GitHub Actions maintains Agent Task labels after a human has applied `agent:ready`. The implementation agent must not orchestrate those transitions.

Applying `agent:ready` to an open Issue starts a dedicated dispatch workflow. That workflow validates the Issue, then creates exactly one Cursor Cloud Agent through `POST https://api.cursor.com/v1/agents`. It does not change lifecycle or risk labels. `agent:working` still happens only when the implementation Draft PR opens.

A pull request whose body contains exactly one `Closes #<issue>` line, matching the pull-request template:

- moves the linked Issue from `agent:ready` to `agent:working` when the PR is opened, and copies that Issue's single `risk:*` label to the PR
- moves the linked Issue from `agent:working` to `needs:human-review` when the PR is marked ready for review

Unexpected lifecycle states, including a missing lifecycle label, produce a diagnostic and leave labels unchanged. Invalid risk classification, conflicting labels, and ambiguous `Closes #<issue>` links still fail.

`agent:ready` is never applied automatically. Risk classification is never inferred. Merged PRs close Issues through GitHub's normal `Closes #N` behavior.

Parsing, REST Issue label reads, retry decisions, and transition rules live in `.github/scripts/agent_lifecycle.py` and are tested locally with synthetic GitHub responses. Issue label reads use GitHub REST via `gh api repos/{owner}/{repo}/issues/{n}` rather than GraphQL. HTTP 500, 502, 503, and 504 are retried a small bounded number of times; other failures fail immediately and perform no label mutation. Live `gh api` HTTP, label mutation, event delivery, and token permissions require the real `pull_request` workflow environment and are not reproduced by the local test suite.

Cursor dispatch lives in `.github/workflows/agent-dispatch.yml` and `.github/scripts/agent_dispatch.py`. It runs only for the `issues.labeled` event when a human `User` applies `agent:ready`; GitHub Apps and bots that add the label do not dispatch. Before any Cursor API call it requires an open GitHub Issue, not a pull request, with exactly one lifecycle label (`agent:ready`) and exactly one `risk:*` label. The Cursor request targets `https://github.com/HenriqueKoga/coding-agent-performance-toolkit` at `main`, omits a model so Cursor uses the account default, and sets `autoCreatePR` to `false` so the implementation agent opens a Draft PR. Duplicate `agent:ready` events reuse a deterministic client-supplied `agentId` derived from the repository and Issue number; a Cursor `409 agent_id_conflict` is treated as already dispatched rather than as a second successful create. Authentication uses the repository Actions secret `CURSOR_API_KEY`. The workflow never prints that secret or Cursor response payloads, and it never mutates Issue labels. Live Cursor HTTP, secret availability, and GitHub event delivery require the real `issues.labeled` workflow environment and are not reproduced by the local test suite.

Codex review rework lives in `.github/workflows/agent-rework.yml` and `.github/scripts/agent_rework.py`. It is a dedicated workflow and is not mixed into CI, dispatch, or lifecycle. It runs only for `pull_request_review` `submitted` events from the Codex GitHub App `chatgpt-codex-connector[bot]`. Before any Cursor API call it requires an open pull request targeting `main`, exactly one standalone `Closes #<issue>` link, matching `risk:*` labels on the PR and linked Issue, and linked-Issue lifecycle `needs:human-review`. The only blocking signal is the structured Codex shields.io `P0`/`P1` badge observed in this repository's review comments; free-form words such as `blocker` or `critical` are ignored. Rework targets the existing PR branch with `prUrl` and `workOnCurrentBranch: true`, sets `autoCreatePR` to `false`, and instructs Cursor not to open another PR, mutate lifecycle or risk labels, or merge. Durable budget state is a machine-owned `github-actions[bot]` HTML-comment marker on the PR; at most two automatic rework dispatches are accepted. Duplicate events for the same Codex review reuse a deterministic `agentId` derived from the repository, PR, and review identity. Cursor create/accept updates that marker; HTTP failures do not. After the budget is exhausted, the workflow posts one human-action diagnostic and does not dispatch again. Shared Cursor HTTP helpers live in `.github/scripts/cursor_agents.py`. Live Cursor HTTP, secret availability, and GitHub event delivery require the real `pull_request_review` workflow environment and are not reproduced by the local test suite.

## Issue and task contract

Prefer this shape for issues and agent tasks:

```text
Context
Goal
Acceptance criteria
Out of scope
Constraints
Validation
```

Do not require plan files in the repository.

## Coding guidelines

Follow the conventions already used in the package:

- Python 3.14
- Modern type aliases
- `@dataclass` with `slots`
- `match` for closed dispatch
- `pathlib.Path`
- `collections.abc` for annotations
- Small functions and explicit names
- Typer only at the CLI boundary
- The standard library when it is enough
- A new dependency only with justification
- Vendor adapters at the edges
- Domain types independent of Claude Code
- Allowlist rendering
- Small exceptions whose messages omit payloads

Pythonic code means clear, typed, and direct. It does not mean maximizing abstractions or compressing logic into one-liners.

## Dependency management

- Add packages with `uv add` or `uv add --dev`.
- Keep `uv.lock` current through `uv`.
- Do not edit the lock file by hand.
- Do not update unrelated dependencies.
- Prefer the current stable version when a new dependency is actually needed.
- Justify runtime dependencies in the pull request.

## Testing strategy

- Unit-test conversions and isolated rules.
- Integration-test the capture → decode → normalize → summarize path.
- Test CLI behavior with `CliRunner`.
- Assert expected errors without a traceback.
- Keep privacy tests that prove identifiers and content stay out of output.
- Use synthetic fixtures only.
- Assert deterministic text and JSON.
- Keep coverage at or above 90%.
- Do not add tests that need a network or a corporate account.

## Adding or changing a CLI command

- Keep the command handler thin.
- Write help text.
- Validate input at the CLI boundary.
- Put use-case logic outside the CLI module.
- Map expected errors to exit codes.
- Test `--help`.
- Test stdout and stderr.
- In JSON mode, write only JSON to stdout.

## Changing capture or report schemas

Public schemas are versioned. Incompatible changes need a new version.

Readers should ignore unknown fields when that is safe. Never reuse an existing field for a new meaning.

Update fixtures, tests, and documentation together. Add an ADR when the change is structural. See [summary-format.md](summary-format.md) for the current summary JSON.

## Adding a provider adapter

- Use an official, documented interface.
- Keep vendor-specific parsing in the adapter.
- Convert to provider-neutral records.
- Do not import the adapter from the generic OTLP decoder.
- Do not add a registry before a second concrete need exists.
- Keep tests synthetic.
- Document privacy risks.
- Do not read unstable internal formats when an official alternative exists.

## Privacy and security

- Never version-control captures.
- Never paste captures into issues or pull requests.
- Do not print payloads.
- Select report fields through allowlists.
- Do not introduce outbound requests.
- Test error messages for leaked content.
- Keep local file permissions restrictive.
- Use synthetic data in fixtures and examples.
- Review filenames and metadata before displaying them.

## Pull request checklist

- [ ] Scope matches the accepted goal
- [ ] Tests cover the change
- [ ] Lint passes
- [ ] Type check passes
- [ ] Coverage stays at or above 90%
- [ ] Privacy review is complete for telemetry changes
- [ ] Public commands and schemas stay compatible, or the version change is documented
- [ ] Documentation is updated when needed
- [ ] New dependencies are justified
- [ ] Related smoke commands were run

## Releases

There is no documented automated release process yet.

Agents must not publish versions, tags, or packages without explicit authorization.

When a real process exists, update this section.
