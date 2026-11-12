# shepherd.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `/shepherd-pr`'s deterministic state machine out of `commands/shepherd-pr.md` into a tested stdlib script with a per-run state file, and shrink the command to a loop.

**Architecture:** Two files. `shepherd_rules.py` holds pure functions (validators, ejection test, deadlines, rerun eligibility, re-read classification, decide, status line), testable without fakes. `shepherd.py` holds the CLI (`start`/`next`/`record`), the state file and lock, the `gh` adapter, and the pass loop that calls the rules and does the writes. `codex_loop.py` and `ci_remediation.py` are called as subprocesses.

**Tech Stack:** Python 3 stdlib (`argparse`, `json`, `fcntl`, `subprocess`, `tempfile`, `unittest`), `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-11-12-shepherd-pr-script-design.md`. Read it and today's `commands/shepherd-pr.md` (on `main`; the rule text being ported) before every task.

## Global Constraints

- stdlib only; JSON on stdout, exactly one object per call; exit 0 for an action, 2 for a tool error.
- stdout fields are only fixed tokens, integers, regex-validated refs/SHAs, remediation entry names, or paths the script created. PR title/body, file paths, check names, bot output, logs and `gh` stderr go only into files.
- Regexes: SHA `^[0-9a-f]{40}$`; ref (`headRefName`, default branch) `^[A-Za-z0-9._/-]+$` with no `..` and no leading `-`; owner/repo `^[A-Za-z0-9._-]+$`; PR number `^[0-9]+$`; run/job/comment id `^[0-9]+$`; model `^[A-Za-z0-9. -]{1,40}$`; `shepherdTimeoutMinutes` `^[1-9][0-9]*$`, unset 180.
- State file `$(git rev-parse --git-dir)/kitchen-sink/shepherd/<n>.json`, mode 0600, atomic write (temp + `os.replace`); lock `<n>.lock` beside it, `fcntl.flock(LOCK_EX | LOCK_NB)` held for the whole call.
- `next` call budget: 540 s of work (≈ 9 min, under the Bash tool's 600 s cap), then `{"action":"next"}`.
- Waits: `time.sleep`, `gh` polls every 15 s; resumable wait 120 s.
- Repair cap 3 per run; rerun per head: 1, plus 1 infra rerun (`rerun` < 2, run `attempt` ≤ 2).
- Queue watch deadlines: queued with integer `estimatedTimeToMerge` ≥ 0 → `now + eta + 900`; queued otherwise → `start + 3600`; not queued → `start + 300`.
- Evidence log tails: last 300 lines, at most 65536 bytes.
- `ci_remediation.py match` run with a 30 s subprocess timeout.
- Never `gh pr merge` except `--auto --<method> --match-head-commit <sha>` and `--disable-auto`; never `gh pr ready`; never `gh run rerun --failed`; the only comment posted is the `@codex review` trigger (body: `@codex review`, blank, `Review of <sha>`, blank, the review footer from `docs/attribution.md` naming the model).
- Tests run as `python3 skills/shepherd-pr-repair/test_shepherd.py` and patch `shepherd.run` with a fake keyed on argv, as `test_codex_loop.py` patches `cl.run`.
- Commits end with `Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Two `next` processes at once** (a compacted agent re-running `next`): the second must return `busy` and change nothing. Test in Task 1.
2. **A hostile PR title / log / `gh` stderr containing a fence, `$(…)` or a fake status line**: never on stdout. Test in Task 3 (stderr) and Task 5 (title, log).
3. **Compaction between a rebase repair's force-push and `record`**: the rebased head (not a descendant of `gated_head`) equal to local HEAD is adopted, not stopped as foreign. Test in Task 3.
4. **The review hook denying `gh pr ready`**: the following `next` stops terminally, never returns `ready` twice. Test in Task 3.
5. **A Codex wait longer than one `next` call** (`--windows 2` = 60 min by default): sliced across calls without re-posting the trigger. Test in Task 4.

---

### Task 1: State file, lock, `start`

**Files:**
- Create: `skills/shepherd-pr-repair/shepherd_rules.py` (validators only in this task)
- Create: `skills/shepherd-pr-repair/shepherd.py`
- Create: `skills/shepherd-pr-repair/test_shepherd.py`
- Modify: `.github/workflows/test.yml` (add `- run: python3 skills/shepherd-pr-repair/test_shepherd.py` after the `test_ci_remediation.py` line)

**Interfaces:**
- Produces in `shepherd_rules.py`: `valid_sha(s) -> bool`, `valid_ref(s) -> bool`, `valid_name(s) -> bool` (owner/repo), `valid_id(s) -> bool`, `valid_model(s) -> bool`, `timeout_minutes(raw: str | None) -> int` (raises `RuleError` on a bad value), `class RuleError(Exception)`.
- Produces in `shepherd.py`:
  - `run(cmd, check=True, **kw) -> CompletedProcess` (same shape as `codex_loop.run`; raises `GhError(cmd, returncode, stderr)` on failure);
  - `gh_json(args: list[str]) -> object`;
  - `state_dir() -> str`, `load_state(n: int) -> dict | None`, `save_state(n: int, state: dict) -> None`;
  - `locked(n: int)` context manager raising `Busy`;
  - `emit(action: dict) -> int`, which prints one JSON line and returns the exit code;
  - `class Stop(Exception)` with `(code: str, terminal: bool, report: list[str])`, which `emit_stop` turns into a `stop` action, writes `report` lines to a file in a fresh `mktemp -d`, and marks the state `ended`;
  - `cmd_start(args)`, `main(argv=None)`.
- State keys exactly as in the spec's table: `pr, branch, owner, repo, default, model, deadline, gated_head, codex_passed, automerge, repairs, rerun, infra, requeued, wait_first, pending, ended`.

- [ ] **Step 1: Write failing tests**
  - `test_timeout_minutes`: `None`→180, `"5"`→5; `"0"`, `"05"`, `"x"` raise `RuleError`.
  - `test_valid_ref`: accepts `fix-174`, `feat/a.b`; rejects `a..b`, `-x`, `a b`, `a;b`.
  - `test_start_writes_state`: fake gh (PR 7 open, viewer = author, same repo, base = default, valid refs, branch matches) → stdout `{"action":"next"}`, state file mode `0o600`, `repairs == 0`, `rerun == 0`, `infra == []`, `deadline == now + 180*60`, `model == "Opus 5.5"`.
  - `test_start_handoff`: `gh pr view` fails, branch `fix-12`, `gh pr list --head fix-12 …` prints `0`, clean tree, commits ahead → `{"action":"handoff","issue":12}` and no state file written.
  - `test_start_rejects`: one subtest each for cross-repo, other author, non-default base, bad `headRefOid`, branch mismatch, detached HEAD, bad model → `action == "stop"`, `terminal` true, distinct `code`s, no state file.
  - `test_lock_busy`: while `locked(7)` is held in-process (open the lock fd in the test), `main(["start", "--model", "X"])` prints `{"action":"busy"}` and leaves an existing state file byte-identical.
- [ ] **Step 2:** Run `python3 skills/shepherd-pr-repair/test_shepherd.py`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement the validators, state/lock helpers and `cmd_start`, porting step 1's checks and the no-PR bullets of today's command (the bullets after `<n>` is set, not the recovered ones). `cmd_start` reads the timeout key first (fail-fast), and computes the deadline only once `<n>` is known.
- [ ] **Step 4:** Run the tests. Expected: PASS. Add the CI line.
- [ ] **Step 5:** Commit: `shepherd.py: state file, lock and start (#174)`.

### Task 2: Pure rules

**Files:**
- Modify: `skills/shepherd-pr-repair/shepherd_rules.py`
- Modify: `skills/shepherd-pr-repair/test_shepherd.py`

**Interfaces (all pure, in `shepherd_rules.py`):**
- `buckets(checks: list[dict]) -> dict[str, int]`: counts by `bucket`.
- `pick_method(repo: dict) -> str | None`: the first allowed of `squash`, `merge`, `rebase`.
- `is_head_removal(nodes: list[dict], removal_index: int, earliest_suite: str | None) -> bool`: today's step 3 rule. A removal is the head's unless the last add before it is earlier than `earliest_suite`; no suites or no earlier add → the head's.
- `ejection(pr: dict, nodes: list[dict], earliest_suite: str | None, requeued: str | None) -> dict | None`: the removal node when the head was ejected (not queued, no `autoMergeRequest`, the last add/removal is a removal that is the head's, `createdAt != requeued`).
- `may_requeue(nodes, removal, earliest_suite) -> bool`: no other removal in `nodes` is the head's.
- `queue_deadline(start: int, now: int, queued: bool, eta) -> int`.
- `rerun_choice(fail_checks: list[dict], runs: list[dict], gated_sha: str, rerun: int) -> tuple[str, list[int]]`: returns `("repair", [])` if any `fail`/`cancel` check's `state` isn't `CANCELLED`/`TIMED_OUT`; otherwise `("rerun", ids)`, `("infra-rerun", ids)` or `("stop", ids)`, with today's step 6 run filter (`event` `pull_request`, `headSha` the gated SHA, `name` equal to a check's `workflow`, `conclusion` in `failure`/`timed_out`/`cancelled`, numeric id) and attempt limits.
- `reread_outcome(pr: dict, checks: list[dict], gated_sha: str, ejected: bool) -> str`: step 5's items 1–3 in first-match order. Returns `merged`, `closed`, `new-head`, `failed`, `ejected` or `continue`.
- `in_queue_watch(pr: dict, checks: list[dict]) -> bool`: step 5 item 4's entry condition.
- `open_outcome(pr: dict, checks: list[dict], automerge: str) -> str`: step 5 item 5, first match. Returns `review-required`, `dirty-queued`, `rebase`, `pending`, `resumable-off-by-run` or `turned-off`.
- `decide(pr: dict, checks: list[dict], automerge: str) -> str`: step 3's decide, guard first. Returns `guard`, `keep-queue`, `ready`, `enable` or `keep`.
- `status_line(state: dict, pr: dict, checks: list[dict]) -> str`: the format in the spec's Actions section.
- `is_resumable_gh_error(cmd: list[str], stderr: str) -> bool`: today's Rules. False for `--disable-auto` and `gh run rerun`; true for HTTP 5xx, secondary rate limit, GraphQL timeout, network errors (timeout, connection reset/refused, unresolved host, TLS, unexpected EOF).

- [ ] **Step 1: Write failing tests** (one each; use literal node lists):
  - `test_ejection_head_removal`: nodes `[add t1, remove t2]`, earliest suite `t0` → returns the `t2` node.
  - `test_ejection_earlier_head`: nodes `[add t1, remove t2]`, earliest suite `t3` → `None`.
  - `test_ejection_requeued_handled`: same as the first, `requeued == t2` → `None`.
  - `test_ejection_no_suites`: earliest `None` → the removal.
  - `test_ejection_queued_or_automerge`: `isInMergeQueue` true → `None`; `autoMergeRequest` set → `None`.
  - `test_may_requeue_once_per_head`: two head removals → `False`.
  - `test_queue_deadline`: `(100, 200, True, 60)` → 1160; `(100, 200, True, None)` → 3700; `(100, 200, False, None)` → 400.
  - `test_rerun_choice`: a `FAILURE` state → `repair`; cancelled-only with `rerun` 0 and attempt 1 → `("rerun", [11])`; `rerun` 1, attempt 2 → `("infra-rerun", [11])`; attempt 3 → `stop`; a check whose workflow has no run → `stop`.
  - `test_reread_order_push_and_ejection`: a new head plus an ejection → `new-head`, not `ejected`.
  - `test_open_outcome_order`: `REVIEW_REQUIRED` with `DIRTY` → `review-required`; `DIRTY` queued → `dirty-queued`; `BEHIND` not queued → `rebase`.
  - `test_decide_guard`: `off-by-run` plus a `fail` check on a draft → `guard`.
  - `test_status_line`: exact string for a fixture state.
  - `test_resumable_errors`: `HTTP 502` → True; `secondary rate limit` → True; the same stderr with `gh pr merge 7 --disable-auto` → False; `HTTP 404` → False.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement each function in `shepherd_rules.py`, porting the matching paragraph of today's command word for word in behaviour.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `shepherd.py: pure rules for ejection, deadlines, reruns and decide (#174)`.

### Task 3: `next` loop skeleton, `pending`, `record`

**Files:**
- Modify: `skills/shepherd-pr-repair/shepherd.py`
- Modify: `skills/shepherd-pr-repair/test_shepherd.py`

**Interfaces:**
- Consumes: Task 1 helpers; Task 2 `status_line`, `is_resumable_gh_error`.
- Produces:
  - `read_pr(state) -> dict`: today's step 1 reads, merged into one dict with keys `pr`, `checks`, `repo`, `queue` (the GraphQL `pullRequest`).
  - `new_evidence_dir(state) -> str`: removes the previous one.
  - `cmd_next(args)` with `pass_once(state, budget_end: float) -> dict | None` (an action, or `None` to pass again).
  - `handle_pending(state, snap) -> dict | None`.
  - `cmd_record(args)`.
  - The `GhError` → resumable/terminal mapping: resumable means a 120 s wait and pass again within the budget, otherwise `{"action":"next"}` at the budget.

- [ ] **Step 1: Write failing tests**
  - `test_next_missing_or_ended`: no state file → terminal stop; `ended` set → terminal stop.
  - `test_next_budget_returns_next`: a fake clock past the 540 s budget during a pending-checks wait → `{"action":"next", "status": …}`.
  - `test_foreign_head`: state `gated_head` A, GitHub head B, no `pending` → terminal stop.
  - `test_automerge_turned_off`: state `automerge` `on`, GitHub off and not queued, no ejection → terminal stop.
  - `test_unconfirmed_decline`: body with `(unconfirmed)` under `## Declined findings` and auto-merge on → runs `gh pr merge 7 --disable-auto`, terminal stop; the body text is not on stdout.
  - `test_pending_repair_reissued`: `pending` repair, head unchanged, clean tree → the same `repair` action, `repairs` unchanged.
  - `test_pending_rebase_adopted`: `pending` repair `rebase`, GitHub head C equal to local HEAD, C not a descendant of A → no stop; `gated_head == C`, `rerun == 0`, `infra == []`, `automerge == "off-by-run"`.
  - `test_pending_local_work`: a rebase in progress (create `rebase-merge` under a temp git dir) → terminal stop.
  - `test_pending_ready_still_draft`: `pending` ready and `isDraft` true → terminal stop, not `ready`.
  - `test_record_repair_pushed_checks_head`: local HEAD ≠ GitHub head → terminal stop, state `ended`.
  - `test_record_resumable_refunds`: `repairs` 2 → 1, `wait_first` true; the next `next` sleeps 120 s before reading.
  - `test_record_terminal_reports_reruns`: cause `checks`, HEAD at gated → the report file contains `gh run rerun 11`; the stop has `automerge` and `queued`.
  - `test_gh_stderr_not_on_stdout`: a `gh` failure whose stderr is ```` ```$(rm -rf ~)``` ```` → stdout contains none of it; the report file does.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `cmd_next` (lock; load; `wait_first`; `handle_pending`; loop `pass_once` until an action or the budget), `read_pr`, the step 1 later-pass checks, the declines check, `UNKNOWN` (wait up to 30 s, then resumable), `DIRTY`/`BEHIND` → `repair_action(state, "rebase")`, and `cmd_record`. `repair_action` counts the repair (cap 3, else `Stop("STOP_REPAIR_CAP")`), sets `automerge` `off-by-run` and `pending`, and runs `codex_loop.py mode` for the `codex_mode` field.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `shepherd.py: next loop, pending recovery and record (#174)`.

### Task 4: Codex gate

**Files:**
- Modify: `skills/shepherd-pr-repair/shepherd.py`
- Modify: `skills/shepherd-pr-repair/test_shepherd.py`

**Interfaces:**
- Consumes: `codex_loop.py mode` and `gh-wait` JSON (fields `status`, `trigger`, `triggers`, `acknowledged`, `action`, `window_ends`), located at `os.path.join(HERE, "..", "codex-review-loop", "codex_loop.py")`.
- Produces: `codex_gate(state, snap, budget_end) -> dict | None`. Returns `None` once the gate passes (and adds the head to `codex_passed`), an action (`repair` cause `codex`, a stop, or `next` at the budget), or raises `Stop`. Per-head gate progress (`windows`, last trigger id) is kept in state under `codex`.

- [ ] **Step 1: Write failing tests**
  - `test_codex_mode_not_github`: mode `local` → the gate is skipped and `summary.txt` says "Codex gate not checked (mode `local`)".
  - `test_codex_clean`: `gh-wait --timeout 0` → `clean`, the head is added to `codex_passed`, and no comment is posted.
  - `test_codex_trigger_posted_once`: `timeout`, `trigger` null → one `gh pr comment 7 --body-file <f>`; the file reads `@codex review\n\nReview of <sha>\n\n🤖 Review by [Claude Code](https://claude.com/claude-code) · Opus 5.5`. Check the footer against `docs/attribution.md`.
  - `test_codex_wait_sliced`: `gh-wait` with `--timeout <remaining budget>` returns `pending` → `{"action":"next"}`. The next call re-runs `gh-wait --trigger-comment <id>` and posts nothing.
  - `test_codex_proceed_acknowledged`: `timeout`, `proceed`, `acknowledged` → one `--windows 2` wait, then a pass.
  - `test_codex_stop_retrigger`: `stop`, not acknowledged, `triggers` 1 → re-trigger once; a second timeout → terminal stop. Never a third trigger.
  - `test_codex_findings_repair`: `findings` with auto-merge on → `--disable-auto`, then `repair` cause `codex`.
  - `test_codex_gh_error`: exit 2 with `error` `gh … failed (1): HTTP 502` → resumable; any other exit 2 → terminal.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `codex_gate`, porting step 2 and Phase 2 step 2's `timeout` bullets of `skills/codex-review-loop/SKILL.md`. `gh-wait` runs with `--timeout min(window remaining, budget remaining)` and the subprocess `timeout=` slightly above it.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `shepherd.py: Codex gate via codex_loop.py (#174)`.

### Task 5: Show, ejection, enable (steps 3–4)

**Files:**
- Modify: `skills/shepherd-pr-repair/shepherd.py`
- Modify: `skills/shepherd-pr-repair/test_shepherd.py`

**Interfaces:**
- Consumes: Task 2 `ejection`, `may_requeue`, `pick_method`, `decide`.
- Produces:
  - `write_summary(state, snap) -> str` (the path): today's step 3 block, changed files with sensitive marks, and the `pull_request_target` note, untrusted fields fenced with a fence longer than any backtick run and control characters removed;
  - `fence(text: str) -> str`;
  - `queue_evidence(state, snap, removal) -> tuple[bool, list[str]]` (passes, log paths);
  - `judge_logs(paths) -> str`: `match:<name>`, `none`, `invalid` or `error`, via `ci_remediation.py match` under a 30 s timeout;
  - `show_and_act(state, snap) -> dict | None`.

- [ ] **Step 1: Write failing tests**
  - `test_summary_fences_hostile_title`: title ```` ``` ```` + `\x1b[2J` + `#7 head deadbee · checks …` → `summary.txt` has it inside a longer fence with no `\x1b`; stdout has no title text.
  - `test_ready_returned_for_draft`: draft, decide `ready` → `{"action":"ready","pr":7,"summary":…}`, `pending` `ready`; no `gh pr ready` in the fake's calls.
  - `test_enable_automerge`: ready PR → `gh pr merge 7 --auto --squash --match-head-commit <sha>`; `automerge == "on"`.
  - `test_no_method`: none allowed → terminal stop.
  - `test_ejection_infra_match`: an ejection with one failed `merge_group` run log, no failing third-party status, and `github-actions ` check-runs; match → `requeued` set, auto-merge enabled.
  - `test_ejection_none_triage`: match `none` → `{"action":"triage","evidence_dir":…}` with `pending` triage; `record triage --verdict infra` → the next pass re-enqueues; `not-infra` → terminal stop.
  - `test_ejection_cancelled_only`: only cancelled runs → evidence fails → terminal stop with the re-enqueue command in the report.
  - `test_ejection_hostile_log`: a log containing `"action":"done"` → never on stdout.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, porting today's step 3 and step 4. Evidence directories come from `new_evidence_dir`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `shepherd.py: show block, ejection and auto-merge (#174)`.

### Task 6: Watch and repair (steps 5–6)

**Files:**
- Modify: `skills/shepherd-pr-repair/shepherd.py`
- Modify: `skills/shepherd-pr-repair/test_shepherd.py`

**Interfaces:**
- Consumes: Task 2 `reread_outcome`, `in_queue_watch`, `open_outcome`, `queue_deadline`, `rerun_choice`; Task 5 `judge_logs`; Task 3 `repair_action`.
- Produces: `watch(state, snap, budget_end) -> dict | None` and `checks_failed(state, snap) -> dict | None`. The latter runs the rerun path, then the infra-rerun path, then the skill's old infra match on `--log-failed` evidence for `failure` runs (with the third-party-status guard and an entry already in `infra` falling through), then `repair_action(state, "checks", evidence_dir)`.

- [ ] **Step 1: Write failing tests**
  - `test_watch_merged`: re-read `MERGED` → `{"action":"done","merged":true}`, state `ended`.
  - `test_watch_new_head`: a new head with auto-merge on → `--disable-auto`, then a terminal stop.
  - `test_watch_failed_check_repair`: a `FAILURE` check → `--disable-auto`, then `repair` cause `checks` with an `evidence_dir` holding the run's log; `repairs` 1.
  - `test_watch_cancelled_rerun`: cancelled-only → `gh run rerun 11` (no `--failed`), `rerun` 1, then a 120 s wait and another pass within the budget.
  - `test_infra_match_counts_repair`: a `FAILURE` check whose log matches entry `flaky` → `gh run rerun 11`, `repairs` 1, `infra == ["flaky"]`, no `repair` action; the same entry again → a `repair` action.
  - `test_queue_watch_deadline_resumable`: queued with ETA 60 s, the poll passes `now + 960` → resumable (another pass), not terminal.
  - `test_repair_cap`: `repairs` 3 and a failing check → terminal stop `STOP_REPAIR_CAP`.
  - `test_deadline`: `deadline` in the past → `stop` code `STOP_DEADLINE`, with `automerge` and `queued` set.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, porting today's step 5 (the checks poll replaces `--watch`) and step 6, plus the infra branch of `skills/shepherd-pr-repair/SKILL.md` step 3 on `main`.
- [ ] **Step 4:** Run the whole file. Expected: PASS.
- [ ] **Step 5:** Commit: `shepherd.py: check and queue watch, reruns and repair hand-out (#174)`.

### Task 7: Command, skill, docs, version

**Files:**
- Modify: `commands/shepherd-pr.md` (rewrite to the spec's Command file section)
- Modify: `skills/shepherd-pr-repair/SKILL.md`
- Modify: `agents/ci-log-triage.md:3`
- Modify: `skills/shepherd-pr-repair/ci_remediation.py:9-10` (docstring)
- Modify: `README.md` (the `/shepherd-pr` section, lines ~320–336)
- Modify: `docs/superpowers/specs/2026-10-31-shepherd-pr-counters-lost-design.md` (add a "Superseded by `2026-11-12-shepherd-pr-script-design.md`" line under the title)
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both fields): minor bump from whatever `main` has (3.6.0 → 3.7.0 at the time of writing)

**Interfaces:**
- Consumes: the CLI from Tasks 1–6 (`start --model`, `next`, `record repair-pushed | repair-stopped --resumable | repair-stopped --terminal | triage --verdict infra|not-infra`, and the actions `next`, `busy`, `handoff`, `repair`, `triage`, `ready`, `stop`, `done`).

- [ ] **Step 1:** Rewrite `commands/shepherd-pr.md`. Keep the frontmatter and the scope paragraph, adjusted to the new flow. Keep the Rules listed in the spec's Command file section, and the hand-off text from today's step 1 hand-off bullet. Add the loop, which runs `python3 <codex-review-loop base dir>/../shepherd-pr-repair/shepherd.py` (how today's command reaches `ci_remediation.py`). The file must contain no "status line" rule, no "recovered" pass, and no step numbers that other files reference.
- [ ] **Step 2:** Edit `SKILL.md`, per the spec's Repair skill section:
  - the guard now names the `repair` action;
  - the resumable error list is inlined in step 2;
  - the `checks` evidence comes from the passed `evidence_dir`;
  - the infra branch is removed;
  - each exit names its `record` event;
  - the `<infra>` input is dropped;
  - the `version` is bumped to 3.0.0 (inputs changed).
- [ ] **Step 3:** Update the `ci-log-triage.md` description, the `ci_remediation.py` docstring, the README section (resumable waits and the per-pass status now inside `next`, with a status line on each return; drop the compaction bullet; the state lives in `$(git rev-parse --git-dir)/kitchen-sink/shepherd/`), and the superseded note.
- [ ] **Step 4: Verify.**
  - `git grep -n -e 'status line' -e 'recovered' -- commands/shepherd-pr.md skills/shepherd-pr-repair/SKILL.md README.md` finds only intended mentions (the new `status` field).
  - `git grep -n 'step 6' -- skills/shepherd-pr-repair agents` is empty.
  - All four test files and `test_shepherd.py` pass.
  - The three version strings match.
- [ ] **Step 5:** Commit: `Move /shepherd-pr's state machine into shepherd.py (v3.7.0) (#174, #175)`.
