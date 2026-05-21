# Adversarial Review — Scope Discipline Rewrite

**Issue**: [#11](https://github.com/oalders/kitchen-sink/issues/11) — `adversarial-review: add scope discipline to prevent finding-count inflation`
**Date**: 2026-05-21
**Status**: Design approved, pending implementation

## Background

The current `skills/adversarial-review/SKILL.md` (22 lines) instructs two subagents to compete with the framing *"whoever finds the largest number of serious issues gets five points."* In a worked example (a 5-round adversarial review of a defensive patch to `WWW::RobotRules::parse` against log-flood / log-injection from hostile `robots.txt`), this framing produced a treadmill:

- Round 1 worked.
- By round 3, findings count was barely converging.
- By round 5, fixes were introducing roughly as much surface as they were removing.

Observed failure modes (issue #11):

1. **No scope or threat model in the dispatch prompt** — reviewers find "everything", including theoretical contract gaps, "what if a future caller does X" cases, and wording nits.
2. **Incentive rewards volume** — reviewers pad with low-value nits to win the points contest.
3. **Findings can ask for new machinery** — "the patch should also handle X" findings grow surface that the next round attacks.
4. **Aggregation is passive** — out-of-scope findings get surfaced to the user as if actionable.
5. **No diminishing-returns signal** — each round runs fresh; the right move after 3+ stalled rounds is often *simplification*, not more review.
6. **Tests drift into theatre** — "lock-down" tests added in earlier rounds turn out to assert trivially-true conditions; later rounds discover this, but the skill never prompts reviewers to verify tests would FAIL against pre-patch code.

## Goal

Rewrite `skills/adversarial-review/SKILL.md` so the load-bearing wording (scope, incentive, output schema, triage) is un-skippable. The skill should structurally block the failure modes above rather than relying on the dispatcher to remember them.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scope/threat-model preamble | **Hard gate** — skill aborts if missing | Issue framed this as "refuse or warn loudly"; the worked example shows scope drift is the root cause, not a downstream symptom |
| Diminishing-returns mechanism | **Caller-supplied round number** | Skill is stateless; round number is cheap and explicit |
| Overall structure | **Prescriptive** — verbatim reviewer-brief template baked in | The exact phrasing of the incentive is what was load-bearing in the worked example; structural variance is what we're eliminating |

## Specification

### File to modify
- `skills/adversarial-review/SKILL.md` — full rewrite (22 → ~170 lines)
- Skill-internal frontmatter version: `1.0.0` → `2.0.0` (breaking change to invocation contract — callers must now supply preamble + round number, and invocations without them abort)

The plugin-level version also bumps to major (see [Plugin version bump](#plugin-version-bump) below) — this is the same breaking change, surfaced at both layers.

### Section 1 — Frontmatter + Overview

```
---
name: adversarial-review
description: Use when the user asks for an "adversarial review", "review this
  adversarially", or wants two reviewers competing to find serious issues in
  code or other work. Enforces scope discipline so findings count doesn't
  inflate across rounds.
version: 2.0.0
---

# Adversarial Review

Two subagents review the same work in parallel, competing under an incentive
that rewards in-scope defects with working repros and penalizes nit-padding
and feature-proposal drift. The skill enforces scope discipline up front and
triages findings against scope before presenting them.

**The failure mode this skill prevents**: without scope, reviewers find
"everything" — theoretical contract gaps, "what if a future caller does X"
cases, POD nits — and fixes accumulate surface that the next round attacks.
Findings count stays high while real signal converges to zero.
```

### Section 2 — Step 1: Scope preamble (hard gate)

Before dispatching, the caller MUST supply:

1. **Invariants** (1-3, crisp): what does the patch claim to make true?
2. **Threat model**: who is the attacker, what's their leverage, what's the impact target?
3. **Out-of-scope list**: which kinds of findings are not in scope?

If the caller can't supply these, the skill **aborts** with:

> adversarial-review requires scope to work. Without invariants and a threat model, reviewers will pad with nits and propose features instead of finding defects. Please supply: (1) invariants the patch claims, (2) threat model, (3) explicit out-of-scope list. Then re-invoke.

### Section 3 — Step 2: Round-number gate

Caller MUST state which round this is — a positive integer (1, 2, 3, ...) where the number counts *the current invocation including this one*. So "round 1" means first invocation on this patch; "round 3" means this is the third.

If the caller can't supply a round number, or supplies something other than a positive integer, the skill aborts with the same posture as the preamble gate (round number is part of the required input).

If round is 1 or 2: proceed silently to Step 3.

If round >= 3: pause and surface this to the user verbatim (substitute N with the caller-supplied round number, which includes the current invocation):

> You're about to run adversarial-review for the Nth time on this patch. If findings haven't converged, more rounds usually won't help — every fix creates new surface for the next round to attack. Consider **simplifying the patch** (shrink to one or two invariants) instead of adding another round. Continue anyway? [yes / step back]

Only dispatches if the user confirms "yes" (or equivalent affirmation). If the user picks "step back" or asks to simplify, the skill exits without dispatching.

### Section 4 — Step 3: Assemble reviewer brief (verbatim template)

The dispatcher pastes this brief, verbatim, to each subagent (substituting `{...}` placeholders):

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

### Section 5 — Step 4: Dispatch in parallel

Use the Agent tool with two `general-purpose` subagents in a single message (parallel). Both get the identical brief from Section 4.

### Section 6 — Step 5: Aggregate + triage

For each unique finding (after deduplication), classify as:

- **in-scope** — violates a stated invariant or breaks legitimate use; has a working repro
- **out-of-scope** — proposes new behavior, gates, or discriminators; or extends surface beyond stated invariants
- **wontfix** — cosmetic, style, doc wording

Present only **in-scope** items as actionable. For each out-of-scope finding, write a one-line rejection that names which scope rule excluded it. This step is mandatory — do not pass raw reviewer output through to the user.

### Section 7 — Step 6: Present to user

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

### Section 8 — Common mistakes / red flags

| Mistake | Fix |
|---|---|
| Dispatching without preamble | Skill should refuse — re-read Step 1 |
| Accepting findings without repros | Zero-point findings; don't present them |
| Pass raw reviewer output to user | Triage step is mandatory |
| Run round 4+ without simplifying | Diminishing returns — shrink the patch first |
| Treat "the patch should also do X" as a finding | That's a feature proposal — out of scope |
| Accept new tests without falsification check | Tests that pass against broken code are theatre |

### Section 9 — Source

Original technique: https://blog.fsck.com/2026/05/01/adversarial-review/
Scope-discipline rewrite motivated by GitHub issue #11.

## Testing strategy

Skills don't have unit tests in this repo. The rewritten skill will be validated by:

1. **Self-review**: re-read the rewritten SKILL.md against each of the six failure modes from the issue and confirm the skill structurally blocks each one (vs relies on the dispatcher to remember).
2. **Dry run**: walk through a hypothetical invocation (caller skips preamble → skill aborts; caller supplies preamble, round=4 → skill prompts to simplify; caller supplies everything → skill dispatches with verbatim brief). Verify each gate fires as designed.
3. **Plugin version bump**: per `CLAUDE.md`, bump version in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (both entries) — see [Plugin version bump](#plugin-version-bump) below for target version and rationale.

No automated tests required — this is a prompt-design change, not code.

## Out of scope for this PR

- Updating `kitchen-sink:code-review-flow` or other skills that may reference `adversarial-review` (they would need their own scope discipline; not part of this issue).
- Tooling to track invocation history across conversations (the skill is stateless; round number is caller-supplied).
- A "lite" or "quick" mode of adversarial-review that skips the preamble. The whole point of the issue is that the preamble is non-negotiable.

## Plugin version bump

<a id="plugin-version-bump"></a>

This is a **breaking change** to an existing skill's invocation contract — pre-rewrite invocations (without preamble + round number) will abort post-rewrite. Per `CLAUDE.md`: breaking change → **major bump**.

Current version: `1.14.0` (confirmed in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`).

Target version: `2.0.0` in **three** locations (per `CLAUDE.md` — must match exactly or the plugin cache serves stale versions):

- `.claude-plugin/plugin.json` — top-level `version`
- `.claude-plugin/marketplace.json` — `metadata.version`
- `.claude-plugin/marketplace.json` — `plugins[0].version` (single entry, since this is one plugin)

The skill's internal frontmatter version (`skills/adversarial-review/SKILL.md`) also bumps `1.0.0` → `2.0.0`. Same change, surfaced at both layers — the plugin-level version is the user-facing one (plugin cache uses it); the skill-internal version is for skill authors tracking the skill's own evolution.

### Downstream caller audit

Grepped the repo for references to `adversarial-review` and `adversarial review`. The only matches are the skill file itself and this spec — no other skills or commands invoke it. So the breaking change has no internal callers to update; only users who directly invoke the skill will see the new requirements.
