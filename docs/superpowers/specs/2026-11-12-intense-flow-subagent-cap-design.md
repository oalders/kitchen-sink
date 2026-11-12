# Keep /code-review-intense-flow under the subagent cap (#184)

## Intent

`/code-review-intense-flow` should get its parallel, independent reviewer reads
under the harness's concurrent-subagent cap, both at top level and inside the
`/shepherd-pr` repair subagent, without raising the cap. The user runs on
underpowered machines and keeps `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` at 5.

## Facts (probe, 2026-11-12)

- The cap is 5 running subagents, counted across the whole agent tree.
- A dispatch over the cap is refused at once ("Concurrent subagent limit
  reached. ... Do not retry."), never queued; the caller falls back to inline.
- Every specialist command dispatches its own inner reviewer `Task`, so each
  intense-flow specialist costs two agents. A typical plugin diff (general,
  security, agent-instructions, test-value) runs 7 at top level, 8 inside the
  repair subagent.

## Goals / non-goals

- Goal: a typical round fits in 5 (4 agents top level, 5 in repair).
- Goal: a reviewer refused on a large fan-out still gets an independent read
  where a slot frees, and an inline fallback is marked in intense-flow's summary.
- Non-goal: surfacing that marker outside intense-flow (e.g. in the
  `/shepherd-pr` repair reply); the summary is enough.
- Non-goal: changing the specialist commands' standalone behaviour.
- Non-goal: changing the user's settings or the repair skill.
- Anti-goal: dropping the security pass from Opus to Sonnet.

## Approaches

- **Flatten the wrappers (chosen).** The specialist subagent intense-flow
  dispatches runs its file's reviewer prompt itself instead of dispatching it.
  Halves the agent count; specialists stay the source of truth.
- Raise the cap to 8: no plugin change, but the idle wrapper turns remain and
  cost more on slow machines.
- Dispatch in waves: more orchestration logic and slower rounds.

## Design (`commands/code-review-intense-flow.md` step 4)

1. The specialist brief: follow the file's steps up to and including its
   reviewer prompt, but run that prompt yourself in this context instead of
   dispatching its `Task`. Dispatch nothing, skip the file's "After Review" /
   fix steps, edit nothing, and return the review verbatim with the one-line
   preamble.
2. The specialist dispatch uses the `model:` from that specialist's reviewer
   `Task` block (the file stays the source of truth; security is `opus`).
3. Security is dispatched first in the message, so a cap refusal never lands
   on it.
4. A dispatch refused for the concurrency cap: once the first reviewer
   returns, dispatch each refused one once more. Refused again: the caller runs
   that specialist's reviewer prompt itself (dispatching nothing) and marks it
   `(ran inline: subagent cap)` in "Reviewers Run".
5. Rewrite the lines that would contradict this: step 4's intro ("executes that
   workflow"), the brief's "Dispatch general-purpose as the file directs", and
   the Related Commands line saying specialists "ultimately spawn"
   general-purpose.
6. Minor version bump. No README change (it states no agent counts).

## Left to the builder

Exact wording.
