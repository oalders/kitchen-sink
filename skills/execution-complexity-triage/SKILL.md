---
name: execution-complexity-triage
description: Evaluate implementation complexity after planning to avoid over-engineering trivial changes with heavyweight processes like subagent-driven development
version: 1.0.0
---

# Execution Complexity Triage

## Overview

**After planning but before execution, evaluate whether the implementation is trivial enough to execute directly rather than using heavyweight processes.**

**Core principle:** Match execution process to implementation complexity. Don't launch 33 subagents to add items to arrays.

## When to Use

**Use this skill:**
- After writing an implementation plan
- Before launching subagent-driven development
- Before launching a multi-step execution workflow
- When user says "just add..." or "simple change..."

**Always check complexity before heavyweight execution.**

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

**For Trivial Implementation:**

```
Plan complete. Checking execution complexity...

Changes required:
- [List specific changes from plan]

This is trivial implementation (adding items to lists/updating data).

I'll implement directly rather than using subagent-driven development.
This will:
- Save time (10 min vs hours)
- Use fewer credits (1 agent vs 33)
- Produce the same quality result

Proceeding with direct implementation.
```

**For Complex Implementation:**

```
Plan complete. Checking execution complexity...

Changes required:
- [List specific changes from plan]

This is complex implementation requiring:
- New business logic / algorithms
- Multi-file coordination
- Database migrations / API changes

I'll use subagent-driven development for:
- Fresh context per task
- Thorough review cycles
- Quality verification

Proceeding with subagent-driven development.
```

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

**Avoided:** 33 subagent invocations (11 implementers + 11 spec reviewers + 11 code reviewers)

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

## Red Flags - DON'T Skip This Check

**Never:**
- Launch subagent-driven development without checking complexity first
- Assume "we wrote a plan, so we need heavyweight execution"
- Over-engineer trivial changes because they "might be complex"
- Ignore user signals like "just add..." or "trivial..."

**Always:**
- Check the triage indicators before execution
- Announce your decision and reasoning
- Match process to complexity
- Optimize for time and credits when appropriate

## Cost-Benefit Analysis

**Trivial implementation executed with heavyweight process:**
- Time: Hours instead of minutes
- Credits: 33x subagents vs 1
- Quality: Same (both produce correct code)
- Overhead: Massive

**Complex implementation executed directly:**
- Time: Same or slightly faster
- Credits: Lower
- Quality: WORSE (no review cycles, fresh context helps)
- Risk: Higher (missed edge cases)

**Match the process to the task.**

## Success Metrics

You're using this skill correctly when:
- Trivial implementations take < 15 minutes
- You rarely launch 30+ subagents for data structure changes
- User doesn't say "this is taking too long for trivial changes"
- Complex implementations still get thorough review

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
-> Run execution-complexity-triage
-> Then either direct implementation OR `superpowers:subagent-driven-development`

**After `superpowers:brainstorming`:**
-> If implementation is clear, run execution-complexity-triage
-> Then either direct implementation OR `superpowers:writing-plans` -> triage -> execution

**User says "fix #123":**
-> Read issue, understand scope
-> Run execution-complexity-triage
-> Execute accordingly
