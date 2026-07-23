# Inline diff-line review comments

**Issue:** #38 — Review skills should post findings as inline diff-line comments, not one wall-of-text PR comment.

## Problem

The review-posting skills (`code-review-flow`, `code-review-intense-flow`, `request-review`)
dump the entire review into a single PR-level comment via `gh pr comment`. That forces the
author to context-switch between a wall of text and the diff, manually mapping each point back
to a file and line. GitHub's inline review comments anchor each finding to the exact diff line,
collapsing the note right where the change is.

`gh pr comment` and `gh pr review --body` can only post PR-level text. Line-anchored comments
are reachable only through the REST API via `gh api`.

## Goal

Teach the review skills to post findings as **inline line comments, batched into a single PR
review**, whenever a finding carries a `file:line`. Fall back to the PR-level summary comment
only for findings that are genuinely file-spanning or architectural. Update the consumer
(`address-gh-review`) to read the inline review-comment endpoint so the "address the review"
loop can see the new notes.

## Design

### Single source of truth: `skills/code-review-flow/SKILL.md`

The full inline-review recipe lives once in `code-review-flow`'s SKILL.md. The other two posting
files already defer to "the `/code-review-flow` protocol", so they reference it in one line rather
than duplicating the `gh api` recipe. This follows the repo's existing "defer to code-review-flow"
convention and avoids the drift the issue warns about. No new shared-snippet directory is
introduced (the repo has none today).

The recipe replaces the current "Posting Review Results" block (lines ~85-88) and specifies:

1. **Resolve the head SHA robustly** — never assume local HEAD matches:
   ```bash
   gh pr view <n> --json headRefOid -q .headRefOid
   ```
2. **Build `review.json` with `jq`**, written to a temp file under `$TMPDIR` (falling back to
   `/tmp` only if unset) rather than a fragile inline heredoc, because finding bodies contain
   markdown/backticks. Shape:
   ```json
   {
     "commit_id": "<head-sha>",
     "event": "COMMENT",
     "body": "Automated review — inline findings below. <un-anchorable findings / assessment here>",
     "comments": [
       { "path": "go/web/foo.go", "line": 42, "side": "RIGHT",
         "body": "**[Important]** This nil check can move above the loop." },
       { "path": "go/web/bar.go", "start_line": 10, "start_side": "RIGHT", "line": 14, "side": "RIGHT",
         "body": "**[Minor]** This block can be simplified." }
     ]
   }
   ```
3. **POST once** — one review carrying all inline comments, so the author gets a single
   notification, not N:
   ```bash
   gh api repos/{owner}/{repo}/pulls/{n}/reviews --method POST --input review.json
   ```
4. **`event: "COMMENT"`** always — preserves the existing "never self-approve" rule for
   `code-review-flow` and `code-review-intense-flow`.

### Anchoring rule and fallback

- Each finding maps to a **changed line inside a diff hunk** (or the nearest changed line in the
  same hunk). `side: "RIGHT"` for the new version, `LEFT` for the deleted side; multi-line spans
  add `start_line` + `start_side`.
- A finding that **cannot** be tied to a diff line (architectural, file-spanning, or about
  unchanged context) goes into the review `body` summary instead. **Nothing is dropped** — every
  finding lands either as an inline comment or in the summary.

### Gotchas documented in the skill

1. **Line must be inside the diff.** Commenting on unchanged context outside a hunk → `422`. Map
   findings to changed lines; route the rest to the summary.
2. **SHA discipline.** Always resolve `headRefOid` via `gh pr view`; a stale/local SHA → `422`.
3. **Batch, don't spray.** One `reviews` POST with a `comments[]` array — not a loop of single
   `pulls/{n}/comments` POSTs.
4. **Never place finding text in a double-quoted shell word — and never as a bare literal inside
   the `jq` program.** This rule covers the summary `body` field EXACTLY as much as each
   `comments[].body`. Bash expands `$(...)`, backticks, and `$var` inside double quotes before jq
   runs, so attacker-controlled diff text quoted into a finding becomes command execution; and an
   apostrophe in a single-quoted-jq literal (e.g. an assessment saying "doesn't") breaks the bash
   arg. Keep every body — summary included — out of the shell: author `review.json` directly with
   your file-writing tool (primary), or in the shell fallback write each body to a file with a
   single-quoted heredoc (`<<'BODY'`) and pull it in with `jq --rawfile` (`body: $summary`).
