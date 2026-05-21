# Adversarial Review Scope Discipline Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `skills/adversarial-review/SKILL.md` to enforce scope discipline (hard-gate scope/threat-model preamble, caller-supplied round number with diminishing-returns prompt, verbatim reviewer brief with anti-splitting and falsifying-tests rules, mandatory triage) so finding-count inflation across rounds is structurally blocked — per [issue #11](https://github.com/oalders/kitchen-sink/issues/11) and the approved spec at `docs/superpowers/specs/2026-05-21-adversarial-review-scope-discipline-design.md`.

**Architecture:** Single skill-file rewrite (22 → ~170 lines) plus a plugin-major version bump in three locations. This is a breaking change to the skill's invocation contract — callers must now supply a scope preamble and a round number, or the skill aborts. No code, no tests, no external dependencies — pure prompt design.

**Tech Stack:** Markdown (the skill is a markdown file with YAML frontmatter). JSON (the version bumps). Bash + Edit + Write tools. No language toolchain.

---

## Background — read this before Task 1

The current skill (`skills/adversarial-review/SKILL.md`, 22 lines) has one instruction: tell two subagents that "whoever finds the largest number of serious issues gets five points." In a real 5-round review of a `WWW::RobotRules::parse` patch, this produced a treadmill — finding count stayed high while real-defect convergence stalled by round 3, because reviewers were rewarded for *volume*, had no scope to filter against, and their "the patch should also handle X" findings grew surface that the next round attacked.

The rewrite addresses six failure modes (full enumeration in the spec, lines 17-22). The structural blocks the spec puts in place:

| Failure mode | Structural block |
|---|---|
| #1 No scope/threat model | Hard-gate preamble — skill aborts without it |
| #2 Volume incentive | Scoring rewards in-scope defects with repros only; out-of-scope findings worth zero points; anti-splitting rule prevents micro-finding gaming |
| #3 "Patch should also X" growth | Explicit zero-point category in scoring; reiterated in DO NOT instructions |
| #4 Passive aggregation | Mandatory triage step (in-scope / out-of-scope / wontfix) before presenting to user |
| #5 No diminishing-returns signal | Round-number gate prompts simplification at round >= 3 |
| #6 Tests as theatre | Required "Tests Verified Falsifying" section with reason-from-assertion check |

The full design — including verbatim reviewer-brief template — is in the spec. **Task 1 below contains the complete new SKILL.md content; you don't need to assemble it from the spec.**

---

## Task 1: Rewrite the adversarial-review skill

**Files:**
- Modify: `skills/adversarial-review/SKILL.md` (full rewrite — replace entire file)

The current file is 22 lines and instructs two subagents to compete on raw finding count. Replace it with the content below verbatim. This is the load-bearing artifact — exact wording matters; do not paraphrase.

- [ ] **Step 1: Confirm current state**

Run: `wc -l skills/adversarial-review/SKILL.md && head -5 skills/adversarial-review/SKILL.md`
Expected: ~22 lines, frontmatter starts with `---` and `name: adversarial-review`. If the file already has the new content (line count ~170, frontmatter version 2.0.0), skip this task entirely.

- [ ] **Step 2: Replace the file with the new content**

Use the `Write` tool to overwrite `skills/adversarial-review/SKILL.md` with **exactly** this content (the triple-backtick fences below mark the file boundary — do NOT include the outer fence in the file):

````markdown
---
name: adversarial-review
description: Use when the user asks for an "adversarial review", "review this adversarially", or wants two reviewers competing to find serious issues in code or other work. Enforces scope discipline so findings count doesn't inflate across rounds.
version: 2.0.0
---

# Adversarial Review

Two subagents review the same work in parallel, competing under an incentive that rewards in-scope defects with working repros and penalizes nit-padding and feature-proposal drift. The skill enforces scope discipline up front and triages findings against scope before presenting them.

**The failure mode this skill prevents**: without scope, reviewers find "everything" — theoretical contract gaps, "what if a future caller does X" cases, POD nits — and fixes accumulate surface that the next round attacks. Findings count stays high while real signal converges to zero.

## When to Use

- The user asks for an "adversarial review", "review this adversarially", or wants two reviewers competing.
- You have a concrete patch, PR, plan, or change to review (not an open-ended question).
- You can supply the scope preamble (see Step 1).

If you can't supply the preamble, this is the wrong skill. Use `superpowers:requesting-code-review` or `/request-review` instead — those don't require scope to work.

