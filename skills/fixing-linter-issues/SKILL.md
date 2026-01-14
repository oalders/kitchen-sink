---
name: fixing-linter-issues
description: Systematic approach to fixing linter issues in batches of 25, avoiding code degradation by using suppression directives when fixes would make code worse, with verification at each step.
version: 1.0.0
---

# Fixing Linter Issues Systematically

## Overview

**When fixing linter issues, use a systematic batch approach that prioritizes code quality over linter satisfaction.**

**Core principle:** Fix 25 issues per iteration. Never make code worse to satisfy the linter - use suppression directives (nolint, eslint-disable, etc.) with clear justifications when appropriate.

## When to Use

**Use this pattern when:**
- Cleaning up existing codebase with many linter warnings
- Working through a backlog of linter issues
- Need to make incremental progress on linter compliance
- Want to maintain code quality while addressing linter feedback
- Each commit should represent a logical unit of work

**Don't use when:**
- Only a few isolated linter issues (fix directly)
- Linter is reporting genuine bugs (fix immediately, don't batch)
- Working on new code (fix as you write)

## The Pattern

### 1. Run Linter and Identify Issues

```bash
# Run your project's linter
<linter-command> 2>&1 | head -100
```

**Analyze output by issue type:**
- Style issues (formatting, naming)
- Complexity issues (cyclomatic complexity, function length)
- Security issues
- Performance issues
- Code smell issues (duplication, magic numbers)

### 2. Categorize and Prioritize

**Fix in this order:**

1. **Quick wins** (do these first):
   - Formatting issues (run auto-formatter)
   - Missing punctuation in comments
   - Extract constants for repeated strings/numbers

2. **Line length issues**:
   - Break long lines across multiple lines
   - Shorten verbose comments
   - Split function signatures
   - Split method chains

3. **Legitimate suppression cases** (use sparingly):
   - Complexity that can't be simplified (inherent to domain logic)
   - Long functions with comprehensive logic
   - Framework constraints that prevent fix (ORM tags, query builders)

### 3. Fixing Strategy

#### Strategy A: Direct Fixes

For issues that improve code quality:

```javascript
// Style: Add punctuation
// Before: Get user returns the user
// After: Get user returns the user.

// Constants: Extract magic values
// Before: if (timeout === 5000) { ... }
// After: const DEFAULT_TIMEOUT = 5000; if (timeout === DEFAULT_TIMEOUT) { ... }

// Line length: Break long signatures
// Before
function processData(input, options, config, callbacks, validators) {
// After
function processData(
    input,
    options,
    config,
    callbacks,
    validators
) {
```

#### Strategy B: Suppression Directives

For issues where fixing would degrade code quality:

```javascript
// Complex business logic - legitimately high complexity
// eslint-disable-next-line complexity -- Location normalization requires country/state inference
function normalizeLocation(loc) {

// Long but necessary function
// eslint-disable-next-line max-lines-per-function -- Comprehensive query building
function searchItems(criteria) {
```

**Suppression directive rules:**
- Always include a justification comment
- Be concise but clear about WHY it's needed
- Combine multiple related exclusions when appropriate
- Place on line before function/declaration or inline

### 4. Workflow for Each Batch

```bash
# 1. Run linter
<linter-command>

# 2. Fix exactly 25 issues
# - Keep count as you go
# - Mix different types for balance
# - Document fixes in notes

# 3. Run formatter
<formatter-command>

# 4. Run tests
<test-command>

# 5. Create descriptive commit
git add <files>
git commit -m "Fix style, constant, line-length issues (25 total)

- Added punctuation to 5 function comments
- Extracted 8 string constants
- Broke 12 long lines

All tests pass."
```

### 5. Commit Message Template

```
[Brief summary of fix types] (X total)

Fixed X linter issues in this iteration:
- N issue-type (description)
- N issue-type (description)
- N issue-type (description)

[Optional: Key changes section for complex fixes]
Changes:
- Specific change 1
- Specific change 2

All tests pass.
```

## Decision Framework: Fix vs Suppress

**Fix the issue when:**
- Fix improves code clarity
- Fix removes duplication
- Fix makes code more maintainable
- Issue is simple formatting/style
- Can refactor without major changes

**Use suppression when:**
- Fix would require major refactoring
- Complexity is inherent to the domain logic
- Fix would split conceptually-related code
- Technical constraint prevents fix (ORM tags, query builders)
- Code is test fixture with intentional duplication

**Never compromise:**
- Don't split cohesive functions just to reduce line count
- Don't extract meaningless helper functions to reduce complexity
- Don't use suppression as a shortcut for lazy code

## Common Patterns

### Pattern 1: Consolidating Suppression Directives

```javascript
// Before: Separate directives
// eslint-disable-next-line complexity
// eslint-disable-next-line max-depth

// After: Combined
// eslint-disable-next-line complexity, max-depth -- Complex query parsing
```

### Pattern 2: Breaking Long Function Signatures

```javascript
// Before
function getItemsWithFilters(category, subcategory, priceMin, priceMax, sortBy, limit) {

// After
function getItemsWithFilters(
    category,
    subcategory,
    priceMin,
    priceMax,
    sortBy,
    limit
) {
```

### Pattern 3: Shortening Long Comments

```javascript
// Before
// eslint-disable-next-line complexity -- Multiple initialization calls for each component - complexity is inherent to setup

// After
// eslint-disable-next-line complexity -- Multiple init calls - inherent to setup
```

### Pattern 4: Breaking Method Chains

```javascript
// Before
db.query(Model).where({ source: 'test', id: 'upsert-123' }).orderBy('created').limit(10)

// After
db.query(Model)
    .where({ source: 'test', id: 'upsert-123' })
    .orderBy('created')
    .limit(10)
```

## Tracking Progress

Use a todo list to track each iteration:

```
1. [in_progress] Run linter to identify remaining issues
2. [pending] Fix up to 25 linter issues
3. [pending] Create commit for fixes
```

Mark completed as you finish each step, move to next iteration.

## Common Mistakes

### Fixing Too Many at Once

```bash
# BAD: Fix 100 issues in one commit
# Makes code review impossible
# Hard to revert if needed
```

**Fix:** Stick to 25 issues per commit. Creates reviewable chunks.

### Using Suppression Without Justification

```javascript
// BAD
// eslint-disable-next-line complexity
function complexFunction() { ... }

// GOOD
// eslint-disable-next-line complexity -- Complex business logic for order processing
function complexFunction() { ... }
```

### Making Code Worse to Satisfy Linter

```javascript
// BAD: Splitting cohesive logic to reduce function length
function processEvent(e) {
    doStep1(e)  // Just calls one line
    doStep2(e)  // Just calls one line
    doStep3(e)  // Just calls one line
}

// GOOD: Use suppression for legitimately long functions
// eslint-disable-next-line max-lines-per-function -- Comprehensive event processing
function processEvent(e) {
    // All related steps together
}
```

## Benefits

- **Incremental progress** - 25 issues at a time is manageable
- **Reviewable commits** - Each commit is a logical unit
- **Maintain quality** - Never compromise code to satisfy linter
- **Clear history** - Commit messages document what was fixed
- **Safe refactoring** - Tests verify each change
- **Team alignment** - Suppression comments explain exceptions

## Autonomous Operation (Nightly Jobs / Unattended Runs)

**Use this guidance when:** Running linter fixes without human oversight (cron jobs, automated cleanup).

**Skip this section when:** Running interactively with human review after each batch.

### Recommended: Subagent-Driven Pattern

Use a subagent-driven approach where a parent coordinator dispatches worker subagents and verifies their output:

- **Parent coordinator:** Verifies worker output, rejects false claims
- **Worker subagents:** Can use cheaper models for cost savings
- **Pattern:** Parent dispatches one worker per batch, reviews output, rejects if verification missing

**Parent verification checklist:**
1. Check worker claimed "tests pass" or "compilation verified"
2. Run build yourself - confirm zero errors
3. Run tests yourself - confirm all pass
4. Check diagnostics for compilation errors
5. If verification fails: reject work, make worker fix and re-verify
6. Only accept work after confirming verification evidence

### Not Recommended: Direct Execution Without Oversight

Direct execution without parent oversight:
- Cheaper models may skip verification steps even with explicit instructions
- May claim "tests pass" without running them
- Results in broken code (compilation errors, test failures)
- Even strong skill language doesn't prevent this

## Exit Criteria

Stop when:
- All legitimate issues are fixed
- Remaining issues have justified suppression directives
- Team agrees on acceptable linter baseline
- Cost of fixing > benefit (diminishing returns)

Don't aim for zero warnings if it means degrading code quality.

## Related Skills (superpowers plugin)

- `superpowers:test-driven-development` - Write tests, watch them pass before committing
- `superpowers:systematic-debugging` - Similar batch approach to fixing bugs
- `superpowers:verification-before-completion` - Verify tests pass before claiming done
