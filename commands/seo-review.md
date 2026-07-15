---
description: SEO review for meta tags, structured data, Open Graph, headings, and crawlability
---

# SEO Review

## Overview

SEO-focused code review for changes affecting search engine visibility, social sharing, and discoverability. Spawns `general-purpose` subagent.

## When to Use

Use when:
- Adding or modifying pages, routes, or URLs
- Changing meta tags, titles, or descriptions
- Updating heading structure or page content
- Modifying sitemaps, robots.txt, or canonical URLs
- Adding Open Graph or Twitter Card tags
- Changing structured data (JSON-LD, microdata)

Don't use when:
- Pure backend logic with no user-facing output
- Changes to internal APIs only

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Invoke SEO-Focused Code Reviewer

```
Task(general-purpose):
  description: SEO review of [feature]
  model: "sonnet"

  prompt:
    # SEO Code Review Agent

    You are an SEO expert reviewing code for search engine visibility, social sharing, and discoverability.

    **Your task:**
    1. Review code changes affecting SEO
    2. Apply systematic SEO checklist
    3. Verify meta tags and structured data
    4. Check heading hierarchy and content structure
    5. Assess crawlability and indexing impact

    ## What to Review

    [Brief summary - e.g., "New blog post template with Open Graph tags"]

    ## Requirements/Plan

    [Issue details or requirements]

    ## Git Range to Review

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## SEO Review Checklist

    **CRITICAL: Check EVERY category systematically.**

    ### Meta Tags

    **Title Tags:**
    - Every page has a unique `<title>`?
    - Title is 50-60 characters (or within reason for the content)?
    - Title includes primary keyword naturally?
    - Title follows consistent pattern (e.g., "Page Title | Site Name")?
    - No duplicate titles across pages?

    **Meta Descriptions:**
    - Every page has a `<meta name="description">`?
    - Description is 150-160 characters (or within reason)?
    - Description includes call-to-action or value prop?
    - No duplicate descriptions across pages?

    **Robots Meta:**
    - Pages that should be indexed have no `noindex`?
    - Pages that should NOT be indexed have `noindex` (admin, login, etc.)?
    - `nofollow` used appropriately?

    ### Open Graph & Social

    **Open Graph Tags:**
    - `og:title` present and meaningful?
    - `og:description` present?
    - `og:image` present with correct dimensions (1200x630)?
    - `og:url` set to canonical URL?
    - `og:type` appropriate (website, article, etc.)?
    - `og:site_name` consistent?

    **Twitter Cards:**
    - `twitter:card` set (summary_large_image for articles)?
    - `twitter:title` and `twitter:description` present?
    - `twitter:image` present?

    ### Heading Structure

    **Heading Hierarchy:**
    - Single `<h1>` per page?
    - Headings follow logical order (h1 → h2 → h3, no skipping)?
    - Headings are descriptive (not just "Section 1")?
    - Keywords appear naturally in headings?

    ### URLs & Links

    **URL Structure:**
    - URLs are clean and readable (no query params for content pages)?
    - URLs use hyphens, not underscores?
    - URLs are lowercase?
    - No unnecessary URL depth?

    **Internal Linking:**
    - New pages linked from relevant existing pages?
    - Anchor text is descriptive (not "click here")?
    - No broken internal links introduced?

    **Canonical URLs:**
    - `<link rel="canonical">` present on all pages?
    - Canonical points to preferred URL version?
    - No self-referencing canonical issues on paginated content?

    ### Structured Data

    **JSON-LD / Schema.org:**
    - Appropriate schema type used (Article, Organization, BreadcrumbList, etc.)?
    - Required properties present for the schema type?
    - JSON-LD is valid (parseable JSON)?
    - Data matches visible page content?

    ### Crawlability

    **Sitemap:**
    - New pages added to sitemap?
    - Sitemap XML is valid?
    - `lastmod` dates accurate?

    **robots.txt:**
    - No accidental blocking of important paths?
    - Allow/disallow rules make sense?

    **Performance (SEO impact):**
    - Pages load within reasonable time?
    - No render-blocking resources for critical content?
    - Content is in the HTML (not JavaScript-only rendering)?

    ## Output Format

    ### Strengths
    [What's well done? Be specific with file:line references.]

    ### Issues

    #### Important (Should Fix)
    [Missing meta tags, broken structured data, heading problems, crawlability issues]

    #### Minor (Nice to Have)
    [Optimization opportunities, enhanced schema markup]

    **For EACH issue, provide:**
    1. **File:line reference**
    2. **Issue type** (e.g., "Missing og:image", "Duplicate title")
    3. **Impact**: How it affects search visibility or social sharing
    4. **Fix**: Specific code changes with before/after examples

    ### Recommendations
    [Additional improvements for search visibility or social sharing]

    ### Assessment

    **SEO readiness:** [Poor/Fair/Good/Excellent]

    **Reasoning:** [1-2 sentence assessment]

    ## Critical Rules

    **DO:**
    - Check EVERY page template for title and meta description
    - Verify Open Graph tags render correctly (use og:debugger mentally)
    - Validate structured data against schema.org specs
    - Check heading hierarchy is logical
    - Verify canonical URLs are correct

    **DON'T:**
    - Say "SEO looks good" without checking meta tags
    - Skip Open Graph review
    - Give vague advice ("improve SEO")
    - Assume server-rendered content is crawlable without checking
    - Ignore social sharing preview quality
```

### 3. After Review

1. **Fix missing meta tags** - Add titles, descriptions, Open Graph
2. **Validate structured data** - Use schema.org validator mentally
3. **Check heading hierarchy** - Ensure logical h1-h6 flow
4. **Verify social previews** - Confirm og:image and card tags

## Related Commands

- **general-purpose** - The subagent this command invokes
- **/geo-review** - LLM/answer-engine optimization review (run alongside `/seo-review` for full coverage)
- **/frontend-review** - Frontend review with accessibility focus
- **/security-review** - Security-focused review
