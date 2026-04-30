---
name: tune-dependabot-config
description: Use when adding, auditing, or editing .github/dependabot.yml — groups minor and patch updates per ecosystem (majors stay individual), and adds a 7-day cooldown so churning releases settle before a PR opens.
version: 1.0.0
---

# Tune Dependabot Config

## Overview

**Two changes applied to every `updates:` entry in `.github/dependabot.yml`:**

1. **Group minor and patch updates.** Add a catch-all group that batches minor and patch bumps for the ecosystem into a single rolling PR. Major updates stay as individual PRs.
2. **Add a 7-day cooldown.** Wait 7 days after a release before opening a PR so broken releases get yanked or patched first.

**Core principle:** Reduce dependabot PR noise on safe updates while preserving one-PR-per-package signal on breaking changes. Majors get individual PRs because each one is a breaking change that needs to be evaluated on its own — batching them hides which package failed CI.

## When to Use

- User asks to set up, tune, harden, clean up, or audit dependabot config
- A repo has `.github/dependabot.yml` with no `groups:` or no `cooldown:` block
- A repo has many open dependabot PRs cluttering the PR queue
- Adding dependabot to a repo for the first time

**Skip when:**
- The user has explicitly customised groups for a reason (e.g. `aws-sdk-*` separated from rest); preserve their groups, only add what's missing
- The entry has `open-pull-requests-limit: 0` (paused) — leave it alone
- An entry is security-updates only — cooldown does not apply to security updates

## The Two Transforms

### 1. Catch-all minor + patch group

Inside each `updates:` entry, ensure a group exists that matches every dependency for minor and patch updates only:

```yaml
groups:
  minor-and-patch:
    patterns:
      - '*'
    update-types:
      - 'minor'
      - 'patch'
```

**Why explicit `update-types`:** Without it, group behaviour depends on dependabot defaults that have shifted over time and differ between version-updates and security-updates. Listing the two update types unambiguously batches minor + patch and leaves majors as individual PRs.

**Why exclude major:** A grouped major-bump PR hides which package broke when CI fails, and reverting one package out of a batch is awkward. Individual PRs for majors keep the signal clean.

**Exception — `github-actions`:** Use **two groups** for the GitHub Actions ecosystem — one for major bumps, one for minor + patch:

```yaml
groups:
  major-updates:
    patterns:
      - '*'
    update-types:
      - 'major'
  minor-and-patch:
    patterns:
      - '*'
    update-types:
      - 'minor'
      - 'patch'
```

**Why two groups:** Related actions (`actions/upload-artifact` and `actions/download-artifact`, `actions/cache/save` and `actions/cache/restore`) ship coordinated major bumps where the artifact or cache format changes — merging one without the other breaks CI. Batching majors together keeps the coordinated pair atomic. Keeping major in its own group (rather than mixing all three) means a routine minor/patch PR can land without waiting for the major-bump PR to clear review, and a failing major-bump PR doesn't block patch updates.

**If the user already has groups:** Preserve them. Only add the catch-all if no existing group has `patterns: ['*']` covering the required update types (minor + patch for most ecosystems; major + minor + patch for `github-actions`). A more-specific group always wins for matched dependencies, so adding a catch-all alongside is safe — it sweeps up everything the named groups don't claim. If the user has an existing catch-all that already includes `major` in its update-types, leave it — they made that choice deliberately.

### 2. Cooldown

Inside each `updates:` entry where `applies-to` is `version-updates` (the default), add:

```yaml
cooldown:
  default-days: 7
```

`default-days: 7` is enough for every ecosystem — both the SemVer-aware ones (npm, Bundler, Cargo, Composer, Gomod, Gradle, Maven, NuGet, Pip, UV, etc.) and the ecosystems that only honour `default-days` (Docker, GitHub Actions, Helm, Terraform, Devcontainers, Bazel, Conda, Hex/Mix, Gitsubmodule, Docker Compose).

**Do not add cooldown to security-update entries** — dependabot ignores it there, and the whole point of security updates is to land fast.

## Schema Reference

### `groups:` (per ecosystem entry)

| Key | Purpose |
|---|---|
| `IDENTIFIER` | Group name (letters, hyphens, underscores; must start and end with a letter) |
| `applies-to` | `version-updates` (default) or `security-updates` |
| `dependency-type` | `production` or `development` |
| `patterns` | List of name globs to include (e.g. `["*"]`, `["aws-sdk-*"]`) |
| `exclude-patterns` | Globs to exclude |
| `update-types` | Subset of `["major", "minor", "patch"]` |

### `cooldown:` (per ecosystem entry, version-updates only)

| Key | Purpose |
|---|---|
| `default-days` | Cooldown for any update without a more-specific rule |
| `semver-major-days` | Major version cooldown (SemVer ecosystems only) |
| `semver-minor-days` | Minor version cooldown (SemVer ecosystems only) |
| `semver-patch-days` | Patch version cooldown (SemVer ecosystems only) |
| `include` | Glob list to scope cooldown to (≤150 entries) |
| `exclude` | Glob list to exclude (≤150 entries) |

This skill writes only `default-days: 7`. If the user later wants tighter patch / longer major windows, they can split it themselves.

## Algorithm

For each `- ` entry under `updates:` in `.github/dependabot.yml`:

1. **Skip if paused.** If the entry has `open-pull-requests-limit: 0`, leave it alone.
2. **Determine update class.** If `applies-to: security-updates`, only step 3 applies.
3. **Ensure grouping.** The required catch-all groups depend on `package-ecosystem`:
   - For `github-actions`: two catch-alls — `major-updates` with `update-types: [major]`, and `minor-and-patch` with `update-types: [minor, patch]`.
   - For every other ecosystem: one catch-all — `minor-and-patch` with `update-types: [minor, patch]`.

   Then, for each required catch-all:
   - If no group with `patterns: ['*']` covers the required `update-types`, add the catch-all alongside the existing groups.
   - Otherwise leave that catch-all out — it's already satisfied.

   Existing user-defined groups are always preserved.
