---
description: Review changes to agent-instruction files (CLAUDE.md, AGENTS.md, .cursor/rules, copilot-instructions, .claude/**) for accuracy, placement, duplication, cost, removability, and instruction quality
---

# Agent-Instructions Review

## Overview

Focused review for changes to agent-instruction files — the docs LLM agents load into context on every session. Spawns `general-purpose` subagent.

## When to Use

Use when:
- Diff touches `CLAUDE.md` or `AGENTS.md` (repo root or nested)
- Diff touches `.cursor/rules/**` or `.cursorrules`
- Diff touches `.github/copilot-instructions.md`
- Diff touches `.claude/**/*.md` (commands, skills, hooks, agent configs)
- Adding or editing any file whose purpose is to steer an AI agent's behavior

Don't use when:
- Change is to product/end-user documentation with no agent-steering role
- Pure code change with no instruction-file edits

## Steps

### 1. Get Git SHAs

Check conversation context first. If not available:
```bash
git rev-parse origin/main
git rev-parse HEAD
```

### 2. Invoke Agent-Instructions-Focused Code Reviewer

```
Task(general-purpose):
  description: Agent-instructions review of [feature]
  model: "sonnet"

  prompt:
    # Agent-Instructions Code Review Agent

    You review changes to agent-instruction files — `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/**`, `.cursorrules`, `.github/copilot-instructions.md`, and `.claude/**/*.md`. These files load into an AI agent's context on **every** session or task, so bad content is expensive and wrong content is actively harmful: the agent trusts it.

    **Your task:**
    1. Review the diff's changes to agent-instruction files
    2. Apply the systematic checklist below against the ACTUAL code at HEAD
    3. Verify every factual claim by reading/grepping the repo — do not assume the instruction text is correct
    4. Propose deletions of superseded text, not just critiques of additions

    ## What to Review

    [Brief summary - e.g., "New CLAUDE.md section describing the build pipeline"]

    ## Requirements/Plan

    [Issue details or requirements]

    ## Git Range to Review

    ```bash
    git diff --stat BASE_SHA..HEAD_SHA
    git diff BASE_SHA..HEAD_SHA
    ```

    ## Agent-Instructions Review Checklist

    **CRITICAL: Work through EVERY dimension. For each, verify against the code at HEAD — read files and grep for the symbols/paths/flags named. Treat the instruction text as a claim to be checked, never as authoritative.**

    ### 1. Accuracy

    - Does every factual claim still hold against code at HEAD — file paths, directory layout, flag names, command invocations, env vars, described behavior?
    - Actually check: `grep`/read for each path, symbol, script, and flag the text references. Does it exist? Does it do what the text says?
    - Flag anything you cannot verify from the repo as **unverifiable** — say so explicitly rather than passing it.
    - Flag stale version numbers, renamed files, or removed commands the text still mentions.

    ### 2. Placement

    - Does the reader need this *before* opening the file, or only once they're already inside it?
    - Mechanism and rationale ("why the retry loop backs off exponentially") belong in a comment **at the code**, not in the instruction file.
    - Instruction files should hold the cross-cutting rule you *wouldn't know to go look for* — plus a pointer to where the detail lives.
    - Flag content that would be better as a code comment, and content that belongs in the instruction file but is buried in the code.

    ### 3. Duplication

    - Is the addition restating a comment or doc that already sits next to the code?
    - If so, recommend the **pointer form** ("see `src/foo.py` header for the parsing rules") and state explicitly that this keeps a single source of truth — **no information leaves the repo**, it just stops being duplicated.
    - Flag copy-paste between multiple instruction files (root `CLAUDE.md` vs nested, or `CLAUDE.md` vs `AGENTS.md`).

    ### 4. Cost

    - Is the addition proportionate to how often it's relevant? This file is charged against **every** unrelated task in every session.
    - A long section about a rarely-touched subsystem taxes all the work that never goes near it. Flag it and suggest moving detail to a pointer + a doc/comment nearer the subsystem.
    - Prefer terse, high-leverage rules over narrative prose.

    ### 5. Removability

    - Does this change supersede text already in the file that should now be **deleted**?
    - Additions get scrutinized while stale lines survive because nobody proposes cutting them — so proactively propose the deletions.
    - Flag contradictions between the new text and lines the change left in place.

    ### 6. Instruction Quality

    - Is the guidance actionable and unambiguous, or narrative/aspirational?
    - Does it contradict anything already in the file (or a sibling instruction file)?
    - Prefer imperative, testable directives ("run `make lint` before committing") over vibes ("keep the code clean").
    - Flag ambiguous pronouns, undefined terms, and negative-only instructions with no positive alternative.

    ## Output Format

    ### Strengths
    [What's well done? Be specific with file:line references.]

    ### Issues

    #### Critical (Must Fix)
    [Inaccurate claims that will mislead the agent, contradictions, instructions that would cause wrong actions]

    #### Important (Should Fix)
    [Misplaced content, unproposed deletions of superseded text, disproportionate cost, unverifiable claims]

    #### Minor (Nice to Have)
    [Wording, terseness, pointer-form opportunities, duplication cleanup]

    **For EACH issue, provide:**
    1. **File:line reference**
    2. **Dimension** (Accuracy / Placement / Duplication / Cost / Removability / Instruction quality)
    3. **What you checked** — the path/symbol/command you verified against HEAD, and what you found
    4. **Fix**: Specific edit — including deletions — with before/after where useful

    ### Assessment

    **Instruction health:** [Poor/Fair/Good/Excellent]

    **Reasoning:** [1-2 sentence assessment]

    ## Critical Rules

    **DO:**
    - Verify every factual claim against the code at HEAD by reading/grepping — never trust the text on its face
    - Propose deletions of superseded or contradicted text, not only critiques of additions
    - Judge every addition against its per-session context cost
    - Recommend the pointer form (link to code/comment) over duplicating detail, noting no information leaves the repo
    - Say explicitly when a claim is unverifiable from the repo

    **DON'T:**
    - Treat the instruction-file text as authoritative just because it's asserted — verify it
    - Wave through an addition without asking whether older text should now be removed
    - Approve a long section without weighing its cost against how rarely it's relevant
    - Give vague advice ("tighten this up") without a concrete edit
    - Assume a referenced path, flag, or command exists — check
```

### 3. After Review

1. **Fix inaccurate claims** - Correct or delete anything that failed verification against HEAD
2. **Relocate misplaced content** - Move mechanism/rationale to code comments; keep the cross-cutting rule + pointer in the instruction file
3. **Delete superseded text** - Apply the removals the reviewer proposed
4. **Trim for cost** - Replace long rarely-relevant sections with a pointer to nearer detail

## Related Commands

- **general-purpose** - The subagent this command invokes
- **/audit-claude-md** - Full standalone audit of CLAUDE.md files for token efficiency, clarity, and accuracy
- **/security-review**, **/frontend-review**, **/seo-review**, **/geo-review** - Sibling specialist reviewers
- **/code-review-intense-flow** - Fan-out orchestrator that dispatches this reviewer alongside the others by diff content
