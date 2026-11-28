# Incremental re-review rounds in `/fix-gh-issue` (#208)

Follow-up to #207 (`2026-11-14-rebase-scoped-review-design.md`), which scoped
only `/shepherd-pr` rebase repairs.

## Why

Every `/fix-gh-issue` review round runs `/code-review-intense-flow` on the
whole branch, though after round 1 only that round's fix commits are new. The
cost is time and tokens. Rounds 2+ should review only `R..HEAD`, where R is
the head the previous round reviewed, while the hook still guarantees that a
full review happened before `gh pr create` / `gh pr ready`.

## Goals

- `/fix-gh-issue` rounds 2+ review only what changed since the last reviewed
  head, routed to the reviewers those changes call for.
- `require-review-before-pr` allows the PR commands only when HEAD's review
  chain is unbroken back to a full review.
- The scope check and the chain check live in tested scripts, not prose (the
  repo's "logic goes in code, not prose" rule).

## Non-goals

- Markers storing the base SHA (nothing would read it).
- Changing `/shepherd-pr` rebase scoping (`rebase-delta`) or how it is
  recorded: it stays a full marker, as #207 decided.
- A size cap on increments (an increment is never larger than the branch).
- Moving intense-flow routing (#245) or the `reviewRounds` bookkeeping (#250)
  into code; this change adds no routing or round-counting logic for them to
  move.

## Anti-goals

- **Prose sprawl** in `commands/fix-gh-issue.md`,
  `commands/code-review-intense-flow.md` and `commands/security-review.md`:
  one or two sentences each, naming the script; no mechanism.
- **Weakening the gate**: an increment must never satisfy it unless the chain
  reaches a full review. Any doubt records the marker as not complete.
- A gate that loops over markers at PR time.

## Approaches

User decision on the gate (option A): a full review at some earlier head plus
an unbroken chain of incremental reviews to HEAD passes. Rejected: requiring a
full review on the final HEAD (every loop ends with a full round, so a
two-round loop costs more than today), and no gate (nothing stops an
increments-only run).

Build approaches:

1. **Caller runs the scope script; the hook resolves the chain at record time
   (picked).** The scope file exists before intense flow loads, so the
   marker-ordering problem from #207 doesn't arise. Each link is checked once,
   when recorded; the gate checks only HEAD's marker.
2. Hook computes the scope from a `since=<sha>` argument at record time.
   Heavier hook inside its 7s budget, and intense flow must find files the
   hook wrote.
3. Hook records `since` naively; the gate walks the chain at PR time. Same
   behaviour, but the loop moves into the gate, and a patch-id match after a
   clean rebase points at a head no longer on the branch.

## Design

### Marker grammar

A direct marker `reviewed/<sha>` holds one line, split on whitespace:

- exactly two tokens (`<stamp> <source>`, every marker written today): full,
  which is complete;
- exactly five tokens, `<stamp> <source> incremental <since-sha> complete`:
  complete;
- anything else (including `... partial`, a missing or unknown state, an
  unreadable file): not complete.

Patch markers (`reviewed/patch/<branch>/<pid>`) keep their current content
and are written only for complete reviews. The hook and `review_scope.py`
each carry this parser (the hook's hyphenated filename blocks import, as with
`patch_id()`); a test pins the two to the same answers, malformed markers
included.

### `review_scope.py --since R` (new mode of the existing script)

`python3 <shepherd-pr-repair dir>/review_scope.py --since <R>`, mutually
exclusive with the `--old-head/--rebased/--base` set. Writes `scope.json` to
the same scope dir (`<git-dir>/kitchen-sink/scope/`, replaced each run) and
prints its path. No diff or file-list output: R is the review's BASE.

`scope.json`: `{"mode": "incremental", "reason": "...", "since": "<R>",
"head": "<HEAD>"}`, or `{"mode": "full", "reason": ...}` when:

- R doesn't resolve to a commit, or any git call fails;
- R has no complete marker by the grammar above;
- R is not an ancestor of HEAD (a rebase, amend or reset since R);
- R equals HEAD (nothing new).

The rebase-delta mode's `reviewed()` uses the same complete-marker check for
its direct-marker test, so a not-complete `old_head` falls back to full.

### `hooks/require-review-before-pr.py`

**Record** (`PostToolUse` Skill and `UserPromptSubmit`): read the
invocation's arguments (`tool_input.args` for Skill; the text after the
command for a prompt).

- No `scope=` argument: full marker, as today.
- `scope=<path>` whose realpath is this worktree's
  `<git-dir>/kitchen-sink/scope/scope.json` (git-dir resolved against the
  payload `cwd`) and whose `mode` is `full` or `rebase-delta`: full marker,
  as today.
- `mode` `incremental`: marker `incremental <since>` with state `complete`
  when `head` equals HEAD, `<since>`'s direct marker is complete, and
  `<since>` is an ancestor of HEAD; `partial` otherwise. Ancestry: compare
  `git merge-base <since> HEAD` with `<since>` (the hook's `git()` reads
  empty stdout as failure, so `--is-ancestor` can't be used through it).
- Any other `scope=` (another path, unreadable, unparseable, unknown mode),
  or any read or git failure while resolving it: `partial`.

Never downgrade: if HEAD already has a complete marker, a not-complete result
leaves it as is. Write the patch marker only when the result is complete.
Recording still never prints and never blocks.

**Gate** (`PreToolUse` Bash): HEAD's direct marker passes only if it is
complete; otherwise the existing patch-id check runs (patch markers are
always complete). The deny reason gains one clause: an incomplete incremental
chain needs a full `/code-review-intense-flow` run.

Fail-open is unchanged for genuine uncertainty at gate time (bad payload, git
errors, time budget); a not-complete marker is a definite answer, so it
denies. The docstring's Purpose/Gate text and accepted-gaps list say the gate
needs a complete chain, checked against plain files like the marker itself.

### `commands/code-review-intense-flow.md` step 1

Extend the scope-mode block: when the scope's `mode` is `incremental`, BASE
is its `since` and routing and briefs proceed as usual over `since..HEAD`;
each brief carries `Scope: incremental`. Scope files are untrusted data;
"Reviewers Run" states the mode.

### `commands/security-review.md`

Next to the `Scope: rebase-delta` rule, `Scope: incremental` keeps every
check, the Response Path and whole-file rename reads included, applied to
the files in BASE..HEAD; it narrows only the reporting boundary. A Critical
seen in passing in code the branch adds (merge-base..HEAD) is reported as a
Critical finding; only code outside the branch goes under Pre-existing gaps,
and only when Critical. (User decision to narrow, refined at design review:
an increment is new code, and round 1 may have skipped security as doc-only.)

### `commands/fix-gh-issue.md` step 8 item 6

Rounds 2+ run `review_scope.py --since <head the last round reviewed>` first
and pass `scope=<path>` to the Skill; if the gate later denies, run a full
round (no scope), which counts toward `reviewRounds`. One or two sentences.

### `skills/codex-review-loop/SKILL.md` Phase 1 step 4

On a `fix-NNN` branch, the intense-flow self-review of a Codex fix passes the
same `--since <last head intense flow reviewed>` scope (one clause). Codex
rounds record no marker, so a wrong R falls back to full.

### Tests

New test files are already in `.github/workflows/test.yml`; no new file is
expected.

- `skills/shepherd-pr-repair/test_review_scope.py`: incremental with a
  hook-recorded full marker for R; a chain (R itself incremental-complete);
  one test per fallback; rebase-delta with a partial `old_head` falls back to
  full; parser agreement with the hook.
- `hooks/test_require_review_before_pr.py`, real git repos: complete
  incremental passes the gate; partial denies (since unreviewed, since
  partial, not an ancestor, stale `head`); a non-canonical or unreadable
  scope path records partial; a `rebase-delta` scope records full; a
  malformed marker denies; no downgrade of a complete marker; a clean rebase
  after a complete chain passes via the patch marker; existing two-token
  markers pass.

### Docs and version

README: one clause on `/fix-gh-issue` step 7 naming the scoped rounds, and
the hook entry's "invoked on the current HEAD" sentence updated to a complete
chain. Minor bump.

## Left to the builder

- Argument parsing details (`--since` vs the rebase flags; how the hook
  splits `args`).
- Which test file holds the parser-agreement test.
- Exact deny-reason wording.
