---
description: Polls the current branch's CI run and reports pass/fail/in-progress (fallback for monitor-ci)
---

Poll the status of the current branch's CI run and report back when it finishes.

Use this as a fallback for monitoring CI **when a `/monitor-ci` command is not present** in the environment. If `/monitor-ci` is available, prefer it — it is purpose-built for this project. `poll-ci` is the generic, `gh`-based fallback.

Steps:
1. Determine the current branch:
   ```bash
   git rev-parse --abbrev-ref HEAD
   ```

2. Find the most recent CI run for that branch (`<branch>` is the value from step 1):
   ```bash
   gh run list --branch "<branch>" --limit 1 \
     --json databaseId,status,conclusion,workflowName,headSha,url
   ```
   - If no runs are found, tell the user no CI run exists for the branch yet (CI may not have started, or the branch may not be pushed). Suggest `git push` if the branch has no remote counterpart, then stop.
   - If the latest run's `headSha` does not match `git rev-parse HEAD`, warn the user that the newest commit has not triggered a run yet, and ask whether to poll the existing run or wait. If they choose to wait, re-run this `gh run list` command every ~20 seconds (capped at ~30 minutes, as in step 3) until a run whose `headSha` matches the current HEAD appears, then poll that run.

3. Poll until the run completes. Prefer `gh run watch`, which blocks until the run finishes:
   ```bash
   gh run watch <databaseId> --exit-status
   ```
   - `--exit-status` makes the command exit non-zero if the run fails, so you can branch on the result.
   - `gh run watch` streams per-job progress to the terminal on its own, so no extra status reporting is needed on that path.
   - If `gh run watch` is unavailable or you need finer control, poll manually instead: re-run the `gh run list` command from step 2 every ~20 seconds until `status` is `completed`, reporting `queued` -> `in_progress` -> `completed` transitions as they happen. Cap polling at a sensible limit (e.g. 30 minutes) and stop with a timeout message if exceeded.

4. Report the final status to the user:
   - **Pass** — `conclusion` is `success`. State that CI passed and include the run URL. Treat `skipped` and `neutral` as non-failing outcomes too: report success but note the qualifier.
   - **Fail** — `conclusion` is `failure`, `cancelled`, `timed_out`, `startup_failure`, or `stale`. State that CI failed, include the run URL, and surface the failing jobs:
     ```bash
     gh run view <databaseId> --json jobs \
       -q '.jobs[] | select(.conclusion != "success") | .name'
     ```
     Offer to show failing logs with `gh run view <databaseId> --log-failed`.
   - **Needs attention** — `conclusion` is `action_required` (e.g. a job awaiting manual approval). This is not a failure; report that the run is paused pending action and include the run URL so the user can approve or investigate.
   - **In progress** — only if polling was stopped early (timeout or user interrupt). Report the current `status` and the run URL so the user can resume checking.
   - **Any other `conclusion`** — report the raw value verbatim along with the run URL rather than guessing, so no terminal state is silently swallowed.

**Notes:**
- Operate on the current branch's CI; do not switch branches.
- On the manual-polling path, report status changes as they happen rather than only at the end, so the user has visibility into long-running pipelines.
