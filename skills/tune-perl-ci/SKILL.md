---
name: tune-perl-ci
description: Use when modernizing a Perl project's GitHub Actions CI — applies six idempotent transforms (fail-fast flag, Perl 5.42 matrix, perl-tester image bump, default-branch push, concurrency cancel, App::cpm pin) to Dist::Zilla-style workflows.
version: 1.0.0
---

# Tune Perl CI

## Overview

**Six transforms applied to Perl CI workflows under `.github/workflows/`:**

1. `fail-fast: false` on every matrix job
2. Extend Linux + macOS matrices through Perl 5.42
3. Bump build + coverage jobs to `perldocker/perl-tester:5.42`
4. Restrict the `push:` trigger to the default branch
5. Add a workflow-level `concurrency:` cancel-in-progress block
6. Pin App::cpm for Perls ≤ 5.22

**Core principle:** modernize the workflow without changing intent. Each transform lands as its own commit so any single change is revertable. Re-running the skill on an already-tuned workflow is a no-op.

## When to Use

- User asks to tune / modernize / harden CI on a Perl repo
- Workflow uses `perldocker/perl-tester`, `shogo82148/actions-setup-perl`, or `perl-actions/install-with-cpm`
- A Dist::Zilla starter template has produced a CI workflow that is a few years stale

**Skip when:**
- No `.github/workflows/*.yml` matches the action-signature detection rule below — there's nothing to tune
- The user has deliberately customised concurrency or branch filters — idempotency preserves their choices

## Scope Detection

For each `.github/workflows/*.yml`, the file is **in scope** if it mentions any of:

- `perldocker/perl-tester`
- `shogo82148/actions-setup-perl`
- `perl-actions/install-with-cpm`

Other workflows are skipped silently. If no workflow file matches across the repo, report "no Perl workflows found" and exit cleanly.

If the caller passes a single workflow path as an argument, operate only on that file (still apply the detection rule for safety; bail out with a clear message if it isn't Perl-shaped).

## The Six Transforms

### 1. `fail-fast: false` on every matrix job

**What:** insert `fail-fast: false` under every `strategy:` block whose nested `matrix:` exists. Flip `fail-fast: true` to `false` if already present. No-op if `false` already.

**Why:** when `fail-fast:` is missing it defaults to `true`. One failing Perl/OS cell shouldn't mask the rest of the matrix.

**Before:**

```yaml
test_linux:
  strategy:
    matrix:
      perl-version: ["5.34"]
```

**After:**

```yaml
test_linux:
  strategy:
    fail-fast: false
    matrix:
      perl-version: ["5.34"]
```

### 2. Extend Linux + macOS matrices through Perl 5.42

**What:** in jobs whose `matrix.perl-version` axis exists **and** the job is either

- a Linux container (`container.image` starts with `perldocker/perl-tester`), or
- macOS (`runs-on: macos-*` or matrix `os:` includes a `macos-*` entry),

append any of `"5.36"`, `"5.38"`, `"5.40"`, `"5.42"` not already in the list. Preserve older entries. Match the file's quote style.

**Skip Windows.** Disabling or extending Windows is situational, not a general best practice.

**Hard-coded target:** `5.42`. A future revision can teach the skill to discover the latest stable.

**Before:**

```yaml
perl-version:
  - "5.10"
  - "5.30"
  - "5.34"
```

**After:**

```yaml
perl-version:
  - "5.10"
  - "5.30"
  - "5.34"
  - "5.36"
  - "5.38"
  - "5.40"
  - "5.42"
```

### 3. Bump build + coverage jobs to `perldocker/perl-tester:5.42`

**What:** replace `container.image:` values matching `perldocker/perl-tester:<X.YY>` with `perldocker/perl-tester:5.42`, but **only when the tag is a literal version** — never touch an image whose tag contains `${{` (those use the matrix variable on purpose).

**Why:** the build job produces the release artifact and the coverage job produces the coverage report. Both should run on the latest stable image, not a stale pin.

**Before:**

```yaml
build:
  container:
    image: perldocker/perl-tester:5.34
```

**After:**

```yaml
build:
  container:
    image: perldocker/perl-tester:5.42
```

### 4. Restrict `push:` to the default branch

**What:** in top-level `on.push.branches:`, replace the list with a single-entry list naming the default branch. Leave `pull_request:` and `workflow_dispatch:` alone (even if they have their own `branches:` filter).

**Skip** transform 4 if `on.push:` itself is absent — nothing to restrict. If the key is present but `branches:` is missing, add `branches:` with the resolved default branch.

**Default branch resolution:** Resolve the default branch with `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` (fall back to `main`, then `master`).

**Why:** avoid double CI runs when a push is also part of a PR. Each pushed commit triggers both a push run and a PR run, doubling queue time and burning Actions minutes.

**Before:**

```yaml
on:
  push:
    branches:
      - "*"
  pull_request:
  workflow_dispatch:
```

**After (default branch is `main`):**

```yaml
on:
  push:
    branches:
      - main
  pull_request:
  workflow_dispatch:
```

### 5. Add a workflow-level `concurrency:` block

**What:** insert this block at workflow level, directly after the `on:` block:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Skip** if any `concurrency:` already exists at workflow level — the user has deliberately customised the concurrency block.

**Why:** new pushes to the same ref cancel the still-running job from the previous push.

### 6. Pin App::cpm for Perls ≤ 5.22

**What:** for every step using `perl-actions/install-with-cpm@<any-ref>`:

1. Bump the action ref to `@v2` (which exposes the `version:` input).
2. Under `with:`, add (if missing):

   ```yaml
   # App::cpm v0.999.0+ requires Perl 5.24+; pin older Perls to the last compatible release.
   version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}
   ```

3. Preserve existing `sudo:`, `args:`, `cpanfile:`, etc.

**Skip** if `version:` is already present under `with:` (user has pinned deliberately).

**Why:** `App::cpm` v0.999.0+ requires Perl 5.24+. Older matrix cells fail to install dependencies with the current cpm release. The expression relies on lexicographic comparison of two-digit-minor strings (`5.10`, `5.12`, …, `5.22`, `5.24`, …), which works for all Perls likely to appear in a matrix.

**Before:**

```yaml
- name: install deps using cpm
  uses: perl-actions/install-with-cpm@v1.9
  with:
    cpanfile: "cpanfile"
    args: "--with-suggests --with-recommends --with-test"
    sudo: false
```

**After:**

```yaml
- name: install deps using cpm
  uses: perl-actions/install-with-cpm@v2
  with:
    cpanfile: "cpanfile"
    args: "--with-suggests --with-recommends --with-test"
    sudo: false
    # pin older Perls to the last cpm release compatible with them; newer Perls track the cpm release channel.
    version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}
```