5. **JSON assembly.** Prefer authoring `review.json` directly with your file-writing tool. In the
   shell fallback, build it with `jq` into a `mktemp -d` workdir (auto-cleaned via
   `trap 'rm -rf "$WORKDIR"' EXIT`), pulling the summary AND every finding body in via `--rawfile`
   (never a literal for either); don't inline a heredoc into jq and don't use a fixed temp path.
6. **Replies vs. new threads.** To follow up on an existing thread, use
   `POST .../pulls/{n}/comments/{comment_id}/replies` rather than opening a new one.

### `commands/code-review-intense-flow.md` (lines ~161-165)

Replace "post the aggregated summary as a PR comment via `gh pr comment`" with a one-line
reference to `/code-review-flow`'s inline-posting protocol. Specialist findings already carry a
lens tag and mostly a `file:line`, so they anchor naturally. Keep "never self-approve", the
>500-line "file issues for Minor" rule, and the re-run-until-clean loop unchanged.

### `commands/request-review.md` (lines ~215-241)

Replace the `gh pr comment` heredoc with a reference to `code-review-flow`'s inline protocol
(the *posting mechanism* is shared). **Keep `request-review`'s `--approve` gating unchanged** —
it approves on a passing review, which is its own behavior, distinct from `code-review-flow`'s
"never approve". Only the posting mechanism is shared, not the approve policy. Update the worked
example transcript to match.

### `commands/address-gh-review.md` — consumer side (line ~14)

Add a read of the inline endpoint alongside the existing conversation-comment read:
```bash
# PR-level (conversation) comments
gh api repos/{owner}/{repo}/issues/{pr}/comments
# Inline review-comment threads anchored to diff lines  (NEW)
gh api repos/{owner}/{repo}/pulls/{pr}/comments
```
The existing `--json reviews` read returns review bodies/state, not per-line comment bodies, so
the `pulls/{pr}/comments` read is required to see the inline notes. Preserve the untrusted-data
handling guidance below it unchanged.

### Example files

Update the two illustrative examples so docs match the new behavior:
- `skills/code-review-flow/examples/README.md` — replace the `gh pr comment` heredoc with the
  inline-review form, and fix the stray `gh pr review --approve` line that contradicts the
  SKILL's "never approve" rule.
- `skills/code-review-flow/examples/02-github-issue-fix.md` — its `File: src/utils/tags.ts:23`
  style references are exactly the findings that should become inline anchored comments; update
  the example to show them posted inline.

### Version bump

Behavioral change to existing skills → **minor** bump `2.12.0 → 2.13.0` in all three strings:
`.claude-plugin/plugin.json` (`version`) and `.claude-plugin/marketplace.json` (both the
`metadata` entry and the `plugins[]` entry).

## Non-goals / decisions

- **No GitHub MCP dependency.** `gh` is already the universal dependency of every kitchen-sink
  review skill; MCP server availability isn't guaranteed (notably in headless/cron review runs).
  The skills stay `gh api`-only for portability. The issue also specifies `gh api`.
- **No new shared-snippet directory.** The canonical-in-SKILL approach reuses the existing
  "defer to code-review-flow protocol" convention.

## Acceptance criteria

- [ ] A review run with findings carrying `file:line` posts them as inline comments on the diff,
      batched into a single review.
- [ ] Findings that can't be anchored to a changed line still land in the summary comment
      (nothing dropped).
- [ ] Head SHA resolved via `gh pr view --json headRefOid`, not assumed.
- [ ] "Never self-approve" preserved for `code-review-flow`/`code-review-intense-flow`
      (`event: COMMENT`); `request-review`'s `--approve`-on-pass gating unchanged.
- [ ] `address-gh-review` reads inline review comments (`pulls/{pr}/comments`), not just
      conversation comments.
- [ ] Docs note the "line must be inside the diff / 422" gotcha and the summary fallback.
- [ ] Example files updated to the inline pattern; stray `--approve` in README example removed.
- [ ] Version bumped to 2.13.0 across plugin.json + marketplace.json (both entries).

## Testing approach

These are markdown skill/command files, not executable code, so "tests" here means verifying the
documented recipe is correct and every acceptance criterion is satisfied by the edits:
- The `jq`-built `review.json` is valid JSON with the correct `reviews`-endpoint shape
  (`commit_id`, `event`, `body`, `comments[]` with `path`/`line`/`side`).
- The `gh api` endpoints and flags are correct (`pulls/{n}/reviews` POST for posting,
  `pulls/{pr}/comments` GET for consuming).
- A grep confirms no review-posting file still routes findings solely through `gh pr comment`,
  and every acceptance-criteria item maps to a concrete edit.
