## Linked task

<!-- capt-lifecycle: ignore -->

Specification review PRs must keep that standalone opt-out marker and must not include a standalone `Closes #<issue>` line.
Add a `Related to #<issue>` line only when an operational Agent Task Issue already exists.
Do not combine the opt-out marker with `Closes #<issue>`.
That marker opts the pull request out of Agent Task lifecycle bookkeeping only; CI, Codex, and branch protection still apply.

## Summary

## Motivation

## Scope

Specification artifacts only. No CAPT runtime, CLI, schema, lifecycle-workflow, dependency, or provider code changes.

## Out of scope

## Acceptance criteria

## Changes

## Validation

## Privacy and security

## Compatibility

## Risk

## Reviewer focus

## Follow-ups

## Checklist

- [ ] Specification-only scope
- [ ] Pinned Spec Kit artifacts under `specs/<feature>/`
- [ ] Approved `analyze.md` is included
- [ ] Lifecycle opt-out marker is present
- [ ] No standalone `Closes #<issue>` line
- [ ] `Related to #<issue>` is used only when an operational Issue already exists
- [ ] `/speckit.implement` and `/speckit.taskstoissues` were not used
- [ ] Validation commands were run
- [ ] Privacy and security impact was assessed
- [ ] Compatibility impact was assessed
- [ ] Ready for human review
