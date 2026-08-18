## Linked task

<!-- capt-lifecycle: ignore -->

<!-- capt-spec:v1
issue: N
spec: specs/<nnn-short-name>/spec.md
-->

Specification review PRs must keep that standalone opt-out marker and must not include a standalone `Closes #<issue>` line.
Replace `N` and `specs/<nnn-short-name>/spec.md` with the existing Agent Task Issue number and canonical spec path.
Add a standalone `Related to #<issue>` line for that same Issue.
Do not combine the opt-out marker with `Closes #<issue>`.
That marker opts the pull request out of Agent Task lifecycle bookkeeping only; CI, Codex, and branch protection still apply.
The capt-spec metadata is the machine-readable Issue ↔ specification index. Do not infer the spec directory from free-form prose.

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
- [ ] Versioned `capt-spec:v1` metadata identifies the existing Agent Task Issue and canonical spec path
- [ ] No standalone `Closes #<issue>` line
- [ ] `Related to #<issue>` matches the capt-spec issue
- [ ] `/speckit.implement` and `/speckit.taskstoissues` were not used
- [ ] Validation commands were run
- [ ] Privacy and security impact was assessed
- [ ] Compatibility impact was assessed
- [ ] Ready for human review
