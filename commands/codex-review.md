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
| `default` | *(key removed)* | Back to the default: `local` when `codex` is on PATH, otherwise `off` |
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
3. Report the effective mode:
   ```bash
   git config --get kitchen-sink.codexReview   # empty: default
   command -v codex
   ```
   Also report the outer-sandbox state (`kitchen-sink.codexOuterSandbox`; `python3 <codex-review-loop skill dir>/codex_loop.py mode` shows its effective `outer_sandbox` and the `codex_version` that actually runs). Never change that key yourself.
   When unset, the effective mode is `local` if `codex` is found, otherwise `off`. Say whether the mode came from config or from the default. If the mode is `github` or `local` but `codex` is missing, warn the user that every `codex-review-loop` run in this repo will stop with an error until they install `codex` or change the mode.
4. When the mode is `github`, remind the user that the repo needs the Codex GitHub integration set up to review PRs. Without it, `@codex review` gets no answer and the gate times out.
