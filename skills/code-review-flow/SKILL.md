---
name: code-review-flow
description: Streamlined code review workflow - gets SHAs and invokes a general-purpose code reviewer without permission prompts
version: 1.0.0
---

# Code Review Flow

Wrapper around `superpowers:requesting-code-review` that avoids permission prompts by using information already in context.

## Usage

When user requests code review:
1. Check conversation context for commit SHAs (they're usually visible in recent git output)
2. If not in context, run separate git commands (not compound commands)
3. Invoke a general-purpose reviewer with the template

## Getting Git SHAs Without Prompts

**Option 1: Use context (BEST - no Bash needed)**
- Base SHA: Look at gitStatus, recent `git log` output, or known commit reference
- Head SHA: Shown in your own `git commit` output or `git log`

**Option 2: Run git commands separately (already allowed in most projects)**
```bash
# Run these as SEPARATE Bash calls, not chained with &&
git merge-base origin/main HEAD  # actual branch point, immune to main advancing
git rev-parse HEAD
```

**DON'T do this** (triggers permission prompts):
```bash
# ❌ Compound command with variable assignment
BASE_SHA=$(git merge-base origin/main HEAD) && HEAD_SHA=$(git rev-parse HEAD) && echo "BASE=$BASE_SHA HEAD=$HEAD_SHA"
```

## Invoking Code Reviewer

Once you have the SHAs, invoke the code-reviewer subagent:

```
Task tool with subagent_type: general-purpose

Prompt template:
# Code Review Agent

You are reviewing code changes for production readiness.

**Your task:**
1. Review [WHAT_WAS_IMPLEMENTED]
2. Compare against [PLAN_OR_REQUIREMENTS]
3. Check code quality, architecture, testing
4. Categorize issues by severity
5. Assess production readiness

## What Was Implemented

[DESCRIPTION - Brief summary of what was built]

## Requirements/Plan

[PLAN_REFERENCE - Link to issue, plan doc, or inline description of requirements]

## Git Range to Review

**Base:** [BASE_SHA]
**Head:** [HEAD_SHA]

```bash
git diff --stat [BASE_SHA]..[HEAD_SHA]
git diff [BASE_SHA]..[HEAD_SHA]
```

[... rest of code-reviewer template from superpowers:requesting-code-review/code-reviewer.md]
```

## Posting Review Results

**After review completes, check if PR exists:**

```bash
gh pr list --head $(git branch --show-current) --json number,url
```

**If no PR exists:**
- Display review results to user in conversation
- User can create PR later or continue with local fixes

**If a PR exists, post findings as inline diff-line comments, batched into a single PR
review.** Each finding that carries a `file:line` anchors to the exact diff line so the author
reads it right where the change is, instead of mapping a wall of text back to the code. This is
the canonical inline-review protocol; `/code-review-intense-flow` and `/request-review` defer to
it. `gh pr comment` / `gh pr review --body` can only post PR-level text — line-anchored comments
are reachable only through the REST API via `gh api`.

### Inline review protocol

1. **Resolve the head SHA robustly** — never assume local `HEAD` matches the PR head:
   ```bash
   gh pr view <n> --json headRefOid -q .headRefOid
   ```

2. **Build `review.json` with `jq`**, written to a temp file under `$TMPDIR` (fall back to `/tmp`
   only if unset), rather than a fragile inline heredoc — finding bodies contain markdown and
   backticks. Shape:
   ```json
   {
     "commit_id": "<head-sha>",
     "event": "COMMENT",
     "body": "Automated review — inline findings below. <un-anchorable findings / overall assessment here>",
     "comments": [
       { "path": "go/web/foo.go", "line": 42, "side": "RIGHT",
         "body": "**[Important]** This nil check can move above the loop." },
       { "path": "go/web/bar.go", "start_line": 10, "line": 14, "side": "RIGHT",
         "body": "**[Minor]** This block can be simplified." }
     ]
   }
   ```
   For example, building it safely with `jq`:
   ```bash
   REVIEW_JSON="${TMPDIR:-/tmp}/review.json"
   HEAD_SHA=$(gh pr view <n> --json headRefOid -q .headRefOid)
   jq -n --arg sha "$HEAD_SHA" \
     --arg body "Automated review — inline findings below." \
     --arg b1 "**[Important]** This nil check can move above the loop." \
     '{commit_id: $sha, event: "COMMENT", body: $body,
       comments: [ {path: "go/web/foo.go", line: 42, side: "RIGHT", body: $b1} ]}' \
     > "$REVIEW_JSON"
   ```

3. **POST once** — one review carrying every inline comment, so the author gets a single
   notification, not N:
   ```bash
   gh api repos/{owner}/{repo}/pulls/<n>/reviews --method POST --input "$REVIEW_JSON"
   ```

4. **`event: "COMMENT"` always** — this preserves the "never self-approve" rule for
   `code-review-flow` and `code-review-intense-flow`. Solo-developer workflows don't allow
   self-approval.

### Anchoring rule and fallback

- Each finding maps to a **changed line inside a diff hunk** (or the nearest changed line in the
  same hunk). Use `side: "RIGHT"` for the new version, `LEFT` for the deleted side; a multi-line
  span adds `start_line` + `start_side`.
- A finding that **cannot** be tied to a diff line (architectural, file-spanning, or about
  unchanged context) goes into the review `body` summary instead. **Nothing is dropped** — every
  finding lands either as an inline comment or in the summary.

### Gotchas

1. **Line must be inside the diff.** Commenting on unchanged context outside a hunk returns
   `422`. Map findings to changed lines; route the rest to the summary `body`.
2. **SHA discipline.** Always resolve `headRefOid` via `gh pr view`; a stale or local SHA returns
   `422`.
3. **Batch, don't spray.** One `pulls/<n>/reviews` POST with a `comments[]` array — not a loop of
   single `pulls/<n>/comments` POSTs.
4. **JSON quoting.** Build `review.json` with `jq` into a temp file; don't inline a heredoc.
5. **Replies vs. new threads.** To follow up on an existing thread, POST to
   `pulls/<n>/comments/{comment_id}/replies` rather than opening a new one.

## Fixing Review Issues

When the review finds issues, fix them automatically rather than just reporting:

1. Fix all Critical, Important, AND Minor issues found
2. **Exception**: If the diff is over 500 lines, fix Critical and Important issues in the branch but create GitHub issues for Minor ones so they don't get lost
3. If a Minor issue seems wrong or counterproductive, push back rather than blindly implementing — but default to fixing since it's less overhead than a follow-up issue
4. Commit fixes with a clear message referencing the review
5. **Re-run the review cycle** on the new commits (update HEAD_SHA and review again)
6. Repeat until the review passes clean

## After Review Passes

Once the review finds no remaining issues:

1. Post the final clean review to the PR (if one exists)
2. **Check if `/monitor-ci` slash command exists** in the current project's available skills
3. If `/monitor-ci` exists, invoke it to monitor CI status
4. If `/monitor-ci` does not exist, fall back to `/poll-ci` (the generic `gh`-based CI poller) to monitor CI status
5. If neither command is available, inform the user the review is complete

## Example

```
User: "request a code review using superpowers"

Step 1: Check context for SHAs
- Recent git commit showed: [fix-1065 d0e856b8]
- git log showed base: 4f940124

Step 2: Invoke code-reviewer
Task(general-purpose):
  WHAT_WAS_IMPLEMENTED: Tag sorting fix with case-insensitive handling
  PLAN_OR_REQUIREMENTS: Issue #1065 - sort tags by distance value
  BASE_SHA: 4f940124
  HEAD_SHA: d0e856b8
  DESCRIPTION: Added parseDistanceTag() and case-insensitive regex

Step 3: Review found 1 major issue (missing nil check) and 2 minor issues
- Diff is 180 lines (under 400) → fix all issues
- Commit fixes: [fix-1065 a1b2c3d4]

Step 4: Re-run review with updated HEAD
Task(general-purpose):
  BASE_SHA: 4f940124
  HEAD_SHA: a1b2c3d4
  ... (same params, new HEAD)

Step 5: Review passes clean

Step 6: Check for PR
$ gh pr list --head fix-1065 --json number
[{"number": 123}]

Step 7: Post clean review to PR as a single review (inline anchored comments + summary body)
$ HEAD_SHA=$(gh pr view 123 --json headRefOid -q .headRefOid)
$ jq -n --arg sha "$HEAD_SHA" --arg body "Automated review — passes clean, no remaining issues." \
    '{commit_id: $sha, event: "COMMENT", body: $body, comments: []}' > "${TMPDIR:-/tmp}/review.json"
$ gh api repos/{owner}/{repo}/pulls/123/reviews --method POST --input "${TMPDIR:-/tmp}/review.json"
✓ Review posted to PR #123 (event: COMMENT — never self-approve)

Step 8: Check for /monitor-ci (pick the first that applies)
- /monitor-ci exists → invoke it
- else /poll-ci exists → fall back to /poll-ci
- else → inform user review is complete
```

## Integration with Permissions

This skill works because:
- `Bash(git rev-parse:*)` is typically already allowed
- Separate commands don't need complex shell parsing
- Reading conversation context needs no permissions

## Benefits

✅ No permission prompts during code review
✅ User can leave window while review runs
✅ Faster workflow - no blocking on permissions
✅ Uses information already in context when available
✅ Posts review to PR when one exists - keeps discussion centralized

## When to Use

- After completing a task/feature
- Before merging to main
- After fixing complex bugs
- When stuck (get fresh perspective)

## Related Skills

- **superpowers:requesting-code-review** - The skill this wraps
- **superpowers:receiving-code-review** - How to handle review feedback
- **/code-review-intense-flow** - Heavyweight variant that also fans out to specialized reviewers (security, frontend, seo, geo, playwright) based on the diff
