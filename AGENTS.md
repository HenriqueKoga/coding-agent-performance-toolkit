# Agent instructions

These rules apply to every coding agent working in this repository.

## Project identity

CAPT is a local-first CLI. It measures and improves coding-agent efficiency.

The core is provider-agnostic. It must work without an LLM, hosted model, or API key.

Session data and source code are sensitive. Keep them on the user's machine.

Read [docs/product.md](docs/product.md) for product intent and [docs/architecture.md](docs/architecture.md) for system structure.

## Required reading

Before a non-trivial change, read only what the task needs:

1. [docs/product.md](docs/product.md)
2. [docs/architecture.md](docs/architecture.md)
3. [docs/development.md](docs/development.md)
4. Related ADRs in [docs/decisions/](docs/decisions/README.md)
5. The source files and tests directly involved

Do not read the entire repository by default.

## Source-of-truth order

Resolve conflicts in this order:

1. Explicit user or current-task instruction
2. Issue acceptance criteria
3. This file
4. Accepted ADRs
5. [docs/architecture.md](docs/architecture.md)
6. [docs/product.md](docs/product.md)
7. [docs/development.md](docs/development.md)
8. Behavior shown by current tests and code

If documentation conflicts with established public behavior or tests, treat it as a potential documentation drift and stop before changing behavior.

If a relevant contradiction remains, stop and ask. Do not choose silently.

## Non-negotiable constraints

- Use Python 3.14.
- Manage the project with `uv`.
- Keep the CLI on Typer.
- Write modern, idiomatic, strongly typed Python.
- Stay local-first by default.
- Do not send user data externally.
- Do not add an LLM or model API to the core.
- Keep vendor-specific adapters at the edges.
- Prefer deterministic analysis before any model-based analysis.
- Treat captures as confidential.
- Use synthetic fixtures only.
- Do not commit prompts, responses, real traces, corporate logs, secrets, or private source.
- Bind telemetry receivers to `127.0.0.1` only.
- Preserve public commands and versioned schemas.
- Do not invent a generic provider framework without a proven need.

## Engineering style

- Follow existing project patterns before introducing new ones.
- Prefer immutable domain values where practical.
- Prefer `dataclass` with `slots` when a data-focused class is appropriate.
- Use simple typed representations for small closed domains.
- Do not put mutable collections inside values declared as immutable.
- Prefer explicit code over metaprogramming.
- Prefer composition over inheritance.
- Use pure functions for conversions and isolated algorithms.
- Avoid `Any`, `cast()`, `# type: ignore`, and lint suppressions.
- Do not create `utils.py`, `helpers.py`, factories, registries, ABCs, or protocols without a concrete consumer.
- Keep CLI, domain, adapters, parsing, and rendering separate.
- Preserve streaming and bounded memory use.
- Do not change working code that the task does not require.
- Do not add comments that only repeat the code.

## Development workflow

1. Inspect the current code and tests.
2. Confirm the goal, acceptance criteria, and out-of-scope items.
3. Identify privacy and compatibility risks.
4. Write a short plan for non-trivial work.
5. Implement the smallest cohesive change.
6. Run targeted tests while developing.
7. Run the full validation set before delivery.
8. Review your own diff.
9. Update documentation when contracts or architecture change.
10. Return a structured handoff.

See [docs/development.md](docs/development.md) for setup, commands, and delivery details.

## Required validation

Run:

```bash
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Coverage must stay at least 90%.

Run smoke commands for the changed feature.

Do not declare success if a required command fails.

Do not hide, ignore, or work around CI failures.

## Privacy review

Before finishing work that processes telemetry, verify:

- Error messages do not include payloads.
- JSON and text output omit disallowed identifiers.
- Summaries never include absolute paths.
- Prompt, response, command, and tool-input content is not emitted.
- Fixtures contain no real information.
- No outbound request was introduced.
- New report fields appear only through an explicit allowlist.

## Documentation rules

Update the matching document when the change affects it:

- [docs/product.md](docs/product.md): goal, users, value, scope, or direction
- [docs/architecture.md](docs/architecture.md): structure, data flow, or boundaries
- [docs/development.md](docs/development.md): setup, commands, tools, or workflow
- [docs/summary-format.md](docs/summary-format.md): public summary JSON
- ADR: a durable, hard-to-reverse decision with meaningful trade-offs

Small internal changes do not need an ADR.

## Git and PR rules

- Use small, focused branches.
- Prefix branches with `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, or `chore/`.
- Write conventional, intentional commits.
- Do not mix unrelated refactors.
- Do not revert existing work without authorization.
- Do not use destructive Git commands.
- Do not force-push.
- Do not change secrets, branch protections, workflows, or GitHub settings without authorization.
- Do not merge automatically.
- Include summary, motivation, validation, risks, and out-of-scope items in the PR.

## Human approval required

Stop and ask before:

- Expanding scope beyond the accepted plan
- Introducing a runtime dependency
- Changing a public command or versioned schema incompatibly
- Adding network access, persistence, or an LLM
- Publishing a release, tag, or package
- Changing CI, secrets, or repository settings
- Using destructive Git commands or force-push
- Merging a pull request

## Handoff format

After an implementation, return:

```text
Summary
- ...

Files changed
- ...

Validation
- ...

Privacy and compatibility
- ...

Risks or follow-ups
- ...
```

Omit empty sections.
