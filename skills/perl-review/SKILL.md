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
if [ -z "$DEFAULT" ]; then
  for b in main master; do
    if git show-ref --verify --quiet "refs/heads/$b" \
      || git show-ref --verify --quiet "refs/remotes/origin/$b"; then
      DEFAULT=$b && break
    fi
  done
fi
BASE=$(git merge-base "$DEFAULT" HEAD)
git diff --name-only "$BASE"...HEAD
```

If `origin/HEAD` is unset, the loop falls back to whichever of `main` or `master` exists locally or on `origin` (so remote-only checkouts, e.g. CI, still resolve).

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
