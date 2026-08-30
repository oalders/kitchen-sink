---
description: Drive Playwright MCP to load live URLs at multiple viewport widths and report responsive breakage static review can't see
---

# Responsive Audit

## Overview

Live-discovery responsive audit: drives the **Playwright MCP** to load one or more
already-serving URLs at several viewport widths and reports responsive breakage that
static review can't see. It fills the gap between `/frontend-review` (which reasons about a
source diff and only *recommends* manual screenshots) and `/playwright-review` (which
reviews existing test *source*) — neither actually drives a browser against a live page.

**Discovery/reporting only:** no test files are written, no source is modified, and no dev
server is started.

**Deliberate departure from the sibling review commands:** the steps below drive the
Playwright MCP tools directly (navigate, resize, evaluate JS, screenshot) rather than
spawning a `Task(general-purpose)` subagent the way `/frontend-review` and
`/playwright-review` do. There is a live browser session to hold, so the work stays in the
caller's context and `## Output Format` is a top-level section (no subagent to nest it in).
This inconsistency is intentional.

**Hard prerequisite:** a working Playwright MCP must be available in the session. The
command cannot probe tool availability up front — if the MCP is absent it simply fails on
the first browser call. State the prerequisite before starting and surface that failure
clearly rather than pretending to detect it. The target URL(s) must already be reachable.

## When to Use

Use when:
- You have a live, already-serving page and want to find responsive layout breakage across
  viewport widths (overflow, occluded controls, tiny touch targets / text).
- You want measured evidence plus full-page screenshots, not just a reasoned guess from a diff.
- A `/frontend-review` flagged possible responsive risk and you want to confirm it on the real page.

Don't use when:
- The page isn't serving yet — this command does **not** start a dev server (start it yourself first).
- You want a source-diff review (use `/frontend-review`) or a review of Playwright test source
  (use `/playwright-review`).
- You want tests written, source auto-fixed, or issues/PRs filed — all explicit non-goals.

## Steps

### 1. Resolve input URL(s)

- Take one or more URLs from the command args (space-separated):
  `/responsive-audit http://localhost:3000/pricing http://localhost:3000/about`
- If no URL is given, ask the user for one before doing anything else.
- Do not start or detect a dev server. If a URL isn't serving, navigation will fail in step 3 —
  report it and stop for that URL.

### 2. Define the viewport sweep

Sweep each URL at these four widths:

| Width | Represents |
|-------|-----------|
| 320px | Smallest common mobile |
| 375px | Typical modern phone |
| 768px | Tablet |
| 1280px | Desktop |

Pin only the **width**. Keep the height normal (~800) and use `fullPage: true` for
screenshots — a full-page capture records the entire scrollable height regardless of viewport
height. Do **not** force a tall viewport to capture more: it distorts `vh`-based layouts, defeats
lazy-loading, and changes sticky/fixed element behaviour. 1920px is omitted deliberately —
large-desktop bugs are rare and usually amount to excess whitespace, not breakage.

### 3. For each URL, navigate once

Use the Playwright MCP `browser_navigate` tool to load the URL. If navigation fails (connection
refused, timeout, error status), record that the URL is unreachable, report it, and move on to the
next URL — do not retry endlessly and do not try to start a server.

### 4. For each viewport width, run the checks

Resize with the Playwright MCP `browser_resize` tool (e.g. width 320, height 800), then run the
following checks via `browser_evaluate` (running JS in the page) and capture a screenshot.

**Check 1 — Horizontal overflow (all widths).**
Detect `document.documentElement.scrollWidth > document.documentElement.clientWidth`. On failure,
walk the DOM to name the overflowing element(s) by selector (the elements whose right edge exceeds
the viewport width). **Skip elements that are off-screen by design** — `position: absolute`
menus/drawers, transformed or hidden elements, and anything inside an `overflow: hidden` ancestor —
those don't cause a visible horizontal scrollbar. Report each real offender's selector and its
measured `scrollWidth` vs `clientWidth`.

**Check 2 — Obscured interactive controls (all widths) — occlusion, not raw box overlap.**
For each interactive control (`a`, `button`, `input`, `select`, `textarea`, `[role=button]`,
`[tabindex]`), compute its center point and test whether `document.elementFromPoint(cx, cy)` returns
that control (or a descendant of it). If it returns some *other* element that isn't an ancestor, the
control is covered and effectively unclickable — report it with the covering element's selector.

- Do **not** flag generic `boundingBox()` / `getBoundingClientRect()` intersection. Overlapping
  boxes are routinely intentional (sticky headers/footers, dropdowns, modals, z-index layering,
  negative margins), and `boundingBox()` is `null` for hidden elements.
- Skip controls that are hidden or have zero size (nothing to click).
- Non-occlusion visual collisions are left to the screenshots — this check only catches
  point-level occlusion.

**Check 3 — Touch targets & text size (mobile widths 320 / 375 only).**
- Flag **standalone** controls (`button`, `input`, nav items, `[role=button]`) whose rendered box
  is under **44×44px**. Inline body-text links are **exempt** from the 44px rule (WCAG 2.5.5).
- Flag text whose computed `font-size` is below **12px**.
- Report each offender's selector and measured value.

**Check 4 — Screenshot (all widths).**
Take one `fullPage` screenshot per viewport via the Playwright MCP `browser_take_screenshot` tool
(`fullPage: true`), saving to the session scratchpad directory with a descriptive filename
(e.g. `responsive-audit-<host>-<path>-320.png`). Reference the saved path in the report so the user
can eyeball what measurements can't express (spacing collisions, wrapping, visual regressions).

### 5. Assemble the report

Collect all findings per URL × viewport into the single report described below. Do not fix anything,
write tests, or file issues — reporting is where this command ends.

## Output Format

A single markdown report, grouped **URL → viewport**. For each URL, and within it each viewport,
lead with a one-line summary, then the details.

```
# Responsive Audit

## http://localhost:3000/pricing

### 320px — 1 Important, 2 Minor

**Important (Should Fix)**
- Horizontal overflow: `div.hero__cta` — scrollWidth 431px > clientWidth 320px
- Obscured control: `button.buy-now` covered by `div.cookie-banner`

**Minor (Nice to Have)**
- Touch target: `a.nav__link` is 40×32px (< 44×44px)
- Small text: `p.legal` computed font-size 11px (< 12px)

Screenshot: /…/scratchpad/responsive-audit-localhost-pricing-320.png

### 375px — clean
Screenshot: /…/scratchpad/responsive-audit-localhost-pricing-375.png

### 768px — …
### 1280px — …
```

Severity labels **reuse the sibling review labels**:
- `Important (Should Fix)` — horizontal overflow and obscured controls (real breakage / unusable UI).
- `Minor (Nice to Have)` — touch-target and text-size findings.

Each finding states: the **severity**, the offending **selector** (or, for occlusion, the covering
element), the **measured values** (e.g. `scrollWidth 431px > clientWidth 320px`, `40×32px`,
`font-size 11px`), and the **screenshot path** for that viewport.

If a URL was unreachable, report that plainly under its heading instead of viewport results.

## Related Commands

- **/frontend-review** — static, source-diff frontend review (accessibility, responsive, CSS). This
  command is its live-discovery complement.
- **/playwright-review** — reviews existing Playwright test *source*; this command drives a live
  browser instead of reviewing tests.
