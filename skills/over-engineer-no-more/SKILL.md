---
name: over-engineer-no-more
description: Use after writing an implementation plan and before launching subagent-driven or other multi-step execution, or when the user frames a change as "just add..." or "a simple change".
version: 1.0.2
---

# Over-Engineer No More

## Overview

**After planning but before execution, evaluate whether the implementation is trivial enough to execute directly rather than using heavyweight processes.**

**Core principle:** Match execution process to implementation complexity.

## When to Use

**Use this skill:**
- After writing an implementation plan
- Before launching subagent-driven development
- Before launching a multi-step execution workflow
- When user says "just add..." or "simple change..."

## The Triage Process

### Step 1: Analyze the Plan

Ask these questions:

**Trivial Implementation Indicators:**
- [ ] Just adding constants, enums, or items to arrays/lists?
- [ ] No new functions or types being created?
- [ ] No new business logic or algorithms?
- [ ] Just updating data structures + corresponding tests?
- [ ] Estimated < 100 lines of actual code?
- [ ] Changes confined to < 3 files?
- [ ] All changes are in the same package/module?

**If 3+ indicators are TRUE -> This is trivial**

### Step 2: Announce Decision

In a sentence or two, tell the user whether the change is trivial or complex, which indicators decided it, and which execution path you're taking. Then proceed.

### Step 3: Execute Accordingly

**Trivial -> Direct implementation:**
1. Make all changes
2. Run tests
3. Commit with clear message
4. Done

**Complex -> Heavyweight process:**
1. Use subagent-driven development
2. Or use a plan execution workflow
3. Full review cycles justified

## Examples

### Example 1: Adding Constants (Trivial)

**Plan says:**
- Add 10 constants to constants file
- Add 4 items to a lookup array
- Add 6 items to a tags array
- Update test assertions for new values

**Triage:**
- [x] Just adding constants
- [x] No new functions
- [x] No business logic
- [x] Just updating data structures
- [x] ~73 lines of code
- [x] 3 files (constants, data, tests)
- [x] Same package

**Decision: TRIVIAL** -> Implement directly

### Example 2: New API Endpoint (Complex)

**Plan says:**
- Create new handler function
- Add route registration
- Implement validation logic
- Add database queries
- Write integration tests
- Update API documentation

**Triage:**
- [ ] Not just adding constants
- [ ] Creating new functions
- [x] Has business logic
- [ ] Not just data structures
- [ ] ~300 lines of code
- [ ] 6+ files
- [ ] Multiple packages

**Decision: COMPLEX** -> Use subagent-driven development

### Example 3: Bug Fix in Validation (Could Go Either Way)

**Plan says:**
- Fix regex in email validation
- Update error message
- Add test case for the edge case

**Triage:**
- [ ] Not just adding constants
- [ ] Some logic changes
- [x] Isolated to validation
- [x] ~20 lines of code
- [x] 2 files
- [x] Same package

**Decision: TRIVIAL** -> Implement directly (simple bug fix)

## Why the Check Matters

Under-processing complex work is the costlier mistake: it skips the review cycles that catch edge cases. Over-processing trivial work only wastes time and credits.

## Common Patterns

**Always Trivial:**
- Adding constants/enums
- Adding items to arrays/maps/lists
- Updating test assertions to match code
- Renaming variables/functions (simple refactor)
- Adding fields to structs/types
- Fixing typos in strings/comments

**Always Complex:**
- New API endpoints
- Database migrations
- Authentication/authorization logic
- Multi-step algorithms
- Cross-cutting refactors
- Performance optimizations

**Context-Dependent:**
- Bug fixes (simple validation fix = trivial, race condition fix = complex)
- Test additions (mirroring existing pattern = trivial, new test framework = complex)
- Configuration changes (add env var = trivial, restructure config system = complex)

## Integration with superpowers plugin

**After `superpowers:writing-plans`:**
-> Run over-engineer-no-more
-> Then either direct implementation OR `superpowers:subagent-driven-development`

**After `superpowers:brainstorming`:**
-> If implementation is clear, run over-engineer-no-more
-> Then either direct implementation OR `superpowers:writing-plans` -> triage -> execution

**User says "fix #123":**
-> Read issue, understand scope
-> Run over-engineer-no-more
-> Execute accordingly
