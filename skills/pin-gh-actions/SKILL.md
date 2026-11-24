---
name: pin-gh-actions
description: Use when adding, bumping, or editing any `uses:` line in `.github/workflows/*` or an `action.yml`.
version: 1.0.0
---

# Pin GitHub Actions

## Overview

Pin every external `uses:` ref to a full commit SHA with the tag as a trailing comment:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

**Why:** a tag or branch can be moved to different code after you review it; a commit SHA cannot. The comment keeps the pin readable and lets Dependabot bump SHA and comment together.

**Scope:** every action or reusable-workflow ref of the form `owner/repo[/path]@ref`, first-party `actions/*` included — there is no exemption. Local `./` refs and `docker://` refs are deliberately out of scope: the first is code in the same commit, the second is an image reference, not a git ref.

## Algorithm

For each in-scope `uses:` line you add, bump, or edit:

1. **Pick the version.** When pinning a ref that already names a tag, keep that tag — pinning is not a version bump — and go to step 2. Otherwise use the latest release:

   ```bash
   gh api repos/<owner>/<repo>/releases/latest --jq .tag_name
   ```

   If that 404s (the repo publishes tags but no releases), take the highest semver tag from:

   ```bash
   gh api --paginate repos/<owner>/<repo>/tags --jq '.[].name'
   ```

   Never assume a `v1` exists: `oalders/install-ubi-action`, for example, only has `v0.0.x` tags.

2. **Resolve the SHA.** This handles annotated and lightweight tags alike; a 404 means the tag does not exist:

   ```bash
   gh api repos/<owner>/<repo>/commits/<tag> --jq .sha
   ```

   If the tag is a moving major (`v1`, `v7`), find the most specific tag on that same commit in the `/tags` listing (each entry carries `.commit.sha`) and use it for the comment.

3. **Write** `uses: <owner>/<repo>[/path]@<40-hex sha> # <tag>`.

## Dependabot

If `.github/dependabot.yml` has no `package-ecosystem: github-actions` entry, add one with `directory: /` and `schedule.interval: weekly` (create the file with `version: 2` and an `updates:` list if it does not exist), then run `/tune-dependabot-config` to add its groups and cooldown. Without the entry, pinned SHAs never get bumped.

## Verify

- Every in-scope `uses:` ref in the edited files matches `@[0-9a-f]{40} # <tag>`.
- `gh api repos/<owner>/<repo>/commits/<sha> --jq .sha` returns the same SHA for each new pin.
- `.github/dependabot.yml` has a `github-actions` entry.
