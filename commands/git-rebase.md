---
description: Rebases onto origin/main (or origin/master) and resolves conflicts
---

Rebase the current branch onto the remote default branch, resolving any conflicts that arise.

Steps:
1. Detect the default branch. Prefer `main`; fall back to `master` if `main` does not exist on the remote:
   - Run `git ls-remote --heads origin main` — if the output is non-empty, use `main`
   - Otherwise run `git ls-remote --heads origin master` — if non-empty, use `master`
   - If neither exists, stop and ask the user which branch to rebase onto
   - Use the detected name as `<base>` in the steps below

2. Create a todo list with these tasks:
   - Fetch latest changes from origin/<base>
   - Pull changes from origin/<base> into current branch (with rebase)
   - Identify and resolve merge conflicts
   - Verify resolution and complete merge

3. Fetch the latest changes: `git fetch origin <base>`

4. Pull with rebase: `git pull --rebase origin <base>`
   - ALWAYS use `--rebase` flag (never plain `git pull`)
   - This keeps a clean linear history

5. If conflicts occur:
   - Read each conflicted file to understand the conflict
   - Resolve by keeping both changes when appropriate, or choosing the correct version
   - After editing, stage the resolved file: `git add <file>`
   - Continue the rebase: `git rebase --continue`

6. Verify the final state: `git status`

7. Update todo list to mark tasks completed as you progress

8. Inform the user:
   - What conflicts were resolved and how
   - The final state of the branch
   - If a force push is needed (branch has remote counterpart), use `git push --force-with-lease`
     - NEVER use `--force` - it can overwrite others' work
     - `--force-with-lease` fails safely if remote has new commits
