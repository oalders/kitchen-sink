# Example 1: Simple Feature Review

## Scenario
You just implemented a simple feature and want a code review before merging.

## Conversation

**User:**
```
I just added a dark mode toggle. Can you review the code?
```

**Assistant:**

I'll review your dark mode implementation. Let me get the commit range.

*Checks context - sees recent commit output:*
```
[main 8a3f21e] Add dark mode toggle
 2 files changed, 45 insertions(+), 3 deletions(-)
```

*Checks git log for base commit:*
```bash
git log --oneline -5
```
Output shows: `4f940124` as base

*Now invokes code-reviewer:*

```
Task(superpowers:code-reviewer, "Review dark mode feature"):

# Code Review Agent

You are reviewing code changes for production readiness.

**Your task:**
1. Review the dark mode toggle implementation
2. Check code quality, architecture, testing
3. Categorize issues by severity
4. Assess production readiness

## What Was Implemented

Added a dark mode toggle feature that allows users to switch between light and dark themes.

## Requirements/Plan

User requested: "Add a dark mode toggle"

Expected:
- Toggle UI component
- Theme switching logic
- Persistent preference storage

## Git Range to Review

**Base:** 4f940124
**Head:** 8a3f21e

git diff --stat 4f940124..8a3f21e
git diff 4f940124..8a3f21e
```

## Key Points

✅ **Used context** - Found HEAD SHA (8a3f21e) from recent commit output
✅ **Simple git log** - Got base SHA with separate command
✅ **No compound commands** - Avoided permission prompts
✅ **Clear description** - Explained what was built

## Expected Review Output

The code-reviewer will analyze the changes and provide categorized feedback:
- Critical issues (must fix before merge)
- Important issues (should fix)
- Minor suggestions (nice to have)
- Production readiness assessment
