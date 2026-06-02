---
name: tune-perl-ci
description: Use when modernizing a Perl project's GitHub Actions CI — applies seven idempotent transforms (fail-fast flag, Perl 5.42 matrix, perl-tester image bump, default-branch push, concurrency cancel, setup-cpm + cpm install, drop pre-5.24 macOS/Windows cells) to Dist::Zilla-style workflows.
version: 1.3.0
---

# Tune Perl CI

## Overview

**Seven transforms applied to Perl CI workflows under `.github/workflows/`:**

1. `fail-fast: false` on every matrix job
2. Extend Linux + macOS matrices through Perl 5.42
3. Bump build + coverage jobs to `perldocker/perl-tester:5.42`
4. Restrict the `push:` trigger to the default branch
5. Add a workflow-level `concurrency:` cancel-in-progress block
6. Install deps with `setup-cpm` + a `cpm install` run step
7. Drop macOS + Windows tests for Perls < 5.24

**Core principle:** modernize the workflow without changing intent. Each transform lands as its own commit so any single change is revertable. Re-running the skill on an already-tuned workflow is a no-op.

## Dispatch this skill to a subagent

When this skill is invoked, dispatch the work to a `general-purpose` subagent via the `Agent` tool. **Do not run the seven transforms inline in the caller's context.**

Why:
- Each transform reads every in-scope workflow, computes a diff, writes the file, runs `yaml.safe_load` + a structural assertion, then stages and commits. Across seven transforms and multiple workflows, that is a lot of `Read`/`Edit`/`Bash` tool traffic — none of it useful to the caller's session.
- The caller only needs the final summary line (`Applied N transforms across M files in K commits`) and the list of commit SHAs. Everything else is intermediate state.

How to dispatch:
- Brief the subagent with this SKILL.md as its working spec — pass the path to the file or invoke the skill from inside the subagent.
- Tell the subagent the working directory and (optionally) a single workflow path if the caller specified one.
- Require the subagent to report back, in under 200 words: the summary line, the per-transform commit SHAs, and any skipped transforms with reason.
- If a transform's verification fails, the subagent must stop and surface the failure rather than continuing or auto-reverting.

If the user explicitly asks to run inline (e.g. "do it here so I can watch"), honour that — the subagent dispatch is the default, not a hard requirement.

## When to Use

- User asks to tune / modernize / harden CI on a Perl repo
- Workflow uses `perldocker/perl-tester`, `shogo82148/actions-setup-perl`, `perl-actions/install-with-cpm`, or `perl-actions/install-with-cpanm`
- A Dist::Zilla starter template has produced a CI workflow that is a few years stale

**Skip when:**
- No `.github/workflows/*.yml` matches the action-signature detection rule below — there's nothing to tune
- The user has deliberately customised concurrency or branch filters — idempotency preserves their choices

## Scope Detection

For each `.github/workflows/*.yml`, the file is **in scope** if it mentions any of:

- `perldocker/perl-tester`
- `shogo82148/actions-setup-perl`
- `perl-actions/install-with-cpm`
- `perl-actions/install-with-cpanm`

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

### 6. Install deps with `setup-cpm` + a `cpm install` run step

**What:** for every step using either `perl-actions/install-with-cpm@<any-ref>` or `perl-actions/install-with-cpanm@<any-ref>`, replace the single composite step with **two** steps:

1. A setup step that installs the single-file `cpm` tool:

   ```yaml
   - uses: perl-actions/setup-cpm@v1
     with:
       version: compat
   ```

2. An explicit install run step (faithful arg mapping from the old step):

   ```yaml
   - run: cpm install -g --cpanfile <cpanfile-value> <args-verbatim>
   ```

Mapping rules:
- The old `cpanfile:` value becomes `--cpanfile <value>`. If no `cpanfile:` key was present, omit `--cpanfile` (cpm reads `./cpanfile` by default).
- The old `args:` value is appended verbatim after `--cpanfile …` (e.g. `--with-recommends --with-suggests --with-test`).
- Keep `-g` (global install) to preserve `install-with-cpm`'s default global-install behavior.
- **Drop the old `sudo:` key.** No sudo is needed: `perldocker/perl-tester` containers run as root, and `shogo82148/actions-setup-perl` provisions a user-local Perl, so the install target is already writable.

The matrix-conditional `version:` expression is gone entirely — `version: compat` on the `setup-cpm` step auto-selects cpm `0.998003` for old Perls (≤ 5.22) and the latest cpm for newer ones, handling the old-Perl pinning upstream.

**Skip** a step already in `setup-cpm@v1` + `cpm install` form — it is a no-op. Still convert any remaining `install-with-cpm`/`install-with-cpanm` step in the file.

