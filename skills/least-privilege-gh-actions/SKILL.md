---
name: least-privilege-gh-actions
description: Use when writing or editing a `.github/workflows/*` file, to give its token least-privilege `permissions:` and stop `actions/checkout` persisting credentials.
version: 1.0.0
---

# Least-Privilege GitHub Actions

## Overview

Give the workflow token read-only scope by default and keep it out of `.git/config`:

```yaml
permissions:
  contents: read

jobs:
  test:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
```

**Why:** without a `permissions:` block the token gets the repo or org default, which may be write-all, and `actions/checkout` writes the token into `.git/config`, where every later step can read it. A compromised step or action then holds a token with more scope than the job needs.

## Algorithm

For each workflow file you apply this skill to:

1. **Top level.** If the workflow has no top-level `permissions:`, add `permissions:` / `contents: read` after `on:` (and after `concurrency:` if present), before `jobs:`. If it already has one that is exactly `contents: read`, or narrower (`{}` or only `: read` scopes), leave it. If it grants more (`write-all`, `read-all`, or any `: write` scope), report it as drift and don't rewrite it.
2. **Per job.** A job that needs more scope gets its own job-level `permissions:` listing only those scopes, never a broader top-level block. Examples: pushing commits or tags or creating releases (`contents: write`), PR comments or labels (`pull-requests: write`), Pages deploys (`pages: write`), OIDC (`id-token: write`). A job-level block replaces the top-level block rather than adding to it, so it must also list `contents: read` when the job checks out code or otherwise needs it. If you can't tell what a job needs, skip the whole file and report it; make no partial edits.
3. **Checkout.** Set `persist-credentials: false` under `with:` on every `actions/checkout` step. Exception: if a later step in that job pushes or otherwise talks to the remote with git, leave that checkout as is and report it. That covers `git push`, `git fetch` and `git pull` in `run:`, and actions that commit or push with the persisted credentials, such as `stefanzweifel/git-auto-commit-action`, `peter-evans/create-pull-request` and `EndBug/add-and-commit`. A step that passes a token explicitly under `with:` (e.g. `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`) doesn't rely on persisted credentials.

## Verify

- `python3 -c 'import yaml, sys; yaml.safe_load(open(sys.argv[1]))' <file>` exits 0.
- The top-level `permissions` is `contents: read` or narrower, or the file is a reported drift item.
- Every `actions/checkout` step not reported sets `persist-credentials: false`.
- Every job-level `permissions:` block in a job with a checkout lists `contents: read`.
