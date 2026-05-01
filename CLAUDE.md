# Kitchen Sink Plugin

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
