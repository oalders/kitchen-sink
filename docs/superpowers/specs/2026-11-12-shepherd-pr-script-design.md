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

`skills/shepherd-pr-repair/shepherd.py` and `test_shepherd.py`, beside `ci_remediation.py` (builder's-call made by the designer: the command already reaches that directory as `<codex-review-loop base dir>/../shepherd-pr-repair/`, so no stub `skills/shepherd-pr/` skill is needed). It imports `codex_loop` and `ci_remediation` by path rather than shelling out where that is simpler; either is acceptable.

### State file

`$(git rev-parse --git-dir)/kitchen-sink/shepherd/<n>.json`, mode 0600, written atomically (temp file + `os.replace`). Fields:

| Field | Meaning (today's equivalent) |
|---|---|
| `run_id` | random, set by `start`; every `next`/`record` is for the current run |
| `pr`, `branch`, `owner`, `repo`, `default` | fixed at `start`, re-checked each pass |
| `deadline` | epoch, `start` time + `shepherdTimeoutMinutes` |
| `gated_head` | last head this run shows/gates (today: last status line's head) |
| `codex_passed` | heads that passed step 2 this run |
| `automerge` | `on`, `off`, `off-by-run` (as today, including "a repair returned this head") |
| `repairs` | 0–3 |
| `rerun` | per-head count, reset on a new head this run pushed |
| `infra` | entries applied on this head |
| `requeued` | `createdAt` of the removal this run re-enqueued after |
| `pending` | `null`, or the action last handed to the agent (`repair`, `triage`, `handoff`) with its args |

`stop` and `done` mark the file `ended`; `next` or `record` on a missing or `ended` file is a terminal stop saying to run `/shepherd-pr` (designer's call: `start` is a single call, so there is no half-started run, and the agent never needs to carry `run_id`).

Per-PR file, so two PRs in one clone don't collide. A second concurrent run on the same PR is not supported; `start` simply overwrites (as a second run today would ignore the first's status line).

### Subcommands

All print exactly one JSON object on stdout; exit 0 for an action, 2 for a tool error (with `error`).

- **`start --model <name>`**: the model name is for the `@codex review` trigger's footer (`docs/attribution.md`), which the script can't detect; it is stored in the state file. Then today's fail-fast key check, detached-HEAD check, PR lookup and every ref/SHA/owner regex, the cross-repo/author/default-branch limits, and the branch-mismatch check. No PR on a `fix-NNN` branch with the no-PR preconditions met → `{"action":"handoff","issue":<digits>}`. (it first writes a state file with `pending` `handoff` and no deadline); after the hand-off, if `/fix-gh-issue`'s outstanding list isn't exactly "nothing outstanding", the agent stops terminally as today; otherwise it runs `start` again, which now finds the draft PR. Otherwise `start` writes a fresh state file, with the deadline computed then (as today: once `<n>` is set, after any hand-off), and returns `{"action":"next"}` (or a stop).
- **`next`**: one call runs passes until it needs the agent. It re-reads GitHub every pass (today's step 1 reads) and applies, in order, today's steps 1–6 minus the judgment parts:
  - step 1 checks: later-pass foreign-head and auto-merge-turned-off stops (against `gated_head`/`automerge` from the file instead of a status line), the `(unconfirmed)` declines stop (with `--disable-auto` first), `UNKNOWN` merge state wait, `DIRTY`/`BEHIND` → repair `rebase`.
  - step 2: the Codex gate via `codex_loop` (`mode`, `gh-wait`, posting the trigger with the footer from `docs/attribution.md`, the `proceed`/`stop` timeout rules, at most two triggers and the `--windows 2` wait). `findings` → repair `codex`.
  - step 3: the show block (written to `evidence_dir/summary.txt`, untrusted fields fenced), changed files with sensitive marks, the `pull_request_target` note, method choice, the ejection test and its evidence gathering, the remediation `match`; a `none` match → `triage`.
  - step 4: `gh pr merge --auto --<method> --match-head-commit`. A draft is not marked ready by the script (user decision): `next` returns `ready`, the agent runs `gh pr ready <n>` itself so the `require-review-before-pr` hook still gates a `fix-NNN` draft, then runs `next` again, which enables auto-merge.
  - step 5: the check watch (`gh pr checks --watch` in 540 s slices), the re-read with first-match-wins, the queue watch and its deadlines.
  - step 6: cap check, the rerun and infra-rerun selection and evidence, `gh run rerun`, `--disable-auto` before a `codex` repair.
  - Resumable stops become an internal 120 s wait and another pass (bounded by the run deadline), so they never reach the agent; the deadline returns `stop` with code `STOP_DEADLINE`.
  - Waiting is plain `time.sleep` inside the script, with `gh` polls every 15 s as today.
  - Before any pass, if `pending` is set (the agent was handed a repair and the run then came back via `next` without a `record`, e.g. after compaction): if a rebase is in progress, HEAD has commits not on the PR head, or the tracked tree is dirty → terminal stop naming what's local (today's recovered-pass guard). Otherwise, for a pending `repair` whose push landed before the `record` (designer's call: `headRefOid` equals local HEAD and descends from `gated_head`), apply `repair-pushed`'s effects itself instead of the foreign-head stop; any other new head is still foreign. Then clear `pending` and go on. A pending `repair` that never recorded its result does not refund the repair. A pending `handoff` → terminal stop as today's recovered pass ("the draft stays draft; the outstanding list may not have been shown; re-running marks it ready").
- **`record <event>`**: the agent reports what only it knows, and the script updates the file:
  - `repair-pushed --head <sha>` (repair skill step 7: new head, auto-merge `off-by-run`, `rerun`/`infra` reset),
  - `repair-stopped --resumable` (refunds the repair, as today's "repairs one lower"),
  - `triage --verdict infra|not-infra`,

### Actions `next` returns

```json
{"action":"repair","cause":"checks|codex|rebase","head":"<sha>","branch":"<ref>","default":"<ref>","codex_mode":"<mode>","evidence_dir":"<path>"}
{"action":"triage","evidence_dir":"<path>"}
{"action":"ready","pr":<n>}
{"action":"stop","terminal":true,"code":"STOP_EJECTED","report":"<path>","automerge":"on|off","queued":false}
{"action":"done","merged":true}
```

Every action also carries `status`, a one-line summary the agent prints (user decision; it replaces today's status line for the user's benefit, not as state): `#<n> head <sha7> · checks <count per bucket> · auto-merge <on|off|off by this run> · queue <position|no> · repairs <r>/3 · rerun <c> · infra <names> · deadline <epoch>`, built only from validated fields. The first return after a head is new to the run also carries `summary`, the path of the step 3 block, which the agent shows fenced; for a draft that is the `ready` return, so the block is still shown before the PR is marked ready. There is no live progress during a wait.

Every field is either a fixed token, an integer, a regex-validated ref/SHA, or a path the script created. Untrusted text only appears inside files in `evidence_dir` (or the stop's `report` file); the agent shows them in a fence. `code` is from a fixed enum in the script (one per distinct stop in today's command).

### Repair skill

`shepherd-pr-repair` keeps evidence gathering for code fixes, code fixes, rebase and Codex fixing. Its infra-match branch (the `--log-failed` evidence for `failure` runs, the third-party-status guard, match → `gh run rerun` → wait) moves into the script, with its counting unchanged (designer's call, per the no-behaviour-change non-goal): on a `checks` failure the script first tries step 6's rerun and infra-rerun paths as today, then, before handing out a `repair`, runs the skill's infra match; a match spends a repair, appends to `infra`, reruns and continues, and an entry already in `infra` falls through to the code-fix `repair`. The skill's `<infra>` input and "returning without a new head" exit go. It ends by telling the agent which `record` event to run.

### Command file

Shrinks to: the scope paragraph, the untrusted-data and never-ask rules, and the loop:

1. `shepherd.py start`; on `handoff`, run `/fix-gh-issue` as step 1's hand-off does today, then `record handoff-done`.
2. `shepherd.py next` in the background; wait for it.
3. Print `status` (and `summary`, fenced, when present). `ready` → `gh pr ready <n>`. `repair` → invoke `kitchen-sink:shepherd-pr-repair` with the fields; `record` its result. `triage` → one `kitchen-sink:ci-log-triage` with the evidence files; `record triage`. `stop`/`done` → show the report fenced and say what the user does next (re-run `/shepherd-pr`, auto-merge state, queue state). Otherwise back to 2.

After a compaction: run `next` again. Never `start` mid-run (that would reset the counters).

### Tests

`test_shepherd.py`, stdlib `unittest`, with a fake `gh` runner keyed on argv (as `test_codex_loop.py` does). One test per rule that today exists only as prose: the ejection test (head's vs earlier head's removal, `requeued` handled, no suites), deadline anchoring and checks, rerun/infra-rerun eligibility, step 5's first-match order (a push both changes head and logs an ejection), the queue watch deadlines, the repair cap and its refund, the `pending` guard after compaction, the untrusted-text rule (a hostile title/log never appears in stdout), and failing `gh` resumable vs terminal. Added to `.github/workflows/` beside the existing test lines.

### Docs

- README `/shepherd-pr` section: drop the compaction bullet; say the run's state lives in `.git/kitchen-sink/shepherd/`.
- The counters-lost design: a one-line "Superseded by" note at the top.
- Version bump (minor: behavioural change) in `plugin.json` and both `marketplace.json` fields.

## Left to the builder

- Module layout inside `shepherd.py`, and whether to import or subprocess `codex_loop`/`ci_remediation`.
- The exact `STOP_*` names.
- How the summary/report files are laid out, as long as untrusted text is fenced as today's rule says.
- Order of porting, as long as the final command no longer references the status line or the recovered pass.
