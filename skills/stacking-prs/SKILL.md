---
name: stacking-prs
description: Use when about to open a PR whose branch builds on another PR that hasn't merged yet, or when opening several related PRs, to decide which to stack and which to open against the default branch, and to link stacks with gh stack
---

# Stacking PRs

## Overview

You decide which PRs to stack; the user only needs the merge order. Stack only when a change needs an unmerged PR's code. When you do stack, link it with GitHub's native stacked PRs (`gh stack`), because a plain base-branch stack breaks on merge.

## 0. Preflight

Run `gh stack --help`. If it fails, `gh stack` isn't installed: tell the user to run `gh extension install github/gh-stack`, and don't run it yourself.

## 1. Try it on trunk first

Cherry-pick or rebase the branch onto the default branch. If it applies and the tests pass, open the PR against the default branch and don't stack.

## 2. Stack only on a real dependency

Open the PR against the base PR's branch, then link the chain bottom → top by PR number:

```bash
gh stack link <bottom-pr> <next-pr> <top-pr>
```

- Use PR numbers, not branch names: branch arguments get pushed and get PRs created, PR numbers push nothing. A PR with the wrong base is retargeted.
- Don't pass `--open`. It marks the PRs ready for review; leave each PR's draft state alone, since readiness is decided elsewhere (e.g. `/fix-gh-issue` step 11).

## 3. Never leave a stack unlinked

If the stack isn't linked, merging the bottom PR doesn't retarget the PR above it. If the bottom branch isn't deleted on merge, the upper PR can then be merged into that leftover branch instead of trunk, and its change never reaches trunk.

## 4. Report the plan

Tell the user which PRs are stacked, in what merge order, and which are independent.

## 5. Merging stays with the user

Don't run `gh stack merge` unless asked.

## 6. After the bottom PR merges

GitHub should retarget the next PR to trunk, but stacked PRs are in public preview, so check: the upper PR's base should be trunk, and its diff should contain only its own commits. If either is wrong, `gh stack rebase` or `gh stack sync` can fix it. Both rewrite the branch and need a force-push, so ask the user first.
