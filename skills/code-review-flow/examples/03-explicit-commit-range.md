# Example 3: Explicit Commit Range Review

## Scenario
User provides specific commit SHAs they want reviewed.

## Conversation

**User:**
```
Review the changes between 4f940124 and d0e856b
```

**Assistant:**

I'll review the changes in that commit range.

*No need to fetch SHAs - user provided them!*

*Optionally get context about what changed:*
```bash
git log --oneline 4f940124..d0e856b
```

Output:
```
d0e856b Fix tag sorting with case-insensitive distance parsing
a3c2f91 Add distance parsing tests
```

*Invokes code-reviewer:*

```
Task(general-purpose, "Review commits 4f940124..d0e856b"):

# Code Review Agent

You are reviewing code changes for production readiness.

## What Was Implemented

Changes from the commit range:
- d0e856b: Fix tag sorting with case-insensitive distance parsing
- a3c2f91: Add distance parsing tests

## Requirements/Plan

**User request:** Review changes between specified commits

Based on commit messages, this appears to be:
- Tag sorting bug fix
- Associated test coverage

## Git Range to Review

**Base:** 4f940124
**Head:** d0e856b

git diff --stat 4f940124..d0e856b
git diff 4f940124..d0e856b
```

## Key Points

✅ **Used provided SHAs** - No need to fetch them
✅ **Got context** - Used git log to understand what changed
✅ **Simple workflow** - Straight to code review

## Variation: Symbolic References

User might also request:

```
Review the last 3 commits
```

In this case, use:
- **Base:** `HEAD~3`
- **Head:** `HEAD`

Or:

```
Review changes since origin/main
```

Use:
- **Base:** `origin/main`
- **Head:** `HEAD`
