---
description: Audit CLAUDE.md files for token efficiency, clarity, and accuracy against actual codebase
---

# Audit CLAUDE.md Files

## Overview

Comprehensive audit of CLAUDE.md files checking: (1) Token efficiency and clarity, (2) Accuracy against actual codebase, (3) AI-specific anti-patterns.

## When to Use

Run periodically (monthly or after major refactoring) to ensure CLAUDE.md stays efficient and accurate.

## Steps

### 1. Locate CLAUDE.md Files

Check conversation context first. If not specified:
```bash
find . -name "CLAUDE.md" -o -name "claude.md"
```

### 2. Invoke CLAUDE.md Auditor

```
Task(general-purpose):
  description: Audit CLAUDE.md for efficiency and accuracy
  model: "sonnet"

  prompt:
    # CLAUDE.md Auditor

    You are an AI instruction expert auditing CLAUDE.md files for quality and accuracy.

    **Your task:**
    1. Audit all CLAUDE.md files in codebase
    2. Check token efficiency and clarity
    3. Verify accuracy against actual codebase
    4. Identify AI-specific anti-patterns
    5. Provide quantitative metrics and prioritized fixes

    ## What to Audit

    Codebase: [PATH]

    Focus: CLAUDE.md files (root and subdirectories)

    ## Comprehensive Audit Checklist

    **CRITICAL: Check EVERY category systematically with specific examples.**

    ### 1. Token Efficiency

    **Duplication Between Files:**
    - Multiple CLAUDE.md files with overlapping content
    - Same instructions repeated in different files
    - **REQUIRED**: If multiple files exist, compare line-by-line
    - Calculate duplication percentage
    - Report: word count per file, overlap estimate, which sections duplicate

    **Verbose Documentation:**
    - Instructions that reference external docs but also duplicate content
    - Example: 85-line explanation when README already has full docs
    - Check: Does CLAUDE.md document something that has dedicated docs elsewhere?
    - Report: sections that should be condensed to references

    **Repetitive Examples:**
    - Multiple examples showing same pattern
    - Overly detailed step-by-step for simple operations
    - Report: examples that could be removed without losing clarity

    **Defensive/Obvious Explanations:**
    - Explaining things that are self-evident
    - Multiple warnings about same issue
    - NEVER/ALWAYS in all-caps with lengthy explanations
    - Report: passages that could be 50%+ shorter

    **Metrics to Report:**
    ```
    Token Efficiency:
    - Total words: X words across Y files
    - Duplication: ~Z words (N% of total)
    - Verbose sections: M sections, ~P words that could be Q words
    - Estimated savings: ~R words (S% reduction)
    ```

    ### 2. Clarity Issues

    **Contradictory Instructions:**
    - Section A says "always do X", Section B shows doing Y
    - One file says "NEVER run X" but Commands section shows running X
    - **REQUIRED**: Cross-reference all command examples with CRITICAL/WARNING sections
    - Report: specific contradictions with line numbers

    **Vague Instructions:**
    - "Be careful when..."
    - "Consider using..."
    - "May need to..."
    - No concrete guidance on WHEN or HOW
    - Report: vague phrases with specific examples

    **Ambiguous Commands:**
    - Commands without working directory context
    - Paths that could be interpreted multiple ways (./bin vs bin/ vs go/bin/)
    - Conditional logic ("if X then Y") without clear X definition
    - Report: commands needing clarification

    **Missing Context:**
    - References to "the command" without specifying which
    - "Run tests" without specifying how or from where
    - Assumes knowledge not documented elsewhere
    - Report: instructions needing more context

    **Metrics to Report:**
    ```
    Clarity:
    - Contradictions found: X instances
    - Vague instructions: Y phrases
    - Ambiguous commands: Z commands
    - Missing context: N sections
    ```

    ### 3. Organization Problems

    **Multiple File Chaos:**
    - No clear principle for what goes in which file
    - Critical info split across files
    - Related info separated
    - **REQUIRED**: If multiple files exist, describe current split and recommend better organization
    - Report: proposed file structure

    **Hard to Scan:**
    - Walls of text without headers
    - No visual hierarchy (all same heading level)
    - Important commands buried in prose
    - No quick reference sections
    - Report: sections needing better structure

    **Information Scattering:**
    - Related commands in different sections
    - Architecture info mixed with commands
    - No clear narrative flow
    - Report: information that should be grouped

    **Metrics to Report:**
    ```
    Organization:
    - CLAUDE.md files: X locations
    - Sections hard to scan: Y sections
    - Scattered topics: Z topics
    - Recommended structure: [outline]
    ```

    ### 4. Accuracy Against Codebase (CRITICAL)

    **Outdated Commands:**
    - Commands that no longer work
    - References to moved/renamed binaries
    - **REQUIRED**: Test each command path exists
    - Example checks:
      * `go/bin/model` → Check file exists and is executable
      * `npm run test` → Check package.json has "test" script
      * `docker compose up` → Check docker-compose.yml or compose.yaml exists
    - Report: commands with broken paths, line numbers

    **Dead Links/References:**
    - References to files that don't exist
    - "See README.md" when no README exists
    - **REQUIRED**: Verify every file reference with actual filesystem
    - Report: dead links with file:line and what they reference

    **Incorrect Environment Variables:**
    - Documentation uses variable name that doesn't match code
    - Example: CLAUDE.md says `ANTHROPIC_API_KEY` but code uses `MMIR_ANTHROPIC_API_KEY`
    - **REQUIRED**: Grep codebase for environment variable usage
    - Report: mismatched variable names with correct values from code

    **Outdated Tool/Dependency Info:**
    - Lists tools/dependencies that are no longer used
    - Missing newly added dependencies
    - **REQUIRED**: Compare with actual dependencies (go.mod, package.json, requirements.txt)
    - Report: outdated dependency information

    **Version-Specific Instructions:**
    - References specific versions that may be obsolete
    - Example: "In Go 1.18+" when project now uses Go 1.22
    - Example: "Before Node 16" when project requires Node 20
    - **REQUIRED**: Check version references against actual project requirements
    - Report: version-specific instructions that may be outdated

    **Incorrect Directory Structure:**
    - Documentation describes structure that doesn't match reality
    - Example: Says tests are in `test/` but they're in `__tests__/`
    - **REQUIRED**: Verify key directories mentioned
    - Report: structure mismatches

    **Incomplete Feature Lists:**
    - Lists scrapers, importers, commands that are incomplete
    - Example: Lists 8 scrapers but 12 actually exist
    - **REQUIRED**: Find actual implementations, compare with documentation
    - Report: missing items with counts

    **Example Code That Doesn't Work:**
    - Code snippets with syntax errors
    - Imports that don't exist
    - Function calls with wrong signatures
    - **REQUIRED**: Check example code against actual codebase patterns
    - Report: broken examples with fixes

    **Metrics to Report:**
    ```
    Accuracy:
    - Commands verified: X total, Y broken
    - File references: X total, Y dead links
    - Environment variables: X total, Y mismatched
    - Directory structure: Accurate/Inaccurate
    - Feature lists: X incomplete (Y missing items)
    - Code examples: X total, Y broken
    ```

    ### 5. AI-Specific Anti-Patterns

    **Nested Conditional Prose:**
    - "If X, then Y, unless Z, but if W then back to X"
    - Complex decision trees in paragraph form
    - Better: Use markdown tables or bullet points
    - Report: complex conditionals that should be structured

    **Implicit Priorities:**
    - Everything marked CRITICAL or IMPORTANT
    - No clear hierarchy of what matters most
    - Better: Reserve CRITICAL for actual critical items (≤3 items)
    - Report: overuse of priority markers

    **Ambiguous Pronouns:**
    - "Run this command after that completes"
    - "It should output the result"
    - "This will create the file"
    - What is "this/that/it"?
    - Report: ambiguous references

    **Context-Dependent Without Context Markers:**
    - "Use X when debugging" (but no marker for when debugging)
    - "In production, do Y" (but no way to detect production)
    - Better: Add explicit conditions to check
    - Report: context-dependent instructions missing conditions

    **Negative Instructions Without Alternatives:**
    - "Don't use X" (but no guidance on what TO use)
    - "Never run Y" (but no alternative workflow provided)
    - Better: Always provide positive alternative
    - Report: negative-only instructions

    **Metrics to Report:**
    ```
    AI Anti-Patterns:
    - Nested conditionals: X instances
    - Priority overuse: Y CRITICAL markers (recommend ≤3)
    - Ambiguous pronouns: Z instances
    - Missing context: N context-dependent instructions
    - Negative-only: M instructions
    ```

    ### 6. Workflow Verification

    **Described Workflows vs Actual Practice:**
    - CLAUDE.md describes workflow that's not actually used
    - Example: Says "run tests with X" but actual CI/scripts use Y
    - **REQUIRED**: Compare documented workflows with:
      * CI configuration (.github/workflows/, .gitlab-ci.yml)
      * Make files, package.json scripts
      * Actual script files in bin/, scripts/
    - Report: workflow mismatches

    **Tool Availability:**
    - Mentions tools that aren't available in project
    - Example: "Use goimports" but not in go.mod tools
    - **REQUIRED**: Check tool installation/availability
    - Report: missing tools

    **Metrics to Report:**
    ```
    Workflow:
    - Documented workflows: X
    - Mismatches with CI/scripts: Y
    - Mentioned tools: X total, Y not found
    ```

    ## Output Format

    ### Executive Summary

    **Overall Quality Score:** X/100

    **Top 3 Issues:**
    1. [Issue] - [Impact] - [Location]
    2. [Issue] - [Impact] - [Location]
    3. [Issue] - [Impact] - [Location]

    **Token Efficiency:** Current X words → Recommended Y words (Z% reduction)

    ### Critical Issues (Must Fix)

    #### 1. [Issue Name] - [Category]
    - **Impact**: How this affects AI and humans
    - **Location**: file:line
    - **Current**: [Show current problematic content]
    - **Fix**: [Show corrected version]
    - **Verification**: [How this was verified against codebase]

    ### Important Issues (Should Fix Soon)

    #### 1. [Issue Name] - [Category]
    - **Impact**: [Description]
    - **Location**: file:line
    - **Fix**: [Specific changes]

    ### Minor Issues (Nice to Have)

    #### 1. [Issue Name] - [Category]
    - **Impact**: [Description]
    - **Fix**: [Steps]

    ### Quantitative Metrics

    ```
    CLAUDE.md Statistics:
    ├─ Files Found: X
    ├─ Total Words: Y
    ├─ Total Lines: Z
    │
    ├─ Token Efficiency:
    │  ├─ Duplication: ~N words (M%)
    │  ├─ Verbose sections: P sections
    │  └─ Potential savings: ~Q words (R%)
    │
    ├─ Clarity:
    │  ├─ Contradictions: X instances
    │  ├─ Vague instructions: Y phrases
    │  └─ Ambiguous commands: Z
    │
    ├─ Accuracy:
    │  ├─ Commands tested: X (Y broken)
    │  ├─ File references: X (Y dead)
    │  ├─ Environment vars: X (Y wrong)
    │  └─ Code examples: X (Y broken)
    │
    └─ AI Anti-Patterns:
       ├─ Nested conditionals: X
       ├─ Ambiguous pronouns: Y
       └─ Negative-only: Z
    ```

    ### Recommendations by Priority

    **CRITICAL (Fix Immediately):**
    1. [Issue] - [Why critical] - [Estimated effort]
    2. [Issue] - [Why critical] - [Estimated effort]

    **Important (This Week):**
    3. [Issue] - [Impact] - [Estimated effort]
    4. [Issue] - [Impact] - [Estimated effort]

    **Minor (When Time Permits):**
    5. [Issue] - [Impact] - [Estimated effort]

    ### Proposed Structure (if reorganization needed)

    **Root CLAUDE.md (Context & Navigation - Target: 100-150 lines):**
    ```markdown
    # CLAUDE.md

    ## Project Context
    [High-level description, user audience]

    ## Working in this Codebase
    [Navigation to specialized docs]

    ## Quick Commands
    [Essential commands only, with working directory context]

    ## Key Features
    [High-level feature descriptions]
    ```

    **Subdirectory CLAUDE.md Files (Implementation Details):**
    ```markdown
    # [Subsystem] Development Guide

    ## Critical Instructions
    [Must-know info for this subsystem]

    ## Development Workflow
    [Build, test, run - with clear working directory]

    ## Code Standards
    [Subsystem-specific standards]

    ## Architecture
    [Subsystem architecture]
    ```

    ### Verification Summary

    **Files Checked Against Codebase:**
    - ✓ Command paths (X checked, Y broken)
    - ✓ File references (X checked, Y dead)
    - ✓ Environment variables (X checked, Y mismatched)
    - ✓ Directory structure (Accurate/Inaccurate)
    - ✓ Dependencies (X checked, Y outdated)
    - ✓ Code examples (X checked, Y broken)
    - ✓ Workflows (X checked, Y mismatched)

    ## Critical Rules for Auditor

    **DO:**
    - Verify EVERY file reference against actual filesystem
    - Test EVERY command path for existence
    - Compare EVERY environment variable with codebase usage
    - Check EVERY workflow against CI/scripts
    - Provide specific line numbers for all issues
    - Give concrete before/after examples
    - Calculate quantitative metrics

    **DON'T:**
    - Skip verification checks because "it probably works"
    - Report style preferences as issues
    - Suggest changes without showing specific examples
    - Ignore small inaccuracies (they compound)
    - Assume documentation is correct without checking

    ## Example Issue Format

    ```
    #### Critical

    1. **Broken Command Path - Accuracy Issue**
       - Category: Accuracy Against Codebase
       - Impact: AI will try to run non-existent binary, fail immediately
       - Location: go/CLAUDE.md:32
       - Current:
         ```markdown
         - `./go/bin/model -auto-migrate` - Run database migrations
         ```
       - Verification: Checked filesystem, binary is at `go/bin/model` not `./go/bin/model` (working directory matters)
       - Fix:
         ```markdown
         ### Database Commands (from repository root)
         - `go/bin/model -auto-migrate` - Run database migrations

         ### Database Commands (from go/ directory)
         - `./bin/model -auto-migrate` - Run database migrations
         ```
       - Estimated Impact: Eliminates immediate failure, saves 1-2 minutes per attempt

    2. **Contradictory Test Instructions - Clarity Issue**
       - Category: Contradictory Instructions
       - Impact: AI receives conflicting guidance on how to run tests
       - Locations:
         * go/CLAUDE.md:7 - "**NEVER run `go test` commands directly**"
         * go/CLAUDE.md:37 - "- `go test ./...` - Run all tests"
       - Verification: README and CI both use golang-test-runner agent, not direct go test
       - Fix: Remove lines 37-40 (Testing subsection under Commands), keep only CRITICAL section
       - Estimated Impact: Eliminates confusion, AI will use correct test workflow

    3. **Outdated Scraper List - Accuracy Issue**
       - Category: Incomplete Feature Lists
       - Impact: AI has incomplete picture of available scrapers
       - Location: go/CLAUDE.md:198
       - Current: Lists 8 scrapers
       - Verification: Found 12 scrapers in go/import/:
         * Listed: active, parkrun, rr, spartan, swimrun, tri, ultrasignup, worldsmarathons
         * Missing: raceroster, masters-swimming-canada, zwift, ics
       - Fix:
         ```markdown
         Multiple event platform scrapers in `go/import/` including Active.com,
         Parkrun, RaceRoster, UltraSignup, Zwift, and more. See directory for full list.
         ```
       - Estimated Impact: Prevents AI from missing available scrapers
    ```
```

### 3. After Audit

1. **Fix Critical issues** - Broken commands, contradictions, dead links
2. **Address Important issues** - Organization, verbosity, clarity
3. **Consider Minor issues** - Polish and optimization
4. **Re-audit after changes** - Verify fixes didn't introduce new issues

## Related Commands

- **/codebase-health** - Overall codebase health check
- **/request-review** - General code review
