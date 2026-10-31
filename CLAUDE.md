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
