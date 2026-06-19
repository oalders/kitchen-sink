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
| **/audit-claude-md** | Audit CLAUDE.md files for token efficiency, clarity, and accuracy against actual codebase |

### Skills

| Skill | Description |
|-------|-------------|
| **code-review-flow** | Streamlined code review workflow that avoids permission prompts |
| **over-engineer-no-more** | Prevents your robot from building a spaceship when you asked for a bicycle |
| **perl-review** | Flags Perl code that strays from your project standards — quoting, core-module use, URL building, test hygiene — reading a living rules doc you edit freely |
| **tune-dependabot-config** | Groups minor/patch Dependabot updates per ecosystem and adds a 7-day cooldown |
| **tune-perl-ci** | Six idempotent transforms to modernize Dist::Zilla-style Perl GitHub Actions CI |
| **tune-precious** | Migrates a Perl repo from `Code::TidyAll` to `precious` (or sets up `precious` from scratch) — config, `.perltidyrc`, `dist.ini`, CI lint job |
| **working-with-dist-zilla** | Stops your robot from committing 100 lines of regenerated `META.json` and other `dzil` faceplants |

### Hooks

| Hook | Description |
|------|-------------|
| **suggest-review-after-commit** | Smart PostToolUse hook that analyzes committed files and suggests relevant review commands (`/frontend-review`, `/playwright-review`, `/security-review`, or `/request-review`) based on file types and patterns |

## Commands Overview

### /fix-gh-issue

Automates the workflow for fixing GitHub issues:
1. Gets issue number from argument or branch name (`fix-978` -> `978`)
2. Fetches issue details with `gh` and applies "in progress" label
3. Assesses complexity (trivial vs non-trivial)
4. Suggests brainstorming for complex issues
5. Implements fix (direct or via subagent-driven-development)
6. Runs specialized code review (conditional: skips if subagent-driven-development used)
   - Frontend changes → `/frontend-review`
   - Security changes → `/security-review`
   - Playwright tests → `/playwright-review`
   - Other changes → `/request-review`
7. Verifies with `verification-before-completion`
8. Creates draft PR that closes the issue

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

### /audit-claude-md

Comprehensive CLAUDE.md audit for quality and accuracy:
- Token efficiency (duplication between files, verbose sections, defensive explanations)
- Clarity issues (contradictory instructions, vague guidance, ambiguous commands)
- Organization problems (multiple file chaos, hard to scan, scattered information)
- Accuracy against codebase (outdated commands, dead links, wrong env vars, broken examples)
- AI-specific anti-patterns (nested conditionals, ambiguous pronouns, negative-only instructions)
- Workflow verification (compare docs against CI/scripts/Makefiles)
- Systematic verification (REQUIRED checks for command paths, file references, tool availability)
- Version-specific instruction checking (detect obsolete version references)
- Generates quality score (0-100) with category breakdown
- Estimates token savings (e.g., 17% reduction from deduplication)
- Prioritized recommendations with before/after examples
- Spawns `general-purpose` subagent with comprehensive 6-category checklist

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

### tune-dependabot-config

Groups Dependabot minor/patch updates per ecosystem (majors stay individual) and adds a 7-day cooldown so churning releases settle before a PR opens:
- Idempotent edits to `.github/dependabot.yml`
- Preserves user-customized schedules, labels, reviewers
- Adds `groups:` block with `update-types: [minor, patch]` per ecosystem
- Sets `cooldown.default-days: 7` to absorb release-day churn

### tune-perl-ci

Six idempotent transforms applied to Dist::Zilla-style Perl GitHub Actions workflows under `.github/workflows/`:
- `fail-fast: false` on every matrix job
- Extends Linux + macOS matrices through Perl 5.42
- Bumps build + coverage jobs to `perldocker/perl-tester:5.42`
- Restricts the `push:` trigger to the default branch
- Adds a workflow-level `concurrency:` cancel-in-progress block
- Pins App::cpm for Perls ≤ 5.22 (via conditional `version:` expression on `install-with-cpm@v2`)
- Each transform lands as its own commit; re-running is a no-op

### tune-precious

Lands [`precious`](https://github.com/houseabsolute/precious) as the canonical tidy/lint driver for a Perl repo via five idempotent transforms:
- Generates (or refreshes) `precious.toml` with `perltidy`, `perlvars`, `omegasort-gitignore`, `omegasort-stopwords`, and optionally `perlcritic`
- Consolidates the perltidy profile to the hidden `.perltidyrc` and strips `-b`
- Deletes `Code::TidyAll` config (`.tidyallrc`, `tidyall.ini`, `.tidyall.d/` ignore line)
- Edits `dist.ini` to drop `Test::TidyAll` and its prereqs via `PluginRemover` + `[RemovePrereqs]`
- Adds a `.github/workflows/lint.yml` job running `precious lint --all`

Handles three modes: migrate (tidyall present), greenfield (no precious yet), tune (precious already configured). Each transform commits separately; re-running on a tuned repo is a no-op.

### working-with-dist-zilla

Captures the non-obvious patterns that trip up first-pass `Dist::Zilla` work:
- Decide PluginRemover vs `[RemovePrereqs]` (and the `-remove` vs `remove` syntax gotcha)
- Revert build artifacts (`META.json`, `Makefile.PL`, `README.md`) in non-release PRs to avoid diff noise
- Phase-scoped re-adds via `[Prereqs / DevelopRequires]`
- Fix `Git::Contributors` warnings with `.mailmap`
- Verify with `dzil test --release --author`
- Sandbox notes for `~/.dzil` symlink targets and network-bound author tests

Triggers when the repo contains a `dist.ini` file or the user mentions `dzil`, `Dist::Zilla`, or `@Author::*` bundles.

## Hooks Overview

### suggest-review-after-commit

Automatically suggests the most relevant review command(s) after you commit changes, with **interactive multi-select** to choose one or more reviews to run immediately:

**Frontend Review (`/frontend-review`)**
- Triggered by: `.tsx`, `.jsx`, `.vue`, `.css`, `.scss`, `.html`
- Directories: `components/`, `pages/`, `styles/`
- Files: `tailwind.config.*`, `globals.css`

**Playwright Review (`/playwright-review`)**
- Triggered by: `.spec.ts`, `.spec.js`, `.test.ts`
- Directories: `e2e/`, `tests/`, `playwright/`
- Files: `playwright.config.*`, `*.e2e.*`

**Security Review (`/security-review`)**
- Triggered by: Files with `auth`, `login`, `password`, `token`, `session`, `api/` in path
- Files: `.env.example`, authentication modules, API endpoints

**Generic Review (`/request-review`)**
- Always offered as a fallback option
- Recommended for general-purpose code changes

**Example:**
```
I notice you just committed 3 file(s):

🎨 Frontend: Header.tsx, globals.css
🎭 Playwright: header.spec.ts

Which review(s) would you like to run?
□ Frontend Review - Images, accessibility, responsive design, CSS patterns
□ Playwright Review - Accessibility, UI issues, performance optimization
□ Generic Review - Comprehensive code review of all changes
```

Select multiple reviews with checkboxes, and they'll run sequentially with a combined summary at the end.

## License

MIT

## Image Credit

"[Mog & the kitchen sink adventure #01](https://www.flickr.com/photos/87285907@N00/3009300486)" by [ju5ti](https://www.flickr.com/photos/87285907@N00) is licensed under [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/?ref=openverse).
