---
description: Shows or switches this repo's Codex review mode (on = local + mandatory GitHub @codex review, local, off, default)
argument-hint: "[on|local|off|default|status]"
---

Show or change how the `codex-review-loop` skill behaves in **this repository**. The setting is the per-clone git config key `kitchen-sink.codexReview`. It is written with `--local`, so it is never committed and never affects other repos.

Argument: `$ARGUMENTS` (empty means `status`)

| Argument | Sets `kitchen-sink.codexReview` to | Effect |
|----------|------------------------------------|--------|
| `on` / `github` | `github` | Local Codex loop, plus a **mandatory** `@codex review` gate from the GitHub bot before the PR is marked ready |
| `local` | `local` | Local Codex loop only. Never comments on the PR. |
| `off` | `off` | Skips Codex entirely, even when `codex` is installed |
| `default` | *(key removed)* | Back to the default: `off` |
| `status` / empty | *(unchanged)* | Reports the effective mode |

Steps:

1. Map the argument to a value using the table. If the argument is anything else, show the table and stop without changing anything.
2. Apply it, running only the line that matches the argument:
   ```bash
   git config --local kitchen-sink.codexReview github   # on / github
   git config --local kitchen-sink.codexReview local    # local
   git config --local kitchen-sink.codexReview off      # off
   git config --local --unset kitchen-sink.codexReview  # default (exit code 5 = already unset; that's fine)
   ```
3. Report the effective mode. Run `python3 <skill base dir>/codex_loop.py mode`, where the base directory is the `codex-review-loop` skill's, and read `mode`, `source`, `codex`, `codex_version` and `outer_sandbox` from its JSON.

   Say whether the mode came from config or from the default (unset means `off`). When the mode isn't `off` and `codex` runs, `codex_version` shows the version that actually runs. Otherwise, for `github` or `local`, the command exits 2 with an `error` field (`codex` missing or unable to run): warn the user that every `codex-review-loop` run in this repo will stop with an error until they install or fix `codex` or change the mode. For `off` there is no version check.

   Also report the outer-sandbox state: `outer_sandbox.enabled` shows whether Codex's own sandbox is bypassed, and `outer_sandbox.source` says why: `git-config` (set via `kitchen-sink.codexOuterSandbox`), `nono` (on by default under nono), or `default` (off; no outer sandbox detected). Never change `kitchen-sink.codexOuterSandbox` or `NONO_CAP_FILE` yourself.
4. When the mode is `github`, remind the user that the repo needs the Codex GitHub integration set up to review PRs. Without it, `@codex review` gets no answer and the gate times out.
