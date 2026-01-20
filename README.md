# kitchen-sink

*Everything but the kitchen sink*

![Mog & the kitchen sink adventure](kitchen-sink.jpg)

A grab bag of skills to automate the boring parts out of your hair and into your robot.

## Requirements

**GitHub CLI:** Several skills and commands use [`gh`](https://cli.github.com/) to interact with GitHub issues and pull requests. Install it and authenticate with `gh auth login`.

**Superpowers plugin:** Most skills and commands rely on [obra/superpowers](https://github.com/obra/superpowers) for workflows like brainstorming, verification, and subagent-driven development. Install it first:

```bash
claude plugin marketplace add obra/superpowers
```

## Installation

Add from the Claude Code plugin marketplace:

```bash
claude plugin marketplace add oalders/kitchen-sink &&
  claude plugin install kitchen-sink
```

## Contents

### Commands

| Command | Description |
|---------|-------------|
| **/fix-gh-issue** | Point your robot at a GitHub issue and let it start beeping and booping |
| **/fix-linter-warnings** | Linter busywork in bite-sized chunks—your robot's idea of a good time, not yours |
| **/git-rebase** | Rebase without the cruel and unusual punishment of solving your own merge conflicts |
| **/break-into-gh-issues** | Maybe split big issues into smaller ones—so you get a code review and not an intervention |
| **/address-gh-review** | A robot that does the urgent repairs now and books appointments for the rest |
| **/request-review** | Get code review feedback without permission prompts stalling the workflow |
| **/frontend-review** | Frontend expert review catching accessibility gaps, responsive design issues, and CSS anti-patterns |
| **/playwright-review** | Playwright test review enforcing ARIA labels, detecting UI layout issues, and optimizing performance |
| **/security-review** | OWASP-based security review catching session fixation, PII logging, and timing attacks |
| **/codebase-health** | Systematic health check optimizing codebase for AI consumption—dead code, token waste, and discoverability |

### Skills

| Skill | Description |
|-------|-------------|
| **code-review-flow** | Streamlined code review workflow that avoids permission prompts |
| **over-engineer-no-more** | Prevents your robot from building a spaceship when you asked for a bicycle |

## Commands Overview

### /fix-gh-issue

Automates the workflow for fixing GitHub issues:
1. Gets issue number from argument or branch name (`fix-978` -> `978`)
2. Fetches issue details with `gh`
3. Assesses complexity (trivial vs non-trivial)
4. Suggests brainstorming for complex issues
5. Guides through verification and PR creation

### /fix-linter-warnings

Batch approach to linter cleanup:
- Fix 25 issues per iteration
- Prioritize quick wins (formatting, constants)
- Use suppression directives when fixes would degrade code
- Always include justification comments

### /git-rebase

Rebases the current branch onto origin/main:
- Fetches latest changes and pulls with `--rebase`
- Reads and resolves merge conflicts
- Uses `--force-with-lease` for safe pushing (never `--force`)

### /break-into-gh-issues

Breaks down work into manageable GitHub issues:
- Single issue for <= 400 lines of changes
- Multi-issue with umbrella tracking for larger work
- Creates labels if they don't exist
- Links sub-issues back to umbrella with progress checklist

### /address-gh-review

Addresses PR code review feedback:
- Fetches comments from the current branch's PR
- Evaluates each suggestion critically (doesn't blindly implement)
- Fixes immediate issues with atomic commits
- Creates GitHub issues for deferred items
- Runs tests and pushes when done

### /request-review

Request code review during development (before creating PR):
- Gets git SHAs from conversation context (no permission prompts)
- Fetches issue details for fix-* branches
- Invokes `superpowers:code-reviewer` with structured template
- Returns categorized feedback (Critical/Important/Minor)
- Allows unattended execution - can leave window while review runs

### /frontend-review

Frontend-focused code review for HTML/CSS/image changes:
- Systematic image optimization and accessibility checks
- ARIA strategy analysis (decorative vs informative)
- Responsive design verification across viewports (320px, 768px, 1920px)
- CSS best practices (custom properties, relative units, performance)
- Visual regression checklist for manual testing
- SVG optimization and preload hints
- Spawns `superpowers:code-reviewer` with frontend-specific checklist

### /playwright-review

Specialized review for Playwright E2E tests:
- Enforces ARIA label verification in tests (aria-invalid, aria-describedby, aria-live)
- Identifies UI/layout issues (buttons bumping footer, viewport overflow)
- Detects 7 performance anti-patterns (waitForFunction, sequential fills, networkidle waits)
- Suggests specific optimizations with estimated time savings
- Checks accessibility test coverage (keyboard navigation, focus management)
- Provides performance improvement summary table
- Spawns `superpowers:code-reviewer` with Playwright-specific checklist

### /security-review

OWASP-based systematic security review:
- Authentication & session management (session fixation, regeneration)
- Authorization & access control (vertical/horizontal privilege escalation)
- Input validation & injection (SQL, XSS, command injection)
- Sensitive data exposure (PII logging, cleartext transmission)
- Security misconfiguration (CSRF, CORS, security headers)
- Business logic flaws (race conditions, timing attacks)
- Uses Opus model for comprehensive security analysis
- Spawns `superpowers:code-reviewer` with OWASP Top 10 checklist

### /codebase-health

Systematic health check optimizing codebase for AI consumption:
- Dead code analysis (unused imports, orphaned files, commented blocks)
- File organization (>1000 line files, deep nesting, vendor directory tracking)
- Discoverability issues (generic naming, missing READMEs, hidden functionality)
- Code duplication detection (template/function similarity, pattern inconsistency)
- Dependency health (circular dependencies, unused exports, orphaned modules)
- Naming convention consistency (mixed case detection across languages)
- Generates health score (0-100) with category breakdown
- Estimates token savings potential (e.g., 148K tokens from vendor removal)
- Prioritized recommendations (Critical/Important/Minor with time estimates)
- Spawns `general-purpose` subagent with comprehensive 7-category checklist

## Skills Overview

### code-review-flow

Wrapper around `superpowers:requesting-code-review` that eliminates permission prompts during code reviews:
- Gets git SHAs from conversation context or separate git commands (not compound commands)
- Invokes `superpowers:code-reviewer` subagent with proper template
- Allows code reviews to run unattended without blocking on permission prompts

**Benefits:**
- No interruptions during code review workflow
- Can leave the window while review runs
- Uses information already in context when available

### over-engineer-no-more

Prevents over-engineering by evaluating whether a task needs heavyweight processes:
- Checks indicators: adding constants? < 100 lines? < 3 files?
- Announces decision with reasoning
- Routes to direct implementation or subagent workflow

## License

MIT

## Image Credit

"[Mog & the kitchen sink adventure #01](https://www.flickr.com/photos/87285907@N00/3009300486)" by [ju5ti](https://www.flickr.com/photos/87285907@N00) is licensed under [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/?ref=openverse).