**Why:**
- `setup-cpm` installs cpm itself and leaves the install command explicit and inspectable, instead of hiding the dependency install behind a composite action's input surface. It also migrates away from the legacy `install-with-cpanm` action (cpanm-based, serial, no parallelism).
- The `version: compat` default auto-selects cpm `0.998003` on Perls ≤ 5.22 (the last cpm release compatible with them) and the latest cpm on newer Perls, replacing the hand-rolled matrix-conditional pin.

**Verify the action ref exists before writing it.** This transform pins `perl-actions/setup-cpm@v1`. Confirm the tag resolves before emitting the ref:

```bash
gh api repos/perl-actions/setup-cpm/git/refs/tags/v1   # 404 → the tag does not exist
```

Action tags move, and not every action ever publishes a given major version — never assume `@v1` is available. Pin only a ref you have confirmed exists.

**Before:**

```yaml
- name: install deps using cpm
  uses: perl-actions/install-with-cpm@v1.9
  with:
    cpanfile: "cpanfile"
    args: "--with-suggests --with-recommends --with-test"
    sudo: false

- name: install deps using cpanm
  uses: perl-actions/install-with-cpanm@v1
  with:
    cpanfile: "cpanfile"
    args: "--with-suggests --with-recommends --with-test"
    sudo: false
```

**After:**

```yaml
- uses: perl-actions/setup-cpm@v1
  with:
    version: compat
- run: cpm install -g --cpanfile cpanfile --with-suggests --with-recommends --with-test

- uses: perl-actions/setup-cpm@v1
  with:
    version: compat
- run: cpm install -g --cpanfile cpanfile --with-suggests --with-recommends --with-test
```

### 7. Drop macOS + Windows tests for Perls < 5.24

**What:** in jobs whose `matrix.perl-version` axis exists **and** the job targets macOS or Windows exclusively, remove every `perl-version` entry strictly less than `5.24` (i.e. `5.10`, `5.12`, `5.14`, `5.16`, `5.18`, `5.20`, `5.22`).

A job targets macOS exclusively when **either**:
- `runs-on:` is a literal `macos-*` string, or
- `runs-on: ${{ matrix.os }}` and `matrix.os` contains only `macos-*` entries.

Same rule for Windows with `windows-*`.

**Skip when:**
- The job is Linux (`perldocker/perl-tester` containers handle older Perls cleanly — `version: compat` from transform 6 covers their cpm install).
- The job has a mixed `matrix.os` (e.g. `[ubuntu-latest, macos-latest]`). Trimming a single `perl-version` entry drops the cell from every OS in the matrix; the right tool there is an explicit `matrix.exclude:` block, which is too situational to auto-generate. Surface a one-line warning naming the job and move on.
- The job's `perl-version` list has no entries < `5.24` (idempotent no-op).

**Why:** older Perls on macOS and Windows runners are flaky or unbuildable. `shogo82148/actions-setup-perl` and the Strawberry distribution focus support on 5.24+; pre-5.24 cells frequently fail to install or run on those hosted runners, masking real failures in the rest of the matrix. Linux is unaffected because the `perldocker/perl-tester` images carry working older Perls.

**Before:**

```yaml
test_macos:
  runs-on: macos-latest
  strategy:
    matrix:
      perl-version:
        - "5.20"
        - "5.30"
        - "5.34"
```

**After:**

```yaml
test_macos:
  runs-on: macos-latest
  strategy:
    matrix:
      perl-version:
        - "5.30"
        - "5.34"
```

## Algorithm

```
1. Scan .github/workflows/*.yml. Keep files matching the detection rule.
   Exit early with "no Perl workflows found" if the set is empty.
2. For each transform in order [1..7]:
     a. For each in-scope file, compute the diff this transform would produce.
     b. Skip any file that is already conformant for this transform (idempotent no-op for that file).
     c. Write the remaining changed files.
     d. Verify each changed file: yaml.safe_load + the structural assertion
        for transform t (see Verification). On failure, stop with a clear
        message; leave files unstaged for inspection.
     e. Stage the changed files and commit with `workflow: <transform description>`.
3. Report summary: "Applied N transforms across M files in K commits".
```

Each transform produces at most one commit (across all in-scope files). Transforms that produce no diff for any file produce no commit.

Suggested commit subjects:

