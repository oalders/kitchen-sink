---
description: Creates a draft PR that closes the GitHub issue from the branch name
---

Create a draft PR that closes a GitHub issue.

**Issue number resolution:**
1. If an issue number is passed as an argument, use that
2. Otherwise, extract from branch name (e.g. `fix-1372` -> `1372`)
3. If neither works, ask the user

Steps:
1. Determine the issue number (from argument or branch name)
2. Fetch issue details:
   ```bash
   gh issue view <number> --json title,body
   ```
3. Fetch latest remote state:
   ```bash
   git fetch origin
   ```
4. Push the current branch if it hasn't been pushed yet:
   ```bash
   git push -u origin HEAD
   ```
5. Create the draft PR:
   ```bash
   gh pr create --draft \
                --title "<concise title based on issue>" \
                --body "Closes #<number>

   ## Changes
   - [Summarize changes from git log/diff against origin/main]

   ## Testing
   - [How changes were verified]"
   ```
6. Report the PR URL to the user
