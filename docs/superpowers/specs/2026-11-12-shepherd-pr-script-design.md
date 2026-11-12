# /shepherd-pr: move the state machine into a tested script

Issues #174 and #175 (folded in by user decision).

## Intent

About 80% of `commands/shepherd-pr.md` is deterministic logic written as prose: ref and SHA checks, check buckets, the "head was ejected" test, deadline math, rerun eligibility, step 5's first-match-wins re-read, the repair cap, and the status line that carries the counters. The agent rereads and re-applies all of it every pass, which is error-prone, and the counters disappear on compaction, which is why a compacted run falls back to a degraded "recovered" pass (`repairs 3/3`, no re-enqueue, terminal on auto-merge turned off).

Move that logic into a stdlib Python script with unit tests, and keep the run's counters in a state file the script owns, so compaction costs nothing: the agent just runs the script again. The agent keeps only judgment work.

## Goals, non-goals, anti-goals

- **Goal:** every deterministic rule in today's command lives in tested code; the command file becomes a short loop.
- **Goal:** a compacted run keeps exactly the limits of an uncompacted one. The status line, its compaction rules and step 1's recovered pass are deleted.
- **Goal:** the script does the mechanical GitHub work itself (user decision, approach B below): it only hands control back when judgment is needed.
- **Non-goal:** changing what the limits mean. Counters stay **per run** (user decision): `start` resets them, so re-running `/shepherd-pr` is still the user choosing to continue. The rerun and re-enqueue limits remain per head across runs because they are counted from GitHub (run `attempt`, `RemovedFromMergeQueueEvent`s), as today.
- **Non-goal:** #178's stop log and `stats`, #176's single-subagent repair. Stop codes are added (the tests need them anyway); the log stays in #178.
- **Non-goal:** loosening or tightening any stop. Behaviour is ported, not redesigned. Where porting exposes a rule that only existed for compaction recovery, it is deleted.
- **Anti-goal:** untrusted text (PR title/body, file paths, check names, bot output, logs) reaching a field the agent puts on a command line, or being printed outside a file.
- **Anti-goal:** the script merging directly, force-pushing, or posting anything but the `@codex review` trigger.
- **Anti-goal:** a script bug that silently passes a gate. Any unexpected `gh` output, schema drift or exception is a terminal stop, never a pass.

## Constraints

- Python 3 stdlib only; same style as `codex_loop.py` and `ci_remediation.py` (argparse subcommands, JSON on stdout, exit 2 = tool error).
- The harness blocks a foreground `sleep` and caps a foreground Bash call at 10 min. A `next` that may wait runs with `run_in_background: true`, like `codex_loop.py gh-wait` today; its exit re-invokes the agent.
- The repo is public and the command acts on GitHub on the user's behalf; the untrusted-data rules in today's Rules stay in force.
- Tests run in CI from `.github/workflows/` (a sensitive surface), so `/fix-gh-issue` step 11 leaves this PR in draft.

## Approaches

Where does the script stop and the agent start?

- **A. Decide only (the issue as written).** `next` reads GitHub and the state file and prints one action; the agent runs `gh pr ready`, `gh pr merge --auto`, `gh run rerun` and the waits from validated fields. Simpler script, every write visible in the transcript, but about ten command templates and the wait mechanics stay in prose for the agent to re-apply.
- **B. Decide and do the mechanical steps (chosen).** `next` also performs the non-judgment writes and the waits, returning only for a repair, a log triage, a hand-off, a stop, or done. The command file shrinks the most and there is least left for the agent to get wrong, which is the problem being fixed. Cost: the script writes to GitHub, so its tests fake `gh`.
- **C. One long-running daemon.** Rejected: a single process outliving the 10-min tool cap and the agent's turns is harder to stop, and the agent couldn't interleave judgment.

Counters (user decision): **per run, saved to disk**, not per PR. A per-PR cap would change what re-running means; it can be its own issue.

This supersedes the watch-only recovery design, `2026-10-31-shepherd-pr-counters-lost-design.md`, whose approach C (a state file) was rejected for its bookkeeping; a script now does that bookkeeping and tests it.

## Design

### Location

