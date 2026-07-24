---
description: Heavy code review - fans out to all applicable specialized reviewers (security, frontend, seo, geo, playwright) based on diff content
---

# Code Review Intense Flow

## Overview

Fan-out orchestrator that dispatches **all relevant specialized reviewers** in parallel for a single diff, then aggregates the findings. This is the heavyweight counterpart to `/code-review-flow` — use it when you want every applicable lens applied (security, frontend, SEO, GEO, Playwright) instead of only the general reviewer.

The general-purpose reviewer always runs. Specialists fire only when the diff touches their domain, with one exception: `/security-review` runs by default unless the diff is documentation-only.

## When to Use

Use when:
- About to open or merge a PR with non-trivial changes
- Branch touches multiple concerns (UI + routes + content)
- Coming back to a long-running branch and want a thorough sweep
- Want the e2e-coverage check for newly added routes

Don't use when:
- Quick sanity check during local iteration — use `/code-review-flow` instead
- Diff is doc-only AND you want zero ceremony — use `/code-review-flow` or skip review

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available, run as separate Bash calls (not chained) to avoid permission prompts:
```bash
git merge-base origin/main HEAD
git rev-parse HEAD
```

### 2. Inspect the Diff

```bash
git diff --name-only BASE_SHA..HEAD_SHA
git diff --stat BASE_SHA..HEAD_SHA
```

Record the list of changed files. You'll use it for routing.

### 3. Apply Routing Rules

| Reviewer | Fires when |
|---|---|
| **General-purpose reviewer** | Always |
| **`/security-review`** | Default. **Skip only if doc-only** (every changed file matches `*.md`, `*.txt`, `docs/**`, `CHANGELOG*`, `LICENSE*`, `README*`, `.github/**/*.md` AND no code files were touched) |
| **`/frontend-review`** | Diff touches `*.jsx`, `*.tsx`, `*.vue`, `*.svelte`, `*.html`, `*.css`, `*.scss`, or known frontend paths (`components/`, `pages/`, `app/`, `views/`, `templates/`) |
| **`/seo-review`** | Diff touches page templates, route definitions, `<head>`/meta tags, `sitemap.*`, `robots.txt`, canonical URL config, Open Graph / Twitter Card tags |
| **`/geo-review`** | Diff touches content pages, `llms.txt`, `llms-full.txt`, JSON-LD schema, AI-bot rules in `robots.txt`, author bios, About page |
| **`/playwright-review`** | Test files touched (`*.spec.*`, `*.test.*` under `e2e/`, `tests/e2e/`, `playwright/`) **OR new route added without a corresponding test** (see route detection below) **OR new/changed client-side interactive behavior without an e2e test exercising it** — even when no new server route was added (see interaction detection below) |

**Doc-only detection:** the security skip is conservative. ALL changed files must match the doc allowlist AND no code files may be touched. If in doubt, run security.

**New-route detection** (heuristic — scan the diff for added lines matching any of):
- `app\.(get|post|put|delete|patch|all|use)\(` (Express/Koa)
- `@app\.route\(` or `@(get|post|put|delete|patch)\(` (Flask, FastAPI)
- `router\.(get|post|put|delete|patch)\(` (Express Router, Vue Router)
- `Route::(get|post|put|delete|patch|resource)` (Laravel)
- New file under `pages/api/`, `app/api/**/route.{ts,js}` (Next.js)
- New file under `routes/` (Rails, Remix, SvelteKit)
- Changes to `config/routes.rb` (Rails)
- `get '/...'`, `post '/...'` patterns (Sinatra, Rails routes)
- Mojolicious / Dancer / Catalyst route declarations (Perl)

If a new route is detected AND no Playwright/e2e test was added in the same diff covering it, dispatch `/playwright-review` with an explicit "verify e2e coverage for newly added route(s): <list>" instruction appended to its normal checklist.

**New-interaction detection** (heuristic — scan the diff for added lines matching any of):
- `addEventListener\(\s*['"](click|submit|change|input|keydown|keyup)` (DOM event handlers)
- `\.(onclick|onsubmit|onchange)\s*=` or `on(click|submit|change)=` attributes in templates/markup
- `fetch\(`, `axios\.`, `XMLHttpRequest`, `\$\.(ajax|post|get)\(` (client-initiated requests tied to a user action)
- `data-action=` / `data-bs-toggle=` wiring, or a new `<button>` / `<form method=` / submit control backed by JS
- New or changed handlers in `*.js` / `*.ts` / `*.jsx` / `*.tsx` modules, or `<script>` blocks in templates

