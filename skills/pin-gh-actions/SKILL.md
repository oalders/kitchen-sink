---
name: pin-gh-actions
description: Use when adding, bumping, or editing any `uses:` line in `.github/workflows/*` or an `action.yml`.
version: 1.0.1
---

# Pin GitHub Actions

## Overview

Pin every external `uses:` ref to a full commit SHA with the tag as a trailing comment:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with:
    persist-credentials: false
```

The `persist-credentials: false` comes from `kitchen-sink:least-privilege-gh-actions`, not this skill.

**Why:** a tag or branch can be moved to different code after you review it; a commit SHA cannot. The comment keeps the pin readable and lets Dependabot bump SHA and comment together.

**Scope:** every action or reusable-workflow ref of the form `owner/repo[/path]@ref`, first-party `actions/*` included — there is no exemption. Local `./` refs and `docker://` refs are deliberately out of scope: the first is code in the same commit, the second is an image reference, not a git ref, and its tag is mutable too, so this exclusion is a known residual risk, not a safe case.

## Algorithm

For each in-scope `uses:` line you add, bump, or edit. When another skill or a request applies this skill to a whole file, every in-scope line in it counts as edited.

Untrusted input: refs and `# <tag>` comments come from workflow files, and tag names from `gh api` come from the action's maintainer. Before putting any of them in a command or a comment, check `<owner>/<repo>` matches `^[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*$` and the tag matches `^[A-Za-z0-9][A-Za-z0-9._+-]*(/[A-Za-z0-9][A-Za-z0-9._+-]*)*$` and contains no `..`. If a check fails, report the line and run nothing for it.

First match the line's current ref:

- **`@<40-hex> # <tag>` and `<tag>` resolves (step 2) to that SHA** → leave it, even when `<tag>` is a moving major such as `# v7`.
- **A 40-hex SHA with no comment, or a comment whose tag doesn't resolve to it** → keep the SHA; comment it with the most specific tag on that commit from the step 2 `/tags` listing. If no tag points at it, report the line rather than guess.
- **A branch (`@main`, `@master`)** → pin the latest release (steps 1 then 2) and note the version change in the commit message.
- **A tag** → pin that tag; pinning is not a version bump. Go to step 2.

1. **Pick the latest release** (new lines and branch refs only):

   ```bash
   gh api 'repos/<owner>/<repo>/releases/latest' --jq .tag_name
   ```

   If that 404s (the repo publishes tags but no releases), take the highest semver tag, ignoring pre-releases (`-rc`, `-beta`):

   ```bash
   gh api --paginate 'repos/<owner>/<repo>/tags' --jq '.[].name' | grep -E '^v?[0-9]+(\.[0-9]+)*$' | sort -V | tail -1
   ```

   Never assume a `v1` exists: `oalders/install-ubi-action`, for example, only has `v0.0.x` tags.

2. **Resolve the SHA.** This handles annotated and lightweight tags alike and can't match a same-named branch; a 404 means the tag does not exist:

   ```bash
   gh api 'repos/<owner>/<repo>/commits/refs/tags/<tag>' --jq .sha
   ```

   If the tag is a moving major (`v1`, `v7`), find the most specific tag on that same commit in `gh api --paginate 'repos/<owner>/<repo>/tags'` (each entry carries `.commit.sha`) and use it for the comment.

3. **Write** `uses: <owner>/<repo>[/path]@<40-hex sha> # <tag>`.

## Dependabot

If `.github/dependabot.yml` has no `package-ecosystem: github-actions` entry, add one with `directory: /` and `schedule.interval: weekly` (create the file with `version: 2` and an `updates:` list if it does not exist), then apply `kitchen-sink:tune-dependabot-config` to add its groups and cooldown — follow its steps inline, since a subagent can't invoke slash commands. Without the entry, pinned SHAs never get bumped. If the repo has composite actions in subdirectories (e.g. `.github/actions/*/action.yml`), the entry uses `directories:` listing `/` plus each of those directories instead of `directory: /`, so their pins get bumped too.

## Verify

- Every in-scope `uses:` ref in the edited files matches `@[0-9a-f]{40} # <tag>`.
- For each pin, `gh api 'repos/<owner>/<repo>/commits/refs/tags/<tag-from-comment>' --jq .sha` equals the pinned SHA. Checking `commits/<sha>` is not enough: a fork-only commit resolves by SHA but not by the upstream tag.
- `.github/dependabot.yml` has a `github-actions` entry.
