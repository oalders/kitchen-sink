# /shepherd-pr: recover in watch-only mode when the counters are lost

Issue #151, the line-17 row.

## Intent

After compaction, if no status line from this run is visible, `/shepherd-pr` stops terminally ("counters lost"), so a long run dies only because its context was compacted. The tool is meant to be autonomous and helpful without doing damage. Looser limits after compaction are fine (user decision). Pushing code, and turning auto-merge back on after someone else turned it off, are not.

## Goals, non-goals and anti-goals

- **Goal:** after the counters are lost, the run carries on watching checks and the merge queue until the PR merges or a stop needs a person.
- **Non-goal:** restoring the exact counters. That rules out a state file and rebuilding them from GitHub.
- **Anti-goal:** a recovered run that pushes a repair, or that re-enables auto-merge someone may have turned off. Either would happen with no limit when compaction repeats.

## Approaches

- **A. Watch-only restart (chosen).** Print a fresh status line marked recovered, with no repairs left, and never re-enable auto-merge after someone else turned it off. This is the smallest change, and it can't push however many times compaction happens.
- **B. Restart with one repair left (`2/3`), as the issue suggested.** Rejected. Repairs use a lot of context, so compaction tends to follow them, and repair → compaction → repair would repeat with no bound.
- **C. Save the status line to a file under `.git` and read it back.** Rejected. It keeps every limit exact, but it adds a write on every print, plus handling for stale files and concurrent runs, and the user accepted looser limits.

## Design

This change replaces the "counters lost" terminal stop in the status-line Rule (`commands/shepherd-pr.md`, Rules). After any compaction with no usable status line visible (none, or one that isn't clearly this run's own), the run goes to step 1 right after the fail-fast key check, before any other step, and that pass recovers. The trigger is compaction; a compacted run that may not have printed a line yet is treated the same. Erring toward recovery is safe: a recovered run can do less, not more. It never hands off, never marks a draft ready, and never pushes.

**Recovery never finishes a hand-off.** Step 1's hand-off to `/fix-gh-issue` prints no status line, so a compaction there leads to a recovered pass. With no PR for the branch, stop (terminal) rather than hand off, which would push. With the PR in draft, stop (terminal): the hand-off's "nothing outstanding" gate may not have run. The report says the draft stays draft, that the outstanding-items list may not have been shown, and that re-running `/shepherd-pr <n>` marks it ready. These checks come first.

**Recovery abandons work in progress.** Any repair-skill work in progress is abandoned and nothing is pushed. A rebase in progress (detached HEAD) stops the run (terminal); the report says it may be the repair's and that `git rebase --abort` ends it. If the PR branch is checked out (`git branch --show-current` is `headRefName`) and either it has commits not on `headRefOid` or the tree is dirty, stop (terminal). A clean branch merely behind `headRefOid` goes on: nothing local is lost, and a recovered run never pushes. Untracked files don't count: a run that never pushes or resets can't lose them. The run fetches first, and an `--is-ancestor` check that still fails for any reason counts as local commits. The report says what is local and that `git reset --hard '<headRefOid>'` drops it. The same check catches a head someone else pushed while the line was lost; that case is left to the issue's 37/74 row.

**The recovered pass.** This is the one pass of step 1 that prints the recovered line. Later passes follow the normal step 1 rules against the last line. The `recovered` marker is carried on later lines only so that the report can say what happened.

**Recovered status line.** The fields:

| Field | Value | Reason |
|---|---|---|
| `repairs` | `3/3` | No further repairs, rebases included. Anything that needs one becomes step 6's cap stop, whose report then notes that the counters were reset after compaction. |
| `rerun` | `0` | Bounded across runs by GitHub's run `attempt` (Rerun needs ≤ 1, Infra rerun ≤ 2). A new run on the same head can allow one more Rerun, which looser limits accept. |
| `infra` | `-` | Used only by the repair skill (unreachable at the cap) and by Infra rerun, which the `attempt` bound limits. |
| `requeued` | `-` | Safe because a recovered run never re-enqueues after an ejection (see Auto-merge). |
| `deadline` | anchored | `<earliest>`: the earliest of the current head's check-suite `created_at` (step 3's lookup, run once on the recovered pass), or with no suites the PR's `createdAt`, plus `kitchen-sink.shepherdTimeoutMinutes`. A recovered run can't push, so the anchor, and therefore the deadline, stays the same across repeated compactions. The deadline is checked right after the recovered line; if it has passed, the deadline report ends the run before step 3 can enable auto-merge. In `/shepherd-prs` it stays `deadline n/a`, with no check. |
| auto-merge | `on`, or `off by this run` when it proceeds while off | See Auto-merge. `off by this run` keeps step 3's guard: auto-merge isn't enabled over a failing or cancelled check. |

In `/shepherd-prs`, a PR's first pass starts normally, never as a recovery.

**Auto-merge.** Add `AUTO_MERGE_DISABLED_EVENT` to step 1's timeline query. On the recovered pass, with auto-merge on or queued, go on. Only if auto-merge is off and the PR isn't `isInMergeQueue`:
- If step 3's "head was ejected" test, with `requeued` taken as `-`, passes, stop (terminal: ejected; a recovered run never re-enqueues).
- If a disable event is the head's, stop (terminal). The event is the head's unless it is earlier than `<earliest>`.
  - A person turning auto-merge off on this head causes this stop.
  - So does this run's own `--disable-auto` before a rerun of a failing check.
  - The reason names the compaction: "status line lost after compaction; auto-merge was turned off on this head, possibly by this run, and the run can't tell who did it; run `/shepherd-pr <n>`".
- Otherwise, proceed as `off by this run`: auto-merge was never on, or was turned off before the head was pushed, for example by this run's own repair. Step 3's guard then keeps it off while a check is failing or cancelled; otherwise step 3 enables it as usual, with `--match-head-commit`.
- A queue ejection is a terminal stop for the rest of a recovered run: step 3's ejection handling stops when the last status line is `recovered`, which covers step 1 and step 5 item 3. A recovered run never re-enqueues after an ejection. It can still re-enable auto-merge after its own `--disable-auto` (step 5 item 2, a rerun, then step 4); that is intended.

**Known looseness, accepted.**
- A head someone else pushed is caught only when the PR branch is checked out locally. Otherwise it gets the Codex gate, and the run doesn't stop for it.
- The Codex gate is re-checked on the recovered pass. GitHub's trigger count still bounds it.
- A rebase or repair needed after recovery ends at the cap stop.
- The timeline query reads the last 100 events, so on a PR with heavy queue churn an older disable event could fall outside the window.
- A recovered run on a PR whose head is older than the timeout ends at once with the deadline report.

## Left to the builder

- Exact wording, and where the recovery sits in the Rules and step 1.
- `/shepherd-prs` line 24, and a new bullet in the README's `/shepherd-pr` section. No existing README line mentions the counters-lost stop.
- A minor version bump (2.66.0) in all three version fields.