This trigger exists because **reusing an existing server route still ships untested browser behavior** — a new button that POSTs to an already-defined endpoint, a confirm dialog, an AJAX call, or a client-side redirect is real user-facing logic the route-detection rule will miss. Backend-only tests (unit/handler tests, template-render assertions) do **not** cover the click → request → response → DOM/redirect path.

If new client-side interaction is detected AND no Playwright/e2e test was added or updated in the same diff to exercise it, dispatch `/playwright-review` with an explicit "verify e2e coverage for new client-side interaction(s): <list>" instruction appended to its normal checklist, and flag missing coverage as **Important**.

### 4. Dispatch in Parallel

**Dispatch all applicable reviews in a single message via multiple `Task` tool calls.** Each subagent reads its specialist `.md` file and executes that workflow — the specialists remain the single source of truth.

For the general reviewer:
```
Task(general-purpose):
  description: General code review of [feature]
  model: "sonnet"
  prompt: [standard code-reviewer prompt with BASE/HEAD SHAs]
```

For each applicable specialist (security/frontend/seo/geo/playwright):
```
Task(general-purpose):
  description: [Specialist] review of [feature]
  model: "sonnet"
  prompt:
    Execute the workflow described in commands/<specialist>.md against this diff:
      Base SHA: BASE_SHA
      Head SHA: HEAD_SHA
      Feature: [brief description]
      [If playwright + new-route detected: "ADDITIONAL FOCUS: verify e2e coverage exists for newly added route(s): <list>. Flag missing coverage as Important."]

    Follow the file's instructions exactly. Dispatch general-purpose as the file directs. Return the resulting review verbatim, plus a one-line preamble identifying which specialist you ran.
```

**Important:**
- Run all `Task` calls in the SAME message so they execute concurrently
- Do not invoke the user-facing slash commands directly — dispatch subagents that read the specialist .md files
- If a specialist is skipped by routing, note it in the final summary (don't silently omit)

### 5. Aggregate Results

When all subagents return, produce a single consolidated report:

```markdown
# Code Review Intense Flow Summary

## Reviewers Run
- ✅ General code-reviewer
- ✅ Security ([reason fired])
- ⏭️ Frontend (skipped: no UI files changed)
- ✅ SEO ([reason fired])
- ...

## Critical Issues (X total)
- [security] Issue description [file:line]
- [general] Issue description [file:line]

## Important Issues (X total)
- [frontend] Issue description [file:line]
- ...

## Minor Issues (X total)
- ...

## Strengths
- [Aggregated positive observations]

## Per-Reviewer Reports
<details><summary>General code-reviewer</summary>

[Full review verbatim]

</details>

<details><summary>Security review</summary>

[Full review verbatim]

</details>

...
```

Tag each finding with the specialist that surfaced it so the user knows which lens to trust on that issue.

### 6. Posting and Fixing

Same protocol as `/code-review-flow`:
- If a PR exists: post findings using `/code-review-flow`'s inline-review protocol — batch them
  into a single `pulls/{n}/reviews` POST (`event: "COMMENT"`) with each `file:line` finding as an
  inline anchored comment and un-anchorable findings in the summary `body`. Specialist findings
  already carry a lens tag and mostly a `file:line`, so they anchor naturally. Per that protocol
  and `docs/attribution.md`, the summary `body` ends with the attribution footer (model version,
  resolved at runtime), e.g.:
  ```
  ---
  🤖 Review by [Claude Code](https://claude.com/claude-code) · Opus 4.8
  ```
- Never self-approve (`event: "COMMENT"`)
- Fix Critical and Important issues automatically; for diffs > 500 lines, file GitHub issues for Minor
- Re-run the orchestrator on the new HEAD until clean

## Critical Rules

**DO:**
- Always run general code-reviewer
- Default to running security; only skip on truly doc-only diffs
- Dispatch in parallel (single message, multiple Task calls)
- Note skipped reviewers in the summary with the routing reason
- Pass the "new route, verify e2e coverage" instruction to `/playwright-review` when triggered by route detection (not test-file changes)
- Fire `/playwright-review` for new client-side interaction (event handlers, `fetch`/AJAX, JS-wired buttons/forms) even when the diff reuses an existing route and adds no new one — a backend test does not cover the browser interaction

**DON'T:**
- Silently skip security on changes that touch any code file
- Run specialists sequentially (kills the speed advantage)
- Modify the user-facing slash commands' standalone behavior
- Discard per-specialist findings — aggregate AND retain them

## Related Commands

- **`/code-review-flow`** — Lightweight version: general reviewer only, no specialists
- **`/security-review`**, **`/frontend-review`**, **`/seo-review`**, **`/geo-review`**, **`/playwright-review`** — The specialists this orchestrator dispatches
- **general-purpose** — The base agent specialists ultimately spawn; the reviewer persona comes from the prompt they pass, not the agent itself
