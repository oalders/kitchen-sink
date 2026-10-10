---
name: tune-dependabot-config
description: Use when adding, auditing, or editing `.github/dependabot.yml`, when that file has no `groups:` or no `cooldown:` block, when dependabot PRs are cluttering a repo's PR queue, or when the user wants dependabot PRs to auto-merge.
version: 1.2.0
---

# Tune Dependabot Config

## Overview

**Two changes applied to every `updates:` entry in `.github/dependabot.yml`, plus one opt-in step:**

1. **Group minor and patch updates.** Add a catch-all group that batches minor and patch bumps for the ecosystem into a single rolling PR. Major updates stay as individual PRs.
2. **Add a 7-day cooldown.** Wait 7 days after a release before opening a PR so broken releases get yanked or patched first.
3. **Optional: auto-merge minor and patch PRs** — per repo, opt-in. See [Optional: Auto-merge minor and patch PRs](#optional-auto-merge-minor-and-patch-prs).

**Core principle:** Reduce dependabot PR noise on safe updates while preserving one-PR-per-package signal on breaking changes. Majors get individual PRs because each one is a breaking change that needs to be evaluated on its own — batching them hides which package failed CI.

## Dispatch this skill to a subagent

When this skill is invoked, dispatch the work to a `general-purpose` subagent via the `Agent` tool. **Do not run the transforms inline in the caller's context.**

Why:
- The skill reads `.github/dependabot.yml`, walks every `updates:` entry, computes minimal edits per entry, writes the file, and runs a YAML parser sanity check. With several ecosystems in play, that is a meaningful amount of `Read`/`Edit`/`Bash` tool traffic the caller doesn't need to see.
- The caller only needs the final summary line (groups added, cooldown added, existing groups preserved). Everything else is intermediate state.

How to dispatch:
- Brief the subagent with this SKILL.md as its working spec — pass the path or invoke the skill from inside the subagent.
- Tell the subagent the working directory.
- Subagents can't ask the user, so before dispatching gather the auto-merge answers listed under [Before starting](#optional-auto-merge-minor-and-patch-prs) and pass them in the brief. Without them, the subagent must not set up auto-merge.
- Require the subagent to report back only: the summary line, whether auto-merge was set up (or why not), and any entries skipped (paused, misplaced `applies-to`, user-tuned cooldown) with reason.
- If the YAML sanity check fails after editing, the subagent must stop and surface the failure rather than continuing or auto-reverting.

If the user explicitly asks to run inline (e.g. "do it here so I can watch"), honour that — the subagent dispatch is the default, not a hard requirement.

## When to Use

- User asks to set up, tune, harden, clean up, or audit dependabot config
- A repo has `.github/dependabot.yml` with no `groups:` or no `cooldown:` block
- A repo has many open dependabot PRs cluttering the PR queue
- Adding dependabot to a repo for the first time

**Skip when:**
- The user has explicitly customised groups for a reason (e.g. `aws-sdk-*` separated from rest); preserve their groups, only add what's missing
- The entry has `open-pull-requests-limit: 0` (paused) — leave it alone
- An entry has `applies-to` directly on it — that key is only valid inside `groups.<name>`; flag it to the user rather than guessing their intent

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

Inside each `updates:` entry, add:

```yaml
cooldown:
  default-days: 7
```

`default-days: 7` is enough for every ecosystem — both the SemVer-aware ones (npm, Bundler, Cargo, Composer, Gomod, Gradle, Maven, NuGet, Pip, UV, etc.) and the ecosystems that only honour `default-days` (Docker, GitHub Actions, Helm, Terraform, Devcontainers, Bazel, Conda, Hex/Mix, Gitsubmodule, Docker Compose).

Cooldown only delays version updates — Dependabot never applies it to security updates, so those still land fast.

## Optional: Auto-merge minor and patch PRs

Never applied by default. Offer it only when the repo's CI is trusted to catch breakage; skip it when the user prefers hands-on review (e.g. heavy npm lockfile churn). Majors stay manual, consistent with the core principle.

**Before starting — gather up front** (the caller does this once before dispatching, or you when running inline; set nothing up without all four):

- (a) The user opts in for this repo.
- (b) The default branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`) requires status checks — without them auto-merge either fails to enable or merges before CI passes. Verify either:
  - classic protection: `gh api repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks` succeeds, or
  - a ruleset: `gh api repos/{owner}/{repo}/rules/branches/{branch} --jq '[.[] | select(.type == "required_status_checks")] | length'` is greater than 0.

  If neither shows required checks, or the result is inconclusive (e.g. 403 without admin access), stop and tell the user.
- (c) The user approves you running `gh repo edit --enable-auto-merge` on their behalf.
- (d) Merge method: run `gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed`; if only one is allowed, use it without asking; if more than one is allowed, the user picks `--merge`, `--squash`, or `--rebase`.

Steps:

1. **Enable the repo setting:** `gh repo edit --enable-auto-merge`.
2. **Write `.github/workflows/dependabot-automerge.yml`** — skip if any `.github/workflows/*.y*ml` already runs `gh pr merge --auto` for `dependabot[bot]` PRs, and report it as already present:

```yaml
name: Dependabot auto-merge

on: pull_request

jobs:
  automerge:
    if: github.event.pull_request.user.login == 'dependabot[bot]'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: write
      pull-requests: write
    steps:
      - id: metadata
        uses: dependabot/fetch-metadata@25dd0e34f4fe68f24cc83900b1fe3fe149efef98 # v3.1.0
      - if: steps.metadata.outputs.update-type == 'version-update:semver-minor' || steps.metadata.outputs.update-type == 'version-update:semver-patch'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Replace `--squash` with the method from (d). For a grouped PR, `fetch-metadata` reports the highest change in the group, so `minor-and-patch` PRs qualify and the `github-actions` `major-updates` PR does not.

**Caveat:** merges made with `GITHUB_TOKEN` don't trigger `push` workflows on the default branch, so release/deploy-on-push won't fire for these merges.

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
2. **Check for a misplaced `applies-to`.** If the entry itself (not one of its groups) has `applies-to`, flag it — the key is only valid inside `groups.<name>` — and leave the entry alone.
3. **Ensure grouping.** The required catch-all groups depend on `package-ecosystem`:
   - For `github-actions`: two catch-alls — `major-updates` with `update-types: [major]`, and `minor-and-patch` with `update-types: [minor, patch]`.
   - For every other ecosystem: one catch-all — `minor-and-patch` with `update-types: [minor, patch]`.

   Then, for each required catch-all:
   - If no group with `patterns: ['*']` covers the required `update-types`, add the catch-all alongside the existing groups.
   - Otherwise leave that catch-all out — it's already satisfied.

   Existing user-defined groups are always preserved.
4. **Ensure cooldown.**
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

After all entries are processed, if the user opted in, follow [Optional: Auto-merge minor and patch PRs](#optional-auto-merge-minor-and-patch-prs) once for the repo.

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

### Example 3 — Misplaced entry-level `applies-to`

**Before:**

```yaml
- package-ecosystem: "pip"
  directory: "/"
  schedule:
    interval: "weekly"
  applies-to: security-updates
```

**After:** Leave the entry unchanged and tell the user that `applies-to` is only valid inside `groups.<name>`. Offer the two fixes, depending on intent:

- **Security updates only:** replace it with `open-pull-requests-limit: 0`. That disables version updates while security PRs continue, and step 1 then skips the entry.
- **Grouped security PRs:** move the key into a group:

```yaml
- package-ecosystem: "pip"
  directory: "/"
  schedule:
    interval: "weekly"
  groups:
    minor-and-patch:
      applies-to: security-updates
      patterns:
        - "*"
      update-types:
        - "minor"
        - "patch"
```

Groups default to `version-updates`, so a security group needs the explicit `applies-to`. Major security advisories still land as individual PRs so each can be triaged on its own.

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
| Putting `applies-to` directly on an `updates:` entry | Not a valid key there; it only exists under `groups.<name>` | Move it into a group, or use `open-pull-requests-limit: 0` for security-only |
| Replacing the user's existing groups with `minor-and-patch` | Destroys their per-package-family routing | Add alongside, don't replace |
| Leaving `update-types` off the catch-all group | Behaviour ambiguous across dependabot versions | Always list `[minor, patch]` explicitly |
| Including `major` in the catch-all `update-types` for non-actions ecosystems | Hides which package broke when a batched major-bump PR fails CI | Group only minor + patch; let majors arrive as individual PRs |
| Skipping a major-updates group for `github-actions` | Coordinated action major releases (upload-artifact / download-artifact, cache save/restore) need to merge together or CI breaks | For `github-actions`, add a separate `major-updates` group |
| Lumping major + minor + patch into a single `github-actions` group | A failing major-bump PR blocks routine patch updates from landing | Use two groups: `major-updates` and `minor-and-patch` |
| Mismatching the file's quote style when adding keys | Mixed quoting reads as careless and may break linters | Match existing quotes; if mixed, default to single |
| Using `default-days: 7` *and* `semver-*-days` together without thought | Conflicting signals; one will silently win | If the user has `semver-*-days`, leave cooldown alone entirely |
| Editing the file as a string and reflowing it | Loses comments, breaks key order users care about | Edit minimally — append the missing keys to each entry |
| Adding the block when the entry has `open-pull-requests-limit: 0` | The entry is intentionally paused | Skip paused entries |
| Auto-merging via `pull_request_target` or a third-party action | Widens the attack surface for a job holding write permissions | Use `on: pull_request` with first-party `dependabot/fetch-metadata` and `gh pr merge` |
| Auto-merging majors | Breaking changes land without anyone evaluating them | Gate the merge step on semver-minor or semver-patch only |
| Enabling auto-merge without required status checks | Nothing makes the merge wait for CI | Verify via the API (classic protection or rulesets) that checks are required first |

## Verification

After writing the file:

1. Parse it: `python3 -c 'import yaml; yaml.safe_load(open(".github/dependabot.yml"))'`
2. Re-read each `updates:` entry and confirm:
   - A group with `patterns: ['*']` covers minor + patch (or another catch-all is in place)
   - For version-updates entries, `cooldown.default-days` is set (or the user already has cooldown configured)
3. Report a summary: "Added grouping to N entries (X minor+patch, Y major-updates for github-actions), added cooldown to M entries, preserved K existing groups; auto-merge set up / not requested."

## Related

- GitHub docs: [Dependabot options reference — groups](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#groups--)
- GitHub docs: [Dependabot options reference — cooldown](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#cooldown--)
- GitHub docs: [Automating Dependabot with GitHub Actions](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/automating-dependabot-with-github-actions)
