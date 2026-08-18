# Spec Kit in CAPT

Spec Kit is the **specification layer** for CAPT. It does not replace the GitHub Issue lifecycle, Cursor Cloud Agent dispatch, CI, Codex review, bounded rework, or the human merge gate.

This document is the operational guide for installing, updating, and using Spec Kit in this repository. Durable principles live in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Agent operating rules live in [`AGENTS.md`](../AGENTS.md).

## Responsibility split

```text
Spec Kit
  └─ specification quality
     ├─ constitution
     ├─ requirements/spec
     ├─ clarification
     ├─ implementation plan
     ├─ task decomposition
     └─ consistency analysis

GitHub
  └─ operational source of truth
     ├─ Issues
     ├─ lifecycle labels
     ├─ risk labels
     ├─ PRs
     └─ review state

Cursor Cloud Agent
  └─ implementation after human agent:ready

GitHub Actions
  └─ deterministic validation / lifecycle / dispatch

Codex
  └─ independent review

Human
  └─ readiness, scope/risk decisions, final merge
```

## Constitution versus AGENTS.md

| Source | Owns |
| --- | --- |
| [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) | Durable product and engineering principles |
| [`AGENTS.md`](../AGENTS.md) | How agents work in this repository: reading order, validation commands, Git/PR/lifecycle rules, human approval gates |
| [Accepted ADRs](decisions/README.md) | Hard-to-reverse architectural decisions |

Do not maintain two full copies of the same rules. If a principle changes, update the constitution and keep `AGENTS.md` as a pointer plus operational detail.

## Version pin

This repository is initialized with **Spec Kit 0.16.4** (`specify-cli` from `github/spec-kit` tag `v0.16.4`).

The pin is recorded in:

- `.specify/init-options.json` (`speckit_version`)
- `.specify/integration.json` (`version`)
- `.specify/integrations/*.manifest.json`

Do not float to Spec Kit `main` or an unpinned PyPI latest during routine work. Generated templates, skills, and scripts should not change unexpectedly between contributors.

Upgrade only in a dedicated change that reviews the generated-file diff. Preferred upgrade command after a human approves the new tag:

```bash
uvx --from git+https://github.com/github/spec-kit.git@vX.Y.Z specify init --here --force --integration cursor-agent --script sh --ignore-agent-tools
```

Then re-check project-local overrides under `.specify/templates/overrides/` and the constitution. Do not add `specify-cli` to CAPT application dependencies or `pyproject.toml`.

## Install and invoke

Spec Kit is development tooling. Use `uv tool` or `uvx`. Do not `uv add` it to this project.

One-time, pinned invocation (preferred for agents and CI-like checks):

```bash
uvx --from git+https://github.com/github/spec-kit.git@v0.16.4 specify version
uvx --from git+https://github.com/github/spec-kit.git@v0.16.4 specify check
```

Persistent local install for maintainers:

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.16.4
specify version
```

`specify version` must report `0.16.4` unless a reviewed upgrade has landed.

This repository is already initialized. Re-running `specify init --here --force` refreshes managed Spec Kit files. Review that diff before committing. Do not commit machine-local caches, `.specify/feature.json`, or environment-specific files. `.specify/.gitignore` already ignores `feature.json` and per-machine extension config.

## Cursor integration

The project uses Spec Kit's `cursor-agent` integration in skills mode.

Skills live in [`.cursor/skills/`](../.cursor/skills/) and are committed so every clone has the same commands. Other `.cursor/` content is ignored so credentials and local agent state stay off the repository.

In Cursor Agent, the skills appear as `/speckit-*` (hyphen form). Spec Kit documentation often writes `/speckit.*`. Both refer to the same commands.

## Recommended specification workflow

Use this path for new roadmap work. The registered `speckit` workflow is truncated so it stops after `/speckit.tasks` and never calls `/speckit.implement`.

```text
/speckit.constitution   # once, or when principles change
/speckit.specify
/speckit.clarify        # when the spec still has NEEDS CLARIFICATION items
/speckit.plan
/speckit.tasks
/speckit.analyze        # read-only; does not write files
        ↓
persist approved report as specs/<feature>/analyze.md
        ↓
manual GitHub Agent Task Issue
        ↓
needs:human-review → human agent:ready
        ↓
