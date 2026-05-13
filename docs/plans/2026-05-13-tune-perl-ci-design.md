# tune-perl-ci — design

**Status:** approved
**Issue:** [#2 — New skill: tune-perl-ci](https://github.com/oalders/kitchen-sink/issues/2)
**Sister skill:** `kitchen-sink:tune-dependabot-config`
**Reference PR:** [libwww-perl/HTTP-Daemon#80](https://github.com/libwww-perl/HTTP-Daemon/pull/80)

## Goal

A new `kitchen-sink` skill — `tune-perl-ci` — that brings a Perl project's GitHub Actions workflow up to current conventions. Scope: workflows shaped like `perldocker/perl-tester` (Linux containers) + `shogo82148/actions-setup-perl` (macOS/Windows), as commonly produced by Dist::Zilla starter templates.

## Detection & file scope

For each `.github/workflows/*.yml`:

- **In scope** iff the file mentions any of:
  - `perldocker/perl-tester`
  - `shogo82148/actions-setup-perl`
  - `perl-actions/install-with-cpm`
- Otherwise skip the file silently.
- If no workflows match across the repo, report "no Perl workflows found" and exit cleanly.
- If the caller passes a single workflow path as an argument, operate only on that file (still apply the detection rule for safety; bail out with a clear message if the file isn't Perl-shaped).

## The six transforms

Each transform lands as its own commit so any single change is revertable.

### Transform 1 — `fail-fast: false` on every matrix job

**Locate:** every `strategy:` block whose nested `matrix:` exists.
**Edit:** insert `fail-fast: false` directly under `strategy:`, above `matrix:`. If `fail-fast: true` is already present, flip it to `false`. If `fail-fast: false` is already present, no-op.

**Why:** one failing Perl/OS cell shouldn't mask the rest of the matrix. Missing key defaults to `true`.

### Transform 2 — Extend Linux + macOS matrices through Perl 5.42

**Locate:** jobs whose matrix has a `perl-version:` axis AND one of:
- A `container:` whose image starts with `perldocker/perl-tester` (Linux), or
- A `runs-on:` that is `macos-*` (or whose matrix `os:` axis includes a `macos-*` entry).

**Edit:** append any of `"5.36"`, `"5.38"`, `"5.40"`, `"5.42"` not already present in the list. Preserve existing older entries (e.g. `5.10`–`5.34`). Match the existing entries' quote style.

**Skip Windows.** Disabling/bumping Windows is situational.

**Hard-coded target:** `5.42`. A future revision can teach the skill to discover the latest stable.

### Transform 3 — Bump build + coverage jobs to `perldocker/perl-tester:5.42`

**Locate:** `container.image:` values matching `perldocker/perl-tester:<X.YY>` where the job is **not** inside a matrix (i.e. a fixed-version build or coverage job, not a matrix test job that uses `${{ matrix.perl-version }}`).

**Edit:** replace with `perldocker/perl-tester:5.42`. Idempotent if already `:5.42`.

**Never touch** images that reference the matrix variable (e.g., `perldocker/perl-tester:${{ matrix.perl-version }}`) — those are the test-matrix jobs and need the variable.

### Transform 4 — Restrict `push:` trigger to the default branch

**Locate:** top-level `on.push.branches:`. If `on.push:` itself is absent, skip silently — nothing to restrict.

**Edit:** replace with a single-entry list naming the default branch.

**Default branch resolution:**
```
git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@'
```
- Fall back to `master` if origin/HEAD is unset **and** a local/remote `master` branch exists.
- Otherwise bail out of this transform with a clear message; do not block the other transforms.

Leave `pull_request:` and `workflow_dispatch:` alone, even if they have their own `branches:` filter.

**Why:** avoid double CI runs when a push is also part of a PR.

### Transform 5 — Workflow-level `concurrency:` block

**Locate:** top of the file. Skip if any `concurrency:` already exists at workflow level (user has chosen their grouping deliberately).

**Edit:** insert directly after the `on:` block:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Why:** new pushes to the same ref cancel the still-running job from the previous push.

### Transform 6 — Pin App::cpm for Perls ≤ 5.22

**Locate:** every step using `perl-actions/install-with-cpm@<any-ref>`.

**Edit:**
1. Bump the action ref to `@v2` (exposes the `version:` input).
2. Under `with:`, add (if missing):
   ```yaml
   # App::cpm v0.999.0+ requires Perl 5.24+; pin older Perls to the last compatible release.
   version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}
   ```
3. Preserve existing `sudo:`, `args:`, `cpanfile:`, etc. Only swap the action version and add the `version:` line.

**Skip** if a `version:` key is already present under `with:` (user has pinned deliberately).

**Why:** `App::cpm` v0.999.0+ requires Perl 5.24+. Older matrix cells fail to install dependencies with the current cpm release. The expression relies on lexicographic comparison of two-digit-minor strings (`5.10`, `5.12`, …, `5.22`, `5.24`, …), which works for all Perls likely to appear in a matrix.

## Algorithm

```
1. Scan .github/workflows/*.yml. Keep files matching the detection rule.
   Exit early with "no Perl workflows found" if the set is empty.
2. For each transform in order [1..6]:
     a. For each in-scope file, compute the diff this transform would produce.
     b. If every file is already conformant → skip transform (idempotent no-op).
     c. Write the changed files.
     d. Verify each changed file: yaml.safe_load + the structural assertion
        for transform t. On failure, stop with a clear message; leave files
        unstaged for inspection.
     e. Stage the changed files and commit with `workflow: <transform description>`.
3. Report summary: "Applied N transforms across M files in K commits"
```

Each transform produces at most one commit (across all in-scope files). Transforms that produced no diff for any file produce no commit.

A commit message names exactly one transform. Suggested commit subjects:

| # | Commit subject |
|---|---|
| 1 | `workflow: disable fail-fast on matrix jobs` |
| 2 | `workflow: extend Linux+macOS matrices through Perl 5.42` |
| 3 | `workflow: bump build/coverage to perldocker/perl-tester:5.42` |
| 4 | `workflow: restrict push trigger to default branch` |
| 5 | `workflow: add concurrency block to cancel superseded runs` |
| 6 | `workflow: pin App::cpm for Perls ≤ 5.22` |

## Idempotency

Idempotency is enforced at step 2b of the algorithm: every transform computes its own diff first; an empty diff means skip. A re-run on a fully-tuned workflow produces no commits and exits cleanly.

## Edge cases

| Situation | Behaviour |
|---|---|
| File has no `strategy.matrix` block | Transforms 1 & 6 may still apply to single-version steps; transform 2 silently skipped. |
| `perl-version` entries aren't bare strings (quoted vs unquoted vs mixed) | Match the file's quote style for the new entries (probe existing entries in the same list). |
| User has already extended past 5.42 (e.g., `5.43-RC`) | Leave extras alone; only ensure `5.36/5.38/5.40/5.42` are present. |
| `on.push.branches:` doesn't exist (push fires on all refs) | Add `branches:` with the resolved default branch. |
| `on.push:` itself isn't present | Skip transform 4 silently — nothing to restrict. |
| Workflow already has a top-level `concurrency:` block | Skip transform 5 entirely. |
| `install-with-cpm@v2` already with `version:` key | Skip transform 6 for that step. |
| Image bumps that already say `:5.42` | No-op. |
| Default branch detection fails (`git symbolic-ref` errors AND no `master` branch found) | Bail out of transform 4 with a clear message; keep transforms 1–3, 5, 6. |
| Workflow uses `actions-setup-perl` only (no container) | Transforms 1, 2 (macOS axis), 6 still apply. Transform 3 silently skipped. |
| Caller passes a single workflow path | Operate only on that file; skip the auto-scan. |
| Re-running on an already-tuned workflow | Each transform produces no diff → no commits → exits with "no changes". |

## Verification

After **each** transform's edit, before committing:

1. **YAML parse:** `python3 -c 'import yaml; yaml.safe_load(open(path))'`. Failure → bail out, leave the file unstaged, surface the error.
2. **Per-transform structural assertion:**

| # | Assertion |
|---|---|
| 1 | every `matrix:` parent has a sibling `fail-fast: false` |
| 2 | each targeted job's `perl-version` list includes `5.36, 5.38, 5.40, 5.42` |
| 3 | each fixed-image `container.image` ends in `:5.42` |
| 4 | `on.push.branches` is a single-item list with the resolved default branch |
| 5 | top-level `concurrency.group` and `concurrency.cancel-in-progress: true` present |
| 6 | every `install-with-cpm` step uses `@v2` and has `with.version` |

If an assertion fails, the skill reports which one failed and stops — the file remains uncommitted so the human can inspect. Do not auto-revert: that would hide bugs in the skill.

## Common mistakes (preview)

| Mistake | Why it's wrong | Fix |
|---|---|---|
| Extending Windows matrix to 5.42 | Issue scopes matrix extension to Linux + macOS; Windows often has dep/toolchain quirks worth a deliberate decision | Skip Windows in transform 2 |
| Bumping every `perldocker/perl-tester:<X>` to `:5.42` | Test-matrix jobs use the matrix variable on purpose; only build/coverage are fixed | Only bump fixed-version images; never touch `:${{ matrix.perl-version }}` |
| Adding `concurrency:` when the user already has one | Overwrites their grouping/cancellation choice | Skip transform 5 if any `concurrency:` exists at workflow level |
| Stripping `pull_request.branches` | Issue says leave `pull_request:` alone | Only touch `on.push.branches`, never `pull_request` |
| Pinning App::cpm with a hardcoded version key (no conditional) | Forces old version on modern Perls, slowing them down | Always use the matrix-conditional expression |
| Batching all 6 transforms into one commit | Can't revert one transform without the others | One commit per transform |
| Auto-reverting on verification failure | Hides bugs in the skill | Stop, surface the failure, leave file uncommitted |
| Bumping `install-with-cpm@v1.9` to `@v2` without the conditional `version:` | v2 default `version: main` is App::cpm v0.999+ which breaks Perls ≤ 5.22 | Always bundle the `version:` line with the `@v2` bump |
| Modifying images that use `${{ matrix.perl-version }}` | Breaks the test matrix — that variable is intentional | Skip any image that contains `${{` |

## SKILL.md structure (mirrors `tune-dependabot-config`)

```
---
name: tune-perl-ci
description: <one line — when to use; mention Perl + GitHub Actions + Dist::Zilla shape>
version: 1.0.0
---

# Tune Perl CI

## Overview
   Six transforms applied to Perl-shaped GitHub Actions workflows.
   One commit per transform. Idempotent on re-run.

## When to Use
   - User asks to tune / modernize / harden CI on a Perl repo
   - Workflow uses perldocker/perl-tester or shogo82148/actions-setup-perl
   Skip when:
   - Workflow isn't Perl-shaped (detection rule below)
   - User has clearly customized concurrency / branch filters (preserved by idempotency)

## Scope detection
   Action-signature check (the three action prefixes).

## The 6 Transforms
   One subsection each: 1) what 2) why 3) before/after snippet.

## Algorithm
   Per file → per transform → diff → write → verify → commit. (~15 lines.)

## Default branch resolution
   `git symbolic-ref --short refs/remotes/origin/HEAD | sed 's@^origin/@@'`,
   fall back to "master" if origin/HEAD unset and "master" branch exists,
   else bail out of transform 4 only.

## Worked Example
   Full before/after on a HTTP-Daemon-shaped workflow. Shows quote-style
   matching, matrix preservation, App::cpm conditional, etc.

## Verification
   YAML parse + per-transform structural assertion (table above).

## Common Mistakes
   Table of footguns (mirrors sister skill).

## Related
   - kitchen-sink:tune-dependabot-config (sister skill)
   - Reference PR: libwww-perl/HTTP-Daemon#80
```

## Plugin-level side-effects

- Bump version `1.8.0` → `1.9.0` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (new skill = minor per `CLAUDE.md`).
- Update `README.md` to list the new skill alongside `tune-dependabot-config`.

## Out of scope

- Action-version bumps for actions other than `install-with-cpm` — Dependabot territory.
- Dependabot config — already handled by `tune-dependabot-config`.
- Disabling specific OSes (e.g. Windows) — situational, not a general best practice.
- Discovering "latest stable Perl" — hard-coded `5.42` for now; future revision.

## Open follow-ups (post-merge)

- Teach the skill to discover the latest stable Perl release rather than hard-coding `5.42`.
- Consider an opt-in flag to also handle Windows matrix extension when a project deliberately supports Windows.
