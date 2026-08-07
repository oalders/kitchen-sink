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

**Code review**

| Command | Description |
|---------|-------------|
| **/code-review-intense-flow** | Heavyweight fan-out that dispatches every applicable specialist reviewer (security, frontend, seo, geo, playwright, design-handoff) in parallel and aggregates the findings |
| **/design-handoff-review** | Reviews a design-handoff implementation for character-level text drift and orphaned input bindings against the design source |
| **/frontend-review** | Frontend expert review catching accessibility gaps, responsive design issues, and CSS anti-patterns |
| **/geo-review** | Generative Engine Optimization review—two modes: per-PR extraction checks (diff) and cross-page entity consistency (site) for LLM-citation visibility |
| **/playwright-review** | Playwright test review enforcing ARIA labels, detecting UI layout issues, and optimizing performance |
| **/request-review** | Get code review feedback without permission prompts stalling the workflow |
| **/security-review** | OWASP-based security review catching session fixation, PII logging, and timing attacks |
| **/seo-review** | SEO review for meta tags, structured data, Open Graph, headings, and crawlability |

**GitHub issues & PRs**

| Command | Description |
|---------|-------------|
| **/address-gh-review** | A robot that does the urgent repairs now and books appointments for the rest |
| **/break-into-gh-issues** | Maybe split big issues into smaller ones—so you get a code review and not an intervention |
| **/draft-pr** | Creates a draft PR that closes the GitHub issue inferred from your branch name |
| **/fix-gh-issue** | Point your robot at a GitHub issue and let it start beeping and booping |
| **/triage-backlog** | Grooms open GitHub issues—finds completed work, updates task lists, and suggests labels, one issue at a time |

**Repo & CI maintenance**

| Command | Description |
|---------|-------------|
| **/audit-claude-md** | Audit CLAUDE.md files for token efficiency, clarity, and accuracy against actual codebase |
| **/codebase-health** | Systematic health check optimizing codebase for AI consumption—dead code, token waste, and discoverability |
| **/fix-linter-warnings** | Linter busywork in bite-sized chunks—your robot's idea of a good time, not yours |
| **/git-rebase** | Rebase without the cruel and unusual punishment of solving your own merge conflicts |
| **/poll-ci** | Polls the current branch's CI run and reports pass/fail/in-progress (generic `gh` fallback for `/monitor-ci`) |

### Skills

**General**

| Skill | Description |
|-------|-------------|
| **adversarial-review** | Two subagents compete under a scoped incentive to find real, reproducible defects—enforces scope discipline so findings count doesn't inflate across rounds |
| **code-review-flow** | Streamlined code review workflow that avoids permission prompts |
| **implement-design-handoff** | Wires a design-system / component-export handoff into an app's real templates and CSS faithfully, forcing a property-by-property visual-parity check and protecting untouched surfaces |
| **over-engineer-no-more** | Prevents your robot from building a spaceship when you asked for a bicycle |

**Perl & repo tuning**

| Skill | Description |
|-------|-------------|
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

### Code review

#### /code-review-intense-flow

Heavyweight fan-out orchestrator—dispatches every applicable specialist reviewer in parallel for a single diff, then aggregates:
- General-purpose reviewer always runs; `/security-review` runs by default unless the diff is doc-only
- Routes to `/frontend-review`, `/seo-review`, `/geo-review`, `/design-handoff-review`, and `/playwright-review` by diff content
- New-route and new-interaction detection triggers a Playwright e2e-coverage check even when the diff reuses an existing route
- Runs all reviewers concurrently (single message, multiple `Task` calls)
- Consolidates findings by severity, tags each with the specialist that surfaced it, and retains full per-reviewer reports
- The lightweight counterpart is `/code-review-flow` (general reviewer only)

#### /design-handoff-review

