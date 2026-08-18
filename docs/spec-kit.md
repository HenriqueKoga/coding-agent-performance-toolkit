# Spec Kit in CAPT

Spec Kit is the **specification layer** for CAPT. It does not replace the GitHub Issue lifecycle, Cursor Cloud Agent dispatch, CI, Codex review, bounded rework, or the human merge gate.

This document is the operational guide for installing, updating, and using Spec Kit in this repository. It also defines the **Spec Agent** authoring contract. Durable principles live in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Agent operating rules live in [`AGENTS.md`](../AGENTS.md).

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

Spec Agent
  └─ specification authoring
     ├─ pinned Spec Kit commands and project-local templates
     ├─ specs/<feature>/ artifacts
     └─ specification-only review PR, then stop

GitHub
  └─ operational source of truth
     ├─ Issues
     ├─ lifecycle labels
     ├─ risk labels
     ├─ PRs
     └─ review state

Cursor Cloud Agent
  ├─ Spec Agent after manual workflow_dispatch (`needs:design`)
  └─ implementation after human agent:ready

GitHub Actions
  └─ deterministic validation / lifecycle / Spec Agent dispatch / implementation dispatch / approved-spec index

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
| This document | Spec Kit pin, install, Spec Agent authoring contract, and the specification-to-Issue bridge |

Do not maintain two full copies of the same rules. If a principle changes, update the constitution and keep `AGENTS.md` as a pointer plus operational detail.

## Spec Agent contract

The Spec Agent is the specification author. It takes a bounded feature brief, uses this repository's pinned Spec Kit workflow, and stops after a specification-only review PR.

The contract is agent-independent. Cursor's `/speckit-*` skills are the installed integration here; another Spec Kit-supported agent may invoke the same commands through its own integration. Do not invent a parallel specification format, skip the project-local template overrides, or treat Cursor-specific reasoning as specification semantics.

### Starting the Spec Agent

A human starts the Spec Agent for an existing Agent Task Issue in `needs:design` by running the dedicated `workflow_dispatch` workflow **Agent spec dispatch** with that Issue number from the default branch. The secret-using job uses GitHub Environment `spec-agent-dispatch`. That workflow validates the Issue and creates one Cursor Cloud Agent in Spec Agent mode against `main`. It requires exactly one lifecycle label (`needs:design`) and exactly one `risk:*` label. It does not change lifecycle or risk labels, does not rewrite the Issue body, does not apply `agent:ready`, and does not run on Issue creation or `needs:design` labeling.

Manual Cursor Cloud Agent launch remains possible. Implementation dispatch on `agent:ready` is unchanged. See [development.md](development.md).

### Input

A bounded feature brief plus this repository's context: constitution, `AGENTS.md`, product, architecture, related ADRs, and the files the brief names.

The brief should state goal, acceptance criteria, out of scope, and constraints. It is not a GitHub Issue. It must not include secrets, credentials, real captures, prompts, tool payloads, or private telemetry.

### Pinned Spec Kit only

Use the repository-pinned Spec Kit integration, scripts, and project-local templates. Do not hand-write an alternative spec, plan, or task format.

Invoke the same commands Spec Kit documents (`/speckit.specify`, `/speckit.plan`, and so on). In Cursor they appear as `/speckit-*`. Other integrations may use a different invocation form. The command sequence and the resulting Markdown artifacts are the contract, not the slash-command spelling.

### Authoring sequence

Use this path for new roadmap work. The registered `speckit` workflow is truncated so it runs through `/speckit.analyze` and never calls `/speckit.implement`.

```text
bounded feature brief + repository context
        ↓
focused spec/ or docs/ branch (not main)
        ↓
/speckit.constitution   # only when a durable principle must change
/speckit.specify
/speckit.clarify        # when the spec still has NEEDS CLARIFICATION items
/speckit.plan
/speckit.tasks
/speckit.analyze        # read-only; does not write files
        ↓
persist approved report as specs/<feature>/analyze.md
        ↓
specification-only review PR
  standalone <!-- capt-lifecycle: ignore -->
  capt-spec:v1 metadata for the existing Agent Task Issue and canonical spec.md
  Related to #N for that same Issue
  no standalone Closes #N
        ↓
STOP  (Spec Agent handoff)
        ↓
human review / merge of the specification
        ↓
automation upserts one capt-spec-approved:v1 Issue comment
  Issue body unchanged
  agent:ready is not applied
        ↓
human agent:ready
        ↓
existing Cursor Cloud Agent / CI / Codex lifecycle
```

