# Attribution

Single source of truth for how Claude attributes the output it produces in this plugin's skills and
commands. Attribution is **always-on**: skills emit it by default. (A user who truly wants it suppressed
can override via their own `CLAUDE.md`; there is no per-invocation opt-out flag in the skills.)

## Resolve the model at runtime — never hardcode

Every place below names the model. **Fill in the model that is actually running when you produce the
output**, resolved from your session context (Claude Code surfaces the running model's id and display
name in your environment). Do **not** copy a literal like `claude-opus-4-8` from this doc into your
output — this doc's model strings are *examples*, and hardcoding one rots the moment the default model
changes. If the running model's identity is genuinely unavailable, fall back to plain `Claude Code`
(no version) rather than guessing a version.

Use the **display name** in commit trailers and the **exact id** in review footers:

| Example running model | Display name (trailers) | Exact id (footers) |
|-----------------------|-------------------------|--------------------|
| Opus 4.8              | `Claude Opus 4.8`       | `claude-opus-4-8`  |

(Illustrative row only — always substitute the model actually running.)

## Commit trailer

Every commit a skill creates ends with a blank line then this trailer (display name = running model):

```
Co-authored-by: Claude Opus 4.8 <noreply@anthropic.com>
```

The email is always `noreply@anthropic.com`; the display name is the running model.

## PR-body line

Every PR body a skill creates ends with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Review footer

Every review body a skill posts to a PR ends with this footer (exact id = running model). It goes on the
**summary/review body**, not on each individual inline finding:

```
---
🤖 Review by [Claude Code](https://claude.com/claude-code) · model: `claude-opus-4-8`
```

**Shell safety:** never build the review body — this footer *or* the findings alongside it — with a
double-quoted shell word or a bare literal inside a single-quoted `jq` program. In a double-quoted word
bash command-substitutes the footer's backticks (and any `$(...)`/`$var`); in a single-quoted `jq`
literal an apostrophe anywhere in the body (e.g. an assessment saying "doesn't") breaks the quoting,
after which trailing content — backticks included — is shell-interpreted. Instead, author the JSON body
directly with a file-writing tool (no shell at all — the preferred path), or emit it through a
single-quoted heredoc (`<<'BODY'`) + `--rawfile`/`--body-file`. See `code-review-flow`'s inline-review
protocol for the full apostrophe/backtick threat model.

The same discipline applies to the **commit trailer** and **PR-body line**, not just the footer: never
place any attribution string in a double-quoted word that would expand `$`/backticks, and — because the
model display name is resolved at runtime — any attribution string emitted inside a *single-quoted*
`gh`/`git` argument must stay apostrophe-free, else use `--body-file`/`--rawfile`. (Today's fixed strings
satisfy this; the caveat guards future edits and any runtime-resolved name that could contain a `'`.)
