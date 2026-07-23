# Example 2: GitHub Issue Fix Review

## Scenario
You're on a `fix-1234` branch and just completed the implementation. The branch name tells the story.

## Conversation

**User:**
```
Request a code review for the fix
```

**Assistant:**

I'll review the changes for issue #1234. Let me get the details.

*Checks branch name from gitStatus:*
```
Current branch: fix-1234
```

*Gets issue details:*
```bash
gh issue view 1234
```

Output:
```
#1234: Tags not sorting correctly by distance
User expects tags sorted by numeric distance value (10m, 50m, 100m)
but currently they sort alphabetically (100m, 10m, 50m)
```

*Checks recent commits in context - sees:*
```
[fix-1234 d0e856b] Fix tag sorting with case-insensitive distance parsing
 3 files changed, 67 insertions(+), 12 deletions(-)
```

*Gets base SHA:*
```bash
git log --oneline origin/main -1
```
Output: `4f940124`

*Invokes code-reviewer:*

```
Task(general-purpose, "Review issue #1234 fix"):

# Code Review Agent

You are reviewing code changes for production readiness.

## What Was Implemented

Fixed tag sorting to handle numeric distance values correctly.

Changes:
- Added parseDistanceTag() helper function
- Implemented case-insensitive regex for distance extraction
- Updated sort comparator to use numeric values
- Added unit tests for edge cases (10m, 50m, 100m, 1km)

## Requirements/Plan

**Issue:** #1234 - Tags not sorting correctly by distance

**Problem:** Tags with distance values were sorting alphabetically instead of numerically
- Expected: 10m, 50m, 100m
- Got: 100m, 10m, 50m

**Acceptance Criteria:**
- Tags sort by numeric distance value
- Case-insensitive matching (10M, 10m)
- Handles mixed units (m, km)

## Git Range to Review

**Base:** 4f940124 (origin/main)
**Head:** d0e856b

git diff --stat 4f940124..d0e856b
git diff 4f940124..d0e856b

## Review Focus

Please verify:
1. Correct numeric sorting implementation
2. Edge case handling (case, units, invalid values)
3. Test coverage for acceptance criteria
4. No regression risks for existing tag sorting

---

## After Review Completes

**Check if PR exists:**
```bash
gh pr list --head fix-1234 --json number,url
```

**Result:**
```json
[{"number": 456, "url": "https://github.com/user/repo/pull/456"}]
```

**Post review to PR as inline anchored comments, batched into one review.** Each finding carries
a `file:line`, so it becomes an inline comment on that exact diff line (see
[../SKILL.md](../SKILL.md#inline-review-protocol)):

```bash
# Resolve the head SHA (don't assume local HEAD matches the PR head)
HEAD_SHA=$(gh pr view 456 --json headRefOid -q .headRefOid)

# Build review.json with jq — the two file:line findings anchor inline; strengths + assessment
# go in the summary body. event: COMMENT (code-review-flow never self-approves).
jq -n --arg sha "$HEAD_SHA" \
  --arg body $'Automated review — inline findings below.\n\n**Strengths:** clean parseDistanceTag(), good edge-case coverage, case-insensitive matching.\n\n**Ready to merge?** With fixes — address the inline validation finding first.' \
  --arg b1 $'**[Important]** No handling for invalid distance formats. Tags like "distance:invalid" will cause parsing errors — add validation and return null for invalid formats.' \
  --arg b2 '**[Minor]** Missing test for mixed unit types — add a test for "10m, 1km, 50m" to verify unit conversion.' \
  '{commit_id: $sha, event: "COMMENT", body: $body,
    comments: [
      {path: "src/utils/tags.ts", line: 23, side: "RIGHT", body: $b1},
      {path: "src/utils/tags.test.ts", line: 45, side: "RIGHT", body: $b2}
    ]}' \
  > "${TMPDIR:-/tmp}/review.json"

gh api repos/{owner}/{repo}/pulls/456/reviews --method POST --input "${TMPDIR:-/tmp}/review.json"
```

✓ Review posted to [PR #456](https://github.com/user/repo/pull/456) — each finding anchored to its diff line

**Review requires fixes.** `code-review-flow` uses `event: "COMMENT"` and never self-approves;
the user addresses the inline findings, then requests another review or merges after fixing.
