---
description: GEO review for LLM-citation visibility — runs in diff mode (per-PR extraction checks) or site mode (cross-page entity consistency, claim contradictions, schema graph)
---

# GEO Review

## Overview

GEO (Generative Engine Optimization) review for how LLMs and AI answer engines (ChatGPT, Claude, Perplexity, Google AI Overviews) discover, extract, and cite content.

GEO operates on two distinct mechanisms, and they fail differently:

| Layer | Question it answers | Unit of analysis | Fails via |
|---|---|---|---|
| **Extraction** | Can a model cleanly lift and cite *this page*? | The page / the diff | Buried answers, unstructured claims, missing schema |
| **Entity** | Would a model recommend *this site* unprompted? | The whole site, over time | Contradictory claims across pages, weak or ambiguous brand identity |

Most GEO tooling only checks extraction, because extraction is visible in a changeset. Entity defects are invisible to any diff — they emerge when one page grows and another doesn't. **This command therefore has two modes.** Run diff mode at PR time and site mode on a schedule.

Run `/seo-review` alongside this for ranked-link visibility.

## When to Use

**Diff mode** — use when:
- Adding or modifying content pages, blog posts, docs, or marketing copy
- Changing structured data (JSON-LD)
- Updating author bios, About pages, or other E-E-A-T surfaces
- Modifying `robots.txt` rules for AI crawlers
- Adding factual claims, statistics, or original research
- Restructuring content into Q&A, lists, or tables

**Site mode** — use when:
- On a schedule (monthly/quarterly), regardless of what changed
- Before a rebrand, repositioning, or major scope expansion
- After the product has outgrown its original description
- Whenever the site's scale, geography, or offering has changed materially since the About page was written
- An external GEO audit returned a finding you can't reproduce from a single page

Don't use when:
- Pure backend logic with no user-facing content
- Internal admin pages explicitly excluded from LLM crawling

---

## Step 1: Determine Mode

If the user specified a mode, use it. Otherwise infer: a git range or PR context in conversation implies diff mode; a bare URL or "audit the site" implies site mode. **If it's ambiguous, ask** — the two modes produce very different reports.

If the user is running diff mode and the site hasn't had a site-mode pass in the last quarter, say so once at the end. Don't block on it.

---

## Step 2a: Diff Mode — Capture the Change

Check conversation context first. If not available:

```bash
git rev-parse origin/main
git rev-parse HEAD
git diff --stat BASE_SHA..HEAD_SHA
```

---

## Step 2b: Site Mode — Capture the Corpus

Site mode needs *rendered output*, not source. Several high-impact defects (geo-personalized content, relative `og:image`, template syntax leaking as literal text, per-crawler divergence) exist only in what a bot actually receives.

**Fetch a fixed key-page set.** At minimum: homepage, About, Contact, one representative content page, and any pricing/product page.

```bash
SITE="https://example.com"
mkdir -p "${TMPDIR:-/tmp}/geo-corpus"
CORPUS="${TMPDIR:-/tmp}/geo-corpus"

for path in "/" "/about" "/contact" "/pricing"; do
  slug=$(echo "$path" | tr '/' '_')
  curl -sSL "$SITE$path" -o "$CORPUS/default$slug.html"
done
```

**Fetch again as AI crawlers and diff.** Divergence between these is a finding, not a curiosity — it means each engine ingests a different version of the entity.

```bash
for ua in "GPTBot/1.2 (+https://openai.com/gptbot)" \
          "ClaudeBot/1.0 (+claudebot@anthropic.com)" \
          "PerplexityBot/1.0 (+https://perplexity.ai/perplexitybot)"; do
  curl -sSL -A "$ua" "$SITE/" -o "$CORPUS/$(echo "$ua" | cut -d/ -f1).html"
done

diff "$CORPUS/default_.html" "$CORPUS/GPTBot.html" || true
```

**Extract the structured data separately**, since most HTML-to-text extractors silently drop `<script>` blocks:

