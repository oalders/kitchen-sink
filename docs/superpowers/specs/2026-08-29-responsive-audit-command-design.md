# `/responsive-audit` command — design

## Problem

The kitchen-sink toolkit has two frontend-adjacent commands, but neither
*discovers* responsive bugs on a live page:

- `/frontend-review` reasons about a source **diff** — it spawns a subagent and
  can *recommend* manual screenshots at various viewports, but it never drives a
  browser itself.
- `/playwright-review` reviews **existing Playwright test source** for coverage
  and performance — it does not drive a browser.

So the workflow of "load the site at several widths and see what breaks" is
still done entirely by hand. This command automates that discovery step.

## Solution

A slash command (`commands/responsive-audit.md`) that drives the
already-configured **Playwright MCP** to load one or more live URLs at several
viewport widths and report responsive breakage that static review cannot see.

It is a **discovery / reporting** tool only: no test files are written, no
source is modified, no dev server is started.

## Scope

### Input

- One or more URLs passed as args:
  - `/responsive-audit http://localhost:3000/pricing`
  - `/responsive-audit http://localhost:3000/ http://localhost:3000/pricing`
    (space-separated list)
- If no URL is given, the command asks for one before proceeding.
- The URL(s) must already be serving. The command does **not** start a dev
  server; if navigation fails it reports the failure and stops rather than
  guessing how to launch the app.

### Viewports

Each URL is swept at four widths. Only the **width** is pinned; height stays a
normal value (e.g. 800) and screenshots use `fullPage: true`, which captures the
entire scrollable page regardless of viewport height. (Forcing a tall viewport
height is unnecessary and can distort `vh`-based layouts, lazy-loading, and
sticky elements, so the command must not do it.)

| Width | Represents          |
|-------|---------------------|
| 320   | smallest common mobile |
| 375   | common mobile       |
| 768   | tablet              |
| 1280  | desktop baseline    |

The set intentionally targets the mobile→tablet→laptop range where responsive
breakage concentrates. Large-desktop (1920) is omitted because bugs there are
rare and usually the reverse (excess whitespace) rather than layout breakage;
add it later if it earns its place.

### Checks (per URL × viewport)

1. **Horizontal overflow** — compare `document.documentElement.scrollWidth`
   against `clientWidth`. On failure, walk the DOM to identify the specific
   element(s) whose right edge extends past the viewport, and report them by
   selector. This is the classic mobile sideways-scroll bug. Skip elements that
   are off-screen by design (e.g. `position:absolute` menus, transformed/hidden
   elements, content inside `overflow:hidden` ancestors) to cut false positives.
2. **Obscured interactive controls** (occlusion, not raw box overlap) — for each
   interactive control, check whether its own center point actually hits itself
   via `document.elementFromPoint()`; if another element sits on top, the control
   is covered and effectively unclickable. This is far more reliable than
   intersecting `boundingBox()` rectangles, which produces false positives
   because overlapping boxes are routinely *intentional* (sticky headers/footers,
   dropdowns, modals, z-index stacks, negative margins) and `boundingBox()`
   returns `null` for hidden elements. The command must **not** flag generic
   box-intersection; only genuine occlusion of an interactive control. Real
   content-collision that isn't occlusion is left to the screenshots (check 4).
3. **Touch targets & text size** — at the mobile widths (320/375): flag
   **standalone** interactive controls (`button`, `input`, nav items,
   `[role=button]`) whose rendered box is under 44×44px, and text whose computed
   `font-size` is below **12px**. Inline links within body-text flow are exempt
   from the 44px rule (per WCAG 2.5.5) to avoid flooding the report.
4. **Screenshots** — capture one full-page screenshot per viewport, saved to
   the session scratchpad directory, and reference each path in the report so
   the user can eyeball what the measurements cannot express.

### Output

A single markdown report, grouped **URL → viewport**, where each finding
carries:

- **Severity**, reusing the sibling commands' labels — `Important (Should Fix)`
  for horizontal overflow and obscured controls (visibly broken / unusable);
  `Minor (Nice to Have)` for undersized touch targets and text.
- The offending **selector** (or the covering element, for occlusion).
- The measured values (e.g. `scrollWidth 431px > clientWidth 320px`).
- The **screenshot path** for that viewport.

A short summary line per viewport ("320px: 1 Critical, 2 Minor") precedes the
detail so the user can scan quickly.

### Non-goals (YAGNI)

- Does **not** start or detect the dev server — assumes the URL is serving.
- Does **not** write Playwright test files — that is what `/playwright-review`
  reviews.
- Does **not** modify source or auto-fix anything.
- Does **not** file GitHub issues or open PRs — the user triages the report.
- Does **not** crawl/discover routes — the user names the URLs.

## Command structure

Follows the existing `commands/*.md` convention in this repo:

- Frontmatter `description:` line summarizing the command.
- `## Overview`, `## When to Use` (with a "Don't use when" list), `## Steps`.
- Steps drive the Playwright MCP tools directly (navigate, set viewport size,
  evaluate measurement JS, screenshot) rather than spawning a subagent — the
  audit is interactive browser work, not a code-diff review. This is a
  deliberate departure from the sibling commands, whose defining element is a
  `Task(general-purpose)` block; note the departure explicitly in the command so
  the inconsistency reads as intentional.
- A top-level `## Output Format` section specifying the grouped report shape
  above (top-level rather than nested in a subagent prompt, since there is no
  subagent).
- A `## Related Commands` section cross-linking `/frontend-review` (static CSS
  review) and `/playwright-review` (test-source review), positioning this
  command as the live-discovery complement to both.

## Dependencies / assumptions

- A working **Playwright MCP** is available in the session (configured globally
  for this user). MCP-live is the only supported drive mechanism (chosen for
  simplicity); there is no script fallback. The command cannot probe tool
  availability in advance, so if the MCP is absent it simply fails on the first
  browser call — the command should surface that failure clearly and state the
  Playwright MCP as a hard prerequisite up front rather than pretending to
  detect it.
- The target URL is reachable from the session.

## Versioning

New command → **minor** bump per project `CLAUDE.md`: `2.20.0 → 2.21.0`,
updated in all three places (`plugin.json` `version`;
`marketplace.json` `metadata.version` and the `plugins[]` entry's `version`).

## Documentation

The command should be added to the README command list (grouped with the other
frontend/review commands), consistent with how existing commands are documented.