`/speckit.checklist` is optional. Use it when a requirements-quality review would reduce ambiguity. It does not mark an Issue ready and does not replace `analyze.md`.

### Output

Write specification artifacts under `specs/<nnn-short-name>/` using the existing project-local Spec Kit templates:

- `spec.md`
- `plan.md`
- `tasks.md`
- `analyze.md` after reviewing the read-only `/speckit.analyze` report

Keep examples synthetic. Do not commit `.specify/feature.json`.

### Specification review PR

Open one specification-only pull request from the specification branch, not from `main`. Prefer a `spec/<nnn-short-name>` branch, distinct from a later `feat/` implementation branch. Copy [`.github/spec-review-pull-request.md`](../.github/spec-review-pull-request.md) as the pull-request body. Do not use the default Agent Task pull-request template.

That body must:

- include a standalone `<!-- capt-lifecycle: ignore -->` line
- include exactly one versioned `capt-spec:v1` metadata block naming the existing Agent Task Issue and canonical `specs/<feature>/spec.md` path
- include a standalone `Related to #<issue>` line for that same Issue
- not include a standalone `Closes #<issue>` line

The metadata block is the machine-readable contract. Do not infer the canonical spec directory from free-form PR prose. Duplicate metadata blocks, unsupported versions, missing or invalid issue numbers, invalid paths, conflicting fields, or a `Related to #<issue>` mismatch fail closed.

Example:

```text
<!-- capt-spec:v1
issue: 58
spec: specs/004-persist-handoff-safely/spec.md
-->
```

Do not combine the opt-out marker with any `Closes #<issue>` line. The marker is the only lifecycle opt-out, and the value must be exactly `ignore`. Any other standalone `<!-- capt-lifecycle: ... -->` value, an empty value, or a malformed namespace comment fails closed. Opt-out does not skip CI, Codex, branch protection, or other repository checks, and it is not inferred from `docs:` titles, `spec/` branches, changed paths, or draft status.

Keep the PR specification-only: Spec Kit artifacts under `specs/` plus the minimum documentation needed to land them. Do not change CAPT runtime code, public CLI behavior, capture or summary schemas, provider adapters, persistence, network behavior, runtime dependencies, or GitHub Actions lifecycle, dispatch, or rework workflows.

Implementation PRs still use the default pull-request template and exactly one standalone `Closes #<issue>` line.

### Stop conditions

After the specification review PR is opened, the Spec Agent stops. It must not:

- run `/speckit.implement` or `/speckit.converge` as a production path
- run `/speckit.taskstoissues`
- create, edit, or close a GitHub Agent Task Issue
- apply or mutate lifecycle or risk labels
- dispatch another agent
- merge the pull request
- change CAPT runtime code or GitHub Actions operational workflows

Human review of the specification, the later Agent Task Issue, `agent:ready`, Cursor dispatch, CI, Codex review, and merge remain unchanged.

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

The project uses Spec Kit's `cursor-agent` integration in skills mode. That is the installed adapter, not a second specification language.

Skills live in [`.cursor/skills/`](../.cursor/skills/) and are committed so every clone has the same commands. Other `.cursor/` content is ignored so credentials and local agent state stay off the repository.

In Cursor Agent, the skills appear as `/speckit-*` (hyphen form). Spec Kit documentation often writes `/speckit.*`. Both refer to the same commands. A Spec Agent on another supported integration should run the equivalent pinned commands and still emit the same `specs/<feature>/` artifacts.

## Command details

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

The Spec Agent does not create the operational Issue and must not create a second implementation Issue for a feature that already has an Agent Task Issue. The Agent Task Issue body remains the original feature brief for the life of the task.

