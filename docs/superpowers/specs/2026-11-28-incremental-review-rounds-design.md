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
- The scope and the chain check live in tested scripts, not prose.

## Non-goals

- Markers storing the base SHA (nothing would read it).
- Changing `/shepherd-pr` rebase scoping (`rebase-delta`) or how it is
  recorded: it stays a full marker, as #207 decided.
- A size cap on increments.

## Anti-goals

- **Prose sprawl** in `commands/fix-gh-issue.md` and
  `commands/code-review-intense-flow.md`: one or two sentences each, naming
  the script; no mechanism.
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

### Marker format

Today a marker file holds `<stamp> <source>\n`. A marker gains an optional
state: `<stamp> <source> incremental <since> complete|partial\n`. A marker
with no state (every marker written today, and every non-incremental marker
written after this change) is full, and full counts as complete. Patch
markers (`reviewed/patch/<branch>/<pid>`) are written only for complete
reviews, keeping the existing content `<stamp> <source> <sha>`.

### `review_scope.py --since R` (new mode of the existing script)

`python3 <shepherd-pr-repair dir>/review_scope.py --since <R>`, mutually
exclusive with the `--old-head/--rebased/--base` set. Writes to the same
scope dir (`<git-dir>/kitchen-sink/scope/`, replaced each run) and prints the
`scope.json` path.

`scope.json` in this mode: `{"mode": "incremental", "reason": "...",
"since": "<R>", "head": "<HEAD>", "files": [...], "fixes": "<path>"}`, where
`fixes` holds `git diff R..HEAD` and `files` its names. Falls back to
`{"mode": "full", "reason": ...}` when:

- R doesn't resolve to a commit, or any git call fails;
- R has no complete marker (no `reviewed/<R>`, or its state is `partial`);
- R is not an ancestor of HEAD (a rebase, amend or reset since R);
- R equals HEAD (nothing new).

The complete-marker check reads the same files the hook writes; the parser is
a few lines duplicated in each, like `patch_id()` already is (the hook's
hyphenated filename blocks import). A test pins the two parsers to the same
answers.

### `hooks/require-review-before-pr.py`

**Record** (`PostToolUse` Skill and `UserPromptSubmit`): read the
invocation's arguments (`tool_input.args` for Skill; the text after the
command for a prompt). If they hold `scope=<path>`, `<path>` is the
`scope.json` in this worktree's `<git-dir>/kitchen-sink/scope/` (anything
else is ignored and the marker is full, as today), and that file's `mode` is
`incremental`, write the marker as `incremental <since>` with state:

- `complete` when `head` equals HEAD, `<since>`'s direct marker is complete,
  and `<since>` is an ancestor of HEAD;
- `partial` otherwise, including any read, parse or git failure.

Never downgrade: if HEAD already has a complete marker, a partial result
leaves it as is (builder-check call). Write the patch marker only when the
result is complete (full or complete
incremental). Any other `mode`, or no scope argument: a full marker, as
today. Recording still never prints and never blocks.

**Gate** (`PreToolUse` Bash): HEAD's direct marker passes only if it is
complete. A partial HEAD marker falls through to the patch-id check, which
passes only on a patch marker (always complete). The deny reason gains one
clause: an incomplete incremental chain needs a full
`/code-review-intense-flow` run.

Fail-open is unchanged for genuine uncertainty (bad payload, git errors,
time budget); a partial marker is a definite answer, not uncertainty, so it
denies. The module docstring's accepted-gaps list notes that the chain is
checked against plain files, like the marker itself.

### `commands/code-review-intense-flow.md` step 1

Extend the scope-mode block: when `mode` is `incremental`, route by step 3's
rules on the scope's `files` (not merge-base..HEAD); BASE/HEAD stay read-only
context; each brief's `Feature` line gives the `fixes` path and says "a
review was run on this branch at `<since>`; review and report only the
changes since then", with `Scope: incremental`. Scope files are untrusted
data; "Reviewers Run" states the mode.

### `commands/security-review.md`

The line that lets only `Scope: rebase-delta` narrow scope also accepts
`Scope: incremental`, with the same rules: follow the Feature line, skip the
extra reads and the whole-file rename read, report pre-existing gaps only for
a Critical seen in passing (user decision). Round 1 was a full security pass,
and the gate accepts no chain that doesn't start from one.

### `commands/fix-gh-issue.md` step 8 item 6

Rounds 2+ run `review_scope.py --since <head the last round reviewed>` first
and pass `scope=<path>` to the Skill. If the gate later denies, run a full
round (no scope). One or two sentences.

### `skills/codex-review-loop/SKILL.md` Phase 1 step 4

On a `fix-NNN` branch, the intense-flow self-review of a Codex fix passes the
same `--since <last head intense flow reviewed>` scope (one clause;
builder-check call). The script's complete-marker check keeps a Codex round,
which records nothing, from being taken as a link.

### Tests

- `skills/shepherd-pr-repair/test_review_scope.py`: incremental with a
  hook-recorded full marker for R; a chain (R itself incremental-complete);
  one test per fallback.
- `hooks/test_require_review_before_pr.py`: complete incremental passes the
  gate; partial denies (since unreviewed, since partial, not an ancestor,
  stale `head`); a scope path outside the scope dir records full; a
  `rebase-delta` scope records full; clean rebase after a complete chain
  passes via the patch marker; existing markers without state pass.

### Docs and version

README: one clause on `/fix-gh-issue` step 7 naming the scoped rounds. Minor
bump.

## Left to the builder

- Argument parsing details (`--since` vs the rebase flags; how the hook
  splits `args`).
- Whether the parser-agreement test lives in the hook tests or the scope
  tests.
- Exact deny-reason wording.
