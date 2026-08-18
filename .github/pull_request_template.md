## Linked task

Closes #

Agent Task implementation PRs must keep exactly one standalone `Closes #<issue>` line.
Specification review PRs must copy `.github/spec-review-pull-request.md` instead of this default template. Other non-Agent-Task review PRs must not use `Closes #<issue>`. Replace this section with a standalone `<!-- capt-lifecycle: ignore -->` line and a `Related to #<issue>` line. Do not combine that marker with `Closes #<issue>`. That marker opts the pull request out of Agent Task lifecycle bookkeeping only; CI, Codex, and branch protection still apply.

## Summary

## Motivation

## Scope

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

- [ ] Linked to an issue
- [ ] Issue scope was respected
- [ ] No out-of-scope changes were included
- [ ] Acceptance criteria are met
- [ ] Validation commands were run
- [ ] Privacy and security impact was assessed
- [ ] Compatibility impact was assessed
- [ ] The correct `risk:*` label is applied
- [ ] Ready for human review
