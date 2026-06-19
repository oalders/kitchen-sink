# perl-review skill — design

**Date:** 2026-06-19
**Status:** approved (design phase)

## Purpose

Integrate the user's living set of Perl coding standards into the kitchen-sink
plugin as an on-demand reviewer. The standards are a document the user maintains
and grows over time; the skill applies whatever is currently in that document
when reviewing Perl code.

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

## Input

- No arguments → review the current diff against the base branch, limited to
  changed Perl files (`.pm`, `.pl`, `.t`).
- Paths given (e.g. `lib/Foo.pm t/`) → review those files/dirs instead.

This mirrors how the other review skills in this repo feel: zero-arg does the
obvious thing, explicit paths override.

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
- prefer single quotes where no interpolation is required — `clear`
- alpha-sort hash keys — `clear`
- use URI to build URLs — `judgment`
- don't quote hash keys which do not require it — `clear`
- prefer Try::Tiny over eval — `clear`

Tests (`tests`):

- test files don't need Pod — `clear`
- tests probably don't need comments. instead put the comments into test descriptions — `judgment`
- if you want to describe a set of tests, consider using a subtest — `judgment`
- consider table driven tests or subtests to avoid shadowing vars — `judgment`
- don't employ use_ok() to assert that a module can be loaded/is present — `clear`
- don't employ isa_ok() to assert what is returned by new() — `clear`
- Prefer Test::Fatal for exceptions — `clear`

(The "delete compile-only tests" rule and "no use_ok" rule overlap in spirit but
target different things — a standalone `*_compile.t` / `use_ok` check vs. an
`isa_ok`-style assertion — so both are kept.)

## Report format

Grouped by rule; only rules with hits are shown. Each hit is `file:line — detail`.

```
## prefer single quotes (3)
- lib/Foo.pm:42 — "constant string" → 'constant string'
- ...

## alpha-sort hash keys (1)
- lib/Bar.pm:88 — keys out of order: zebra, apple, mango

No violations: use URI, Try::Tiny over eval, ...
```

Ends with a one-line summary: `N violations across M files, K rules`.

`clear` rules are asserted as violations; `judgment` rules are phrased as
suggestions in the same grouped layout.

## Out of scope (deferred)

- Auto-fix / one-commit-per-transform (the `tune-perl-ci` model). Parked; the
  `Type` column future-proofs it.
- Other review flows citing `STANDARDS.md`. The two-file split makes this
  possible later, but no wiring is built now.

## Versioning

New skill → minor version bump in `.claude-plugin/plugin.json` and both entries
in `.claude-plugin/marketplace.json` (per CLAUDE.md). README "Contents" table
gets a `perl-review` row.
