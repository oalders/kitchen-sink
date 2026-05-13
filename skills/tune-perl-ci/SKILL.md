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
