# tune-perl-ci Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new `kitchen-sink:tune-perl-ci` skill that applies six idempotent transforms to Perl-shaped GitHub Actions workflows, plus the plugin metadata bump and README entry.

**Architecture:** The skill is procedural Markdown — `skills/tune-perl-ci/SKILL.md` — describing detection, six transforms, an algorithm, a worked example, verification rules, and common mistakes. No executable code; the algorithm is followed by an agent at call time. Companion edits: version bump in `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`, and README entries under `Skills` + `Skills Overview`.

**Tech Stack:** Plain Markdown (skill body), JSON (plugin manifests), Python's `yaml.safe_load` for the verification check in the final task.

**Spec:** `docs/plans/2026-05-13-tune-perl-ci-design.md`

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `skills/tune-perl-ci/SKILL.md` | Create | The whole skill body — frontmatter, six transforms, algorithm, worked example, verification, common mistakes |
| `.claude-plugin/plugin.json` | Modify | Bump `version` to `1.9.0` |
| `.claude-plugin/marketplace.json` | Modify | Bump `metadata.version` and `plugins[0].version` to `1.9.0` |
| `README.md` | Modify | Add `tune-perl-ci` (and missing `tune-dependabot-config`) to the `Skills` table and `Skills Overview` section |

The SKILL.md is built up section-by-section across tasks 1–6 so each commit is focused and bisect-friendly. Task 7 verifies the worked example actually parses and satisfies the structural assertions described in the skill itself. Tasks 8–9 land the plugin metadata + README entry.

---

## Task 1: Create skill skeleton — frontmatter, Overview, When to Use, Scope detection

**Files:**
- Create: `skills/tune-perl-ci/SKILL.md`

- [ ] **Step 1: Create the skill directory and write the opening sections**

```bash
mkdir -p skills/tune-perl-ci
```

Write `skills/tune-perl-ci/SKILL.md`:

````markdown
---
name: tune-perl-ci
description: Use when modernizing a Perl project's GitHub Actions workflow — applies six idempotent transforms (fail-fast, Perl 5.42 matrix, perl-tester image bump, default-branch push trigger, concurrency cancel, App::cpm pin for ≤ 5.22) for workflows shaped by Dist::Zilla starters using perldocker/perl-tester or shogo82148/actions-setup-perl.
version: 1.0.0
---

# Tune Perl CI

## Overview

**Six transforms applied to Perl-shaped GitHub Actions workflows under `.github/workflows/`:**

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
- The user has deliberately customized concurrency or branch filters — idempotency preserves their choices

## Scope detection

For each `.github/workflows/*.yml`, the file is **in scope** iff it mentions any of:

- `perldocker/perl-tester`
- `shogo82148/actions-setup-perl`
- `perl-actions/install-with-cpm`

Other workflows are skipped silently. If no workflow file matches across the repo, report "no Perl workflows found" and exit cleanly.

If the caller passes a single workflow path as an argument, operate only on that file (still apply the detection rule for safety; bail out with a clear message if it isn't Perl-shaped).
````

- [ ] **Step 2: Verify the frontmatter is valid YAML**

Run:
```bash
python3 -c "import yaml,re; m=re.match(r'---\n(.*?)\n---', open('skills/tune-perl-ci/SKILL.md').read(), re.S); print(yaml.safe_load(m.group(1)))"
```

Expected output (one line, dict on stdout):
```
{'name': 'tune-perl-ci', 'description': 'Use when modernizing ...', 'version': '1.0.0'}
```

If the parse fails, fix the frontmatter and re-run.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: add tune-perl-ci skeleton (frontmatter + scope)

Sets up the new skill file with frontmatter, Overview, When to Use,
and Scope detection. Transforms, algorithm, and examples land in
follow-up commits.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Document Transforms 1–3 (fail-fast, matrix extension, image bump)

**Files:**
- Modify: `skills/tune-perl-ci/SKILL.md` (append `## The Six Transforms` + transforms 1–3)

- [ ] **Step 1: Append transforms 1–3 to the SKILL.md**

Append to `skills/tune-perl-ci/SKILL.md`:

````markdown

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
````

- [ ] **Step 2: Verify the file still parses as Markdown (rough check) and the frontmatter is unchanged**

Run:
```bash
python3 -c "import yaml,re; m=re.match(r'---\n(.*?)\n---', open('skills/tune-perl-ci/SKILL.md').read(), re.S); d=yaml.safe_load(m.group(1)); assert d['name']=='tune-perl-ci' and d['version']=='1.0.0', d; print('OK')"
```

Expected: `OK`.

Then sanity-check that all three transforms are documented:
```bash
grep -c '^### [1-3]\.' skills/tune-perl-ci/SKILL.md
```
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: document transforms 1-3 (fail-fast, matrix, image bump)

Covers the three transforms that operate on matrix jobs and fixed
container images: disabling fail-fast, extending Linux+macOS
matrices to 5.42, and bumping build/coverage containers.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Document Transforms 4–6 (push restriction, concurrency, App::cpm pin)

**Files:**
- Modify: `skills/tune-perl-ci/SKILL.md` (append transforms 4–6)

- [ ] **Step 1: Append transforms 4–6 to the SKILL.md**

Append to `skills/tune-perl-ci/SKILL.md`:

````markdown

### 4. Restrict `push:` to the default branch

**What:** in top-level `on.push.branches:`, replace the list with a single-entry list naming the default branch. Leave `pull_request:` and `workflow_dispatch:` alone (even if they have their own `branches:` filter).

**Skip** transform 4 if `on.push:` itself is absent — nothing to restrict. If the key is present but `branches:` is missing, add `branches:` with the resolved default branch.

**Default branch resolution:** see the `Default branch resolution` section below.

**Why:** avoid double CI runs when a push is also part of a PR.

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

**Skip** if any `concurrency:` already exists at workflow level — the user has chosen their grouping deliberately.

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
    # App::cpm v0.999.0+ requires Perl 5.24+; pin older Perls to the last compatible release.
    version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}
