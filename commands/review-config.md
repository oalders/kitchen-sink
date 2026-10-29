---
description: Use when the user wants to view or change this repo's Codex bot wait and Codex timeout action (both also read by /shepherd-pr), Codex round cap, review round cap, or /shepherd-pr deadline (per-clone git config).
disable-model-invocation: true
---

Show and change the per-repo review settings that `codex-review-loop`, `/fix-gh-issue` and `/shepherd-pr` read. They are per-clone git config keys written with `--local`, so they are never committed; skills only read them. The Codex mode itself is set with `/codex-review`.

| Key | Values | Default |
|-----|--------|---------|
| `kitchen-sink.codexTimeoutMinutes` | positive integer | `30` |
| `kitchen-sink.codexTimeoutAction` | `stop`, `proceed` | `stop` |
| `kitchen-sink.codexRounds` | `1`–`5` | `3` |
| `kitchen-sink.reviewRounds` | `1`–`5` | `3` |
| `kitchen-sink.shepherdTimeoutMinutes` | positive integer | `180` |

Steps:

1. **Show.** Run `git config --local --get-regexp '^kitchen-sink\.'` for the raw values (exit 1 = none set; that's fine). List each key in the table with its value, or its default when unset, and flag any value that fails its step 3 pattern as invalid (the readers tolerate forms like `05` or `Proceed`, but this command writes only canonical ones). Show `kitchen-sink.codexOuterSandbox` read-only, and leave `kitchen-sink.codexReview` to `/codex-review`. Then run `python3 <skill base dir>/codex_loop.py mode`, where the base directory is the `codex-review-loop` skill's, and show its `bot_wait` and `rounds`. If it prints only `{"error": ...}`: when the key it names is one you flagged, go on to step 2; otherwise report it and stop, since this command doesn't write that key. An `error` next to the full JSON (the `codex` CLI is missing) is not a config problem.
2. **Ask.** One question per key in the table, over two AskUserQuestion calls (at most 4 questions each). Each offers **Keep** (current value; leave it out for a key flagged invalid) and **Default** (unset), plus:
   - `codexTimeoutAction`: `proceed`, described as: a timeout passes the gate without a bot review, so the PR can be marked ready, and a `/fix-gh-issues` run with merging on may merge it. Mark **Default** (`stop`) as Recommended.
   - Numeric keys: one sample value that isn't the current one (`codexTimeoutMinutes` `60`, else `15`; `shepherdTimeoutMinutes` `240`, else `60`; rounds `5`, else `1`), so the question always has two options; its description says any other value goes in via Other.
3. **Validate** each answer as a whole string: minutes `^[1-9][0-9]*$`, rounds `^[1-5]$`, action `^(stop|proceed)$`. On a mismatch, re-ask that question once; if it still doesn't match, stop without writing anything. Never write a value that hasn't passed.
4. **Warn** if any key will change, then go on: `--local` lives in the clone's shared `.git/config`, so the change applies to every worktree of this clone, including runs already in progress.
5. **Write** only the keys whose answer changed:
   ```bash
   git config --local <key> '<value>'   # new value
   git config --local --unset <key>     # Default (exit code 5 = already unset; that's fine)
   ```
   Then re-run step 1.

Never set `kitchen-sink.codexOuterSandbox`, `NONO_CAP_FILE`, or any key the user didn't answer in this run.