```bash
for f in "$CORPUS"/*.html; do
  echo "=== $f"
  python3 -c "
import sys, re, json
html = open(sys.argv[1], encoding='utf-8', errors='replace').read()
for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S|re.I):
    try:
        print(json.dumps(json.loads(m), indent=2)[:2000])
    except json.JSONDecodeError as e:
        print(f'INVALID JSON-LD: {e}')
" "$f"
done
```

**Flag if the site is geo-personalized.** If the homepage varies by requesting IP, crawler-facing content is non-deterministic across crawls. Note it explicitly — it undermines every other entity signal on the page.

---

## Step 3: Invoke the Reviewer

```
Task(general-purpose):
  description: GEO review of [feature or site]
  model: "sonnet"

  prompt:
    # GEO Review Agent

    You are reviewing how well LLMs and answer engines can discover, extract,
    and cite this content. GEO is distinct from SEO: SEO optimizes for ranked
    link results, GEO optimizes for being cited inside a generated answer.

    ## Mode
    [diff | site]

    ## What to Review
    [Brief summary]

    ## Inputs
    [Git range for diff mode, or geo-corpus paths + extracted JSON-LD for site mode]

    ## Checklist
    [Sections A–H below. Run ALL of them. In diff mode, section A is
    best-effort — flag anything you cannot verify from the diff alone and
    recommend a site-mode pass rather than guessing.]
```

---

# The Checklist

**Run every section. The field is unsettled — flag ambiguity rather than guessing.**

## A. Entity Layer

*Primary in site mode. In diff mode, check only what the changed files reveal, and say so.*

### A1. Claim consistency matrix

This is the highest-value check in the entire command, and it is the one a diff can never perform.

Extract every assertion about **scope, scale, geography, ownership, offering, pricing, and stage** from each key page. Build a matrix and compare rows against each other:

| Claim | Homepage | About | Footer | Meta description | Conflict? |
|---|---|---|---|---|---|
| Geographic scope | | | | | |
| Scale (counts) | | | | | |
| What it is | | | | | |
| Who runs it | | | | | |
| Commercial stage | | | | | |

**Any contradiction is an Important finding.** A model deciding what an organization *is* leans hardest on the About page; if that page contradicts the homepage, the About page usually wins and the site is described wrongly.

Watch specifically for **drift**: the homepage evolves as the product grows while the About page keeps the founding description. This is the single most common entity defect and it produces zero diff noise.

### A2. Entity graph, not entity presence