```
````

- [ ] **Step 2: Verify all six transforms are now documented**

Run:
```bash
grep -c '^### [1-6]\.' skills/tune-perl-ci/SKILL.md
```
Expected: `6`.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: document transforms 4-6 (push, concurrency, App::cpm)

Covers the workflow-level transforms (push branch restriction,
concurrency cancel-in-progress) and the per-step App::cpm pin
for older Perls.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Algorithm + Default branch resolution sections

**Files:**
- Modify: `skills/tune-perl-ci/SKILL.md` (append `## Algorithm` and `## Default branch resolution`)

- [ ] **Step 1: Append the Algorithm and Default branch resolution sections**

Append to `skills/tune-perl-ci/SKILL.md`:

````markdown

## Algorithm

```
1. Scan .github/workflows/*.yml. Keep files matching the detection rule.
   Exit early with "no Perl workflows found" if the set is empty.
2. For each transform in order [1..6]:
     a. For each in-scope file, compute the diff this transform would produce.
     b. If every file is already conformant → skip transform (idempotent no-op).
     c. Write the changed files.
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
| 6 | `workflow: pin App::cpm for Perls ≤ 5.22` |

## Default branch resolution

Used by transform 4.

```bash
git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@'
```

- If that prints a branch name, use it.
- Otherwise, if `git show-ref --verify --quiet refs/remotes/origin/master` (or `refs/heads/master`) succeeds, fall back to `master`.
- Otherwise, bail out of transform 4 with a clear message — do not block transforms 1–3, 5, 6.
````

- [ ] **Step 2: Verify the sections are present**

Run:
```bash
grep -c '^## \(Algorithm\|Default branch resolution\)$' skills/tune-perl-ci/SKILL.md
```
Expected: `2`.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: document algorithm and default-branch resolution

The per-transform commit cadence and the resolution chain
(symbolic-ref → master fallback → bail) for the push restriction
transform.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Worked Example (full HTTP-Daemon-shaped before/after)

**Files:**
- Modify: `skills/tune-perl-ci/SKILL.md` (append `## Worked Example` with full before/after YAML)

- [ ] **Step 1: Append the worked example**

Append to `skills/tune-perl-ci/SKILL.md`:

````markdown

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

### After (six transforms applied, default branch is `main`)

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
      - name: Install deps
        uses: perl-actions/install-with-cpm@v2
        with:
          cpanfile: "cpanfile"
          args: "--with-recommends --with-suggests --with-test"
          sudo: false
          # App::cpm v0.999.0+ requires Perl 5.24+; pin older Perls to the last compatible release.
          version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}

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
      - name: install deps using cpm
        uses: perl-actions/install-with-cpm@v2
        with:
          cpanfile: "cpanfile"
          args: "--with-recommends --with-suggests --with-test"
          sudo: false
          # App::cpm v0.999.0+ requires Perl 5.24+; pin older Perls to the last compatible release.
          version: ${{ matrix.perl-version <= '5.22' && '0.998003' || 'main' }}