| # | Commit subject |
|---|---|
| 1 | `workflow: disable fail-fast on matrix jobs` |
| 2 | `workflow: extend Linux+macOS matrices through Perl 5.42` |
| 3 | `workflow: bump build/coverage to perldocker/perl-tester:5.42` |
| 4 | `workflow: restrict push trigger to default branch` |
| 5 | `workflow: add concurrency block to cancel superseded runs` |
| 6 | `workflow: install deps with setup-cpm + cpm install` |
| 7 | `workflow: drop macOS/Windows tests for Perls < 5.24` |

## Default branch resolution

Used by transform 4.

```bash
git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@'
```

- If that prints a branch name, use it.
- Otherwise check `git show-ref --verify --quiet refs/remotes/origin/master` first, then `refs/heads/master`; if either succeeds, fall back to `master`.
- Otherwise, bail out of transform 4 with a clear message — do not block transforms 1–3, 5, 6.

## Worked Example

A HTTP-Daemon-shaped workflow that exercises every transform.

### Before

```yaml
name: dzil build and test
on:
  push:
    branches:
      - "*"
  pull_request:
    branches:
      - "*"
  workflow_dispatch:

jobs:
  build:
    name: Build distribution
    runs-on: ubuntu-24.04
    container:
      image: perldocker/perl-tester:5.34
    steps:
      - uses: actions/checkout@v6
      - name: Build Dist
        run: dzil build

  coverage-job:
    needs: build
    runs-on: ubuntu-24.04
    container:
      image: perldocker/perl-tester:5.34
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v7

  test_linux:
    name: Perl ${{ matrix.perl-version }} on ubuntu-latest
    needs: build
    strategy:
      matrix:
        perl-version:
          - "5.10"
          - "5.30"
          - "5.34"
    container:
      image: perldocker/perl-tester:${{ matrix.perl-version }}
    steps:
      - uses: actions/checkout@v6
      - name: Install deps
        uses: perl-actions/install-with-cpm@v1.9
        with:
          cpanfile: "cpanfile"
          args: "--with-recommends --with-suggests --with-test"
          sudo: false

  test_macos:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: true
      matrix:
        os: ["macos-latest"]
        perl-version:
          - "5.20"
          - "5.30"
          - "5.34"
    needs: build
    steps:
      - uses: actions/checkout@v6
      - uses: shogo82148/actions-setup-perl@v1
        with:
          perl-version: ${{ matrix.perl-version }}
      - name: install deps using cpm
        uses: perl-actions/install-with-cpm@v1.9
        with:
          cpanfile: "cpanfile"
          args: "--with-recommends --with-suggests --with-test"
          sudo: false
```

### After (seven transforms applied, default branch is `main`)

```yaml
name: dzil build and test
on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - "*"
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Build distribution
    runs-on: ubuntu-24.04
    container:
      image: perldocker/perl-tester:5.42
    steps:
      - uses: actions/checkout@v6
      - name: Build Dist
        run: dzil build

  coverage-job:
    needs: build
    runs-on: ubuntu-24.04
    container:
      image: perldocker/perl-tester:5.42
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v7

  test_linux:
    name: Perl ${{ matrix.perl-version }} on ubuntu-latest
    needs: build
    strategy:
      fail-fast: false
      matrix:
        perl-version:
          - "5.10"
          - "5.30"
          - "5.34"
          - "5.36"
          - "5.38"
          - "5.40"
          - "5.42"
    container:
      image: perldocker/perl-tester:${{ matrix.perl-version }}
    steps:
      - uses: actions/checkout@v6
      - uses: perl-actions/setup-cpm@v1
        with:
          version: compat
      - run: cpm install -g --cpanfile cpanfile --with-recommends --with-suggests --with-test

  test_macos:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: ["macos-latest"]
        perl-version:
          - "5.30"
          - "5.34"
          - "5.36"
          - "5.38"
          - "5.40"
          - "5.42"
    needs: build
    steps:
      - uses: actions/checkout@v6
      - uses: shogo82148/actions-setup-perl@v1
        with:
          perl-version: ${{ matrix.perl-version }}
      - uses: perl-actions/setup-cpm@v1
        with:
          version: compat
      - run: cpm install -g --cpanfile cpanfile --with-recommends --with-suggests --with-test
```

Things to notice in the after-state:

- `build` and `coverage-job` containers bumped to `:5.42`. The `test_linux` container still uses `:${{ matrix.perl-version }}` — transform 3 skips any image tag containing `${{`.
- `pull_request.branches: ["*"]` is preserved — transform 4 only touches `on.push.branches`.
- Quotes are preserved on existing list entries; new entries match (here, double quotes).
- `test_macos.strategy.fail-fast: true` was flipped to `false`; `test_linux` had no `fail-fast` key — transform 1 inserts `fail-fast: false` regardless.
- Both `install-with-cpm` steps became a `setup-cpm@v1` step (`version: compat`) followed by an explicit `cpm install -g` run step; the old `sudo:` key was dropped (the perl-tester container runs as root and the macOS Perl is user-local) and the matrix-conditional `version:` expression is gone — `version: compat` pins old Perls upstream.
- `test_macos.matrix.perl-version` lost `"5.20"` (transform 7) but `test_linux.matrix.perl-version` keeps `"5.10"` — transform 7 leaves Linux container jobs alone.

