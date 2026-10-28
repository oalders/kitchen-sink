---
description: Walk through this repo's per-clone review settings (Codex bot wait, timeout action, Codex and review round caps) and write the ones the user changes with git config --local.
disable-model-invocation: true
---

Show and change the per-repo review settings that `codex-review-loop` and `/fix-gh-issue` read. They are per-clone git config keys written with `--local`, so they are never committed. Only the user runs this command; skills only read these keys. The Codex mode itself is set with `/codex-review`.

| Key | Values | Default |
|-----|--------|---------|
| `kitchen-sink.codexTimeoutMinutes` | positive integer | `30` |
| `kitchen-sink.codexTimeoutAction` | `stop`, `proceed` | `stop` |
| `kitchen-sink.codexRounds` | `1`–`5` | `3` |
| `kitchen-sink.reviewRounds` | `1`–`5` | `3` |

Steps:

1. **Show.** Run `git config --local --get-regexp '^kitchen-sink\.'` for the raw values, and `python3 <skill base dir>/codex_loop.py mode`, where the base directory is the `codex-review-loop` skill's, for the effective `bot_wait` and `rounds`. List each key in the table with its value, or its default when unset. Show `kitchen-sink.codexOuterSandbox` read-only. If `mode` prints only `{"error": ...}`, say which key is invalid and offer to fix it in step 2.
2. **Ask.** Use one AskUserQuestion with one question per key in the table (4 questions). Each offers **Keep** (current value), **Default** (unset), plus:
   - `codexTimeoutAction`: `stop` (Recommended) and `proceed`. Describe `proceed` as: a timeout passes the gate without a bot review, and `/fix-gh-issues` may then auto-merge the PR.
   - Numeric keys: "type a value via Other".
3. **Validate** each answer as a whole string: minutes `^[1-9][0-9]*$`, rounds `^[1-5]$`, action `^(stop|proceed)$`. On a mismatch, re-ask once; if it still doesn't match, stop without writing anything.
4. **Warn once** before writing: `--local` lives in the clone's shared `.git/config`, so the change applies to every worktree of this clone, including runs already in progress.
5. **Write** only the keys whose answer changed:
   ```bash
   git config --local <key> '<value>'   # new value
   git config --local --unset <key>     # Default (exit code 5 = already unset; that's fine)
   ```
   Then re-run step 1.

Never set `kitchen-sink.codexOuterSandbox`, `NONO_CAP_FILE`, or any key the user didn't answer in this run.
