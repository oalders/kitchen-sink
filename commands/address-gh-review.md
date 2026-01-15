---
description: Fixes immediate PR feedback, defers remaining items as issues
---

Check the last code review on the current branch and address all the feedback.

Steps:
1. Get the PR number and fetch comments:
   ```bash
   # Get PR number for current branch
   gh pr view --json number -q .number

   # Get PR conversation comments (where Claude posts reviews)
   gh api repos/{owner}/{repo}/issues/{pr}/comments

   # Also check for formal review comments if present
   gh pr view --json reviews
   ```
2. Review the feedback systematically, considering:
   - Technical accuracy of the suggestions
   - Whether each suggestion improves the code
   - Any suggestions that might be based on misunderstanding
3. For each piece of feedback:
   - Determine if it should be addressed now or deferred
   - If deferred, create a new GitHub issue for it using `gh issue create`
   - If addressing now, make the necessary code changes
   - Create an atomic commit for each fix
4. After all feedback is addressed, run the project's test suite to verify everything works
5. If tests pass, push the changes with `git push`
6. Report what was addressed, what was deferred (with issue links), and test results

**Important:** Don't blindly implement all suggestions. Evaluate each one critically:
- Does this actually improve the code?
- Is this based on correct understanding of the context?
- Is this the right time to make this change?