## Required Inputs

The caller MUST provide all of the following. If any is missing, abort with the message in Step 1 or Step 2 — do not improvise defaults, do not dispatch with placeholders.

1. **Scope preamble** (Step 1): invariants, threat model, out-of-scope list.
2. **Round number** (Step 2): positive integer counting this invocation.
3. **Work under review**: a patch ref, diff, or file paths.

## Step 1: Scope preamble (hard gate)

Before dispatching, the caller MUST supply:

1. **Invariants** (1-3, crisp): what does the patch claim to make true?
2. **Threat model**: who is the attacker, what's their leverage, what's the impact target?
3. **Out-of-scope list**: which kinds of findings are not in scope? (e.g. "feature proposals", "theoretical contract gaps", "documentation wording")

If the caller can't supply these, **abort** with this exact message:

> adversarial-review requires scope to work. Without invariants and a threat model, reviewers will pad with nits and propose features instead of finding defects. Please supply: (1) invariants the patch claims, (2) threat model, (3) explicit out-of-scope list. Then re-invoke.

Do NOT dispatch with improvised defaults. Do NOT proceed.

## Step 2: Round-number gate

The caller MUST state which round this is — a positive integer (1, 2, 3, ...) where the number counts *the current invocation including this one*. So "round 1" means first invocation on this patch; "round 3" means this is the third.

If the caller can't supply a round number, or supplies something other than a positive integer, abort with the same posture as Step 1 (round number is part of the required input).

If round is 1 or 2: proceed silently to Step 3.

If round >= 3: pause and surface this to the user verbatim (substitute N with the caller-supplied round number, which includes the current invocation):

> You're about to run adversarial-review for the Nth time on this patch. If findings haven't converged, more rounds usually won't help — every fix creates new surface for the next round to attack. Consider **simplifying the patch** (shrink to one or two invariants) instead of adding another round. Continue anyway? [yes / step back]

Only dispatch if the user confirms "yes" (or equivalent affirmation). If the user picks "step back" or asks to simplify, exit without dispatching.

## Step 3: Assemble reviewer brief (verbatim template)

Paste this brief, verbatim, to each subagent (substituting `{...}` placeholders with the caller-supplied content from Step 1 and the work-under-review reference):

```
You are one of two reviewers competing to find serious issues in this work.

WORK UNDER REVIEW: {patch ref / diff / file paths}

INVARIANTS THIS PATCH CLAIMS:
{invariants from preamble}

THREAT MODEL:
{threat model from preamble}

OUT OF SCOPE — these findings are worth ZERO points:
{out-of-scope list from preamble}
- Findings that propose new behavior, new gates, or new discriminators
- Findings that propose the patch should "also handle X" beyond stated invariants
- Documentation/wording nits

SCORING:
Five points go to the reviewer who finds the most IN-SCOPE DEFECTS WITH WORKING
REPROS. A finding without a repro is worth zero points. A finding that proposes
new behavior is worth zero points.

Anti-splitting rule: findings that share the same invariant violation count as
ONE finding for scoring, no matter how many input variants you list. Don't
split "URL parser breaks" into separate findings for http://, https://, file://.
Pick the strongest single repro and list the variants under it.

A test-quality finding counts only if you can argue, citing the specific
assertion in the test, why the test would PASS against deliberately broken
(pre-patch) code — otherwise the test is real and your finding is theatre.
You don't need to execute the pre-patch code; reason from the assertion.

REQUIRED OUTPUT SECTIONS (use these exact headings):

## Findings
For each finding:
- Title
- Severity (Critical / Important / Minor)
- Invariant violated: {which stated invariant}
- Repro: {minimal code or input sequence demonstrating the defect; list
  additional variants here, not as separate findings}

## Tests Verified Falsifying
For each test the patch adds/modifies that you ACCEPT as real:
- Test name
- Argue why it would FAIL against pre-patch code: {cite the assertion and
  the pre-patch behavior the assertion would catch}
For each test you REJECT as theatre:
- Test name
- Argue why it would PASS against deliberately broken code: {cite the
  assertion and the trivially-true condition it actually checks}

## Hypotheses Checked Clean
For each attack lane or concern you investigated and dismissed:
- Lane: {what you considered}
- Verdict: {why it's not exploitable / why it's out of scope}

DO NOT propose new features. DO NOT propose new gates or discriminators. DO NOT
flag wording nits. If you're unsure whether a finding is in scope, write it
under "Hypotheses Checked Clean" with your reasoning, not under "Findings".
```