Do not check "is there `Organization` schema?" — that boolean passes on nested organizations that describe someone else entirely (an event's organizer, an article's publisher, a job's hiring company).

Check instead:
- Is there a **site-level publisher entity** with a stable `@id`?
- Is it **distinct from** nested organization entities elsewhere in the graph?
- Do content pages **reference** it (`"publisher": {"@id": "..."}`) rather than each asserting a fresh orphan entity?
- Does `sameAs` **resolve**, and does it disambiguate the brand from unrelated meanings of the same words?

`sameAs` matters most when the brand name collides in general search. If the name is a common phrase, `sameAs` is the primary disambiguation mechanism available, and its absence is Important rather than Minor.

### A3. Distinctiveness

Apply the removal test to every description, title, and meta description:

> Delete the brand name. Is the sentence still identifiably about this site, or could a competitor paste it verbatim?

If a competitor could paste it, it's generic, and a model has nothing ownable to say about you when asked "what are good sites for X?" This is a GEO failure even though it involves no markup.

Also check: **is the strongest description on the site actually deployed where it counts?** Sites frequently bury their most distinctive sentence on the About page while shipping a generic meta description. See `talk-about-us` for the full framework.

### A4. Naming and terminology consistency

- Brand name spelling, capitalization, and spacing identical everywhere?
- Primary content nouns consistent site-wide (not "organisations" on one page and "organizations" on another)?
- Navigation and footer labels stable across pages, or do the same destinations get different names?
- Page titles carry the brand where entity grounding matters? A title of literally `About` wastes the single most entity-relevant title on the site.

---

## B. Extraction Layer

*Primary in diff mode.*

**Direct answers up front:**
- Does the first paragraph (or first ~50 words) directly answer the page's implied question?
- Is the summary extractable without scrolling past hero imagery, interstitials, or ad slots?
- **Check DOM order, not visual order.** Ads, banners, and consent interstitials placed above the logo mean the first content a model ingests is a third party's.

**Atomic factual claims:**
- Claims stated as discrete, self-contained sentences rather than buried mid-paragraph?
- Can each claim be quoted without losing its context?

**Q&A patterns:**
- Headings phrased as questions a user would actually ask an LLM?
- Answers placed immediately under the question heading?

**Lists, tables, comparisons:**
- Comparison content in real tables, not prose?
- Steps in ordered lists? Specs in definition lists or tables?

**Definitions:**
- Key terms defined inline on first use? Glossary for domain-specific terminology?

---

## C. Citation-Worthiness

- Statistics and numbers cite a source with link or attribution?
- Original research or proprietary data clearly labelled as such? Models preferentially cite original sources.
- Quotes attributed to named people with their role?
- Visible author byline linking to an author bio?
- Visible publication date **and** last-updated date?

**Precise counts age badly.** A meta description containing an exact live figure will be stale within hours and models cache descriptions. Prefer a rounded figure in cached surfaces; keep the exact number in visible page content where it's evidently live.

---

## D. Schema Quality

- `Article` / `BlogPosting` with `author`, `datePublished`, `dateModified`, `headline`?
- `FAQPage` on genuine Q&A content; `HowTo` on step-by-step guides?
- `Person` on author pages with `sameAs`?
- `BreadcrumbList` for hierarchical context?
- JSON-LD parses as valid JSON?
- Schema content matches visible content (no cloaking)?
- No conflicting or duplicate types on the same page?
- Entity references connect across pages via `@id` (see A2)?

---

## E. Rendered Output

*Site mode. These defects are invisible in source review.*

- `og:image` and other social URLs **absolute**, not relative? Many scrapers won't resolve relative paths.
- Templating or markdown syntax leaking as literal text (`</submit/event>`, unrendered `{{ }}`, raw autolinks)?
- Content varying by requesting IP, session, or A/B bucket? Flag as non-deterministic entity signal.
- Crawler-UA responses matching the default response (from Step 2b)?
- Canonical present and pointing at the version you want cited?
- No duplicate content across URLs splitting citation signal?

---

## F. AI Crawler Policy

**Surface the policy as a deliberate decision. Do NOT recommend allow or block.** Report the current state, flag inconsistencies, and ask the user to confirm intent.

| Bot | Operator | Purpose |
|---|---|---|
| `GPTBot` | OpenAI | Training |
| `OAI-SearchBot` | OpenAI | SearchGPT indexing |
| `ChatGPT-User` | OpenAI | On-demand fetches |
| `ClaudeBot` | Anthropic | Training |
| `anthropic-ai` | Anthropic | Legacy / general |
| `Claude-Web` | Anthropic | On-demand fetches |
| `PerplexityBot` | Perplexity | Indexing |
| `Perplexity-User` | Perplexity | On-demand fetches |
| `Google-Extended` | Google | Gemini / AI Overviews opt-out token |
| `Applebot-Extended` | Apple | Apple Intelligence opt-out token |
| `CCBot` | Common Crawl | Feeds many training pipelines |
| `Bytespider` | ByteDance | Training |
| `Amazonbot` | Amazon | General |
| `Meta-ExternalAgent` | Meta | Training |

**This table drifts. Verify current user-agent strings before recommending anything, and flag your uncertainty rather than asserting stale strings.**

Check:
- `robots.txt` exists and is reachable?
- Each major bot explicitly allowed or disallowed, not silently default-allowed?
- Policy internally consistent — e.g. blocking `GPTBot` while allowing `CCBot`, which feeds the same pipelines, unless that's intentional?
- On-demand fetch bots treated separately from training bots, if the site wants citations without training use?
- Comments explaining intent for future maintainers?

---

## G. Freshness and Canonical

- Visible `Published` / `Updated` dates on time-sensitive content?
- `dateModified` in schema matching the visible updated date?
- Stale content that would be cited as current?

---

## H. Cheap Hygiene

Low cost, low current impact. **Do not lead a report with these.** Adoption among answer engines is marginal, Google has stated on the record that it doesn't support `llms.txt`, and crawler fetches of it are a rounding error against total AI bot traffic. Ship one because it's an hour's work and a cheap forward bet — not because it moves citations today.

- `llms.txt` present at site root, following the proposed spec (H1 name, blockquote summary, sectioned link lists)?
- Links resolve; stale entries removed?
- `llms-full.txt` for documentation-heavy sites?

If `llms.txt` is the most significant finding in a report, the report has not looked hard enough at sections A–E.

---

# Output Format

### Strengths
What's well done, with `file:line` references (diff mode) or page + selector (site mode).

### Issues

#### Important (Should Fix)
Cross-page claim contradictions, missing or orphaned publisher entity, generic descriptions failing the removal test, buried answers, non-deterministic crawler content, schema validation errors, crawler policy inconsistencies.

#### Minor (Nice to Have)
Additional schema types, finer Q&A structure, glossary additions, `llms.txt` gaps.

**For each issue provide:**
1. **Location** — `file:line`, or page URL + element
2. **Issue type**
3. **Impact** — how it affects citation likelihood or entity resolution
4. **Fix** — specific before/after

### Decisions to Confirm
Crawler policy questions, positioning choices that depend on intent. Surface, don't decide.

### Assessment

Report **two independent scores**. They have different fixes and conflating them hides the diagnosis.

**Extraction readiness:** [Poor/Fair/Good/Excellent] — can a model cleanly lift and cite these pages?

**Entity strength:** [Poor/Fair/Good/Excellent] — would a model recommend this site unprompted, and does it describe the site correctly?

**Reasoning:** 1–2 sentences each.

A site can be Excellent on extraction and Poor on entity. That combination means individual pages get cited when someone already found you, but nothing recommends you to someone who hasn't.

---

# Critical Rules

**DO:**
- Ask which mode to run when it's ambiguous
- Treat cross-page claim contradictions as the highest-severity finding class
- Test the entity *graph*, not the presence of a schema type
- Apply the brand-removal test to every description
- Check rendered output, not just source
- Verify JSON-LD parses and matches visible content
- Treat citation-worthiness (sources, original data, named authors, dates) as first-class
- Flag anything you cannot verify from the inputs you were given

**DON'T:**
- Report a diff-mode pass as a site-wide clean bill of health
- Lead with `llms.txt`
- Recommend allow or block for AI crawlers without explicit user intent
- Assume current bot user-agent strings are stable
- Treat keyword density as a GEO signal
- Say "GEO looks good" without checking sections A through E
- Enforce a hard SEO/GEO partition. Where a signal serves entity resolution — title quality, canonical, crawlability — check it here even if `/seo-review` also owns it. A defect falling between two commands is worse than a duplicated finding.

---

# After Review

1. **Reconcile contradicted claims first.** Rewriting one About paragraph typically outweighs every markup change in the report.
2. **Establish the publisher entity** with a stable `@id` and resolving `sameAs`, then reference it from content pages.
3. **Rewrite descriptions that fail the removal test**, and promote the site's strongest existing sentence into its cached surfaces.
4. **Fix rendered-output defects** — absolute social URLs, leaked template syntax, crawler-facing determinism.
5. **Restructure buried answers** and add extraction-oriented schema.
6. **Confirm crawler policy** and document intent in `robots.txt` comments.
7. **Add or refresh `llms.txt`** last.

# Related Commands

- **`/seo-review`** — ranked-link visibility; run alongside this
- **`talk-about-us`** — shareability and distinctiveness framework; feeds section A3
- **`/frontend-review`** — frontend review with accessibility focus
