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

2. Find the most recent CI run for that branch:
   ```bash
   gh run list --branch "<branch>" --limit 1 \
     --json databaseId,status,conclusion,workflowName,headSha,url
   ```
   - If no runs are found, tell the user no CI run exists for the branch yet (CI may not have started, or the branch may not be pushed). Suggest `git push` if the branch has no remote counterpart, then stop.
   - If the latest run's `headSha` does not match `git rev-parse HEAD`, warn the user that the newest commit has not triggered a run yet, and ask whether to poll the existing run or wait.

3. Poll until the run completes. Prefer `gh run watch`, which blocks until the run finishes:
   ```bash
   gh run watch <databaseId> --exit-status
   ```
   - `--exit-status` makes the command exit non-zero if the run fails, so you can branch on the result.
   - If `gh run watch` is unavailable or you need finer control, poll manually instead: re-run the `gh run list` command from step 2 every ~20 seconds until `status` is `completed`, reporting `in_progress`/`queued` transitions as they happen. Cap polling at a sensible limit (e.g. 30 minutes) and stop with a timeout message if exceeded.

4. Report the final status to the user:
   - **Pass** — `conclusion` is `success`. State that CI passed and include the run URL.
   - **Fail** — `conclusion` is `failure`, `cancelled`, `timed_out`, or `action_required`. State that CI failed, include the run URL, and surface the failing jobs:
     ```bash
     gh run view <databaseId> --json jobs \
       -q '.jobs[] | select(.conclusion != "success") | .name'
     ```
     Offer to show failing logs with `gh run view <databaseId> --log-failed`.
   - **In progress** — only if polling was stopped early (timeout or user interrupt). Report the current `status` and the run URL so the user can resume checking.

**Notes:**
- Operate on the current branch's CI; do not switch branches.
- Report status changes as they happen rather than only at the end, so the user has visibility into long-running pipelines.
