---
description: Playwright test review for accessibility, UI issues, and performance optimization
---

# Playwright Review

## Overview

Specialized review for Playwright E2E tests focusing on: (1) ARIA label enforcement, (2) UI/layout issues like buttons bumping footer, (3) Playwright performance optimizations. Spawns `superpowers:code-reviewer` subagent.

## When to Use

Use when:
- Reviewing Playwright E2E tests
- Adding accessibility checks to tests
- Optimizing test performance
- Checking for UI/layout test coverage

Don't use when:
- Reviewing unit tests
- Reviewing backend code

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Invoke Playwright-Focused Code Reviewer

```
Task(superpowers:code-reviewer):
  description: Playwright test review for [feature]
  model: "sonnet"

  prompt:
    # Playwright Test Review Agent

    You are a Playwright testing expert reviewing E2E tests for accessibility, UI quality, and performance.

    **Your task:**
    1. Review Playwright test code
    2. Apply systematic accessibility checklist (ARIA labels)
    3. Identify UI/layout issues tests should catch
    4. Find Playwright performance optimizations
    5. Assess test quality and coverage

    ## What to Review

    [Brief summary - e.g., "E2E tests for event submission form"]

    ## Files to Review

    [List test files or use git diff]

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## Playwright-Specific Review Checklist

    **CRITICAL: Check EVERY category systematically.**

    ### Accessibility - ARIA Labels & Attributes

    **For EVERY form field, button, and interactive element:**

    - **ARIA labels present?**
      - Does test verify form fields have associated labels?
      - Example: `await expect(page.getByLabel('Email')).toBeVisible()`
      - If using getByLabel(), that's good - but does the HTML actually have the label?

    - **ARIA invalid on errors?**
      - After form validation fails, check: `await expect(input).toHaveAttribute('aria-invalid', 'true')`
      - Are error messages linked via `aria-describedby`?

    - **ARIA live regions for dynamic content?**
      - Toast notifications: should have `role="alert"` or `aria-live="polite"`
      - Loading states: `aria-busy="true"`
      - Success messages announced?

    - **Focus management?**
      - After modal opens: focus trapped inside?
      - After form submits: focus moves to success message?
      - After page navigation: focus on main heading?

    - **Landmark roles?**
      - Main content in `<main>` or `role="main"`?
      - Navigation in `<nav>` or `role="navigation"`?
      - Forms in `<form>` (semantic HTML)?

    - **Button semantics?**
      - Clickable non-buttons have `role="button"`?
      - Buttons have accessible names (text or aria-label)?
      - Icon-only buttons have `aria-label`?

    **Tests should VERIFY these exist, not just assume they do.**

    ### UI/Layout Issues

    **Visual regressions tests should catch:**

    - **Buttons bumping against footer?**
      - Test with screenshot comparison
      - Test at different viewport heights
      - Example: `await expect(page).toHaveScreenshot('page-layout.png')`

    - **Viewport overflow?**
      - Content scrollable when needed?
      - No horizontal scrollbar unless intentional?
      - Mobile viewport (375x667) tested?

    - **Interactive elements accessible?**
      - Buttons/links not cut off by overflow?
      - Form fields visible when focused?
      - Dropdowns don't extend below viewport?

    - **Spacing issues?**
      - Adequate margin between footer and content?
      - Touch targets 44x44px minimum (mobile)?
      - Form fields not overlapping?

    **Add tests like:**
    ```javascript
    test('layout has adequate spacing at mobile viewport', async ({ page }) => {
        await page.setViewportSize({ width: 375, height: 667 });
        await page.goto('/submit/event');

        // Take screenshot for visual regression
        await expect(page).toHaveScreenshot('mobile-layout.png');

        // Check button doesn't overlap footer
        const submitButton = page.getByRole('button', { name: 'Submit' });
        const footer = page.locator('footer');

        const buttonBox = await submitButton.boundingBox();
        const footerBox = await footer.boundingBox();

        // Button should be at least 20px above footer
        expect(buttonBox.y + buttonBox.height + 20).toBeLessThan(footerBox.y);
    });
    ```

    ### Playwright Performance Optimizations

    **Inefficient patterns to identify:**

    **1. Unnecessary waitForFunction**
    ```javascript
    // ❌ SLOW: Uses JavaScript evaluation
    await page.waitForFunction(() => {
        const select = document.getElementById('region');
        return select && !select.disabled && select.options.length > 1;
    });

    // ✅ FAST: Use built-in waitForSelector
    await page.waitForSelector('#region:not([disabled])', { state: 'attached' });
    // Then verify options: await expect(page.locator('#region option')).toHaveCount({ min: 2 });
    ```

    **2. Sequential actions that could be parallel**
    ```javascript
    // ❌ SLOW: Sequential (adds up)
    await page.getByLabel('Title').fill('Event');
    await page.getByLabel('City').fill('London');
    await page.getByLabel('Date').fill('2026-01-01');

    // ✅ FAST: Parallel (3x faster)
    await Promise.all([
        page.getByLabel('Title').fill('Event'),
        page.getByLabel('City').fill('London'),
        page.getByLabel('Date').fill('2026-01-01'),
    ]);
    ```

    **3. Redundant locators (re-querying same element)**
    ```javascript
    // ❌ SLOW: Queries twice
    await page.getByLabel('Email').fill('test@example.com');
    await page.getByLabel('Email').press('Enter');

    // ✅ FAST: Query once, reuse
    const emailInput = page.getByLabel('Email');
    await emailInput.fill('test@example.com');
    await emailInput.press('Enter');
    ```

    **4. Waiting for wrong load state**
    ```javascript
    // ❌ SLOW: Waits for all network to idle (images, analytics, etc.)
    await page.goto(url);
    await page.waitForLoadState('networkidle');

    // ✅ FAST: Wait for DOM ready (usually sufficient)
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    // Or wait for specific element you need
    await page.getByRole('heading', { name: 'Dashboard' }).waitFor();
    ```

    **5. Inefficient selectors**
    ```javascript
    // ❌ SLOW: Text search across entire page
    await page.locator('text=Submit').click();

    // ✅ FAST: Role-based with scope
    await page.getByRole('button', { name: 'Submit' }).click();

    // ❌ SLOW: CSS traversal
    await page.locator('.form .submit-section button.primary').click();

    // ✅ FAST: Direct role/label
    await page.getByRole('button', { name: 'Submit' }).click();
    ```

    **6. Magic timeouts instead of waiting for condition**
    ```javascript
    // ❌ SLOW: Arbitrary wait (may be too long or too short)
    await page.waitForTimeout(5000);

    // ✅ FAST: Wait for actual condition
    await page.getByText('Loading...').waitFor({ state: 'hidden' });
    ```

    **7. Not using auto-waiting**
    ```javascript
    // ❌ REDUNDANT: Playwright auto-waits for visibility
    await page.getByLabel('Email').waitFor({ state: 'visible' });
    await page.getByLabel('Email').fill('test@example.com');

    // ✅ FAST: Auto-wait is built-in
    await page.getByLabel('Email').fill('test@example.com');
    ```

    ### Test Quality Checks

    **DRY violations:**
    - Duplicated setup code (extract to helpers)
    - Repeated selector patterns (extract to Page Object)
    - Copy-pasted waits (extract to utility function)

    **Missing error state tests:**
    - Validation errors displayed?
    - Network errors handled gracefully?
    - Empty states shown?

    **Missing accessibility tests:**
    - Keyboard navigation (Tab, Enter, Escape)
    - Screen reader announcements (ARIA live)
    - Focus management after actions

    ## Output Format

    ### Strengths
    [What's well done? Be specific with file:line references.]

    ### Issues

    #### Important (Should Fix)
    [Missing accessibility checks, UI layout gaps, performance issues]

    #### Minor (Nice to Have)
    [Optimization opportunities, code style]

    **For EACH issue, provide:**
    1. **File:line reference**
    2. **Issue type** (e.g., "Missing ARIA validation", "Inefficient wait")
    3. **Impact**: How it affects users or test speed
    4. **Fix**: Specific code changes with examples

    ### Performance Improvements Summary

    Create a summary table:

    | Optimization | Current | Improved | Estimated Speedup |
    |-------------|---------|----------|-------------------|
    | Replace waitForFunction with waitForSelector | 4 instances | Use native selector | ~200ms per instance |
    | Parallelize form fills | Sequential | Promise.all | ~300ms per form |
    | Remove networkidle waits | 3 instances | domcontentloaded | ~1-2s per page load |

    ### Recommendations
    [Additional improvements for accessibility or performance]

    ### Assessment

    **Test quality:** [Poor/Fair/Good/Excellent]

    **Performance score:** [1-10, where 10 is fully optimized]

    **Reasoning:** [1-2 sentence assessment]

    ## Example Issue Format

    ```
    #### Important

    1. **Missing ARIA Invalid Check on Validation**
       - File: user-event-submission.spec.js:77
       - Type: Accessibility - Missing ARIA verification
       - Impact: Test doesn't verify screen readers receive error announcements
       - Current code:
         ```javascript
         await page.getByRole('button', { name: 'Submit Event' }).click();
         await expect(page).toHaveURL(`${server.baseURL}/submit/event/manual`);
         ```
       - Improved code:
         ```javascript
         await page.getByRole('button', { name: 'Submit Event' }).click();

         // Verify validation triggered
         await expect(page).toHaveURL(`${server.baseURL}/submit/event/manual`);

         // Verify ARIA attributes for screen readers
         const titleInput = page.getByLabel('Event Title *');
         await expect(titleInput).toHaveAttribute('aria-invalid', 'true');
         await expect(titleInput).toHaveAttribute('aria-describedby');

         // Verify error message is linked and visible
         const errorId = await titleInput.getAttribute('aria-describedby');
         const errorMessage = page.locator(`#${errorId}`);
         await expect(errorMessage).toBeVisible();
         await expect(errorMessage).toContainText(/required/i);
         ```

    2. **Inefficient waitForFunction (4 instances)**
       - File: user-event-submission.spec.js:18-25, 93-99, 127-133, 184-190
       - Type: Performance - Slow JavaScript evaluation
       - Impact: Adds ~200ms per wait (800ms total)
       - Fix: Replace with native Playwright selector:
         ```javascript
         // Extract to helper in test-utils.js
         export async function waitForRegionSelect(page) {
             await page.waitForSelector('#region:not([disabled])', { state: 'attached' });
             await expect(page.locator('#region option')).toHaveCount({ min: 2 });
         }

         // Usage
         await waitForRegionSelect(page);
         ```
    ```

    ## Critical Rules

    **DO:**
    - Check EVERY form field for ARIA label verification
    - Identify ALL waitForFunction that could use waitForSelector
    - Suggest parallel execution for independent actions
    - Provide specific code examples for fixes
    - Estimate performance impact (milliseconds saved)

    **DON'T:**
    - Say "accessibility looks good" without checking ARIA attributes
    - Skip performance analysis
    - Give vague advice ("improve selectors")
    - Assume semantic selectors mean ARIA is present (verify!)
```

### 3. After Review

1. **Fix accessibility gaps** - Add ARIA verification to tests
2. **Add UI/layout tests** - Screenshot comparison, viewport testing
3. **Apply performance optimizations** - Replace slow patterns
4. **Run tests** - Verify improvements don't break functionality

## Related Commands

- **superpowers:code-reviewer** - The subagent this command invokes
- **/request-review** - General code review
- **/security-review** - Security-focused review
