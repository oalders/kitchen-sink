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
- You can already name the invariants the patch claims and its threat model (the precondition Step 1 enforces).

If you can't supply the preamble, this is the wrong skill. Use `superpowers:requesting-code-review` or `/request-review` instead — those don't require scope to work.

## Required Inputs

The caller MUST provide all of the following. If any is missing, abort using the Step 1 message (which Step 2 also reuses for the round-number case) — do not improvise defaults, do not dispatch with placeholders.

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

If you're unsure whether a finding is in scope, write it under "Hypotheses
Checked Clean" with your reasoning, not under "Findings".

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
If the patch adds no tests, write: "No tests added by this patch." and skip the per-test bullets.
Otherwise, for each test the patch adds/modifies that you ACCEPT as real:
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
flag wording nits.
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

## Hypotheses Checked Clean
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
