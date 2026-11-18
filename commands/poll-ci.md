---
description: Use when polling the current branch's CI run for pass/fail/in-progress status and no /monitor-ci command is available in the environment.
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
   - If the latest run's `headSha` does not match `git rev-parse HEAD`, warn the user that the newest commit has not triggered a run yet, and ask whether to poll the existing run or wait. If they choose to wait, use one Monitor call (never a foreground `sleep`, which the harness blocks) with `timeout_ms` 1800000, running a script that sets `branch=$(git rev-parse --abbrev-ref HEAD)` and `head=$(git rev-parse HEAD)`, then until-loops on this `gh run list` with `--branch "$branch"` until a run's `headSha` equals `"$head"`, `sleep 20` between checks, capped inside the script with `SECONDS` at 1780 (~30 minutes), loop output silenced, printing one line on exit; a `gh` error inside it only keeps it waiting. The script reads the branch and HEAD itself; never paste them into it (a branch name can contain shell syntax). Run nothing else until the Monitor call's exit notification, then re-run this `gh run list`: if a run for HEAD exists, poll that run; otherwise stop, saying no run for HEAD was seen within ~30 minutes.

3. Poll until the run completes. Prefer `gh run watch`, which blocks until the run finishes:
   ```bash
   gh run watch <databaseId> --exit-status
   ```
   - `--exit-status` makes the command exit non-zero if the run fails, so you can branch on the result.
   - `gh run watch` streams per-job progress to the terminal on its own, so no extra status reporting is needed on that path.
   - If `gh run watch` is unavailable or you need finer control, poll manually instead: one Monitor call with `timeout_ms` 1800000, running an until-loop on `gh run view <databaseId> --json status` (by id, so a newer run can't take its place) until `status` is `completed`, `sleep 20` between checks, capped inside the script with `SECONDS` at 1780, printing a line only when `status` is non-empty and differs from the last one printed, so `queued` -> `in_progress` -> `completed` transitions are reported as they happen and a `gh` error (empty `status`) prints nothing. Run nothing else until the Monitor call's exit notification, then read `gh run view <databaseId> --json status,conclusion,url` once: if `status` still isn't `completed`, the cap was hit, so report **In progress** per step 4; otherwise report per step 4.

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
