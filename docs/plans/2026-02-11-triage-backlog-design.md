# Design: `/triage-backlog` Command

## Problem

Solo developer tracking work via GitHub issues. Issues go stale not because
they're irrelevant, but because they fell off the radar. Some issues have been
completed as part of overlapping work but are still open. Labels are incomplete,
making it hard to find issues by topic (SEO, testing, Playwright, performance).

## Solution

A `/triage-backlog` slash command for incremental backlog grooming.

## Core Principles

- **Never delete** issues
- **Interactive approval** before any edits
- **Incremental** - track triaged issues via label so work can be done in stages

## Analysis Depth

| Level | Invocation | Behavior | Cost |
|-------|-----------|----------|------|
| Quick | `/triage-backlog quick` | Light heuristic: linked PRs, comment mentions, obvious keyword matches in recent commits | Low |
| Standard | `/triage-backlog` | Commit search: `git log --all --grep` with keywords from issue title/body | Medium |
| Deep | `/triage-backlog deep` | Commit + codebase grep for features/fixes described in the issue | Higher |

## Workflow

### Phase 1: Setup

1. Fetch all open issues via `gh issue list --state open --json number,title,labels,body,createdAt,updatedAt --limit 500`
2. Fetch repo labels via `gh label list --json name,color`
3. Filter out issues already labeled "triaged"
4. Report: "Found X open issues, Y already triaged, Z to review"

### Phase 2: Per-Issue Analysis (interactive)

For each untriaged issue:

1. **Display**: Show number, title, current labels, age, body summary
2. **Completion check** (at chosen depth):
   - Quick: Check for linked PRs/commits in issue comments
   - Standard: `git log --all --grep="<keywords>"` from title/body
   - Deep: Standard + grep codebase for features/fixes described
3. **Task list check**: If issue has `- [ ]` items, check each against codebase and propose updates
4. **Label suggestions**: Based on issue content, suggest from repo's existing labels + standard topic set
5. **Present recommendations** and wait for approval:
   - "Close as completed? (resolved by commit abc123)"
   - "Check off tasks 2 and 4?"
   - "Add labels: playwright, testing?"
6. **Execute** only approved actions
7. **Add "triaged" label** to mark as processed

### Phase 3: Summary

Report actions taken across all issues in the session:
- Issues closed as completed
- Task list items checked off
- Labels added
- Issues reviewed but unchanged

## Label Strategy

- Use a `triaged` label (create if not exists) to track processed issues
- Suggest topic labels based on issue content from standard set:
  SEO, testing, playwright, performance, bug, enhancement, documentation, etc.
- Always use existing repo labels where they match; only suggest creating new ones when needed
- Create labels via `gh label create` before applying

## Implementation

Single slash command file: `commands/triage-backlog.md`
