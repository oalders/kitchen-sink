# perl-review Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a flag-only `perl-review` skill to the kitchen-sink plugin that applies a living document of Perl coding standards to changed (or named) Perl files.

**Architecture:** A skill directory `skills/perl-review/` with two files — a stable `SKILL.md` (process: when to use, subagent dispatch, what to review, report format) and a living `STANDARDS.md` (a rules table the user edits freely, read at review time). The skill dispatches the actual review to a `general-purpose` subagent. No code, no tooling — the reviewing model reads the diff/files and applies `STANDARDS.md` as a checklist.

**Tech Stack:** Markdown skill files. Plugin-conformant YAML frontmatter. No runtime code.

## Global Constraints

- This is a **documentation/skill-authoring** task — there is no compiled code and no test suite. "Tests" are lightweight shell validations (frontmatter parses, row counts, version strings match). Run them exactly as written.
- **Flag-only:** the skill must never edit files or commit. It reports only.
- **Version bump (per CLAUDE.md):** new skill → minor bump `2.8.0` → `2.9.0` in ALL THREE version strings: `.claude-plugin/plugin.json`, and both the `metadata` and `plugins[]` entries in `.claude-plugin/marketplace.json`. All three must match or the plugin cache serves stale versions.
- **Frontmatter convention:** every skill in this repo uses a trigger-laden `description:` ("Use when …") plus a `version:` field. Match it.
- Reference spec: `docs/superpowers/specs/2026-06-19-perl-review-design.md`.

## File Structure

- Create: `skills/perl-review/STANDARDS.md` — the living rules table (General + Tests, each row: Rule / Detail / Type).
- Create: `skills/perl-review/SKILL.md` — process, dispatch, diff resolution, report format.
- Modify: `.claude-plugin/plugin.json` — `version` → `2.9.0`.
- Modify: `.claude-plugin/marketplace.json` — both `version` strings → `2.9.0`.
- Modify: `README.md` — add a `perl-review` row to the Skills table.

---

### Task 1: STANDARDS.md — the living rules document

**Files:**
- Create: `skills/perl-review/STANDARDS.md`

**Interfaces:**
- Produces: a markdown file with two tables (`## General`, `## Tests`), each row having columns `Rule | Detail | Type` where `Type` ∈ {`clear`, `judgment`}. SKILL.md (Task 2) references this file by relative path `STANDARDS.md` and relies on the `Type` column for report tone and the section headers (`General`/`Tests`) for scope.

- [ ] **Step 1: Create the file with the exact content below**

````markdown
# Perl Review Standards

A living checklist applied by the `perl-review` skill. Edit it freely — the
review reads whatever is here at runtime.

## How to extend

Append a row to the appropriate table below. No other file needs touching.

- **Scope** is the table the row lives in: **General** (all Perl) or **Tests**
  (`.t` files).
- **Type** — `clear` (report as a violation) or `judgment` (report as a
  suggestion; the author may have a deliberate reason).

## General

| Rule | Detail | Type |
|------|--------|------|
| prefer core modules | Avoid custom code when a core Perl module does the same thing. | judgment |
| no compile-only tests | If a module has unit tests, delete any test whose only job is checking the module compiles. | clear |
| prefer `use` over `require` | Use `require` sparingly; prefer `use`. | judgment |
| single-quote non-interpolated strings | Prefer single quotes where no interpolation is required. Don't flag literals containing apostrophes or an intentional literal `$`/`@`, where switching quotes would need escaping. | clear |
| alpha-sort hash keys | Hash keys should be alpha-sorted. Keys are often ordered intentionally (grouping, precedence), so suggest rather than assert. | judgment |
| build URLs with URI | Use the `URI` module to build URLs rather than string concatenation. | judgment |
| don't quote bareword hash keys | Don't quote hash keys that don't require it. | clear |
| prefer Try::Tiny over eval | Prefer `Try::Tiny` over `eval` for exception handling. Modern Perl also has native `try/catch`, and not every `eval` is exception handling (e.g. `eval { require Foo }`), so suggest rather than assert. | judgment |

## Tests