4. **Ensure cooldown** (skip for security-updates entries).
   - If no `cooldown:` key exists, add `cooldown: { default-days: 7 }`.
   - If `cooldown:` exists with no `default-days`, add `default-days: 7`.
   - Otherwise leave cooldown alone — the user has tuned it deliberately.
5. **Preserve everything else** — comments, key order, `schedule`, `directory`, `ignore`, `assignees`, `labels`, etc.
6. **Match the file's quoting style.** Scan the existing file for quote usage on string values:
   - If the file uses double quotes consistently, write new strings with double quotes.
   - If the file uses single quotes consistently, write new strings with single quotes.
   - If the file mixes quotes (or uses bare strings), default new strings to single quotes.
   - Preserve unquoted bare values (e.g. `weekly`, `daily`, `npm`) on existing keys.

After editing, run a YAML parser sanity check (e.g. `python3 -c 'import yaml,sys; yaml.safe_load(open(".github/dependabot.yml"))'`) to confirm the file still parses.

## Examples

### Example 1 — Bare config (most common starting point)

**Before:**

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

**After** (file uses double quotes, so new strings use double quotes):

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      minor-and-patch:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    cooldown:
      default-days: 7

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      major-updates:
        patterns:
          - "*"
        update-types:
          - "major"
      minor-and-patch:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    cooldown:
      default-days: 7
```

npm major bumps arrive as individual PRs. GitHub Actions yields up to two PRs per run — one for batched major bumps (so coordinated artifact/cache releases land atomically) and one for routine minor + patch.

### Example 2 — Existing custom groups preserved

**Before:**

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "daily"
    groups:
      aws-sdk:
        patterns:
          - "@aws-sdk/*"
```

**After:**

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "daily"
    groups:
      aws-sdk:
        patterns:
          - "@aws-sdk/*"
      minor-and-patch:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
    cooldown:
      default-days: 7
```

The `aws-sdk` group still wins for `@aws-sdk/*` packages; `minor-and-patch` sweeps up the rest. Majors for any package land as individual PRs.

### Example 3 — Security-only entry left alone

**Before:**

```yaml
- package-ecosystem: "pip"
  directory: "/"
  schedule:
    interval: "weekly"
  applies-to: security-updates
```

**After:** Same plus the catch-all group (security updates can also be grouped) but **no `cooldown:` block** — cooldown is ignored for security-updates and adding it would be misleading.

```yaml
- package-ecosystem: "pip"
  directory: "/"
  schedule:
    interval: "weekly"
  applies-to: security-updates
  groups:
    minor-and-patch:
      applies-to: security-updates
      patterns:
        - "*"
      update-types:
        - "minor"
        - "patch"
```

Note `applies-to: security-updates` inside the group — groups default to `version-updates`, so an explicit match is required. Major security advisories still land as individual PRs so each can be triaged on its own.

### Example 4 — User has already tuned cooldown

**Before:**

```yaml
- package-ecosystem: "cargo"
  directory: "/"
  schedule:
    interval: "weekly"
  cooldown:
    semver-major-days: 14
    semver-minor-days: 3
```

**After:** Add the catch-all group, but **leave cooldown alone** — the user has split major/minor deliberately. Don't overwrite their judgement with a flat 7.

## Common Mistakes

| Mistake | Why it's wrong | Fix |
|---|---|---|
| Adding `cooldown:` to a security-updates entry | Dependabot ignores it; misleads readers | Skip cooldown for `applies-to: security-updates` |
| Replacing the user's existing groups with `minor-and-patch` | Destroys their per-package-family routing | Add alongside, don't replace |
| Leaving `update-types` off the catch-all group | Behaviour ambiguous across dependabot versions | Always list `[minor, patch]` explicitly |
| Including `major` in the catch-all `update-types` for non-actions ecosystems | Hides which package broke when a batched major-bump PR fails CI | Group only minor + patch; let majors arrive as individual PRs |
| Skipping a major-updates group for `github-actions` | Coordinated action major releases (upload-artifact / download-artifact, cache save/restore) need to merge together or CI breaks | For `github-actions`, add a separate `major-updates` group |
| Lumping major + minor + patch into a single `github-actions` group | A failing major-bump PR blocks routine patch updates from landing | Use two groups: `major-updates` and `minor-and-patch` |
| Mismatching the file's quote style when adding keys | Mixed quoting reads as careless and may break linters | Match existing quotes; if mixed, default to single |
| Using `default-days: 7` *and* `semver-*-days` together without thought | Conflicting signals; one will silently win | If the user has `semver-*-days`, leave cooldown alone entirely |
| Editing the file as a string and reflowing it | Loses comments, breaks key order users care about | Edit minimally — append the missing keys to each entry |
| Adding the block when the entry has `open-pull-requests-limit: 0` | The entry is intentionally paused | Skip paused entries |

## Verification

After writing the file:

1. Parse it: `python3 -c 'import yaml; yaml.safe_load(open(".github/dependabot.yml"))'`
2. Re-read each `updates:` entry and confirm:
   - A group with `patterns: ['*']` covers minor + patch (or another catch-all is in place)
   - For version-updates entries, `cooldown.default-days` is set (or the user already has cooldown configured)
3. Report a summary: "Added grouping to N entries (X minor+patch, Y major-updates for github-actions), added cooldown to M entries, preserved K existing groups."

## Related

- GitHub docs: [Dependabot options reference — groups](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#groups--)
- GitHub docs: [Dependabot options reference — cooldown](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#cooldown--)