When an operational Issue already exists, the specification review PR must include `capt-spec:v1` metadata and `Related to #<issue>` for that Issue. After that PR is merged to `main`, repository automation validates the canonical artifacts (`spec.md`, `plan.md`, `tasks.md`, `analyze.md`) and creates or updates exactly one managed Issue comment identified by `<!-- capt-spec-approved:v1 -->` and authored by `github-actions[bot]`. Marker-shaped comments from other identities are ignored and are never patched. That comment is an index: specification PR, canonical paths, and the source-of-truth split. It does not copy acceptance criteria, design, or tasks from the Spec Kit artifacts. Reruns update the same comment. The Issue body is not rewritten. `agent:ready` is not applied.

If a specification PR has the lifecycle opt-out marker but no `capt-spec` metadata, automation does not select a `specs/` directory and does not rewrite the Issue. Historical Issues without an approved-spec comment remain valid; implementation dispatch then treats the Issue body as the task specification.

A human later applies exactly one `risk:*` label and, when ready, `agent:ready`. That remains the only dispatch trigger for Cursor Cloud Agent. The implementation prompt includes the original Issue brief plus the approved specification reference when the managed comment exists. The merged `spec.md` is authoritative when it conflicts with the original brief.

### `taskstoissues` evaluation

`/speckit.taskstoissues` converts each Spec Kit task into a GitHub Issue titled `T001: <description>`.

It does **not** preserve the CAPT issue contract:

- It does not use the Agent Task issue template or required field IDs.
- It does not require context, goal, acceptance criteria, out of scope, constraints, validation, risk, privacy, or compatibility fields.
- It does not apply `needs:design` or any other lifecycle label.
- It does not apply a `risk:*` label. Risk classification is never inferred in this repository.
- It can create many issues from one feature, instead of one reviewable Agent Task.
- It has no human `agent:ready` gate and must not be treated as implementation dispatch.

Because those gaps cannot be closed without changing the lifecycle, **do not run `/speckit.taskstoissues` in this repository**. Keep Issue creation as an explicit manual bridge after specification review.

## What this pilot does not change

- CAPT runtime code, CLI, schemas, persistence, network behavior, and provider adapters
- Lifecycle or risk labels
- The rule that only a human applies `agent:ready`
- The specification-PR `<!-- capt-lifecycle: ignore -->` opt-out and implementation `Closes #<issue>` contract

`/speckit.implement` and `/speckit.converge` remain installed because they ship with the Cursor integration. Do not use them as the production implementation path until a later human-approved evaluation.

## Project-local customizations

CAPT uses only project-local template overrides, one bundled-workflow truncation, and one specification-review pull-request template:

- `.specify/templates/overrides/spec-template.md`
- `.specify/templates/overrides/plan-template.md`
- `.specify/templates/overrides/tasks-template.md`
- `.specify/workflows/speckit/workflow.yml` runs through `/speckit.analyze`, persistence of `analyze.md`, and a specification-review PR handoff gate; it does not call `/speckit.implement`
- `.github/spec-review-pull-request.md` is the Spec Agent pull-request body

These exist to surface CAPT constraints in generated artifacts and to make the Spec Agent PR contract executable. This pilot does not add a custom extension, bundle, catalog, or organization-wide preset. On Spec Kit upgrade, keep the workflow truncated; do not restore the bundled implement step.

## What to commit

Commit:

- `.specify/memory/constitution.md`
- `.specify/templates/` and `.specify/templates/overrides/`
- `.specify/scripts/bash/`
- `.specify/init-options.json`, `.specify/integration.json`, `.specify/integrations/`
- `.specify/workflows/` (bundled workflow truncated to stop before `/speckit.implement`)
- `.cursor/skills/speckit-*/`
- `specs/` feature artifacts that are synthetic and reviewable
- `.github/spec-review-pull-request.md`
- This document and the related `AGENTS.md` / `docs/development.md` pointers

Do not commit:

- `.specify/feature.json`
- secrets, captures, prompts, tool payloads, or real telemetry
- machine-local caches or environment-specific files
- `.cursor/` content other than the committed skills

## Pilot

[`specs/001-compaction-pressure/`](../specs/001-compaction-pressure/) is the first feature taken through `specify → plan → tasks → analyze`. It is a specification example only. It does not implement compaction-pressure detection.

The existing operational Issue for that feature is [#34](https://github.com/HenriqueKoga/coding-agent-performance-toolkit/issues/34). This adoption does not create or close that Issue and does not apply lifecycle or risk labels to it.
