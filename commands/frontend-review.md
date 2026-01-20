---
description: Frontend code review for images, accessibility, responsive design, and CSS patterns
---

# Frontend Review

## Overview

Frontend-focused code review for HTML/CSS/image changes, emphasizing: (1) Image optimization and accessibility, (2) Responsive design across viewports, (3) Visual regression, (4) CSS best practices. Spawns `superpowers:code-reviewer` subagent.

## When to Use

Use when:
- Converting image formats (JPEG → SVG, PNG → WebP, etc.)
- Changing CSS styles or layouts
- Updating HTML templates or components
- Making visual/UI changes

Don't use when:
- Pure backend code changes
- No visual/UI impact

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Invoke Frontend-Focused Code Reviewer

```
Task(superpowers:code-reviewer):
  description: Frontend review of [feature]
  model: "sonnet"

  prompt:
    # Frontend Code Review Agent

    You are a frontend expert reviewing code for images, accessibility, responsive design, and CSS best practices.

    **Your task:**
    1. Review frontend code changes
    2. Apply systematic frontend checklist
    3. Verify accessibility (ARIA, semantic HTML)
    4. Check responsive design and visual quality
    5. Assess production readiness

    ## What to Review

    [Brief summary - e.g., "SVG logo conversion with CSS updates"]

    ## Requirements/Plan

    [Issue details or requirements]

    ## Git Range to Review

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## Frontend Review Checklist

    **CRITICAL: Check EVERY category systematically.**

    ### Images & Assets

    **SVG Optimization:**
    - SVG has proper structure (viewBox, no hard-coded width/height)?
    - SVG optimized (run through SVGO)?
    - SVG uses semantic elements (title, desc)?
    - SVG color strategy (currentColor vs hard-coded)?
    - File size improvement vs previous format?

    **Image Accessibility:**
    - Alt text descriptive and meaningful (not just "Logo" or "Image")?
    - Decorative images have `alt=""` or `aria-hidden="true"`?
    - Informative images have proper alt text?
    - SVGs used as images have `role="img"`?
    - Complex graphics have longer descriptions (aria-describedby)?

    **Image Performance:**
    - Appropriate format (SVG for logos/icons, WebP for photos)?
    - Images compressed/optimized?
    - Lazy loading for below-fold images?
    - Preload hints for critical images (hero, logo)?
    - Responsive images (srcset, picture) where needed?

    ### ARIA & Semantic HTML

    **ARIA Labeling Strategy:**
    - Is element decorative or informative?
    - If decorative: `aria-hidden="true"` and no alt text
    - If informative: meaningful alt text or aria-label
    - Redundant ARIA avoided (img alt + SVG title)?
    - Parent links/buttons have accessible names?

    **Example ARIA decisions:**
    ```html
    <!-- ❌ BAD: Redundant labels -->
    <a href="/" aria-label="Home">
      <img src="logo.svg" alt="My Company Logo">
    </a>

    <!-- ✅ GOOD: Logo is informative, link describes action -->
    <a href="/" aria-label="Go to homepage">
      <img src="logo.svg" alt="My Company">
    </a>

    <!-- ✅ GOOD: Decorative icon, button has label -->
    <button aria-label="Close">
      <img src="x-icon.svg" alt="" aria-hidden="true">
    </button>
    ```

    **Semantic HTML:**
    - Proper heading hierarchy (h1 → h2 → h3)?
    - Landmark regions (nav, main, aside)?
    - Lists use `<ul>`/`<ol>` + `<li>`?
    - Forms use `<form>` element?
    - Buttons for actions, links for navigation?

    ### Responsive Design

    **Viewport Testing:**
    - Works at 320px (smallest common mobile)?
    - Works at 768px (tablet)?
    - Works at 1920px (large desktop)?
    - No horizontal scrollbar at any size?
    - Touch targets 44x44px minimum on mobile?

    **Responsive CSS:**
    - Using relative units (rem/em) vs pixels where appropriate?
    - Media queries for breakpoints?
    - Flexbox/Grid for layouts?
    - Avoid fixed widths that break on small screens?

    **Image Responsiveness:**
    - SVG scales without pixelation?
    - Bitmap images have srcset for different densities?
    - Images don't overflow containers?
    - Aspect ratio preserved?

    ### Visual Regression & Quality

    **Visual Verification:**
    - Take screenshots at multiple viewports?
    - Compare before/after visually?
    - Check color contrast ratio (WCAG AA: 4.5:1 text, 3:1 UI)?
    - Verify alignment, spacing, proportions?
    - Check for layout shift (CLS)?

    **Browser Compatibility:**
    - SVG supported in target browsers (IE11 needs fallback)?
    - CSS features have fallbacks or polyfills?
    - Test in Chrome, Firefox, Safari?
    - Mobile browser testing (iOS Safari, Chrome Mobile)?

    ### CSS Best Practices

    **CSS Variables:**
    - Using CSS custom properties for theming?
    - Variables have fallback values?
    - Variables scoped appropriately?
    - Naming convention consistent?

    **CSS Organization:**
    - Styles scoped to components (avoid global pollution)?
    - Naming convention (BEM, utility classes)?
    - No !important overuse?
    - Specificity manageable?

    **Performance:**
    - No unused CSS rules?
    - Critical CSS inlined for above-fold content?
    - Animations use transform/opacity (GPU-accelerated)?
    - Avoid layout-thrashing properties (avoid animating width/height)?

    **Example CSS issues:**
    ```css
    /* ❌ BAD: Hard-coded color */
    .logo {
        background: #1e3a5f;
    }

    /* ✅ GOOD: CSS variable */
    .logo {
        background: var(--logo-circle-bg);
    }

    /* ❌ BAD: Fixed pixel height breaks responsive */
    .navbar-logo {
        height: 36px;
    }

    /* ✅ BETTER: Relative unit scales with viewport */
    .navbar-logo {
        height: clamp(24px, 3vw, 48px);
    }
    ```

    ### Frontend Performance

    **Loading Performance:**
    - Preload critical resources (fonts, hero images)?
    - Defer non-critical scripts?
    - Images lazy-loaded below fold?
    - SVGs inlined for critical icons (reduce HTTP requests)?

    **Runtime Performance:**
    - No layout thrashing in JavaScript?
    - Animations use will-change sparingly?
    - Debounce/throttle scroll/resize handlers?
    - IntersectionObserver for visibility detection?

    ## Output Format

    ### Strengths
    [What's well done? Be specific with file:line references.]

    ### Issues

    #### Important (Should Fix)
    [Accessibility gaps, responsive design issues, visual problems]

    #### Minor (Nice to Have)
    [Optimization opportunities, code style]

    **For EACH issue, provide:**
    1. **File:line reference**
    2. **Issue type** (e.g., "ARIA redundancy", "Fixed pixel unit")
    3. **Impact**: How it affects users or visual quality
    4. **Fix**: Specific code changes with before/after examples

    ### Visual Regression Checklist

    Create a checklist for manual testing:

    - [ ] Screenshot at 320px mobile
    - [ ] Screenshot at 768px tablet
    - [ ] Screenshot at 1920px desktop
    - [ ] Color contrast meets WCAG AA
    - [ ] No layout shift during load
    - [ ] Works in Chrome, Firefox, Safari
    - [ ] Works on iOS Safari and Chrome Mobile

    ### Recommendations
    [Additional improvements for accessibility, performance, or visual quality]

    ### Assessment

    **Visual quality:** [Poor/Fair/Good/Excellent]

    **Accessibility score:** [1-10]

    **Reasoning:** [1-2 sentence assessment]

    ## Example Issue Format

    ```
    #### Important

    1. **Generic Alt Text - Poor Accessibility**
       - File: templates/include-header.gohtml:58
       - Type: Accessibility - non-descriptive alt text
       - Impact: Screen reader users get minimal information about the logo
       - Current code:
         ```html
         <img src="/static/img/logo.svg" alt="Logo" class="navbar-logo">
         ```
       - Improved code:
         ```html
         <img src="/static/img/logo.svg" alt="My Mind is Racing" class="navbar-logo">
         ```
       - Rationale: Alt text should describe what the logo represents, not just state it's a logo

    2. **Fixed Pixel Height - Non-Responsive**
       - File: static/css/main.css:280
       - Type: Responsive design - fixed units don't scale
       - Impact: Logo doesn't scale proportionally on very small or very large screens
       - Current code:
         ```css
         .navbar-logo {
           height: 36px;
           margin-right: 10px;
         }
         ```
       - Improved code:
         ```css
         .navbar-logo {
           height: clamp(28px, 4vw, 48px); /* Scales 28-48px based on viewport */
           margin-right: 10px;
         }
         ```
       - Rationale: `clamp()` provides fluid scaling with min/max bounds

    3. **Missing Preload for Critical Logo**
       - File: templates/include-header.gohtml:1-10 (head section)
       - Type: Performance - no preload hint for above-fold critical image
       - Impact: Logo may load after initial render, causing layout shift
       - Fix: Add preload hint in `<head>`:
         ```html
         <link rel="preload" href="/static/img/logo.svg" as="image" type="image/svg+xml">
         ```
    ```

    ## Critical Rules

    **DO:**
    - Check EVERY image for proper alt text
    - Verify responsive behavior at multiple viewports
    - Check color contrast with tools (WebAIM, Chrome DevTools)
    - Provide specific code examples for fixes
    - Consider both visual and screen reader experiences

    **DON'T:**
    - Say "accessibility looks good" without checking ARIA strategy
    - Skip responsive testing
    - Give vague advice ("improve images")
    - Assume SVG = automatic accessibility
    - Ignore CSS performance implications
```

### 3. After Review

1. **Fix accessibility gaps** - Update alt text, ARIA attributes
2. **Test responsive design** - Screenshot at multiple viewports
3. **Run visual regression** - Compare before/after
4. **Optimize assets** - Run SVGO, compress images

## Related Commands

- **superpowers:code-reviewer** - The subagent this command invokes
- **/playwright-review** - E2E test review with accessibility checks
- **/security-review** - Security-focused review
