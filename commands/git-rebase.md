---
description: Rebases onto origin/main and resolves conflicts
---

Rebase the current branch onto origin/main, resolving any conflicts that arise.

Steps:
1. Create a todo list with these tasks:
   - Fetch latest changes from origin/main
   - Pull changes from origin/main into current branch (with rebase)
   - Identify and resolve merge conflicts
   - Verify resolution and complete merge

2. Fetch the latest changes: `git fetch origin main`

3. Pull with rebase: `git pull --rebase origin main`
   - ALWAYS use `--rebase` flag (never plain `git pull`)
   - This keeps a clean linear history

4. If conflicts occur:
   - Read each conflicted file to understand the conflict
   - Resolve by keeping both changes when appropriate, or choosing the correct version
   - After editing, stage the resolved file: `git add <file>`
   - Continue the rebase: `git rebase --continue`

5. Verify the final state: `git status`

6. Update todo list to mark tasks completed as you progress

7. Inform the user:
   - What conflicts were resolved and how
   - The final state of the branch
   - If a force push is needed (branch has remote counterpart), use `git push --force-with-lease`
     - NEVER use `--force` - it can overwrite others' work
     - `--force-with-lease` fails safely if remote has new commits
