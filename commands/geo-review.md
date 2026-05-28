---
description: GEO review for LLM-citation content structure, llms.txt, schema markup, and AI crawler policy
---

# GEO Review

## Overview

GEO (Generative Engine Optimization) review for changes affecting how LLMs and AI answer engines (ChatGPT, Claude, Perplexity, Google AI Overviews) discover, extract, and cite content. Spawns `superpowers:code-reviewer` subagent.

GEO complements SEO: SEO optimizes for ranked link results, GEO optimizes for being cited inside generated answers. Run `/seo-review` for traditional search visibility and `/geo-review` for LLM/answer-engine visibility.

## When to Use

Use when:
- Adding or modifying content pages, blog posts, docs, or marketing copy
- Adding or updating `llms.txt` or `llms-full.txt`
- Changing structured data (JSON-LD, especially `FAQPage`, `HowTo`, `Article`, `Organization`)
- Updating author bios, About pages, or other E-E-A-T surfaces
- Modifying `robots.txt` rules for AI crawlers
- Adding factual claims, statistics, or original research to a page
- Restructuring content into Q&A, lists, or tables LLMs can extract

Don't use when:
- Pure backend logic with no user-facing content
- Internal admin pages explicitly excluded from LLM crawling

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Invoke GEO-Focused Code Reviewer

