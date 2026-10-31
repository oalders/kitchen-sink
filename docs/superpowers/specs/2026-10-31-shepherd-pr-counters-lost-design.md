# /shepherd-pr: recover in watch-only mode when the counters are lost

Issue #151, the line-17 row.

## Intent

After compaction, if no status line from this run is visible, `/shepherd-pr` stops terminally ("counters lost"), so a long run dies only because its context was compacted. The tool is meant to be autonomous and helpful without doing damage. Looser limits after compaction are fine (user decision). Pushing code and turning auto-merge back on are not.

## Goals, non-goals and anti-goals

- **Goal:** after the counters are lost, the run carries on watching checks and the merge queue until the PR merges or a stop needs a person.
- **Non-goal:** restoring the exact counters. That rules out a state file and rebuilding them from GitHub.
- **Anti-goal:** a recovered run that pushes a repair, or re-enables auto-merge that someone may have turned off. Either would happen with no limit when compaction repeats.

## Approaches

- **A. Watch-only restart (chosen).** Print a fresh status line marked recovered, with no repairs left, and never re-enable auto-merge. This is the smallest change, and it stays bounded however many times compaction happens.
- **B. Restart with one repair left (`2/3`), as the issue suggested.** Rejected. Repairs use a lot of context, so compaction tends to follow them, and repair → compaction → repair would repeat with no bound.
- **C. Save the status line to a file under `.git` and read it back.** Rejected. It keeps every limit exact, but it adds a write on every print, plus handling for stale files and concurrent runs, and the user accepted looser limits.

## Design

This change replaces the "counters lost" terminal stop in the status-line Rule (`commands/shepherd-pr.md`, Rules). Both trigger cases recover instead of stopping: no status line visible, and a line that isn't clearly this run's own.

**Recovered status line.** Step 1 prints a fresh line before going on, with these fields:

| Field | Value | Reason |
|---|---|---|
| `repairs` | `3/3` | No further repairs (rebases included). Anything that needs one becomes step 6's existing cap stop. |
| `rerun` | `0` | Already bounded across runs by GitHub's run `attempt` (the Rerun bullet requires `attempt` ≤ 1, Infra rerun ≤ 2). |
| `infra` | `-` | Used only by the repair skill (unreachable at the cap) and the Infra rerun, whose `attempt` bound applies. |
| `requeued` | `-` | Already bounded across runs, because step 3 re-enqueues only when no other removal is the head's. |
| `deadline` | fresh | Computed from the config key as at the start of a run. |
| auto-merge | `on`, or `off` (never `off by this run`) | See below. |

The line is marked `recovered` so that the report says what happened.

**Auto-merge.** If, on a recovered pass, auto-merge is off and the PR isn't `isInMergeQueue`, the run stops (terminal). It can't tell who turned auto-merge off, and only the user re-running `/shepherd-pr <n>` may turn it back on. This uses the existing "the user turned it off" stop.

**Known looseness, accepted.**
- A head pushed by someone else between the lost line and the recovery isn't caught by step 1's "someone else pushed it" test. The run treats it like a fresh user re-run: it still goes through the Codex gate and `--match-head-commit`.
- The deadline restarts.

## Left to the builder

- Exact wording and where the recovery sits in the Rules and step 1.
- The README and `/shepherd-prs` lines that mention the counters-lost stop.
- A minor version bump in all three version fields.
