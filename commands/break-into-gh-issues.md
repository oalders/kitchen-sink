---
description: Break down a feature into small GitHub issues with a tracking issue
---

Break down the current feature or work into small, manageable GitHub issues.

**Label Management**: Before using any label that may not exist, create it first using `gh label create "<label-name>" --description "<description>" --color "<hex-color>"` (the command succeeds either way: creating the label if it doesn't exist, or printing a message if it does).

## Decision Criteria

Choose the appropriate approach based on the scope of work:

**Use single-issue approach when**:
- Estimated changes are <= 400 lines (excluding dependencies, vendor dirs, docs)
- Work can be completed as one logical unit
- Changes are tightly coupled and can't be meaningfully separated
- No opportunity for parallel work

**Use multi-issue approach when**:
- Estimated changes are > 400 lines (excluding dependencies, vendor dirs, docs)
- Work can be split into independent components
- Multiple developers could work in parallel
- Clear boundaries exist between different parts of the work

## Estimating Line Counts

When estimating line counts for issues:
- **Exclude**: `node_modules`, vendor directories, docs
- **Include**: All application code, tests, configuration files
- **Quick estimation methods**:
  - Count files affected x average lines per file
  - Reference similar past issues as benchmarks
  - Use `git diff --stat` on comparable changes

**Example estimation**:
```bash
# For a completed feature, check actual line count
git diff --stat <base-branch> <feature-branch> -- . ':(exclude)node_modules' ':(exclude)vendor' ':(exclude)docs'

# Output might show:
# 5 files changed, 287 insertions(+), 45 deletions(-)
# Net change: ~242 lines (fits in single issue)
```

## Common Sections (All Issues)

Every issue should include:

### Overview and Goals
Brief description of the feature and what it aims to accomplish

### Design Details
Comprehensive design covering:
- Architecture and components
- Implementation approach
- File structure and changes
- Success criteria

## Single-Issue Workflow

When work fits within a single issue:

1. **Create Issue**: Use `gh issue create` with appropriate labels and body

2. **Include Implementation Plan**:
   - Clear scope (what will be changed)
   - Files affected
   - Checklist of changes to make
   - Estimated line count (excluding dependencies, vendor, docs)
   - Test requirements

## Multi-Issue Workflow

When work requires multiple issues:

### Step 1: Create Umbrella Issue

Create the umbrella issue with:

```bash
gh issue create --label "Umbrella Issue" --title "Feature: <name>" --body "<body>"
```

Include:
- Overview and Goals (see Common Sections)
- Design Details (see Common Sections)
- **Implementation Plan**: Breakdown of all tasks including:
  - List of all sub-issues with estimated line counts (keep under 400 lines per issue)
  - Dependencies between issues
  - Test requirements
  - Implementation phases/sequencing
- **Progress Tracking**: Leave blank initially - will be populated in Step 4

### Step 2: Create Sub-Issues

For each task, create issues with a link to the umbrella:

```bash
gh issue create --label "enhancement" --body "**Part of**: #<umbrella-issue-number>

<issue body>"
```

Each sub-issue must include:
- Link to umbrella issue: `**Part of**: #X` (at the top, before other content)
- Clear scope (what will be changed)
- Files affected
- Checklist of changes to make
- Estimated line count (excluding dependencies, vendor, docs)
- Dependencies (reference other issue numbers)
- Test requirements

### Step 3: Size Sub-Issues Appropriately

Keep each sub-issue under 400 lines of changes (excluding dependencies, vendor, docs):
- If a task would be larger, find logical ways to break it into smaller pieces
- Split by file, component, or functionality
- Ensure each issue can be completed and reviewed independently

### Step 4: Link and Track

After creating all issues:
- Update the umbrella issue description with links to all sub-issues
- Add checklist: `- [ ] #<issue-number> - <title>`
- Pin the umbrella issue using `gh issue pin <issue-number>`
- This creates a clear hierarchy and progress tracking

## Guidelines

- **DRY**: Look for opportunities to refactor shared code
- **KISS**: Reuse existing patterns, don't over-engineer
- **YAGNI**: Focus on essential features only
- **Independent**: Each issue should be independently testable and reviewable
- **Parallel**: Issues can be worked on in parallel where dependencies allow
- **Clear criteria**: Include clear acceptance criteria for each issue
- **Self-contained**: Write each issue assuming the implementer has no context from this conversation. Include all necessary background, rationale, and implementation details within the issue itself
