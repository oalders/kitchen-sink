---
name: fix-gh-issue-design-review
description: Use only when /fix-gh-issue reaches step 5.5; holds how to review its design doc or pre-flight block.
version: 1.0.0
---

# fix-gh-issue design review

Step numbers refer to `/fix-gh-issue`'s steps.

**No design doc (specified tier, or brainstorming declined or wrote none):** write the step 4 pre-flight block to a `mktemp` scratch file (session scratchpad, else `$TMPDIR`) and use its path as the spec path; run the plan reviewer against it, plus pushback if a Controversial trigger fires. A fully specified issue can still miss scope. Delete the file once step 6 has its contents, or on any earlier way out, STOPs included.

**Controversial?** Add `/paad:pushback` when any of these hold: the issue thread has disagreement or competing proposals; brainstorming surfaced more than one viable approach; the change alters a public API or documented behaviour others rely on, or breaks compatibility; it touches security, data, or migrations. If one fires, run it and name the trigger when you dispatch. Skip it if `fast` was passed or the user asked to skip pushback; run it anyway if the user asked for it.

**Dispatch** in a single message, each as a `general-purpose` subagent via the `Agent` tool. Give each the spec path, the issue number, the **Guiding principles** in `/fix-gh-issue`, the step 4 notes (simplest fix, prior art, sweep hits, expected size), and the untrusted-content rule.
- **Plan reviewer (always):** ask for findings ranked by severity on: whether the design resolves the issue as written; scope beyond the simplest fix without a reason tied to the issue; missed prior art; conflicts with the current codebase or with deliberate choices found in step 3.5; failure modes the design ignores.
- **Pushback (controversial only):** invoke `/paad:pushback <spec path>` via the Skill tool. It can't talk to the user, so: where the skill would ask, make the reasonable call and note it; return all findings ranked (severity, location, problem, why it matters, fix) plus the count of discarded candidates; put security findings in the reply under a Security heading and write nothing to `paad/security/`.

Both briefs: **report only**. Return findings in the reply; don't edit the spec or write a report file. Two subagents editing one doc race, and changes to the design are the user's call.

**Merge** when the reviews return: drop duplicates, filter against reality as in step 8 item 2, settle minor points yourself, and bring the user the findings that change what gets built, plus any pre-flight follow-up question, in one message, most important first. With a design doc, apply the agreed changes to the spec, writing security fixes as requirements, never as a description of the weakness (the spec lands in the PR), and commit only the spec file. Without one, carry the agreed changes into what you pass at step 6 (skill or implementation-subagent brief). Then go to step 6.