## Step 4: Dispatch in parallel

Use the Agent tool to launch two `general-purpose` subagents in a single message (so they run in parallel). Both get the identical brief from Step 3.

## Step 5: Aggregate + triage

When both subagents return, for each unique finding (after deduplication across the two reviewers), classify as:

- **in-scope** — violates a stated invariant or breaks legitimate use; has a working repro
- **out-of-scope** — proposes new behavior, gates, or discriminators; or extends surface beyond stated invariants
- **wontfix** — cosmetic, style, doc wording

Present only **in-scope** items as actionable. For each out-of-scope finding, write a one-line rejection that names which scope rule excluded it. This step is mandatory — do not pass raw reviewer output through to the user.

## Step 6: Present to user

Structure the final output as:

```
## Actionable findings (in-scope)
{ranked by severity, with repros}

## Hypotheses checked clean
{merged from both reviewers — surface what was investigated and came up empty}

## Out-of-scope findings (rejected)
{one line each, with the scope rule that excluded them — so the user can override if they disagree}

## Tests flagged as theatre
{if any}
```

## Common Mistakes

| Mistake | Fix |
|---|---|
| Dispatching without preamble | Skill should refuse — re-read Step 1 |
| Improvising the preamble yourself | Ask the caller; aborting is the right move when scope is unknown |
| Accepting findings without repros | Zero-point findings; don't present them |
| Pass raw reviewer output to user | Triage step (Step 5) is mandatory |
| Run round 4+ without simplifying | Diminishing returns — shrink the patch first |
| Treat "the patch should also do X" as a finding | That's a feature proposal — out of scope |
| Accept new tests without falsification check | Tests that pass against broken code are theatre |
| Paraphrase the reviewer brief | Paste verbatim — the exact wording is what eliminates round-to-round variance |

## Source

Original technique: https://blog.fsck.com/2026/05/01/adversarial-review/

Scope-discipline rewrite motivated by GitHub issue #11 (worked example: 5-round review of a `WWW::RobotRules::parse` patch where finding count stayed high but real-defect convergence stalled by round 3).
````

- [ ] **Step 3: Verify the new file**

Run: `wc -l skills/adversarial-review/SKILL.md && head -5 skills/adversarial-review/SKILL.md && tail -5 skills/adversarial-review/SKILL.md`
Expected:
- Line count: between 160 and 200 (the spec estimates ~170).
- Frontmatter starts with `---` then `name: adversarial-review`.
- Frontmatter contains `version: 2.0.0`.
- File ends with the Source section mentioning issue #11.

