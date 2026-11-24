---
description: Use when polling the current branch's PR checks for pass/fail/in-progress status and no /monitor-ci command is available in the environment.
---

Poll the checks on the current branch's PR until they settle for HEAD, and report the result.

Use this as a fallback for monitoring CI **when a `/monitor-ci` command is not present** in the environment. If `/monitor-ci` is available, prefer it — it is purpose-built for this project. `poll-ci` is the generic, `gh`-based fallback.

Steps:
1. Find the PR: `gh pr view --json number -q .number`. If there is no PR for the branch, say so, suggest opening one (after `git push` if the branch isn't pushed), and stop.

2. Run `python3 <codex-review-loop base dir>/../shepherd-pr-repair/poll_checks.py <number> "$(git rev-parse HEAD)"` (the `codex-review-loop` skill's base directory) with the Bash tool's `run_in_background`; never a foreground `sleep` or a Monitor call. It does the polling and waits up to ~30 minutes. Run nothing else until its completion notification, then act on its last `VERDICT=` line.

3. Report per `VERDICT`:
   - **GREEN** — **Pass**. If it printed `CANCELLED_CHECKS=`, also list those checks under **Needs attention**: they were cancelled, not passed.
   - **FAILED** — if every check named in `FAILED_CHECKS=` has `state=ACTION_REQUIRED` on its `CHECK` line, report **Needs attention** (e.g. awaiting approval); otherwise **Fail**. List the `CHECK` lines, and offer `gh run view <run id> --log-failed`, the run id taken from the check's `link`.
   - **STALL** — no checks are attached for HEAD. If it printed `PR_HEAD=`, the PR's head is that commit, not HEAD: suggest `git push`. Otherwise suggest `gh pr view --json mergeStateStatus,isDraft` to look for a merge conflict or a draft that CI skips.
   - **TIMEOUT** — **In progress**: checks were still running after ~30 minutes. Include `LAST_GH_ERROR=` if it printed one.
   - Exit 64 or any other output — report it verbatim rather than guessing.

**Notes:**
- Operate on the current branch; do not switch branches.