| Rule | Detail | Type |
|------|--------|------|
| no Pod in tests | Test files don't need Pod. | clear |
| comments into test descriptions | Tests probably don't need comments; put the comment into the test description instead. | judgment |
| group with subtests | If you want to describe a set of tests, consider a subtest. | judgment |
| table-driven tests | Consider table-driven tests or subtests to avoid shadowing vars. | judgment |
| no use_ok | Don't use `use_ok()` to assert a module can be loaded / is present. | clear |
| no isa_ok on new() | Don't use `isa_ok()` to assert what `new()` returns. | clear |
| Test::Fatal for exceptions | Prefer `Test::Fatal` for testing exceptions. | clear |
````

- [ ] **Step 2: Validate the file has all 15 seed rules**

Run:
```bash
grep -cE '^\| (prefer|no |single|alpha|build|don|group|table|comments|Test::Fatal)' skills/perl-review/STANDARDS.md
```
Expected: `15`

- [ ] **Step 3: Validate both scope sections exist**

Run:
```bash
grep -cE '^## (General|Tests)$' skills/perl-review/STANDARDS.md
```
Expected: `2`

- [ ] **Step 4: Validate every rule row has a valid Type**

Run (counts rows whose last column is neither `clear` nor `judgment`; the two header/separator rows of each table are excluded by the `clear|judgment` filter):
```bash
awk -F'|' '/^\|/ && $0 !~ /Rule|----/ {t=$(NF-1); gsub(/ /,"",t); if (t!="clear" && t!="judgment") print}' skills/perl-review/STANDARDS.md
```
Expected: no output (every rule row ends in `clear` or `judgment`).

- [ ] **Step 5: Commit**

```bash
git add skills/perl-review/STANDARDS.md
git commit -m "Add perl-review STANDARDS.md living rules document"
```

---

### Task 2: SKILL.md — process, dispatch, and report format

**Files:**
- Create: `skills/perl-review/SKILL.md`

**Interfaces:**
- Consumes: `STANDARDS.md` from Task 1 (relative path `STANDARDS.md`; its `Type` column and `General`/`Tests` sections).
- Produces: a plugin-discoverable skill (`skills/perl-review/SKILL.md`) with frontmatter `name: perl-review`, a `description:` starting `Use when`, and `version: 1.0.0`. README (Task 3) names this skill.

- [ ] **Step 1: Create the file with the exact content below**

````markdown
---
name: perl-review
description: Use when reviewing or improving Perl code against project standards — reads changed .pm/.pl/.t files (or named paths) and flags violations of the rules in STANDARDS.md (quoting, core-module use, URL building, test hygiene, and more).
version: 1.0.0
---

# Perl Review

## Overview

Flag-only reviewer that applies the living standards in
[`STANDARDS.md`](STANDARDS.md) to Perl code. It reports violations grouped by
rule and makes **no edits and no commits** — you apply fixes yourself.

`STANDARDS.md` is a table you edit freely. Adding or changing a rule needs no
change to this file; the review reads whatever is in `STANDARDS.md` at runtime.

## When to Use

- You ask to review / Perl-review / check Perl against the project standards.
- After writing or changing Perl (`.pm`, `.pl`, `.t`) on a branch.

**Skip when:** there is no in-scope Perl to review — report that and exit.

## Dispatch this skill to a subagent

When invoked, dispatch the review to a `general-purpose` subagent via the
`Agent` tool. **Do not read every Perl file inline in the caller's context.**

Why: reading the in-scope files and applying every rule is token-heavy, and the
caller only needs the final grouped report.

How to dispatch:
- Brief the subagent with this `SKILL.md` and `STANDARDS.md` as its spec (pass
  both paths), the working directory, and the review target (the diff, or the
  paths the caller named).
- Require it to return **only** the grouped report and the one-line summary, in
  the format under "Report format" below.

If the user asks to run inline ("do it here so I can watch"), honour that —
dispatch is the default, not a hard requirement.

## What to Review

**No paths given** → the branch's committed changes against the base:

```bash
DEFAULT=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')
DEFAULT=${DEFAULT:-main}
BASE=$(git merge-base "$DEFAULT" HEAD)
git diff --name-only "$BASE"...HEAD
```

