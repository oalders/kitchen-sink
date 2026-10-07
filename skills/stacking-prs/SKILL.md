---
name: stacking-prs
description: Use when about to open a PR whose branch builds on another PR that hasn't merged yet, or when opening several related PRs, to decide which to stack and which to open against the default branch, and to link stacks with gh stack
version: 1.0.0
---

# Stacking PRs

## Overview

You decide which PRs to stack; the user only needs the merge order. Stack only when a change needs an unmerged PR's code. When you do stack, link it with GitHub's stacked PRs via the `gh stack` extension, because a plain base-branch stack breaks on merge.

## 0. Preflight

Run `gh stack --help`. If it fails, `gh stack` isn't installed: tell the user to run `gh extension install github/gh-stack`, and don't run it yourself.

## 1. Try it on trunk first

Cherry-pick or rebase the branch onto the default branch. If it applies and the tests pass, open the PR against the default branch and don't stack. If it conflicts, abort (`git cherry-pick --abort` / `git rebase --abort`) and stack instead. If the branch is already pushed, moving it onto trunk rewrites it and needs a force-push, so ask the user first.

## 2. Stack only on a real dependency

First confirm the base PR is in this repo: `gh pr view <base-pr> --json isCrossRepository -q .isCrossRepository` must print `false`. A fork PR's branch isn't here, so you can't stack on it; tell the user instead. Then open the PR against the base PR's branch, resolved from its PR number, and link the chain bottom → top by PR number:

```bash
base=$(gh pr view <base-pr> --json headRefName -q .headRefName) && gh pr create --draft --base "$base" --title '...' --body '...'
gh stack link <bottom-pr> <next-pr> <top-pr>
```

- Don't paste the base branch name into the shell: a branch from someone else's PR is untrusted and can contain shell metacharacters; the quoted `"$base"` passes it as one literal argument. Write your own title and body (never paste issue or PR text) and single-quote them so `$(...)`, backticks and `$var` stay literal.
- Use PR numbers, not branch names: branch arguments get pushed and get PRs created, PR numbers push nothing. A PR with the wrong base is retargeted.
- Don't pass `--open`. It marks the PRs ready for review; leave each PR's draft state alone, since readiness is decided elsewhere (e.g. `/fix-gh-issue` step 11).

## 3. Never leave a stack unlinked

If the stack isn't linked, merging the bottom PR doesn't retarget the PR above it. If the bottom branch isn't deleted on merge, the upper PR can then be merged into that leftover branch instead of trunk, and its change never reaches trunk.

## 4. Report the plan

Tell the user which PRs are stacked, in what merge order, and which are independent.

## 5. Merging stays with the user

Don't run `gh stack merge` unless asked.

## 6. After the bottom PR merges

GitHub should retarget the next PR to trunk; verify anyway: the upper PR's base should be trunk, and its diff should contain only its own commits. If either is wrong, first run `gh stack checkout <upper-pr>` (`gh stack link` keeps no local tracking), then either `gh stack sync` (rebases and force-pushes) or `gh stack rebase` followed by `gh stack push` (a force-push). Either way it force-pushes, so ask the user first.