## Verification

After **each** transform's edit, before committing:

1. **YAML parse:** `python3 -c 'import yaml; yaml.safe_load(open(path))'`. Failure → stop, leave file unstaged, surface the error.
2. **Per-transform structural assertion:**

| # | Assertion |
|---|---|
| 1 | every job whose `strategy:` contains a `matrix:` has `fail-fast: false` set |
| 2 | each targeted job's `perl-version` list includes `5.36`, `5.38`, `5.40`, `5.42` |
| 3 | every `container.image` whose tag contains no `${{` ends in `:5.42` |
| 4 | `on.push.branches` is a single-item list with the resolved default branch |
| 5 | top-level `concurrency.group` and `concurrency.cancel-in-progress: true` present |
| 6 | no `install-with-cpm`/`install-with-cpanm` steps remain; every `cpm install` run step is preceded by a `setup-cpm@v1` step with `version: compat` (and the `v1` tag resolves via `gh api`) |
| 7 | every macOS-only and Windows-only job's `perl-version` list has no entry < `5.24` |

Do not auto-revert on failure — that would hide bugs in the skill. Stop and surface the failure so a human can inspect.

## Common Mistakes

| Mistake | Why it's wrong | Fix |
|---|---|---|
| Extending Windows matrix to 5.42 | Scope is Linux + macOS; Windows often has dep/toolchain quirks worth a deliberate decision | Skip Windows in transform 2 |
| Bumping every `perldocker/perl-tester:<X>` to `:5.42` | Test-matrix jobs use the matrix variable on purpose; only build/coverage are fixed | Only bump literal-tag images; never touch a tag containing `${{` |
| Adding `concurrency:` when the user already has one | Overwrites their grouping/cancellation choice | Skip transform 5 if any `concurrency:` exists at workflow level |
| Stripping `pull_request.branches` | Spec says leave `pull_request:` alone | Only touch `on.push.branches`, never `pull_request` |
| Hardcoding a single cpm `version:` on the `setup-cpm` step | Forces one cpm release across all Perls instead of per-Perl selection | Use `version: compat` so old Perls get cpm `0.998003` and newer Perls get the latest |
| Batching all 6 transforms into one commit | Can't revert one transform without the others | One commit per transform |
| Auto-reverting on verification failure | Hides bugs in the skill | Stop, surface the failure, leave files uncommitted |
| Carrying the old `sudo:` key onto the `cpm install` run step | There is no `sudo:` input on a `run:` step, and the install target is already writable (root container / user-local Perl) | Drop `sudo:` when converting to `setup-cpm` + `cpm install` |
| Leaving `perl-actions/install-with-cpanm` in place | The cpanm action is the legacy serial installer; cpm is parallel and the supported path | Rewrite any `install-with-cpanm@*` step to `setup-cpm@v1` + `cpm install` in the same transform |
| Pinning `setup-cpm@v1` (or any action ref) without checking the tag exists | Action tags move and some actions never publish a given major; a non-existent ref fails the workflow on every run | Confirm the tag resolves with `gh api repos/<owner>/<repo>/git/refs/tags/<ref>` before writing the `uses:` line |
| Trimming pre-5.24 Perls from Linux container jobs | `perldocker/perl-tester` images carry working older Perls; transform 6 already covers the cpm install path via `version: compat` | Transform 7 only touches macOS-only and Windows-only jobs |
| Trimming pre-5.24 entries from a mixed-OS matrix (`os: [ubuntu, macos]`) | `perl-version` is a single axis — dropping one entry kills the cell on every OS, including Linux | Skip mixed matrices in transform 7; use `matrix.exclude:` manually if you really want per-OS trimming |

## Related

- `kitchen-sink:tune-dependabot-config` — the sister skill (Dependabot config harden).
- Reference PR: [libwww-perl/HTTP-Daemon#80](https://github.com/libwww-perl/HTTP-Daemon/pull/80) — exact transforms applied to a real Dist::Zilla project.
- GitHub docs: [`workflow.concurrency`](https://docs.github.com/en/actions/using-jobs/using-concurrency).
- GitHub docs: [`matrix.fail-fast`](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs#handling-failures).
