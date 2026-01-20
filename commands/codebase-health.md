---
description: Codebase health check for AI optimization - token efficiency, discoverability, and code quality
---

# Codebase Health Check

## Overview

Automated analysis of codebase organization optimized for AI consumption. Checks for: (1) Dead code and token waste, (2) Discoverability issues, (3) Code duplication, (4) Dependency health.

## When to Use

Run periodically (monthly or before major releases) to ensure codebase remains AI-friendly.

## Steps

### 1. Determine Scope

Check conversation context first. If not specified:
```bash
# Analyze entire codebase
pwd

# Or specific subdirectory
ls -d specific/path
```

### 2. Invoke Codebase Health Analyzer

```
Task(general-purpose):
  description: Analyze codebase health for AI optimization
  model: "sonnet"

  prompt:
    # Codebase Health Analyzer

    You are a codebase health expert analyzing code organization for AI consumption.

    **Your task:**
    1. Systematically check for AI optimization issues
    2. Apply comprehensive checklist
    3. Provide quantitative metrics
    4. Categorize issues by severity
    5. Generate actionable recommendations

    ## What to Analyze

    Codebase: [PATH]

    Focus areas: Token efficiency, discoverability, code quality, dependency health

    ## Comprehensive Checklist

    **CRITICAL: Check EVERY category systematically with specific examples.**

    ### 1. Dead Code Analysis (Token Waste)

    **Unused Imports:**
    - Grep for import statements, cross-reference with actual usage
    - Example tools: `goimports -l`, `eslint --rule 'no-unused-vars'`
    - Check every file type: Go, JavaScript, Python, etc.

    **Unused Functions:**
    - Find unexported/private functions with no callers
    - Go: `grep -r "^func [a-z]" | check for references`
    - JavaScript: Functions defined but never called
    - Report: file:line with function name and size

    **Orphaned Files:**
    - Files that nothing imports/requires
    - Build dependency graph, find disconnected nodes
    - Exclude: _test files, main packages, scripts

    **Commented-Out Code:**
    - Large blocks of commented code (>10 lines)
    - `git log` can recover - no need to keep in codebase
    - Report: file:line with size of block

    **Dead Branches:**
    - `if false`, unreachable code after return
    - Conditions that can never be true

    **Metrics to Report:**
    ```
    Dead Code Summary:
    - Unused imports: X files, Y import statements
    - Unused functions: X functions, ~Y total lines
    - Orphaned files: X files
    - Commented code blocks: X blocks, ~Y lines
    - Estimated token savings: ~Z tokens
    ```

    ### 2. File Size & Organization (Token Efficiency)

    **Large Files:**
    - Error: >1000 lines (should be split)
    - Warning: 500-1000 lines (consider splitting)
    - Report top 10 largest files with line counts

    **Monolithic Files:**
    - Single file containing unrelated functionality
    - Example: web.go with 50+ handler functions
    - Check if file contains multiple domain concepts

    **Deep Nesting:**
    - Error: >5 levels deep
    - Warning: 4-5 levels deep
    - Report deepest paths with depth count
    - Example: `src/app/features/user/components/profile/details/forms/edit/fields/name.tsx` (10 levels)

    **Vendor/Dependencies:**
    - Check if vendor/ or node_modules/ is tracked in git
    - Report size if present
    - Recommend .gitignore and AI ignore patterns

    **Metrics to Report:**
    ```
    File Organization:
    - Files >1000 lines: X files (list top 5)
    - Files 500-1000 lines: Y files
    - Deepest path: X levels (path)
    - Vendor directory size: X MB (if tracked)
    ```

    ### 3. Discoverability Issues (AI Can't Find Things)

    **Generic Naming:**
    - Flag: utils, helpers, common, misc, handler, service (without context)
    - Flag: data, types, constants (too broad)
    - Example: ❌ `utils.go` → ✅ `date-utils.go`
    - Report: file count and specific examples

    **Missing Documentation:**
    - Package-level: directories without README.md
    - File-level: files without top-comment explaining purpose
    - Check major packages (>5 files in directory)
    - Report: directories needing READMEs, files needing doc comments

    **Unclear Package Structure:**
    - Directories with >20 files but no README
    - Directories with unclear purpose (mixed concerns)
    - Report: packages needing structure documentation

    **Hidden Functionality:**
    - Important logic in >500-line functions
    - Functions that should be extracted and named
    - Report: functions >100 lines that could be split

    **Metrics to Report:**
    ```
    Discoverability:
    - Generic filenames: X files
    - Packages without README: X directories
    - Files without documentation: X files
    - Large functions (>100 lines): X functions
    ```

    ### 4. Code Duplication (AI Confusion)

    **Template/View Duplication:**
    - Nearly identical templates differing only in URLs
    - Example: pagination-*.gohtml files 95% identical
    - Use diff or similarity analysis

    **Function-Level Duplication:**
    - Similar function signatures across files
    - Copy-pasted logic with minor variations
    - Example: `validateUserInput` in 3 different packages
    - Report: function pairs with >80% similarity

    **Pattern Inconsistency:**
    - Same operation implemented different ways
    - Example: Some handlers use middleware for auth, others inline
    - Example: Error handling varies (some use helper, some don't)
    - Report: inconsistent patterns with examples

    **Metrics to Report:**
    ```
    Code Duplication:
    - Duplicate templates: X sets of Y files each
    - Duplicate functions: X function pairs
    - Inconsistent patterns: X categories
    - Estimated duplication: ~Y lines
    ```

    ### 5. Dependency Health (Import Graph Analysis)

    **Circular Dependencies:**
    - Package A imports B, B imports A
    - Prevents clean mental model
    - **REQUIRED**: Run `go mod graph | grep -E "^(.+) \1$"` or equivalent
    - JavaScript: Use `npx madge --circular src/`
    - Report: cycles with package names or "0 circular dependencies found"

    **Unused Exports:**
    - Exported functions/types never imported elsewhere
    - Should be unexported (private)
    - **REQUIRED**: Build import graph, check each exported symbol
    - Go: Grep for `^func [A-Z]`, `^type [A-Z]`, cross-reference imports
    - Report: count and examples or "all exports used"

    **Orphaned Modules:**
    - Entire packages/modules that nothing imports
    - May be leftover from refactoring
    - **REQUIRED**: Build dependency tree, find disconnected packages
    - Exclude: main packages, _test.go files, cmd/* binaries
    - Report: package names or "no orphaned packages"

    **Deep Dependency Chains:**
    - A → B → C → D → E (too deep)
    - Warning: >4 levels deep
    - Makes changes risky (cascading failures)

    **Metrics to Report:**
    ```
    Dependency Health:
    - Circular dependencies: X cycles
    - Unused exports: Y symbols
    - Orphaned packages: Z packages
    - Deepest dependency chain: N levels
    ```

    ### 6. Naming Convention Consistency

    **Mixed Conventions:**
    - camelCase and snake_case in same directory
    - PascalCase and lowercase mixed
    - Inconsistent file naming (admin-events.go vs admin_users.go)

    **Check by Language:**
    - Go: Should be camelCase for vars, PascalCase for exports
    - JavaScript: camelCase for files and vars
    - Python: snake_case for everything
    - Files: kebab-case or snake_case consistently

    **Metrics to Report:**
    ```
    Naming Conventions:
    - Files with mixed case: X files
    - Directories with inconsistent naming: Y dirs
    - Top violators: (list files)
    ```

    ### 7. Configuration & Documentation

    **Multiple CLAUDE.md Files:**
    - Should be single source of truth
    - Check for contradictions between files
    - Report: locations and recommendation

    **CLAUDE.md Completeness:**
    - Does it cover: testing, structure, patterns?
    - Are worktrees documented?
    - Are ignore patterns specified?

    **Architecture Documentation:**
    - Is there docs/ARCHITECTURE.md or equivalent?
    - High-level system overview for AI context

    **Metrics to Report:**
    ```
    Documentation:
    - CLAUDE.md files: X locations
    - Missing sections: Y items
    - Architecture docs: Present/Missing
    ```

    ## Output Format

    ### Executive Summary

    **Overall Health Score:** X/100

    **Top 3 Issues:**
    1. [Issue] - [Impact] - [Files affected]
    2. [Issue] - [Impact] - [Files affected]
    3. [Issue] - [Impact] - [Files affected]

    **Estimated Token Savings:** ~X tokens per typical operation if recommendations applied

    ### Critical Issues (Must Fix)

    #### 1. [Issue Name] - [Category]
    - **Impact**: How this affects AI and humans
    - **Locations**: file:line references (top 5 examples)
    - **Count**: X occurrences, Y lines affected
    - **Fix**: Specific actionable steps
    - **Estimated Savings**: ~X tokens

    #### 2. [Next critical issue...]

    ### Important Issues (Should Fix Soon)

    #### 1. [Issue Name] - [Category]
    - **Impact**: [Description]
    - **Locations**: [Examples]
    - **Fix**: [Steps]

    ### Minor Issues (Nice to Have)

    #### 1. [Issue Name] - [Category]
    - **Impact**: [Description]
    - **Fix**: [Steps]

    ### Quantitative Metrics

    ```
    Codebase Statistics:
    ├─ Total Files: X
    ├─ Total Lines: Y
    ├─ Average File Size: Z lines
    ├─ Largest File: A lines (path)
    ├─ Deepest Nesting: B levels (path)
    │
    ├─ Dead Code:
    │  ├─ Unused imports: X
    │  ├─ Unused functions: Y (~Z lines)
    │  └─ Orphaned files: N
    │
    ├─ Duplication:
    │  ├─ Duplicate templates: X sets
    │  ├─ Duplicate functions: Y pairs
    │  └─ Estimated duplicate lines: ~Z
    │
    ├─ Discoverability:
    │  ├─ Generic names: X files
    │  ├─ Missing READMEs: Y packages
    │  └─ Undocumented files: Z
    │
    └─ Dependencies:
       ├─ Circular deps: X cycles
       ├─ Unused exports: Y
       └─ Orphaned packages: Z
    ```

    ### Recommendations by Priority

    **Immediate Actions** (High ROI, Low Effort):
    1. Remove unused imports (automated)
    2. Delete commented-out code blocks
    3. Add README to top 3 packages
    4. Consolidate duplicate templates

    **Short Term** (This Sprint):
    5. Split monolithic files (>1000 lines)
    6. Fix circular dependencies
    7. Consolidate CLAUDE.md files
    8. Document common patterns

    **Medium Term** (Next Month):
    9. Refactor deep directory nesting
    10. Standardize naming conventions
    11. Extract hidden functionality
    12. Create architecture docs

    **Long Term** (Nice to Have):
    13. Remove orphaned packages
    14. Flatten dependency chains
    15. Automate health checks in CI

    ### Health Score Breakdown

    **Token Efficiency:** X/25
    - Dead code cleanup potential: Y points
    - File size optimization: Z points

    **Discoverability:** X/25
    - Naming quality: Y points
    - Documentation completeness: Z points

    **Code Quality:** X/25
    - Duplication level: Y points
    - Consistency: Z points

    **Dependency Health:** X/25
    - Import graph cleanliness: Y points
    - Module organization: Z points

    ## Critical Rules for Analyzer

    **DO:**
    - Check EVERY category systematically
    - Provide specific file:line examples
    - Give quantitative metrics (counts, sizes, percentages)
    - Estimate token savings for each recommendation
    - Prioritize by impact × effort

    **DON'T:**
    - Skip categories because "codebase looks clean"
    - Give vague advice ("improve organization")
    - Ignore small issues (they compound)
    - Recommend changes without specific examples
    - Assume patterns are consistent without checking

    ## Example Issue Format

    ```
    #### Critical

    1. **Dead Code - 2,847 Lines of Unused Functions**
       - Category: Token Waste
       - Impact: AI loads ~11,000 unused tokens on typical operations
       - Locations:
         * go/web/helpers.go:234 - formatDate() (67 lines, no callers)
         * go/model/legacy.go:89 - convertOldFormat() (143 lines, no callers)
         * [3 more examples]
       - Count: 23 unused functions across 8 files
       - Fix:
         ```bash
         # Find unused functions
         grep -rn "^func [a-z]" . | # find unexported functions
         # Cross-reference with grep calls
         # Delete functions with 0 references
         ```
       - Estimated Savings: ~11,000 tokens per typical session

    2. **Duplicate Pagination Templates - 95% Identical**
       - Category: Code Duplication & Token Waste
       - Impact: AI may edit one copy, miss others; wastes ~1,200 tokens
       - Locations:
         * go/templates/include-pagination.gohtml (75 lines)
         * go/templates/include-pagination-nearby.gohtml (76 lines)
         * go/templates/include-pagination-organizations.gohtml (76 lines)
       - Difference: Only URL building logic differs (5 lines)
       - Fix: Create single parameterized template:
         ```go
         {{define "pagination"}}
           {{/* Accept URL builder function as parameter */}}
           {{$urlFunc := .URLBuilder}}
           {{range .Pages}}
             <a href="{{call $urlFunc .}}">{{.}}</a>
           {{end}}
         {{end}}
         ```
       - Estimated Savings: ~900 tokens per pagination edit
    ```
```

### 3. After Analysis

1. **Review report** - Understand categories and impact
2. **Prioritize fixes** - Start with Critical, move to Important
3. **Automate checks** - Add to CI/linting for prevention
4. **Re-run periodically** - Monthly health checks

## Related Commands

- **/request-review** - General code review
- **/security-review** - Security-focused review
- **/frontend-review** - Frontend code review