`skills/shepherd-pr-repair/shepherd.py` and `test_shepherd.py`, beside `ci_remediation.py` (designer's call: the command already reaches that directory as `<codex-review-loop base dir>/../shepherd-pr-repair/`, so no stub `skills/shepherd-pr/` skill is needed). It calls `codex_loop.py` and `ci_remediation.py` as subprocesses with a `timeout=` (30 s for `match`, as today, because the remediation regex is user-supplied), reading their JSON; it doesn't import them, since their subcommands print to stdout.

### State file

`$(git rev-parse --git-dir)/kitchen-sink/shepherd/<n>.json`, mode 0600, written atomically (temp file + `os.replace`). `--git-dir` is per worktree (`.git/worktrees/<name>` in a linked one), which is deliberate: a run belongs to one checkout. Fields:

| Field | Meaning (today's equivalent) |
|---|---|
| `pr`, `branch`, `owner`, `repo`, `default`, `model` | fixed at `start`, re-checked each pass |
| `deadline` | epoch, `start` time + `shepherdTimeoutMinutes` |
| `gated_head` | last head this run shows/gates (today: last status line's head) |
| `codex_passed` | heads that passed step 2 this run |
| `automerge` | `on`, `off`, `off-by-run` (as today, including "a repair returned this head") |
| `repairs` | 0–3 |
| `rerun` | per-head count, reset on a new head this run pushed |
| `infra` | entries applied on this head |
| `requeued` | `createdAt` of the removal this run re-enqueued after |
| `wait_first` | set by `record repair-stopped --resumable`; the next pass starts with the 120 s resumable wait |
| `pending` | `null`, or the action last handed to the agent (`repair`, `triage`, `ready`) with its args |
| `ended` | set by every `stop` and `done` |

`next` and `record` find `<n>` the way `start` does (`gh pr view` on the current branch, re-checked anyway). A missing or `ended` file is a terminal stop saying to run `/shepherd-pr`. No file is written until `<n>` is known.

**One process at a time.** `start`, `next` and `record` hold an exclusive `fcntl.flock` on `<n>.lock` (beside the state file) for their whole run. A caller that can't take it returns `{"action":"busy"}` at once, changing nothing: the agent waits for the running task's notification (after `start`: stop, saying a run is still active). This covers a compacted agent starting a second `next` while the first is alive.

### Subcommands

All print exactly one JSON object on stdout; exit 0 for an action, 2 for a tool error. A tool error's stdout carries only a fixed `code`; `gh` stderr and any other detail go to the report file.

- **`start --model <name>`**: `<name>` must match `^[A-Za-z0-9. -]{1,40}$` (it goes into the public `@codex review` trigger's footer, `docs/attribution.md`, which the script can't detect). Then today's fail-fast key check, detached-HEAD check, PR lookup and every ref/SHA/owner regex, the cross-repo/author/default-branch limits, and the branch-mismatch check. No PR on a `fix-NNN` branch with the no-PR preconditions met → `{"action":"handoff","issue":<digits>}`, writing nothing. After the hand-off, if `/fix-gh-issue`'s outstanding list isn't exactly "nothing outstanding", the agent stops terminally as today; otherwise it runs `start` again (the one allowed second `start`), which now finds the draft PR. With a PR, `start` writes a fresh state file, with the deadline computed then (as today: once `<n>` is set, after any hand-off), and returns `{"action":"next"}` (or a stop).
- **`next`**: each call does at most about 9 minutes of work (user decision): passes until the agent is needed, a wait slice runs out, or the call's budget is used, then returns. A call that only ran out of time returns `{"action":"next"}` with `status`; the agent prints it and runs `next` again. So an interrupted agent stops writes within minutes and the user sees a status line at least that often. It re-reads GitHub every pass (today's step 1 reads) and applies, in order, today's steps 1–6 minus the judgment parts:
  - step 1 checks: later-pass foreign-head and auto-merge-turned-off stops (against `gated_head`/`automerge` from the file instead of a status line), the `(unconfirmed)` declines stop (with `--disable-auto` first), `UNKNOWN` merge state wait, `DIRTY`/`BEHIND` → repair `rebase`.
  - step 2: the Codex gate via `codex_loop.py` (`mode`, `gh-wait`, posting the trigger with the footer, the `proceed`/`stop` timeout rules, at most two triggers and the `--windows 2` wait). A `gh-wait` longer than the call's budget runs in slices: `gh-wait` already resumes its window from the trigger comment, so the script re-calls it with the same `--trigger-comment` on the next `next`. `findings` → repair `codex`.
  - step 3: the show block (written to `summary.txt`, untrusted fields fenced), changed files with sensitive marks, the `pull_request_target` note, method choice, the decide guard (`off-by-run` with a `fail` or `cancel` check: don't enable, and a draft stays draft), the ejection test and its evidence gathering, the remediation `match`; a `none` match → `triage`. For a non-draft head the block is shown on the first return after auto-merge is enabled, not before; it is for the record only, so that is accepted.
  - step 4: `gh pr merge --auto --<method> --match-head-commit`. A draft is not marked ready by the script (user decision): `next` returns `ready` and sets `pending` `ready`; the agent runs `gh pr ready <n>` itself so the `require-review-before-pr` hook still gates a `fix-NNN` draft, then runs `next`, which enables auto-merge. A `next` that finds `pending` `ready` and the PR still a draft is a terminal stop (`gh pr ready` failed or the hook refused it), never another `ready`.
  - step 5: the check watch (polling `gh pr checks --json` every 15 s; the 540 s `--watch` slices existed only for the Bash tool's cap), the re-read with first-match-wins, the queue watch and its deadlines.
  - step 6: cap check, the rerun and infra-rerun selection and evidence, `gh run rerun`, `--disable-auto` before a `codex` repair.
  - Resumable stops become an internal 120 s wait and another pass (bounded by the run deadline), so they never reach the agent; the deadline returns `stop` with code `STOP_DEADLINE`. A failed `gh` command is resumable or terminal by today's Rules (HTTP 5xx, secondary rate limit, GraphQL timeout, network error; never for `--disable-auto` or `gh run rerun`).
  - Waiting is plain `time.sleep` inside the script, with `gh` polls every 15 s as today.
  - Handing out a `repair` counts it, sets `automerge` `off-by-run` (the skill runs `--disable-auto` before it pushes, as today), and sets `pending`.
  - Before any pass, if `pending` is set (the agent came back via `next` without a `record`, e.g. after compaction):
    - A rebase in progress, HEAD with commits not on `headRefOid`, or a dirty tracked tree → terminal stop naming what's local (today's recovered-pass guard).
    - Pending `repair`, head unchanged: return the same `repair` action again, without counting another repair (the agent may never have started it).
    - Pending `repair`, `headRefOid` equal to local HEAD: the repair's push landed before its `record`; apply `repair-pushed`'s effects. This holds for a rebase, whose head doesn't descend from `gated_head`. Any other new head is still foreign.
    - Pending `triage`: re-gather the evidence and hand out the triage again; counters unchanged.
    - Pending `ready`: as in step 4 above.
  - **Evidence directories:** each pass's `evidence_dir` is a private `mktemp -d` under `$TMPDIR`. The script removes the previous one at the start of each pass and on `stop`/`done`. A `repair` with cause `checks` passes its `evidence_dir`, and the skill reads it instead of gathering its own.
- **`record <event>`**: the agent reports what only it knows; the script checks it and updates the file:
  - `repair-pushed` (repair skill's new head): the script reads local HEAD and requires `headRefOid` to equal it, or it's a terminal stop (it never takes a SHA from the agent). Then new head, auto-merge `off-by-run`, `rerun`/`infra` reset, `pending` cleared.
  - `repair-stopped --resumable`: refunds the repair (as today's "repairs one lower") and sets `wait_first`.
  - `repair-stopped --terminal`: marks the run ended and returns a `stop` action with `automerge`, `queued` and, for cause `checks` with HEAD still at the gated head, today's list of `gh run rerun <id>` commands to try first in the report.
  - `triage --verdict infra|not-infra`.

### Actions

```json
{"action":"next"}
{"action":"busy"}
{"action":"handoff","issue":<digits>}
{"action":"repair","cause":"checks|codex|rebase","head":"<sha>","branch":"<ref>","default":"<ref>","codex_mode":"<mode>","evidence_dir":"<path>"}
{"action":"triage","evidence_dir":"<path>"}
{"action":"ready","pr":<n>}
{"action":"stop","terminal":true,"code":"STOP_EJECTED","report":"<path>","automerge":"on|off","queued":false}
{"action":"done","merged":true}
```

Every action after `start` also carries `status`, a one-line summary the agent prints (user decision; it replaces today's status line for the user's benefit, not as state): `#<n> head <sha7> · checks <count per bucket> · auto-merge <on|off|off by this run> · queue <position|no> · repairs <r>/3 · rerun <c> · infra <names> · deadline <epoch>`, built only from validated fields. The first return after a head is new to the run also carries `summary`, the path of the step 3 block, which the agent shows fenced; for a draft that is the `ready` return, so the block is still shown before the PR is marked ready.

Every field is either a fixed token, an integer, a regex-validated ref/SHA, a remediation entry name (which `ci_remediation` already validates), or a path the script created. Untrusted text only appears inside files in `evidence_dir` (or the stop's `report` file); the agent shows them in a fence. `code` is from a fixed enum in the script (one per distinct stop in today's command).

### Repair skill

`shepherd-pr-repair` keeps code fixes, rebase and Codex fixing, and its `codex` evidence. Its infra-match branch (the `--log-failed` evidence for `failure` runs, the third-party-status guard, match → `gh run rerun` → wait) moves into the script, with its counting unchanged (designer's call, per the no-behaviour-change non-goal): on a `checks` failure the script first tries step 6's rerun and infra-rerun paths as today, then, before handing out a `repair`, runs the skill's infra match; a match spends a repair, appends to `infra`, reruns and continues, and an entry already in `infra` falls through to the code-fix `repair` with that evidence. Other skill edits:

- The guard becomes "invoked from a `/shepherd-pr` `repair` action in this conversation" (there is no step 6 any more), and the description says the same.
- Step 2's transient-`gh` exception lists the resumable error classes itself instead of pointing at `/shepherd-pr`'s Rules.
- Each exit names its `record` event (`repair-pushed`, `repair-stopped --resumable`, `repair-stopped --terminal`); the `<infra>` input and the "returning without a new head" exit go.
- Its `version` frontmatter is bumped.

`agents/ci-log-triage.md` (which names step 3 or 6) and the `ci_remediation.py` docstring (re-enqueue use) are updated to name the script.

### Command file

Shrinks to the scope paragraph, the rules that bind the agent, and the loop.

Rules kept:
- Never ask the user anything.
- The untrusted-data rule.
- Never run `/shepherd-pr` yourself (`ffe9e0a`, #140), and never run `shepherd.py start` except at the start of a run and once after a hand-off. Another `start` resets the counters.
- The agent never runs `gh pr merge`; only the repair skill runs `--disable-auto`.
- Any failure of a command the agent runs itself (`gh pr ready`, the skill, the triage agent) ends the run with a report; the script turns a failed `gh pr ready` into a terminal stop on its next call.

The loop:
1. `shepherd.py start --model <running model>`. On `handoff`, run `/fix-gh-issue` as step 1's hand-off does today, then `start` again if nothing is outstanding.
2. `shepherd.py next` with `run_in_background: true`; wait for its notification.
3. Print `status` (and `summary`, fenced, when present), then act on the action:
   - `next`: back to 2.
   - `busy`: wait for the running task's notification, then back to 2.
   - `ready`: `gh pr ready <n>`, then back to 2.
   - `repair`: invoke `kitchen-sink:shepherd-pr-repair` with the fields, then `record` its result.
   - `triage`: one `kitchen-sink:ci-log-triage` with the evidence files, then `record triage`.
   - `stop`/`done`: show the report fenced and say what the user does next (re-run `/shepherd-pr`, auto-merge state, queue state). This ends the run.
   - Otherwise back to 2.

After a compaction: run `next` again (a `busy` reply means the earlier call is still running).

### Tests

`test_shepherd.py`, stdlib `unittest`, with a fake `gh` runner keyed on argv (as `test_codex_loop.py` does). One test per rule that today exists only as prose:
- the ejection test: the head's vs an earlier head's removal, `requeued` handled, no suites;
- deadline anchoring and checks;
- rerun/infra-rerun eligibility;
- step 5's first-match order (a push both changes the head and logs an ejection);
- the queue watch deadlines;
- the repair cap and its refund;
- the `pending` cases after compaction, including a rebase repair pushed before its `record`;
- the lock (`busy`);
- `pending` `ready` with the PR still a draft;
- `record repair-pushed` refusing a head that isn't local HEAD;
- the untrusted-text rule: a hostile title, log or `gh` stderr never appears in stdout;
- a failing `gh`, resumable vs terminal.

The tests are added to `.github/workflows/test.yml` beside the existing test lines.

### Docs

- README `/shepherd-pr` section: rewrite the line about waiting after resumable stops and printing a status each pass (it's now inside `next`, with a status line on each return), drop the compaction bullet, and say the run's state lives in `$(git rev-parse --git-dir)/kitchen-sink/shepherd/`.
- The counters-lost design: a one-line "Superseded by" note at the top.
- Version bump (minor: behavioural change) in `plugin.json` and both `marketplace.json` fields.

## Left to the builder

- Module layout inside `shepherd.py`.
- The exact `STOP_*` names.
- How the summary/report files are laid out, as long as untrusted text is fenced as today's rule says.
- Order of porting, as long as the final command no longer references the status line or the recovered pass.