```
Task(superpowers:code-reviewer):
  description: GEO review of [feature]
  model: "sonnet"

  prompt:
    # GEO Code Review Agent

    You are a GEO (Generative Engine Optimization) expert reviewing code for how well LLMs and AI answer engines (ChatGPT, Claude, Perplexity, Google AI Overviews, etc.) can discover, extract, and cite this content.

    GEO is distinct from SEO. SEO optimizes for ranked link results; GEO optimizes for being cited inside a generated answer. Do not duplicate the SEO checklist — focus on what LLMs specifically reward.

    **Your task:**
    1. Review code changes affecting LLM/answer-engine visibility
    2. Apply systematic GEO checklist
    3. Verify content is structured for LLM extraction and citation
    4. Check llms.txt and schema markup useful for answer engines
    5. Surface AI crawler policy as a deliberate decision

    ## What to Review

    [Brief summary - e.g., "New product comparison page with FAQ section"]

    ## Requirements/Plan

    [Issue details or requirements]

    ## Git Range to Review

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## GEO Review Checklist

    **CRITICAL: Check EVERY category systematically. The field is shifting; flag anything ambiguous rather than guessing.**

    ### llms.txt / llms-full.txt

    - `llms.txt` present at site root?
    - Format follows the proposed spec (H1 site name, blockquote summary, sectioned link lists)?
    - Important pages (docs, key marketing, pricing) are listed?
    - `llms-full.txt` provided for documentation-heavy sites?
    - Links resolve and point to clean markdown or text where possible?
    - Stale entries removed when pages move or 404?

    ### Content Structure for LLM Extraction

    **Direct answers up front:**
    - Does the first paragraph (or first ~50 words) directly answer the page's implied question?
    - Is the "TL;DR" / summary extractable without scrolling past hero imagery or marketing fluff?

    **Atomic factual claims:**
    - Are claims stated as discrete, self-contained sentences (vs. buried in long paragraphs)?
    - Can each claim be quoted by an LLM without losing context?

    **Q&A patterns:**
    - Section headings phrased as questions a user would actually ask an LLM?
    - Answers placed immediately under the question heading?

    **Lists, tables, and comparisons:**
    - Comparison content uses real tables, not prose?
    - Steps use ordered lists?
    - Specs/properties use definition lists or tables?

    **Definitions and glossary terms:**
    - Key terms defined inline on first use?
    - Glossary or definition page exists for domain-specific terminology?

    ### Citation-Worthiness

    **Sources and evidence:**
    - Factual claims, statistics, and numbers cite a source (with link or attribution)?
    - Original research, surveys, or proprietary data clearly labeled as such (LLMs preferentially cite original sources)?
    - Quotes attributed to named people with their role?

    **Author and freshness signals:**
    - Visible author byline with link to author bio?
    - Visible publication date AND last-updated date?
    - "Reviewed by" / "Fact-checked by" surfaces where appropriate?

    ### Schema.org for LLMs

    **High-leverage schema types:**
    - `FAQPage` schema on pages with Q&A content?
    - `HowTo` schema on step-by-step guides?
    - `Article` (or `BlogPosting`/`NewsArticle`) with `author`, `datePublished`, `dateModified`, `headline`?
    - `Organization` schema with `name`, `url`, `logo`, and `sameAs` linking to Wikipedia/Wikidata/social profiles for entity grounding?
    - `Person` schema on author pages with `sameAs`?
    - `BreadcrumbList` for hierarchical context?

    **Schema quality:**
    - JSON-LD validates as JSON?
    - Schema content matches visible page content (no cloaking)?
    - No conflicting schema types on the same page?

    ### Entity and Brand Signals (E-E-A-T)

    - Brand/product name used consistently (same spelling, capitalization, spacing) across pages?
    - About page exists and clearly identifies the organization?
    - Author bios establish Experience / Expertise (credentials, prior work, links)?
    - External corroboration linked where it exists (Wikipedia, Wikidata, industry registries)?
    - Contact and ownership info easy to find (LLMs use these as trust signals)?

    ### AI Crawler Policy (robots.txt)

    **Surface the policy as a deliberate decision — do not assume the user wants to allow or block. Flag misconfigurations and missing rules.**

    Bots to check for (current as of late 2025 / early 2026 — verify before recommending):

    | Bot | Operator | Purpose |
    |---|---|---|
    | `GPTBot` | OpenAI | Training |
    | `OAI-SearchBot` | OpenAI | SearchGPT indexing |
    | `ChatGPT-User` | OpenAI | On-demand fetches from ChatGPT |
    | `ClaudeBot` | Anthropic | Training |
    | `anthropic-ai` | Anthropic | Legacy / general |
    | `Claude-Web` | Anthropic | On-demand fetches |
    | `PerplexityBot` | Perplexity | Indexing |
    | `Perplexity-User` | Perplexity | On-demand fetches |
    | `Google-Extended` | Google | Gemini / AI Overviews training opt-out token |
    | `Applebot-Extended` | Apple | Apple Intelligence opt-out token |
    | `CCBot` | Common Crawl | Training data source for many LLMs |
    | `Bytespider` | ByteDance | Training |
    | `Amazonbot` | Amazon | Alexa / general |
    | `Meta-ExternalAgent` | Meta | Training |

    **Check:**
    - `robots.txt` exists and is reachable?
    - Each major bot is either explicitly Allow'd or Disallow'd (not silently default-allowed)?
    - Policy is internally consistent (e.g., not blocking GPTBot but allowing CCBot, which feeds the same training pipeline — unless that's intentional)?
    - On-demand user-fetch bots (`ChatGPT-User`, `Perplexity-User`, `Claude-Web`) treated separately from training bots if the site wants citations but not training use?
    - Comments in `robots.txt` explain intent for future maintainers?

    **Do NOT recommend allow or block.** Report the current policy, flag inconsistencies, and ask the user to confirm intent.

    ### Page-Level Freshness and Canonical Signals

    - Visible `Published` / `Updated` dates on time-sensitive content?
    - `dateModified` in schema matches the visible "Updated" date?
    - Canonical URL present and points to the version LLMs should cite?
    - No duplicate content across URLs that would split citation signal?

    ## Output Format

    ### Strengths
    [What's well done for LLM citation? Be specific with file:line references.]

    ### Issues

    #### Important (Should Fix)
    [Missing llms.txt, no author/date signals, schema validation errors, content structure that buries answers, AI crawler policy inconsistencies]

    #### Minor (Nice to Have)
    [Additional schema types, more granular Q&A structure, glossary additions]

    **For EACH issue, provide:**
    1. **File:line reference**
    2. **Issue type** (e.g., "Missing FAQPage schema", "First paragraph buries the answer")
    3. **Impact**: How it affects LLM citation likelihood or answer-engine visibility
    4. **Fix**: Specific code changes with before/after examples

    ### Decisions to Confirm
    [AI crawler policy questions, schema choices that depend on intent — surface for the user, do not decide for them]

    ### Recommendations
    [Additional improvements for LLM citation, entity grounding, or content extractability]

    ### Assessment

    **GEO readiness:** [Poor/Fair/Good/Excellent]

    **Reasoning:** [1-2 sentence assessment]

    ## Critical Rules

    **DO:**
    - Check whether the first paragraph answers the page's implied question
    - Verify `llms.txt` if the project has one, and flag its absence on content-heavy sites
    - Validate JSON-LD parses and that schema content matches visible content
    - Check all listed AI bots are explicitly handled in `robots.txt`
    - Treat citation-worthiness (sources, original data, named authors, dates) as first-class

    **DON'T:**
    - Duplicate the SEO checklist — focus on LLM-specific concerns
    - Recommend allow or block for AI crawlers without the user's explicit intent
    - Assume current bot user-agent strings are stable; flag uncertainty
    - Treat keyword density as a GEO signal (it's an SEO concept, not a GEO one)
    - Say "GEO looks good" without checking content structure and schema
```

### 3. After Review

1. **Add/update `llms.txt`** - Ensure key pages are listed and links resolve
2. **Restructure buried answers** - Move direct answers to the first paragraph
3. **Add schema markup** - `FAQPage`, `HowTo`, `Article`, `Organization` with `sameAs`
4. **Confirm AI crawler policy** - Decide allow/block per bot, document intent in `robots.txt` comments
5. **Surface freshness signals** - Visible `Updated` dates and matching `dateModified` in schema

## Related Commands

- **superpowers:code-reviewer** - The subagent this command invokes
- **/seo-review** - Traditional SEO review (run alongside `/geo-review` for full coverage)
- **/frontend-review** - Frontend review with accessibility focus
