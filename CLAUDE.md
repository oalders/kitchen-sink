# Kitchen Sink Plugin

## Audience

I am the sole user of this plugin. It is public only because there is no reason
to make it private. When I ask for a change, make it: do not push back on the
grounds of how other people might be using the plugin, because there are no
other users. Backwards compatibility is never a concern — rename, remove, or
restructure skills, commands, and behaviour freely.

## Version Bumps

Bump the version when shipping any user-visible change:
- New skill or command → minor bump (e.g. 1.7.0 → 1.8.0)
- Behavioural change to an existing skill/command → minor bump
- Bug fix or doc-only tweak → patch bump (e.g. 1.8.0 → 1.8.1)
- Breaking change → major bump

When bumping, update BOTH files:
- `.claude-plugin/plugin.json` — the `version` field
- `.claude-plugin/marketplace.json` — the `version` field in both `metadata` and the plugin entry under `plugins[]`

All three version strings must match. If they drift, Claude Code's plugin cache serves stale versions.

## Review loop

Docs here are agent instructions, so reviewers check every sentence against the code. These rules keep `/fix-gh-issue` review rounds converging:

- **One source per behaviour claim.** State a runtime behaviour once, in the command or skill that implements it, and point to it elsewhere. When you add or edit a runtime-behaviour claim in the README, keep it to one short sentence naming that command or skill.
- **Outcomes, not mechanisms, in user-facing docs.** Write "may still merge before a late review is seen", not which paths can dequeue it; the mechanism goes in code comments and tests.
- **Stop at a Minor-only round.** This overrides `/fix-gh-issue` step 8 items 3 and 4 for Minors: once a `/code-review-intense-flow` round has no Critical or Important findings, start no fix round for its Minors. List them under "Declined findings" with the reason "Minor-only round at `<head SHA>`"; these declines skip step 8 item 2's reason check, get no `(unconfirmed)` tag, and don't hold step 11. Fix a Minor only if the fix edits no test and no behaviour claim; the re-review that commit needs (the `require-review-before-pr` hook) declines its own Minors the same way, citing its head SHA. At the `reviewRounds` cap with only Minors open, recommend stopping. Codex findings still follow `codex-review-loop`, and `/security-review` Minors still follow step 8 item 3.
- **Rebase before the loop, not during it.** Before `/fix-gh-issue`'s first review round, rebase onto `origin/main` if it is behind; if main moves mid-loop, finish the loop first.