Also run: `grep -c "^## " skills/adversarial-review/SKILL.md`
Expected: 11 (When to Use, Required Inputs, Step 1, Step 2, Step 3, Step 4, Step 5, Step 6, Common Mistakes, Source — plus one inside the reviewer brief that lives inside a code fence and won't match the `^## ` anchor, so just the 10 top-level. Adjust expectation to 10 if grep reports that.).

If the file looks wrong, do NOT commit — re-read this task and fix.

- [ ] **Step 4: Commit**

```bash
git add skills/adversarial-review/SKILL.md
git commit -m "adversarial-review: rewrite with scope discipline (closes #11)

Hard-gate scope/threat-model preamble. Caller-supplied round number with
diminishing-returns prompt at round >= 3. Verbatim reviewer brief with
anti-splitting rule and reason-from-assertion falsifying-tests check.
Mandatory triage in aggregation. Breaking change to invocation contract."
```

---

## Task 2: Bump plugin versions to 2.0.0

**Files:**
- Modify: `.claude-plugin/plugin.json` (top-level `version`)
- Modify: `.claude-plugin/marketplace.json` (`metadata.version` and `plugins[0].version`)

Per the spec, this is a breaking change → major bump. All three strings must match exactly (per `CLAUDE.md` — the plugin cache serves stale versions otherwise).

- [ ] **Step 1: Confirm current versions**

Run: `grep -n '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json`
Expected output (line numbers may shift slightly if the files have been edited since this plan was written; the three matches and their values are what matter):
```
.claude-plugin/plugin.json:3:  "version": "1.14.0",
.claude-plugin/marketplace.json:9:    "version": "1.14.0"
.claude-plugin/marketplace.json:16:      "version": "1.14.0",
```

Note the two `marketplace.json` lines differ: the metadata version (4-space indent, no trailing comma) and the plugins-entry version (6-space indent, trailing comma). The Edit tool's `old_string` match keys off the full line including whitespace, so each is uniquely identifiable.

If any version is already 2.0.0, that location is done; skip the matching step below. If versions are not all 1.14.0, STOP — the spec assumed 1.14.0 as the baseline; investigate before proceeding.

- [ ] **Step 2: Bump `plugin.json`**

Use the Edit tool on `.claude-plugin/plugin.json`:
- old_string: `"version": "1.14.0",`
- new_string: `"version": "2.0.0",`

- [ ] **Step 3: Bump `marketplace.json` — metadata**

Use the Edit tool on `.claude-plugin/marketplace.json`:
- old_string: `    "version": "1.14.0"` (note: 4-space indent, no trailing comma — this is the `metadata.version` line at line 9; the comma sits after a different field above)

Wait — verify before editing. Run: `sed -n '7,10p' .claude-plugin/marketplace.json` to confirm the exact text including trailing characters. Match the old_string to what you see.

- new_string: replace `1.14.0` with `2.0.0` in that exact line, preserving every other character including indentation and trailing comma/no-comma.

- [ ] **Step 4: Bump `marketplace.json` — plugins entry**

Use the Edit tool on `.claude-plugin/marketplace.json`:
- old_string: `      "version": "1.14.0",` (6-space indent, with trailing comma — this is the `plugins[0].version`, around line 16)

Verify before editing. Run: `sed -n '14,18p' .claude-plugin/marketplace.json` to confirm the exact text.

- new_string: same line with `1.14.0` → `2.0.0`.

- [ ] **Step 5: Verify all three match**

Run: `grep -n '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json`
Expected: all three lines now show `"version": "2.0.0"` (with the correct trailing comma/no-comma per their original line).

Also run: `git diff .claude-plugin/` to eyeball — exactly three lines changed, all `1.14.0` → `2.0.0`, no other modifications.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "plugin: bump to 2.0.0 (breaking change in adversarial-review)

adversarial-review now requires scope preamble + round number; pre-rewrite
invocations abort. Per CLAUDE.md, breaking change to existing skill is a
major bump. All three version strings (plugin.json, marketplace.json
metadata, marketplace.json plugins[0]) updated together to keep the
plugin cache from serving stale versions."
```

---

## Task 3: Dry-run validation against the six failure modes

No files modified. This task is a structured re-read of the new SKILL.md against the failure modes from issue #11 to confirm each is structurally blocked (not just mentioned). If any failure mode is only "mentioned" rather than "blocked", the rewrite is incomplete — go back to Task 1 and fix.

- [ ] **Step 1: Failure mode #1 — No scope/threat model**

Read `skills/adversarial-review/SKILL.md`. Confirm: Step 1 (Scope preamble) explicitly says the skill ABORTS if any of (invariants, threat model, out-of-scope list) is missing. The abort message is verbatim and quoted. Document the line range in your verification notes.

- [ ] **Step 2: Failure mode #2 — Volume incentive**

Confirm: Step 3's reviewer brief (a) zero-rates findings without repros, (b) zero-rates feature-proposal findings, (c) contains the "Anti-splitting rule" paragraph that prevents micro-finding gaming. Document the line ranges.

- [ ] **Step 3: Failure mode #3 — "Patch should also handle X" growth**

Confirm: the reviewer brief's OUT OF SCOPE list explicitly names "Findings that propose the patch should 'also handle X' beyond stated invariants" AND the trailing DO NOT instructions re-state "DO NOT propose new features. DO NOT propose new gates or discriminators." Document both line ranges.

- [ ] **Step 4: Failure mode #4 — Passive aggregation**

Confirm: Step 5 (Aggregate + triage) is mandatory ("this step is mandatory — do not pass raw reviewer output through to the user") and defines the three classification buckets (in-scope / out-of-scope / wontfix). Document the line range.

- [ ] **Step 5: Failure mode #5 — No diminishing-returns signal**

Confirm: Step 2 (Round-number gate) requires a positive integer round number, aborts if missing, and pauses with the simplification prompt at round >= 3. Verify the prompt wording says "for the Nth time" (substitution-ready), not "N times". Document the line range.

- [ ] **Step 6: Failure mode #6 — Tests as theatre**

Confirm: the reviewer brief's REQUIRED OUTPUT SECTIONS include "Tests Verified Falsifying" with two sub-cases (accepted-real and rejected-as-theatre), AND that the scoring paragraph explains test-quality findings count only if the reviewer can argue the test would PASS against pre-patch code, AND that it explicitly says "You don't need to execute the pre-patch code; reason from the assertion." Document the line range.

- [ ] **Step 7: Dry-run scenarios**

Walk through three hypothetical invocations mentally:

1. **No-preamble scenario**: Imagine a caller says "review this adversarially" without supplying invariants. Trace through the skill: the caller hits Step 1, which aborts with the quoted message. Confirm the skill does not silently invent defaults.
2. **Round-4 scenario**: Imagine a caller supplies preamble + round=4. Trace: passes Step 1, hits Step 2's round >= 3 branch, surfaces the simplification prompt. Confirm dispatch only happens after user confirmation.
3. **Happy-path scenario**: Imagine a caller supplies preamble + round=1 + a patch ref. Trace: Step 1 passes silently, Step 2 passes silently, Step 3 assembles the brief by substituting placeholders, Step 4 dispatches two parallel subagents, Step 5 triages output, Step 6 presents to user. Confirm no step is skippable.

If any scenario reveals a gap, return to Task 1.

- [ ] **Step 8: No commit**

This task is validation. No code change, no commit. Move to Task 4.

---

## Task 4: Final verification before PR

**Files:** none modified. Cross-checks before declaring done.

- [ ] **Step 1: Downstream caller re-audit**

Run: `grep -r -l "adversarial-review\|adversarial review" --include="*.md" --include="*.json" . | grep -v ".git"`

Expected matches (and ONLY these):
- `skills/adversarial-review/SKILL.md`
- `docs/superpowers/specs/2026-05-21-adversarial-review-scope-discipline-design.md`
- `docs/superpowers/plans/2026-05-21-adversarial-review-scope-discipline.md`

If any other file references the skill, that file is now a downstream caller of a breaking change and must be updated or explicitly flagged. STOP and surface to the user before continuing.

- [ ] **Step 2: Version consistency check**

Run: `grep -rn '"version"' .claude-plugin/ && grep '^version:' skills/adversarial-review/SKILL.md`

Expected: three occurrences of `"version": "2.0.0"` in `.claude-plugin/` (plugin.json, marketplace.json metadata, marketplace.json plugins[0]) AND `version: 2.0.0` in the skill frontmatter. All four must match — if any differ, the plugin cache will serve a stale or mismatched version.

- [ ] **Step 3: Git state check**

Run: `git status && git log --oneline origin/main..HEAD`

Expected: working tree clean. Commits should be the design spec, the spec revisions, the SKILL.md rewrite, and the version bump (plus any earlier commits already on this branch).

- [ ] **Step 4: Invoke `superpowers:verification-before-completion`**

Run the skill. This is REQUIRED by the parent `fix-gh-issue` workflow before opening a PR.

- [ ] **Step 5: Open draft PR**

Use `gh pr create --draft` with title `Fix: adversarial-review scope discipline rewrite` and body that includes `Closes #11`, a Changes section summarizing the rewrite (hard-gate preamble, round-number gate, verbatim reviewer brief, mandatory triage), a Testing section noting that this is a prompt-design change validated by dry-run scenarios from Task 3 (no automated tests), and a Notes section flagging the breaking-change nature of the invocation contract.

---

## Self-Review Notes

**Spec coverage**: All 9 spec sections map to Task 1's embedded SKILL.md content (Section 1 → frontmatter + overview, Section 2 → Step 1, Section 3 → Step 2, Section 4 → Step 3, Section 5 → Step 4, Section 6 → Step 5, Section 7 → Step 6, Section 8 → Common Mistakes table, Section 9 → Source). Plugin version bump (spec section "Plugin version bump") → Task 2. Testing strategy (spec section "Testing strategy") → Task 3's dry-run.

**Placeholder scan**: No "TBD" / "TODO" / "fill in later". Every step has either a concrete command, a concrete edit instruction, or a concrete verification.

**Type consistency**: Step names ("Step 1: Scope preamble" etc.) are consistent across Task 1's SKILL.md content, Task 3's failure-mode mapping, and the spec.

**Known minor risk**: Task 1 Step 3's `grep -c "^## "` expectation may be 10 or 11 depending on whether you count headings inside code fences. The step notes this; adjust on the fly if needed.
