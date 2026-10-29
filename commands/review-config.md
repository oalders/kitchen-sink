---
description: Use when the user wants to view or change this repo's Codex bot wait and Codex timeout action (both also read by /shepherd-pr), Codex round cap, review round cap, /shepherd-pr deadline, or /shepherd-pr CI remediation entries (per-clone git config).
disable-model-invocation: true
---

Show and change the per-repo review settings that `codex-review-loop`, `/fix-gh-issue` and `/shepherd-pr` read. They are per-clone git config keys written with `--local`, so they are never committed; skills only read them. The Codex mode itself is set with `/codex-review`. It also manages the remediation entries `/shepherd-pr`'s repair skill matches against failed-check logs before attempting a code fix.

| Key | Values | Default |
|-----|--------|---------|
| `kitchen-sink.codexTimeoutMinutes` | positive integer | `30` |
| `kitchen-sink.codexTimeoutAction` | `stop`, `proceed` | `stop` |
| `kitchen-sink.codexRounds` | `1`–`5` | `3` |
| `kitchen-sink.reviewRounds` | `1`–`5` | `3` |
| `kitchen-sink.shepherdTimeoutMinutes` | positive integer | `180` |

A remediation entry is the section `kitchen-sink.remediation.<name>`: `match` (one Python regex, searched over the whole log), `run` (one: `rerun-full`, or a shell command) and `reads` (repo paths, one per value, a trailing `/` for a directory; at least one for a shell `run`). A shell `run` executes in the PR checkout: before adding one, show the user the security model in `ci_remediation.py`'s docstring (what `reads` must list, and that the command must not call `gh run rerun` or trigger workflows).

Steps:

1. **Show.** Run `git config --local --get-regexp '^kitchen-sink\.'` for the raw values (exit 1 = none set; that's fine). List each key in the table with its value, or its default when unset, and flag any value that fails its step 3 pattern as invalid (the Codex readers tolerate forms like `05` or `Proceed`, but `/shepherd-pr` reads `kitchen-sink.shepherdTimeoutMinutes` strictly and stops on a non-canonical value; this command writes only canonical ones). Show `kitchen-sink.codexOuterSandbox` read-only, and leave `kitchen-sink.codexReview` to `/codex-review`. Then run `python3 <skill base dir>/codex_loop.py mode`, where the base directory is the `codex-review-loop` skill's, and show its `bot_wait` and `rounds`. If it prints only `{"error": ...}`: when the key it names is one you flagged, go on to step 2; otherwise report it and stop, since this command doesn't write that key. An `error` next to the full JSON (the `codex` CLI is missing) is not a config problem. Then run `python3 <repair base dir>/ci_remediation.py list`, where `<repair base dir>` is `<codex-review-loop base dir>/../shepherd-pr-repair`, and show each entry, flagging those with an `error` as invalid and showing each entry's `error` (exit 2 means at least one is; any invalid entry makes `/shepherd-pr` stop at its next failed check). A top-level `error` with no `entries` is a tool error: report it and stop.
2. **Ask.** One question per key in the table, over two AskUserQuestion calls (at most 4 questions each). Each offers **Keep** (current value; leave it out for a key flagged invalid) and **Default** (unset), plus:
   - `codexTimeoutAction`: `proceed`, described as: a timeout passes the gate without a bot review, so the PR can be marked ready, and a `/fix-gh-issues` run with merging on may merge it. Mark **Default** (`stop`) as Recommended.
   - Numeric keys: one sample value that isn't the current one (`codexTimeoutMinutes` `60`, else `15`; `shepherdTimeoutMinutes` `240`, else `60`; rounds `5`, else `1`), so the question always has two options; its description says any other value goes in via Other.
   - **Remediation entries**, in the second call: **Keep**, **Add an entry**, and, if any listed entry's name passes step 3's name rule, **Remove an entry** (its name goes in via Other). Add asks two more AskUserQuestion calls: name, `match` and `run` first, then `reads` (one path per line; skipped when `run` is `rerun-full`). Their sample options (e.g. `ci-bundle`, `rerun-full`) are examples; real values go in via Other.
3. **Validate** each answer as a whole string: minutes `^[1-9][0-9]*$`, rounds `^[1-5]$`, action `^(stop|proceed)$`. On a mismatch, re-ask that question once; if it still doesn't match, stop without writing anything. Never write a value that hasn't passed.
   - A new entry: the name matches `^[A-Za-z0-9][A-Za-z0-9-]*$` and isn't already listed; no value contains a newline or starts with `-`. Write each value to its own file in one private `mktemp -d` directory (under the session scratchpad, else `$TMPDIR`), removed when done, build the entry in a scratch config there with `git config --file <scratch> 'kitchen-sink.remediation.<name>.<field>' "$(cat <valuefile>)"` (`--add` for each `reads`), so quotes in a regex stay intact, and run `ci_remediation.py list --file <scratch>`. Exit 2: show the entry's `error` (or the top-level `error`), re-ask once, then stop without writing.
   - A removal: the name must be one step 1 listed and match the name rule above; an invalid name can't be passed to `--remove-section` safely, so tell the user to remove that section from `.git/config` by hand.
4. **Warn** if any key or remediation entry will change, then go on: `--local` lives in the clone's shared `.git/config`, so the change applies to every worktree of this clone, including runs already in progress (a running `/shepherd-pr` keeps the deadline it computed at start, but uses a remediation entry change at its next failed check).
5. **Write** only the keys whose answer changed:
   ```bash
   git config --local <key> '<value>'   # new value
   git config --local --unset <key>     # Default (exit code 5 = already unset; that's fine)
   ```
   A new remediation entry: the same `git config` commands as its scratch build, with `--local` in place of `--file <scratch>`. A removal: `git config --local --remove-section 'kitchen-sink.remediation.<name>'`.
   Then re-run step 1.

Never set `kitchen-sink.codexOuterSandbox`, `NONO_CAP_FILE`, or any key or remediation entry the user didn't answer in this run.
