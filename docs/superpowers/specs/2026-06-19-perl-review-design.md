# perl-review skill — design

**Date:** 2026-06-19
**Status:** approved (design phase)

## Purpose

Integrate the user's living set of Perl coding standards into the kitchen-sink
plugin as an on-demand reviewer. The standards are a document the user maintains
and grows over time; the skill applies whatever is currently in that document
when reviewing Perl code.

## Detection mechanism

The reviewing model reads the in-scope Perl and applies `STANDARDS.md` as a
checklist. There is **no tooling** (no `perlcritic`/PPI) in v1 — this is a pure
LLM-checklist reviewer, the same pattern as `security-review` and
`code-review-flow`. This is stated explicitly because the repo has a
`perlcritic` story via `tune-precious`, and a reader might otherwise expect
tooling. The `Type` column governs *report confidence*, not detection.

## Shape

A skill at `skills/perl-review/` with two files:

- `SKILL.md` — the process: when to use, what to review, how to report. Stable;
  changes rarely.
- `STANDARDS.md` — the living document. A table of rules the user edits freely.
  The skill reads it at runtime, so adding or changing a rule requires no edit
  to `SKILL.md`.

## Behavior

Flag-only. The skill reads Perl, reports violations grouped by rule, and makes
no edits and no commits. The user applies fixes themselves. (Auto-fix was
considered and deliberately deferred — start slowly.)

## Execution: dispatch to a subagent

Reading many Perl files and applying ~15 rules is token-heavy and pollutes the
caller's context. When invoked, the skill dispatches the review to a
`general-purpose` subagent (via the `Agent` tool), as `tune-perl-ci` does. The
subagent does the file reading and rule application and returns **only** the
grouped report + one-line summary. The SKILL.md carries an explicit "Dispatch
this skill to a subagent" section. If the user asks to run inline ("do it here
so I can watch"), honour that — dispatch is the default, not a hard rule.

## Input

- No arguments → review the branch's committed changes against the base:
  `git diff $(git merge-base <default-branch> HEAD)...HEAD`, limited to changed
  in-scope Perl files. Resolve `<default-branch>` with the same block
  `tune-perl-ci` uses (`git symbolic-ref refs/remotes/origin/HEAD`, falling back
  to `main` then `master`).
- Paths given (e.g. `lib/Foo.pm t/`) → review those files/dirs instead.
- No in-scope changes → report "no Perl changes to review" and exit cleanly.

This mirrors how the other review skills in this repo feel: zero-arg does the
obvious thing, explicit paths override.

### In-scope Perl files (v1)

- Extensions `.pm`, `.pl`, `.t`.
- Extensionless changed files whose first line is a Perl shebang
  (`#!...perl`).
- Not covered in v1 (deliberate limitation): `.psgi`, `.cgi`, `.PL`, `.pod`.

`tests`-scope rules apply to `.t` files; `general`-scope rules apply to all
in-scope Perl.

## Frontmatter

Matches repo convention — a trigger-laden description drives auto-invocation:

```yaml
---
name: perl-review
description: Use when reviewing or improving Perl code against project standards — reads changed .pm/.pl/.t files (or named paths) and flags violations of the rules in STANDARDS.md (quoting, core-module use, URL building, test hygiene, …).
version: 1.0.0
---
```

## STANDARDS.md structure

A markdown table, grouped by scope into **General** and **Tests** (matching how
the user wrote them). Columns:

| Column | Purpose |
|--------|---------|
| **Rule** | Short name, e.g. "prefer single quotes" |
| **Detail** | The full standard, phrased as guidance to a reviewer |
| **Scope** | `general` or `tests` |
| **Type** | `clear` (assert confidently) or `judgment` (raise as a suggestion) |

A short **"How to extend"** note at the top explains: append a row, no other
file needs touching. That is what makes it the living document.

### Seed rules (verbatim from the user)

General (`general`):

- avoid using custom code when there's a core Perl module that does the same thing — `judgment`
- if we have unit tests for a module, delete any test which checks specifically if that module can be compiled — `clear`
- `require` is to be used sparingly. prefer `use` — `judgment`
- prefer single quotes where no interpolation is required — `clear` (caveat: don't flag literals containing apostrophes or intentional `$`/`@`, where switching quotes would need escaping)
- alpha-sort hash keys — `judgment` (keys are often ordered intentionally — grouping, precedence; suggest, don't assert)
- use URI to build URLs — `judgment`
- don't quote hash keys which do not require it — `clear`
- prefer Try::Tiny over eval — `judgment` (modern Perl has native `try/catch`; and not every `eval` is exception handling, e.g. `eval { require Foo }`)

Tests (`tests`):

- test files don't need Pod — `clear`
- tests probably don't need comments. instead put the comments into test descriptions — `judgment`
- if you want to describe a set of tests, consider using a subtest — `judgment`
- consider table driven tests or subtests to avoid shadowing vars — `judgment`
- don't employ use_ok() to assert that a module can be loaded/is present — `clear`
- don't employ isa_ok() to assert what is returned by new() — `clear`
- Prefer Test::Fatal for exceptions — `clear`

(The "delete compile-only tests" and "no `use_ok`" rules overlap in spirit but
target different things — the first deletes a whole test whose only job is
asserting a module compiles; the second drops a `use_ok()` load-assertion that
sits inside an otherwise useful test. Both are kept. The report-format dedup
rule handles the case where one line trips both.)

## Report format

Grouped by rule; only rules with hits are shown (no "No violations:" trailer —
it is noise on small diffs). Each hit is `file:line — detail`.

```
## prefer single quotes (3)
- lib/Foo.pm:42 — "constant string" → 'constant string'
- ...

## alpha-sort hash keys — suggestion (1)
- lib/Bar.pm:88 — keys out of order: zebra, apple, mango
```

Ends with a one-line summary: `N violations across M files, K rules`.

`clear` rules are asserted as violations; `judgment` rules are labelled
`— suggestion` in the heading and phrased as suggestions, in the same grouped
layout. When two rules flag the same line (e.g. a compile-only test that also
uses `use_ok`), report it once under the most specific rule.

## Out of scope (deferred)

- Auto-fix / one-commit-per-transform (the `tune-perl-ci` model). Parked; the
  `Type` column future-proofs it.
- Other review flows citing `STANDARDS.md`. The two-file split makes this
  possible later, but no wiring is built now.

## Registration & versioning

Skills are auto-discovered from `skills/*/SKILL.md` — there is no per-skill
entry in plugin.json/marketplace.json. Shipping this skill therefore means:

1. Add `skills/perl-review/{SKILL.md,STANDARDS.md}`.
2. New skill → minor bump: `2.8.0` → `2.9.0` in all three version strings
   (`.claude-plugin/plugin.json`, and both the `metadata` and `plugins[]`
   entries in `.claude-plugin/marketplace.json`), per CLAUDE.md.
3. Add a `perl-review` row to the README "Contents" → Skills table.