existing Cursor Cloud Agent / CI / Codex lifecycle
```

`/speckit.checklist` is optional. Use it when a requirements-quality review would reduce ambiguity. It does not mark an Issue ready.

### constitution

Creates or updates [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). CAPT already has a ratified constitution. Update it only when a durable principle changes, and keep `AGENTS.md` from growing a second copy.

### specify

Describe the **what** and **why**. Do not prescribe an unnecessary tech stack. The project-local spec template requires CAPT constraints: privacy, deterministic evidence, bounded memory, provider neutrality, compatibility, out of scope, validation, and human decisions.

The feature directory is `specs/<nnn-short-name>/`. Spec Kit tracks the active feature in `.specify/feature.json` (local, gitignored) or `SPECIFY_FEATURE` / `SPECIFY_FEATURE_DIRECTORY`. Checking out a Git branch does not by itself change the active feature.

### clarify

Run `/speckit.clarify` when the spec still has `[NEEDS CLARIFICATION]` markers or underspecified behavior. Fold answers back into `spec.md` before planning. Skip it when the spec is already precise.

### plan

Record the **how** against the existing CAPT architecture. The project-local plan template includes a constitution gate and CAPT design notes. Prefer the current package layout. Do not introduce a runtime dependency, LLM, network service, or generic framework in the plan without an explicit human decision.

### tasks

Break the plan into actionable tasks with real file paths. CAPT behavior changes include tests and synthetic fixtures. Tasks are specification artifacts, not GitHub Issues.

### analyze

Run `/speckit.analyze` as the read-only consistency check across `spec.md`, `plan.md`, and `tasks.md`.

The command itself does not write files. After reviewing the returned report, explicitly persist the approved report as `specs/<feature>/analyze.md` so it can be reviewed with the remaining specification artifacts.

Do not modify `spec.md`, `plan.md`, or `tasks.md` from the analyze command itself. Fix gaps at the source and re-run `/speckit.analyze` when the artifacts change.

## Bridge to GitHub Issues

After `analyze` is clean, create **one** GitHub Issue with the [Agent Task template](../.github/ISSUE_TEMPLATE/agent-task.yml). Copy the goal, acceptance criteria, out of scope, constraints, validation, privacy, compatibility, and human decisions from the Spec Kit artifacts. Keep examples synthetic.

A human later applies exactly one `risk:*` label and, when ready, `agent:ready`. That remains the only dispatch trigger for Cursor Cloud Agent.

### Specification review pull requests

Specification-only review PRs are part of the development flow. They must not close or mutate the operational Agent Task Issue.

Those PRs should:

- include a standalone `<!-- capt-lifecycle: ignore -->` line in the pull-request body
- link the operational Issue with `Related to #<issue>` rather than `Closes #<issue>`

The marker is the only lifecycle opt-out. The Agent lifecycle workflow then exits successfully without reading or mutating Issue labels. It does not skip CI, Codex, branch protection, or other repository checks, and it does not infer opt-out from `docs:` titles, `spec/` branches, changed paths, or draft status. Implementation PRs still use exactly one standalone `Closes #<issue>` line and remain under the Agent Task lifecycle.

### `taskstoissues` evaluation

`/speckit.taskstoissues` converts each Spec Kit task into a GitHub Issue titled `T001: <description>`.

It does **not** preserve the CAPT issue contract:

- It does not use the Agent Task issue template or required field IDs.
- It does not require context, goal, acceptance criteria, out of scope, constraints, validation, risk, privacy, or compatibility fields.
- It does not apply `needs:design` or any other lifecycle label.
- It does not apply a `risk:*` label. Risk classification is never inferred in this repository.
- It can create many issues from one feature, instead of one reviewable Agent Task.
- It has no human `agent:ready` gate and must not be treated as implementation dispatch.

Because those gaps cannot be closed without changing the lifecycle, **do not run `/speckit.taskstoissues` in this repository**. Keep Issue creation as an explicit manual bridge.

## What this pilot does not change

- CAPT runtime code, CLI, schemas, persistence, network behavior, and provider adapters
- GitHub Actions workflows for CI, lifecycle, Cursor dispatch, and Codex rework
- Lifecycle or risk labels
- The rule that only a human applies `agent:ready`

`/speckit.implement` and `/speckit.converge` remain installed because they ship with the Cursor integration. Do not use them as the production implementation path until a later human-approved evaluation.

## Project-local customizations

CAPT uses only project-local template overrides and one bundled-workflow truncation:

- `.specify/templates/overrides/spec-template.md`
- `.specify/templates/overrides/plan-template.md`
- `.specify/templates/overrides/tasks-template.md`
- `.specify/workflows/speckit/workflow.yml` stops after `/speckit.tasks` and a manual Agent Task handoff gate; it does not call `/speckit.implement`

These exist to surface CAPT constraints in generated artifacts. This pilot does not add a custom extension, bundle, catalog, or organization-wide preset. On Spec Kit upgrade, keep the workflow truncated; do not restore the bundled implement step.

## What to commit

Commit:

- `.specify/memory/constitution.md`
- `.specify/templates/` and `.specify/templates/overrides/`
- `.specify/scripts/bash/`
- `.specify/init-options.json`, `.specify/integration.json`, `.specify/integrations/`
- `.specify/workflows/` (bundled workflow truncated to stop before `/speckit.implement`)
- `.cursor/skills/speckit-*/`
- `specs/` feature artifacts that are synthetic and reviewable
- This document and the related `AGENTS.md` / `docs/development.md` pointers

Do not commit:

- `.specify/feature.json`
- secrets, captures, prompts, tool payloads, or real telemetry
- machine-local caches or environment-specific files
- `.cursor/` content other than the committed skills

## Pilot

[`specs/001-compaction-pressure/`](../specs/001-compaction-pressure/) is the first feature taken through `specify → plan → tasks → analyze`. It is a specification example only. It does not implement compaction-pressure detection.

The existing operational Issue for that feature is [#34](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/34). This adoption does not create or close that Issue and does not apply lifecycle or risk labels to it.