```

Things to notice in the after-state:

- `build` and `coverage-job` containers bumped to `:5.42`. The `test_linux` container still uses `:${{ matrix.perl-version }}` — transform 3 skips any image tag containing `${{`.
- `pull_request.branches: ["*"]` is preserved — transform 4 only touches `on.push.branches`.
- Quotes are preserved on existing list entries; new entries match (here, double quotes).
- `test_macos.strategy.fail-fast: true` was flipped to `false`.
- Both `install-with-cpm` steps got the conditional `version:` line and the `@v2` bump.
````

- [ ] **Step 2: Verify the worked example is present**

Run:
```bash
grep -c '^### \(Before\|After ' skills/tune-perl-ci/SKILL.md
```
Expected: `2`.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: add worked example (HTTP-Daemon shape, all 6 transforms)

Full before/after YAML showing every transform applied to a
Dist::Zilla-shaped workflow. Doubles as the test fixture for the
verification task below.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Verification + Common Mistakes + Related sections

**Files:**
- Modify: `skills/tune-perl-ci/SKILL.md` (append final sections)

- [ ] **Step 1: Append the closing sections**

Append to `skills/tune-perl-ci/SKILL.md`:

````markdown

## Verification

After **each** transform's edit, before committing:

1. **YAML parse:** `python3 -c 'import yaml; yaml.safe_load(open(path))'`. Failure → stop, leave file unstaged, surface the error.
2. **Per-transform structural assertion:**

| # | Assertion |
|---|---|
| 1 | every `matrix:` parent has a sibling `fail-fast: false` |
| 2 | each targeted job's `perl-version` list includes `5.36`, `5.38`, `5.40`, `5.42` |
| 3 | each fixed-image `container.image` ends in `:5.42` |
| 4 | `on.push.branches` is a single-item list with the resolved default branch |
| 5 | top-level `concurrency.group` and `concurrency.cancel-in-progress: true` present |
| 6 | every `install-with-cpm` step uses `@v2` and has a `with.version` key |

Do not auto-revert on failure — that would hide bugs in the skill. Stop and surface the failure so a human can inspect.

## Common Mistakes

| Mistake | Why it's wrong | Fix |
|---|---|---|
| Extending Windows matrix to 5.42 | Scope is Linux + macOS; Windows often has dep/toolchain quirks worth a deliberate decision | Skip Windows in transform 2 |
| Bumping every `perldocker/perl-tester:<X>` to `:5.42` | Test-matrix jobs use the matrix variable on purpose; only build/coverage are fixed | Only bump literal-tag images; never touch a tag containing `${{` |
| Adding `concurrency:` when the user already has one | Overwrites their grouping/cancellation choice | Skip transform 5 if any `concurrency:` exists at workflow level |
| Stripping `pull_request.branches` | Spec says leave `pull_request:` alone | Only touch `on.push.branches`, never `pull_request` |
| Pinning App::cpm with a hardcoded `version:` (no conditional) | Forces the old release on modern Perls, slowing them down | Always use the matrix-conditional expression |
| Batching all 6 transforms into one commit | Can't revert one transform without the others | One commit per transform |
| Auto-reverting on verification failure | Hides bugs in the skill | Stop, surface the failure, leave files uncommitted |
| Bumping `install-with-cpm@v1.9` to `@v2` without adding the conditional `version:` | v2's default `version: main` is App::cpm v0.999+, which breaks Perls ≤ 5.22 | Always bundle the `version:` line with the `@v2` bump |

## Related

- `kitchen-sink:tune-dependabot-config` — the sister skill (Dependabot config harden).
- Reference PR: [libwww-perl/HTTP-Daemon#80](https://github.com/libwww-perl/HTTP-Daemon/pull/80) — exact transforms applied to a real Dist::Zilla project.
- GitHub docs: [`workflow.concurrency`](https://docs.github.com/en/actions/using-jobs/using-concurrency).
- GitHub docs: [`matrix.fail-fast`](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs#handling-failures).
````

- [ ] **Step 2: Verify all the sections we expect now exist**

Run:
```bash
grep -c '^## \(Overview\|When to Use\|Scope detection\|The Six Transforms\|Algorithm\|Default branch resolution\|Worked Example\|Verification\|Common Mistakes\|Related\)$' skills/tune-perl-ci/SKILL.md
```
Expected: `10`.

- [ ] **Step 3: Commit**

```bash
git add skills/tune-perl-ci/SKILL.md
git commit -m "skill: add verification, common mistakes, related sections

Closes out the SKILL.md body. Verification table lists per-transform
structural assertions; common mistakes captures the footguns spotted
during the design pass.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Verify the worked example actually satisfies the structural assertions

The worked example doubles as the test fixture. Extract the after-state YAML, parse it, and run every structural assertion against it. If any assertion fails, the SKILL.md is wrong and must be fixed.

**Files:**
- No edits (pure verification). If the assertions fail, edit `skills/tune-perl-ci/SKILL.md` to correct the worked example.

- [ ] **Step 1: Extract the after-state YAML to a temp file**

Run:
```bash
python3 <<'PY'
import re
text = open('skills/tune-perl-ci/SKILL.md').read()
# Find every ```yaml ... ``` block that appears AFTER the "### After" heading.
m = re.search(r'### After.*?```yaml\n(.*?)\n```', text, re.S)
assert m, "couldn't find After-state YAML block"
open('/tmp/tune-perl-ci-after.yml','w').write(m.group(1))
print("Extracted", len(m.group(1)), "chars to /tmp/tune-perl-ci-after.yml")
PY
```

Expected: prints `Extracted <N> chars to /tmp/tune-perl-ci-after.yml`.

- [ ] **Step 2: Run YAML parse + every structural assertion**

Run:
```bash
python3 <<'PY'
import yaml
doc = yaml.safe_load(open('/tmp/tune-perl-ci-after.yml'))

# PyYAML uses YAML 1.1 implicit types, so the unquoted top-level key `on:`
# parses as Python True. Real workflows are written that way, so we look up
# whichever form is in the parsed dict.
on_key = True if True in doc else 'on'
top_on = doc[on_key]

# Assertion 1: every strategy with a matrix has fail-fast: false
for jname, job in doc['jobs'].items():
    if 'strategy' in job and 'matrix' in job['strategy']:
        assert job['strategy'].get('fail-fast') is False, \
            f"{jname}: strategy.matrix present but fail-fast != false"

# Assertion 2: targeted jobs' perl-version includes 5.36..5.42
required = {'5.36','5.38','5.40','5.42'}
for jname in ('test_linux','test_macos'):
    pv = doc['jobs'][jname]['strategy']['matrix']['perl-version']
    missing = required - set(map(str, pv))
    assert not missing, f"{jname}: missing perl versions {missing}"

# Assertion 3: literal-tag perl-tester images end in :5.42
for jname in ('build','coverage-job'):
    img = doc['jobs'][jname]['container']['image']
    assert img == 'perldocker/perl-tester:5.42', f"{jname}: image={img}"
# The test_linux container intentionally uses ${{ ... }} — verify we LEFT it alone
assert '${{' in doc['jobs']['test_linux']['container']['image']

# Assertion 4: on.push.branches is a single-item list with the default branch
b = top_on['push']['branches']
assert b == ['main'], f"on.push.branches = {b!r}"

# Assertion 5: concurrency block correct
c = doc['concurrency']
assert c['group'] == '${{ github.workflow }}-${{ github.ref }}'
assert c['cancel-in-progress'] is True

# Assertion 6: every install-with-cpm step uses @v2 and has with.version
seen = 0
for job in doc['jobs'].values():
    for step in job.get('steps', []):
        uses = step.get('uses','')
        if uses.startswith('perl-actions/install-with-cpm@'):
            assert uses == 'perl-actions/install-with-cpm@v2', uses
            assert 'version' in step['with'], step
            seen += 1
assert seen >= 2, f"expected >=2 install-with-cpm steps, saw {seen}"

print(f"OK - all 6 structural assertions pass ({seen} install-with-cpm steps)")
PY
```

Expected: `OK — all 6 structural assertions pass (2 install-with-cpm steps)`.

If any assertion fails, fix the worked example in `skills/tune-perl-ci/SKILL.md`, re-extract, and re-run until all assertions pass. Then amend the most recent commit (which added the worked example):
```bash
git add skills/tune-perl-ci/SKILL.md
git commit --amend --no-edit
```

If everything passes on the first run, no commit is needed for this task — the worked example was correct as-written.

- [ ] **Step 3: Clean up the temp file**

```bash
rm -f /tmp/tune-perl-ci-after.yml
```

---

## Task 8: Bump plugin version to 1.9.0

**Files:**
- Modify: `.claude-plugin/plugin.json` (`version` → `1.9.0`)
- Modify: `.claude-plugin/marketplace.json` (`metadata.version` and `plugins[0].version` → `1.9.0`)

- [ ] **Step 1: Bump `plugin.json`**

Edit `.claude-plugin/plugin.json`:

```diff
-  "version": "1.8.0",
+  "version": "1.9.0",
```

- [ ] **Step 2: Bump `marketplace.json` (both locations)**

Edit `.claude-plugin/marketplace.json`:

```diff
   "metadata": {
     "description": "A collection of useful Claude Code skills and commands for software development workflows",
-    "version": "1.8.0"
+    "version": "1.9.0"
   },
   "plugins": [
     {
       "name": "kitchen-sink",
       "source": "./",
       "description": "Development workflow skills and commands",
-      "version": "1.8.0",
+      "version": "1.9.0",
```

- [ ] **Step 3: Verify all three version strings now match**

Run:
```bash
grep -h '"version":' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```
Expected: three lines, each `"version": "1.9.0"`.

Also verify both files still parse as JSON:
```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "Bump version to 1.9.0 for tune-perl-ci skill

New skill = minor bump per CLAUDE.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Update README — Skills table + Skills Overview

The README's `### Skills` table currently lists only `code-review-flow` and `over-engineer-no-more`. The sister `tune-dependabot-config` is missing too — list both alongside the new `tune-perl-ci` so the README matches the actual plugin contents.

**Files:**
- Modify: `README.md` (lines 46–51 region: `### Skills` table) and the `## Skills Overview` section (after line 196 — `### over-engineer-no-more`)

- [ ] **Step 1: Extend the `### Skills` table**

Replace the Skills table at `README.md` lines 46–51 with:

```markdown
### Skills

| Skill | Description |
|-------|-------------|
| **code-review-flow** | Streamlined code review workflow that avoids permission prompts |
| **over-engineer-no-more** | Prevents your robot from building a spaceship when you asked for a bicycle |
| **tune-dependabot-config** | Groups minor/patch dependabot updates per ecosystem and adds a 7-day cooldown |
| **tune-perl-ci** | Applies six idempotent transforms to Perl GitHub Actions workflows (fail-fast, Perl 5.42 matrix, perl-tester image, default-branch push, concurrency, App::cpm pin) |
```

- [ ] **Step 2: Append `tune-dependabot-config` and `tune-perl-ci` sections to `## Skills Overview`**

After the existing `### over-engineer-no-more` section (ends around line 201, before `## Hooks Overview`), insert:

```markdown
### tune-dependabot-config

Hardens `.github/dependabot.yml`:
- Groups minor and patch updates per ecosystem into a single rolling PR (majors stay individual)
- Adds a 7-day cooldown so churning releases settle before a PR opens
- Preserves user-defined groups; idempotent on re-run

### tune-perl-ci

Modernises a Perl project's GitHub Actions workflow. Six idempotent transforms, one commit each:

1. `fail-fast: false` on every matrix job
2. Extend Linux + macOS matrices through Perl 5.42
3. Bump build + coverage jobs to `perldocker/perl-tester:5.42`
4. Restrict `push:` trigger to the default branch
5. Add a workflow-level `concurrency:` cancel-in-progress block
6. Pin App::cpm for Perls ≤ 5.22 (works around App::cpm v0.999+ requiring Perl 5.24+)

Detection is action-signature based: a workflow is in scope iff it mentions `perldocker/perl-tester`, `shogo82148/actions-setup-perl`, or `perl-actions/install-with-cpm`. Re-running on an already-tuned workflow is a no-op.
```

- [ ] **Step 3: Verify the entries are present**

Run:
```bash
grep -c '\*\*tune-perl-ci\*\*\|\*\*tune-dependabot-config\*\*\|^### tune-perl-ci\|^### tune-dependabot-config' README.md
```
Expected: `4` (two from the table, two from Skills Overview).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document tune-perl-ci (and tune-dependabot-config) in README

Adds both skills to the Skills table and Skills Overview section.
The sister skill was missing from the README too; folding it in
alongside the new one.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Step 1: Confirm the branch is clean and the commit history is clean**

```bash
git status
```
Expected: `nothing to commit, working tree clean`.

```bash
git log --oneline origin/main..HEAD
```
Expected: roughly 8 commits — design doc + 6 SKILL.md commits + version bump + README update (Task 7 may add 0 or 1 commit). All commits have single-purpose subjects.

- [ ] **Step 2: Confirm versions match across all three places**

```bash
grep -h '"version":' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```
Expected: three identical `"version": "1.9.0"` lines.

- [ ] **Step 3: Confirm the SKILL.md frontmatter still parses**

```bash
python3 -c "import yaml,re; m=re.match(r'---\n(.*?)\n---', open('skills/tune-perl-ci/SKILL.md').read(), re.S); d=yaml.safe_load(m.group(1)); print(d)"
```
Expected: a dict with `name: tune-perl-ci`, `version: 1.0.0`.

If everything passes, the implementation is done. Hand off to `/kitchen-sink:fix-gh-issue`'s next step (review + PR).