If `origin/HEAD` is unset, `DEFAULT` falls back to `main` (then try `master` if
`main` doesn't exist locally).

**Paths given** (e.g. `lib/Foo.pm t/`) → review those files / directories
instead of the diff.

### In-scope Perl files

- Extensions `.pm`, `.pl`, `.t`.
- Extensionless changed files whose first line is a Perl shebang (`#!...perl`).
- Out of scope (v1): `.psgi`, `.cgi`, `.PL`, `.pod`.

`Tests`-section rules apply to `.t` files; `General`-section rules apply to all
in-scope Perl. If nothing is in scope, report "no Perl changes to review" and
stop.

## How to Apply the Rules

For each in-scope file, read it and check every applicable rule from
`STANDARDS.md`:

- **`clear`** rules → report as violations.
- **`judgment`** rules → report as suggestions (the author may have a reason).

When one line trips two rules (e.g. a compile-only test that also uses
`use_ok`), report it once under the most specific rule.

## Report format

Group by rule; show only rules with hits. Each hit is `file:line — detail`.
Label `judgment`-rule groups with `— suggestion` in the heading.

```
## single-quote non-interpolated strings (3)
- lib/Foo.pm:42 — "constant string" → 'constant string'
- ...

## alpha-sort hash keys — suggestion (1)
- lib/Bar.pm:88 — keys out of order: zebra, apple, mango
```

End with one line: `N violations across M files, K rules`.
````

- [ ] **Step 2: Validate the frontmatter parses and has the required fields**

Run:
```bash
python3 -c "import yaml,re,sys; t=open('skills/perl-review/SKILL.md').read(); m=re.match(r'^---\n(.*?)\n---\n', t, re.S); d=yaml.safe_load(m.group(1)); assert d['name']=='perl-review', d.get('name'); assert d['description'].startswith('Use when'), d['description'][:20]; assert d['version']=='1.0.0', d.get('version'); print('frontmatter OK')"
```
Expected: `frontmatter OK`

- [ ] **Step 3: Validate the dispatch + flag-only intent is present**

Run:
```bash
grep -q "general-purpose" skills/perl-review/SKILL.md && grep -q "no edits and no commits" skills/perl-review/SKILL.md && echo "intent OK"
```
Expected: `intent OK`

- [ ] **Step 4: Commit**

```bash
git add skills/perl-review/SKILL.md
git commit -m "Add perl-review SKILL.md process and report format"
```

---

### Task 3: Register the skill — version bump + README row

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: the skill name `perl-review` (Task 2) and its one-line purpose.
- Produces: three matching `2.9.0` version strings and a README Skills-table row.

- [ ] **Step 1: Bump the version in `.claude-plugin/plugin.json`**

Change line 3 from `"version": "2.8.0",` to `"version": "2.9.0",`.

- [ ] **Step 2: Bump BOTH version strings in `.claude-plugin/marketplace.json`**

Change the `metadata` version (line ~9) and the `plugins[]` entry version (line ~16), both from `"version": "2.8.0"` to `"version": "2.9.0"`.

- [ ] **Step 3: Verify all three version strings now read 2.9.0 and none read 2.8.0**

Run:
```bash
grep -rn '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```
Expected: three lines, all showing `2.9.0`, none showing `2.8.0`.

- [ ] **Step 4: Add the README Skills-table row (alphabetical — after `over-engineer-no-more`, before `tune-dependabot-config`)**

Insert this line immediately after the `over-engineer-no-more` row in the Skills table (currently `README.md:51`):

```markdown
| **perl-review** | Flags Perl code that strays from your project standards — quoting, core-module use, URL building, test hygiene — reading a living rules doc you edit freely |
```

- [ ] **Step 5: Verify the README row landed in the right place**

Run:
```bash
grep -n "perl-review" README.md
awk '/^\| \*\*over-engineer-no-more/{print NR": "$0} /^\| \*\*perl-review/{print NR": "$0} /^\| \*\*tune-dependabot-config/{print NR": "$0}' README.md
```
Expected: `perl-review` appears once, on a line between the `over-engineer-no-more` and `tune-dependabot-config` rows.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "Register perl-review skill: bump to 2.9.0, add README row"
```

---

## Final verification

- [ ] **All version strings match**

Run:
```bash
grep -roh '"version": "[0-9.]*"' .claude-plugin/ | sort -u
```
Expected: a single line `"version": "2.9.0"`.

- [ ] **Skill directory is complete**

Run:
```bash
ls skills/perl-review/
```
Expected: `SKILL.md  STANDARDS.md`

- [ ] **Nothing was auto-edited outside the planned files**

Run:
```bash
git status --short
```
Expected: clean (all work committed across the three task commits).
