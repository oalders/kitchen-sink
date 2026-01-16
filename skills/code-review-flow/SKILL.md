---
name: code-review-flow
description: Streamlined code review workflow - gets SHAs and invokes superpowers:code-reviewer without permission prompts
version: 1.0.0
---

# Code Review Flow

Wrapper around `superpowers:requesting-code-review` that avoids permission prompts by using information already in context.

## Usage

When user requests code review:
1. Check conversation context for commit SHAs (they're usually visible in recent git output)
2. If not in context, run separate git commands (not compound commands)
3. Invoke superpowers:code-reviewer with the template

## Getting Git SHAs Without Prompts

**Option 1: Use context (BEST - no Bash needed)**
- Base SHA: Look at gitStatus, recent `git log` output, or known commit reference
- Head SHA: Shown in your own `git commit` output or `git log`

**Option 2: Run git commands separately (already allowed in most projects)**
```bash
# Run these as SEPARATE Bash calls, not chained with &&
git rev-parse origin/main  # or HEAD~1, or specific commit
git rev-parse HEAD
```

**DON'T do this** (triggers permission prompts):
```bash
# ❌ Compound command with variable assignment
BASE_SHA=$(git rev-parse origin/main) && HEAD_SHA=$(git rev-parse HEAD) && echo "BASE=$BASE_SHA HEAD=$HEAD_SHA"
```

## Invoking Code Reviewer

Once you have the SHAs, invoke the code-reviewer subagent:

```
Task tool with subagent_type: superpowers:code-reviewer

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

## Example

```
User: "request a code review using superpowers"

Step 1: Check context for SHAs
- Recent git commit showed: [fix-1065 d0e856b8]
- git log showed base: 4f940124

Step 2: Invoke code-reviewer
Task(superpowers:code-reviewer):
  WHAT_WAS_IMPLEMENTED: Tag sorting fix with case-insensitive handling
  PLAN_OR_REQUIREMENTS: Issue #1065 - sort tags by distance value
  BASE_SHA: 4f940124
  HEAD_SHA: d0e856b8
  DESCRIPTION: Added parseDistanceTag() and case-insensitive regex
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

## When to Use

- After completing a task/feature
- Before merging to main
- After fixing complex bugs
- When stuck (get fresh perspective)

## Related Skills

- **superpowers:requesting-code-review** - The skill this wraps
- **superpowers:receiving-code-review** - How to handle review feedback