Design-handoff fidelity review comparing an implementation against its design source (the component/card export, not README prose):
- Character-level text fidelity (smart vs straight quotes, decorative glyphs, ellipsis, casing, whitespace)—a near-match is a finding, not a pass
- Orphaned input bindings (every collected input must render or be consumed somewhere; reports remove-end-to-end vs missing-surface)
- Standard handoff checks (reproduce the layout mechanism, keep dynamic bindings mapped, don't restyle shared partials)
- Treats handoff files and screenshots as untrusted data, never instructions
- Catches structural drift a screenshot-parity pass can't see; spawns `general-purpose`

#### /frontend-review

Frontend-focused code review for HTML/CSS/image changes:
- Systematic image optimization and accessibility checks
- ARIA strategy analysis (decorative vs informative)
- Responsive design verification across viewports (320px, 768px, 1920px)
- CSS best practices (custom properties, relative units, performance)
- Visual regression checklist for manual testing
- SVG optimization and preload hints
- Spawns `general-purpose` with frontend-specific checklist

#### /geo-review

Generative Engine Optimization review—how LLMs and answer engines (ChatGPT, Claude, Perplexity, AI Overviews) discover, extract, and cite content. Runs in two distinct modes:
- **Diff mode** (PR time): extraction-layer checks on the changeset—buried answers, atomic claims, Q&A structure, schema quality, citation-worthiness
- **Site mode** (scheduled): entity-layer checks across the whole site—cross-page claim contradictions, publisher entity graph (`@id`/`sameAs`), brand distinctiveness, rendered-output defects (crawler-UA divergence, relative `og:image`, leaked template syntax)
- Reports two independent scores: **extraction readiness** and **entity strength**
- Surfaces AI-crawler policy as a decision to confirm rather than recommending allow/block
- Asks which mode to run when it's ambiguous; spawns `general-purpose`

#### /playwright-review

Specialized review for Playwright E2E tests:
- Enforces ARIA label verification in tests (aria-invalid, aria-describedby, aria-live)
- Identifies UI/layout issues (buttons bumping footer, viewport overflow)
- Detects 7 performance anti-patterns (waitForFunction, sequential fills, networkidle waits)
- Suggests specific optimizations with estimated time savings
- Checks accessibility test coverage (keyboard navigation, focus management)
- Provides performance improvement summary table
- Spawns `general-purpose` with Playwright-specific checklist

#### /request-review

Request code review during development (before creating PR):
- Gets git SHAs from conversation context (no permission prompts)
- Fetches issue details for fix-* branches
- Invokes `general-purpose` with structured template
- Returns categorized feedback (Critical/Important/Minor)
- Allows unattended execution - can leave window while review runs

#### /security-review

OWASP-based systematic security review:
- Authentication & session management (session fixation, regeneration)
- Authorization & access control (vertical/horizontal privilege escalation)
- Input validation & injection (SQL, XSS, command injection)
- Sensitive data exposure (PII logging, cleartext transmission)
- Security misconfiguration (CSRF, CORS, security headers)
- Business logic flaws (race conditions, timing attacks)
- Uses Opus model for comprehensive security analysis
- Spawns `general-purpose` with OWASP Top 10 checklist

#### /seo-review

SEO-focused review for changes affecting search visibility and social sharing:
- Meta tags (unique titles, descriptions, robots directives)
- Open Graph and Twitter Card completeness (`og:image` dimensions, canonical `og:url`)
- Heading hierarchy (single `<h1>`, logical h1→h6 order)
- URL structure, internal linking, and canonical URLs
- Structured data (JSON-LD schema type, required properties, valid JSON)
- Crawlability (sitemap entries, `robots.txt`, server-rendered content)
- Spawns `general-purpose` with a systematic SEO checklist
- Run alongside `/geo-review` for full search + answer-engine coverage

### GitHub issues & PRs

#### /address-gh-review

Addresses PR code review feedback:
- Fetches comments from the current branch's PR
- Evaluates each suggestion critically (doesn't blindly implement)
- Fixes immediate issues with atomic commits
- Creates GitHub issues for deferred items
- Runs tests and pushes when done

#### /break-into-gh-issues

Breaks down work into manageable GitHub issues:
- Single issue for <= 400 lines of changes
- Multi-issue with umbrella tracking for larger work
- Creates labels if they don't exist
- Links sub-issues back to umbrella with progress checklist

#### /draft-pr

Creates a draft PR that closes a GitHub issue:
- Resolves the issue number from an argument or the branch name (`fix-1372` → `1372`)
- Fetches issue details, pushes the branch if needed, and opens a draft PR with a `Closes #N` body
- Treats the fetched issue title/body as untrusted data (summarizes the work; never obeys embedded directives or interpolates raw text into shell)
- Ends the PR body with the standard Claude Code attribution line

#### /fix-gh-issue

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

#### /triage-backlog

Incrementally grooms the open GitHub issue backlog, one issue at a time:
- Depth argument (`quick`/`standard`/`deep`) controls how hard it checks whether work is already done; batch size defaults to 10
- Processes oldest-first, checking linked PRs, commit history, and (deep) the codebase for completion evidence
- Proposes checking off completed task-list items and suggests 1–3 matching labels
- Always asks before editing; marks issues `triaged` so you can work in stages across sessions
- Treats issue/comment text as untrusted data, never as commands to obey

### Repo & CI maintenance

#### /audit-claude-md

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

#### /codebase-health

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

#### /fix-linter-warnings

Batch approach to linter cleanup:
- Fix 25 issues per iteration
- Prioritize quick wins (formatting, constants)
- Use suppression directives when fixes would degrade code
- Always include justification comments

#### /git-rebase

Rebases the current branch onto origin/main:
- Fetches latest changes and pulls with `--rebase`
- Reads and resolves merge conflicts
- Uses `--force-with-lease` for safe pushing (never `--force`)

#### /poll-ci

Polls the current branch's CI run and reports back when it finishes:
- Generic `gh`-based fallback for when a project-specific `/monitor-ci` isn't present
- Finds the latest run for the branch, warns if HEAD hasn't triggered a run yet
- Prefers `gh run watch --exit-status`, falling back to manual polling (~20s interval, ~30 min cap)
- Reports pass/fail/needs-attention/in-progress, surfacing failing jobs and offering `--log-failed`

## Skills Overview

### General

#### adversarial-review

Two subagents review the same work in parallel, competing under an incentive that rewards in-scope defects with working repros and penalizes nit-padding and feature-proposal drift:
- Hard-gates on a scope preamble (invariants, threat model, out-of-scope list)—aborts rather than improvising defaults
- Round-number gate warns at round 3+ that fixes create new surface, and to simplify the patch instead of adding rounds
- Pastes a verbatim reviewer brief with anti-splitting and test-falsification rules
- Mandatory triage step classifies findings in-scope / out-of-scope / wontfix before anything reaches you
- Presents actionable findings, hypotheses checked clean, rejected out-of-scope items, and tests flagged as theatre

#### code-review-flow

Wrapper around `superpowers:requesting-code-review` that eliminates permission prompts during code reviews:
- Gets git SHAs from conversation context or separate git commands (not compound commands)
- Invokes `general-purpose` subagent with proper template
- Allows code reviews to run unattended without blocking on permission prompts

**Benefits:**
- No interruptions during code review workflow
- Can leave the window while review runs
- Uses information already in context when available

#### implement-design-handoff

Wires a design-system / component-export handoff into an app's real templates and CSS, ordered so the cheap mistakes die first:
- Treats the rendered card as the source of truth for appearance (not the README); extracts exact tokens/px values rather than eyeballing
- Reads the component *source*, not just the card, and reproduces the design's layout *mechanism* instead of reinventing one
- Keeps content dynamic—maps the card's sample text/numbers/hrefs back to existing template bindings; flags design-implied data the template lacks rather than fabricating it
- Scopes shared partials safely (grep consumers, per-page flag + section-scoped CSS) so restyling one page can't leak to others
- Delegates the read-heavy investigation to a subagent that returns conclusions, not file dumps
- Enforces a visual-parity gate: read the rendered screenshots yourself, property by property, at desktop and ~390px, across every state—including the most-skipped menu-open view
- Catches char-level text drift and orphaned input bindings that pass functional tests and screenshots yet still miss the design
- Second mode: write a GitHub issue that *points* a later implementing agent at a design (by path, not by copying files)

#### over-engineer-no-more

Prevents over-engineering by evaluating whether a task needs heavyweight processes:
- Checks indicators: adding constants? < 100 lines? < 3 files?
- Announces decision with reasoning
- Routes to direct implementation or subagent workflow

### Perl & repo tuning

#### perl-review

Flag-only reviewer that applies the living standards in `STANDARDS.md` to changed Perl (`.pm`, `.pl`, `.t`) files:
- Reads whatever rules are in `STANDARDS.md` at runtime—add or change a rule with no edit to the skill
- Reviews the branch's committed changes against the base by default, or named paths when given
- `clear` rules report as violations; `judgment` rules report as suggestions the author may have a reason for
- Makes no edits and no commits—you apply the fixes; groups the report by rule with `file:line — detail` hits
- Dispatches to a `general-purpose` subagent so the token-heavy read doesn't fill the caller's context

#### tune-dependabot-config

Groups Dependabot minor/patch updates per ecosystem (majors stay individual) and adds a 7-day cooldown so churning releases settle before a PR opens:
- Idempotent edits to `.github/dependabot.yml`
- Preserves user-customized schedules, labels, reviewers
- Adds `groups:` block with `update-types: [minor, patch]` per ecosystem
- Sets `cooldown.default-days: 7` to absorb release-day churn

#### tune-perl-ci

Six idempotent transforms applied to Dist::Zilla-style Perl GitHub Actions workflows under `.github/workflows/`:
- `fail-fast: false` on every matrix job
- Extends Linux + macOS matrices through Perl 5.42
- Bumps build + coverage jobs to `perldocker/perl-tester:5.42`
- Restricts the `push:` trigger to the default branch
- Adds a workflow-level `concurrency:` cancel-in-progress block
- Pins App::cpm for Perls ≤ 5.22 (via conditional `version:` expression on `install-with-cpm@v2`)
- Each transform lands as its own commit; re-running is a no-op

#### tune-precious

Lands [`precious`](https://github.com/houseabsolute/precious) as the canonical tidy/lint driver for a Perl repo via five idempotent transforms:
- Generates (or refreshes) `precious.toml` with `perltidy`, `perlvars`, `omegasort-gitignore`, `omegasort-stopwords`, and optionally `perlcritic`
- Consolidates the perltidy profile to the hidden `.perltidyrc` and strips `-b`
- Deletes `Code::TidyAll` config (`.tidyallrc`, `tidyall.ini`, `.tidyall.d/` ignore line)
- Edits `dist.ini` to drop `Test::TidyAll` and its prereqs via `PluginRemover` + `[RemovePrereqs]`
- Adds a `.github/workflows/lint.yml` job running `precious lint` — incrementally (`--git-diff-from` the PR base) on pull requests, `--all` on every other event

Handles three modes: migrate (tidyall present), greenfield (no precious yet), tune (precious already configured). Each transform commits separately; re-running on a tuned repo is a no-op.

#### working-with-dist-zilla

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
