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
