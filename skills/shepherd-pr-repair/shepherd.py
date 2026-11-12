#!/usr/bin/env python3
"""State machine for /shepherd-pr: carries the current branch's PR to merged.

Subcommands print exactly one JSON object on stdout (exit 0 for an action, 2
for a tool error):

  start --model NAME   Check the branch and PR, then write a fresh state file.
                       Returns next, handoff, busy or stop.
  next                 Pass over the PR until the agent is needed or about 9
                       minutes are used. Returns any action.
  record EVENT         Report what only the agent knows: repair-pushed,
                       repair-stopped --resumable|--terminal, or
                       triage --verdict infra|not-infra.

State lives in `<git-dir>/kitchen-sink/shepherd/<n>.json`; see
docs/superpowers/specs/2026-11-12-shepherd-pr-script-design.md.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # sibling module, however we're loaded
import shepherd_rules as rules  # noqa: E402

TIMEOUT_KEY = "kitchen-sink.shepherdTimeoutMinutes"
CODEX_LOOP = os.path.join(HERE, "..", "codex-review-loop", "codex_loop.py")
BUDGET = 540  # seconds of work per `next`, under the Bash tool's 600 s cap
HARD_CAP = 580  # no subprocess outlives this, whatever the budget left it
CALL_TIMEOUT = 60
hard_end = None  # set by main()
RESUMABLE_WAIT = 120
POLL = 15
GH_WAIT_MARGIN = 35  # a `gh-wait` slice ends this long before the budget: its last poll and sleep run past --timeout
MIN_SLICE = 30
UNKNOWN_WAIT = 30
EVIDENCE_PREFIX = "shepherd-evidence-"
QUEUE_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number)"
    "{isInMergeQueue mergeQueueEntry{position estimatedTimeToMerge}"
    " timelineItems(itemTypes:[ADDED_TO_MERGE_QUEUE_EVENT,REMOVED_FROM_MERGE_QUEUE_EVENT,AUTO_MERGE_DISABLED_EVENT],last:100)"
    "{nodes{__typename ... on AddedToMergeQueueEvent{createdAt}"
    " ... on RemovedFromMergeQueueEvent{reason createdAt beforeCommit{oid}} ... on AutoMergeDisabledEvent{createdAt}}}}}}"
)
PR_FIELDS = (
    "number,title,state,createdAt,isDraft,isCrossRepository,author,baseRefName,headRefName,headRefOid,"
    "autoMergeRequest,mergeStateStatus,reviewDecision"
)


class GhError(Exception):
    def __init__(self, cmd, returncode, stderr):
        super().__init__(f"{' '.join(cmd)} failed ({returncode}): {stderr.strip()}")
        self.cmd, self.returncode, self.stderr = cmd, returncode, stderr


class Busy(Exception):
    pass


class Stop(Exception):
    def __init__(self, code, terminal, report, fields=None):
        super().__init__(code)
        self.code, self.terminal, self.report = code, terminal, report
        self.fields = fields or {}  # extra validated stdout fields: automerge, queued


class Resumable(Exception):
    """Wait RESUMABLE_WAIT and pass again; never reaches the agent."""


class OutOfBudget(Exception):
    """A wait would overrun this `next` call; return `next` and let the agent call again."""


def run(cmd, check=True, timeout=CALL_TIMEOUT, **kw):
    """A hung call becomes a GhError ("timed out", resumable for `gh`) and never runs past HARD_CAP."""
    if hard_end is not None:
        timeout = min(timeout, hard_end - time.time())
    try:
        if timeout <= 0:
            raise subprocess.TimeoutExpired(cmd, timeout)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        raise GhError(cmd, "timeout", "timed out") from None
    if check and proc.returncode != 0:
        raise GhError(cmd, proc.returncode, proc.stderr)
    return proc


def gh_json(args):
    return json.loads(run(["gh", *args]).stdout)


# --- state and lock ----------------------------------------------------------


def state_dir():
    git_dir = run(["git", "rev-parse", "--git-dir"]).stdout.strip()
    path = os.path.join(git_dir, "kitchen-sink", "shepherd")
    os.makedirs(path, exist_ok=True)
    return path


def _state_path(n):
    return os.path.join(state_dir(), f"{n}.json")


def load_state(n):
    try:
        with open(_state_path(n)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_state(n, state):
    path = _state_path(n)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))  # mkstemp creates 0600
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(n):
    fd = os.open(os.path.join(state_dir(), f"{n}.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy() from None
        yield


# --- output ------------------------------------------------------------------


def emit(action):
    print(json.dumps(action, separators=(",", ":")))
    return 0


def write_report(lines):
    path = os.path.join(tempfile.mkdtemp(), "report.txt")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def end_state(n):
    """Mark an existing state file ended; the caller holds the lock."""
    state = load_state(n)
    if state is not None:
        state["ended"] = True
        save_state(n, state)


def emit_stop(stop):
    report = write_report(stop.report)
    return emit({"action": "stop", "terminal": stop.terminal, "code": stop.code, "report": report, **stop.fields})


def find_pr():
    """Return (n, None) for the branch's PR, or (None, gh's error) when there is none."""
    lookup = run(["gh", "pr", "view", "--json", "number", "-q", ".number"], check=False)
    if lookup.returncode != 0:
        return None, lookup.stderr.strip()
    if not rules.valid_id(lookup.stdout.strip()):
        raise Stop("STOP_BAD_PR", True, ["`gh pr view` returned a non-numeric PR number."])
    return int(lookup.stdout), None


def live_state(n):
    state = load_state(n)
    if state is None or state["ended"]:
        raise Stop("STOP_NO_RUN", True, [f"No live /shepherd-pr run for PR #{n}; run /shepherd-pr."])
    return state


def finish(state):
    """End the run: every stop and done."""
    drop_evidence(state)
    state["ended"] = True
    save_state(state["pr"], state)


def drop_evidence(state):
    path = state.get("evidence_dir")
    if path and os.path.basename(path).startswith(EVIDENCE_PREFIX):  # never rm a path we didn't create
        shutil.rmtree(path, ignore_errors=True)
    state["evidence_dir"] = None


def new_evidence_dir(state):
    drop_evidence(state)
    state["evidence_dir"] = tempfile.mkdtemp(prefix=EVIDENCE_PREFIX)
    return state["evidence_dir"]


# --- start -------------------------------------------------------------------


def _first_failure(checks):
    """Return (code, message) for the first check whose `failed` flag is true, else None."""
    for failed, code, message in checks:
        if failed:
            return code, message
    return None


def _handoff(branch, pr_view_error):
    """No PR for the branch: hand a committed fix-NNN branch to /fix-gh-issue, else stop."""
    if re.fullmatch(r"fix-[0-9]+", branch) is None:
        raise Stop("STOP_NO_PR", True, [f"No PR for {branch!r} and it is not a fix-NNN branch.", pr_view_error])
    count = run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number", "-q", "length"]).stdout.strip()
    if count != "0":
        raise Stop("STOP_PR_EXISTS", True, [f"`gh pr view` did not pick a PR, but {count!r} exist for {branch}.", pr_view_error])
    default = run(["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]).stdout.strip()
    if not rules.valid_ref(default):
        raise Stop("STOP_BAD_DEFAULT", True, ["The default branch name is not a valid ref."])
    if run(["git", "status", "--porcelain"]).stdout.strip():
        raise Stop("STOP_DIRTY_TREE", True, ["The working tree has uncommitted changes; commit or stash them first."])
    if int(run(["git", "rev-list", "--count", f"origin/{default}..HEAD"]).stdout.strip()) == 0:
        raise Stop("STOP_NO_COMMITS", True, [f"{branch} has no commits ahead of origin/{default}."])
    return emit({"action": "handoff", "issue": int(branch.split("-", 1)[1])})


def _pr_failure(pr, viewer, repo, branch):
    """(code, message) for the first limit the PR breaks, else None; `start` and every pass check these."""
    n = pr["number"]
    owner, name, default = repo["owner"]["login"], repo["name"], repo["defaultBranchRef"]["name"]
    return _first_failure(
        [
            (pr["state"] != "OPEN", "STOP_CLOSED", "The PR is closed."),
            (pr["isCrossRepository"], "STOP_CROSS_REPO", "The PR is from a fork; only same-repo PRs are shepherded."),
            (pr["author"]["login"] != viewer, "STOP_NOT_AUTHOR", "The PR is not yours; only your own PRs are shepherded."),
            (pr["baseRefName"] != default, "STOP_BASE_NOT_DEFAULT", f"The PR is not based on {default}."),
            (not (rules.valid_name(owner) and rules.valid_name(name)), "STOP_BAD_REPO", "Owner or repo name is invalid."),
            (not rules.valid_sha(pr["headRefOid"]), "STOP_BAD_SHA", "headRefOid is not a 40-hex SHA."),
            (not (rules.valid_ref(default) and rules.valid_ref(pr["headRefName"])), "STOP_BAD_REF", "A branch name is invalid."),
            (
                pr["headRefName"] != branch,
                "STOP_BRANCH_MISMATCH",
                f"The PR's branch is {pr['headRefName']!r}; check it out (`gh pr checkout {n}`) and re-run /shepherd-pr.",
            ),
        ]
    )


def _start_with_pr(n, branch, model, minutes):
    pr = gh_json(
        ["pr", "view", str(n), "--json", "number,state,isCrossRepository,author,baseRefName,headRefName,headRefOid"]
    )
    viewer = run(["gh", "api", "user", "-q", ".login"]).stdout.strip()
    repo = gh_json(["repo", "view", "--json", "owner,name,defaultBranchRef"])
    owner, name, default = repo["owner"]["login"], repo["name"], repo["defaultBranchRef"]["name"]
    if pr["state"] == "MERGED":
        return emit({"action": "done", "merged": True})
    failure = _pr_failure(pr, viewer, repo, branch)
    if failure:
        raise Stop(failure[0], True, [failure[1]])
    save_state(
        n,
        {
            "pr": n, "branch": branch, "owner": owner, "repo": name, "default": default, "model": model,
            "deadline": int(time.time()) + minutes * 60,
            "gated_head": None, "codex_passed": [], "automerge": None, "repairs": 0, "rerun": 0, "infra": [],
            "requeued": None, "wait_first": False, "pending": None, "ended": False, "evidence_dir": None,
        },
    )  # fmt: skip
    return emit({"action": "next"})


def cmd_start(args):
    if not rules.valid_model(args.model):
        raise Stop("STOP_BAD_MODEL", True, ["--model must match ^[A-Za-z0-9. -]{1,40}$."])
    proc = run(["git", "config", "--local", "--get", TIMEOUT_KEY], check=False)
    if proc.returncode not in (0, 1):  # 1 means the key is unset
        raise GhError(proc.args, proc.returncode, proc.stderr)
    try:
        minutes = rules.timeout_minutes(proc.stdout.strip() if proc.returncode == 0 else None)
    except rules.RuleError as e:
        raise Stop("STOP_BAD_TIMEOUT", True, [str(e), "Fix or unset the key."]) from None
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    if not branch:
        raise Stop("STOP_DETACHED", True, ["HEAD is detached; check out the PR's branch."])
    n, error = find_pr()
    if n is None:
        return _handoff(branch, error)
    with locked(n):
        try:
            return _start_with_pr(n, branch, args.model, minutes)
        except Stop as stop:
            end_state(n)
            raise


# --- next ----------------------------------------------------------------------


def read_pr(state):
    """Step 1's reads: the PR, its checks, the repo, the viewer and the merge-queue GraphQL `pullRequest`."""
    n = str(state["pr"])
    pr = gh_json(["pr", "view", n, "--json", PR_FIELDS])
    checks = read_checks(n)
    viewer = run(["gh", "api", "user", "-q", ".login"]).stdout.strip()
    repo = gh_json(
        ["repo", "view", "--json", "owner,name,defaultBranchRef,visibility,squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed"]
    )
    query = ["api", "graphql", "-f", f"owner={state['owner']}", "-f", f"name={state['repo']}", "-F", f"number={n}"]
    queue = gh_json([*query, "-f", f"query={QUEUE_QUERY}"])["data"]["repository"]["pullRequest"]
    return {"pr": pr, "checks": checks, "repo": repo, "viewer": viewer, "queue": queue}


def read_checks(n):
    """`gh pr checks` exits non-zero for pending or failing checks, so its JSON decides."""
    cmd = ["gh", "pr", "checks", n, "--json", "name,bucket,state,workflow"]
    proc = run(cmd, check=False)
    if "no checks reported" in proc.stderr:
        return []
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise GhError(cmd, proc.returncode, proc.stderr) from None


def status(state, snap):
    return rules.status_line(state, {**snap["pr"], **snap["queue"]}, snap["checks"])


def with_status(action, state, snap):
    if snap is not None and state["automerge"] is not None:
        action["status"] = status(state, snap)
    return action


def stop_fields(snap):
    return {"automerge": "on" if snap["pr"]["autoMergeRequest"] else "off", "queued": bool(snap["queue"]["isInMergeQueue"])}


def sleep_within(seconds, budget_end):
    if time.time() + seconds > budget_end:
        raise OutOfBudget()
    time.sleep(seconds)


def resumable_wait(state, budget_end):
    """The 120 s wait; False when it doesn't fit this call, so the next call does it first."""
    if time.time() >= state["deadline"]:
        raise Stop("STOP_DEADLINE", True, ["The run's deadline passed; run /shepherd-pr again to continue."])
    if time.time() + RESUMABLE_WAIT > budget_end:
        state["wait_first"] = True
        return False
    save_state(state["pr"], state)  # the wait is long; keep what this call learned if it is killed
    time.sleep(RESUMABLE_WAIT)
    return True


def next_loop(state, budget_end):
    snap = None
    try:
        if state["wait_first"]:
            state["wait_first"] = False
            resumable_wait(state, budget_end)
        while time.time() < budget_end:
            try:
                snap = read_pr(state)
                action = pass_once(state, snap, budget_end)
            except OutOfBudget:
                action = {"action": "next"}
            except (GhError, Resumable) as e:
                if isinstance(e, GhError) and not rules.is_resumable_gh_error(e.cmd, e.stderr):
                    raise Stop("STOP_GH_FAILED", True, [str(e)]) from None
                action = None if resumable_wait(state, budget_end) else {"action": "next"}
            if action:
                return with_status(action, state, snap)
            save_state(state["pr"], state)
        return with_status({"action": "next"}, state, snap)
    except Stop as stop:
        if snap is not None and not stop.fields:
            stop.fields = stop_fields(snap)
        raise


def local_head():
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def local_work_guard(head):
    """Pending work the agent may have abandoned (compaction): stop rather than build on or lose it."""
    if not rules.valid_sha(head):
        raise Stop("STOP_BAD_SHA", True, ["headRefOid is not a 40-hex SHA."])
    for name in ("rebase-merge", "rebase-apply"):
        if os.path.exists(run(["git", "rev-parse", "--git-path", name]).stdout.strip()):
            raise Stop("STOP_LOCAL_WORK", True, ["A rebase is in progress, possibly the repair's; `git rebase --abort` ends it."])
    try:
        fetched = run(["git", "fetch", "origin"], check=False).returncode == 0
    except GhError:  # timed out
        fetched = False
    if not fetched:
        raise Stop("STOP_FETCH_FAILED", True, ["`git fetch origin` failed."])
    if run(["git", "merge-base", "--is-ancestor", "HEAD", head], check=False).returncode != 0:
        raise Stop("STOP_LOCAL_WORK", True, [f"Local HEAD has commits not on the PR's head {head}."])
    if run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
        raise Stop("STOP_LOCAL_WORK", True, ["The working tree has uncommitted changes to tracked files."])


def adopt(state, head):
    """A head this run's repair pushed."""
    state.update(gated_head=head, automerge="off-by-run", rerun=0, infra=[], pending=None)


def handle_pending(state, snap):
    """The agent came back via `next` without a `record` (e.g. after compaction)."""
    pending, pr = state["pending"], snap["pr"]
    head = pr["headRefOid"]
    local_work_guard(head)
    if pending["action"] == "repair":
        if head == pending["head"]:
            return dict(pending)  # the agent may never have started it; not counted again
        if head != local_head():
            raise Stop("STOP_FOREIGN_HEAD", True, [f"The PR's head is {head}, neither the repaired head nor local HEAD."])
        adopt(state, head)  # the push landed before its `record`; a rebase's head needn't descend from gated_head
        return None
    if pending["action"] == "ready" and pr["isDraft"]:
        raise Stop("STOP_READY_FAILED", True, ["`gh pr ready` failed or was refused; the PR is still a draft."])
    state["pending"] = None  # ready: step 4 enables auto-merge; triage: step 3 re-gathers and hands it out again
    return None


def check_limits(state, snap):
    """The PR's limits, checked by `start` and on every pass."""
    pr = snap["pr"]
    failure = _pr_failure(pr, snap["viewer"], snap["repo"], state["branch"])
    repo = snap["repo"]
    if failure is None and (repo["owner"]["login"], repo["name"], repo["defaultBranchRef"]["name"]) != (
        state["owner"], state["repo"], state["default"]
    ):  # fmt: skip
        failure = ("STOP_REPO_CHANGED", "The repo or its default branch changed since /shepherd-pr started.")
    if failure:
        raise Stop(failure[0], True, [failure[1]])


def step1_checks(state, snap):
    """Step 1's later-pass checks against the state file."""
    pr, queue = snap["pr"], snap["queue"]
    head = pr["headRefOid"]
    if state["gated_head"] not in (None, head):
        raise Stop("STOP_FOREIGN_HEAD", True, [f"Someone else pushed {head}; decide whether to gate it, then re-run /shepherd-pr."])
    armed = pr["autoMergeRequest"] is not None
    if state["automerge"] == "on" and not armed and not queue["isInMergeQueue"]:
        nodes = queue["timelineItems"]["nodes"]
        if rules.ejection({**pr, **queue}, nodes, earliest_suite(state, head), state["requeued"]) is None:
            raise Stop("STOP_AUTOMERGE_OFF", True, ["Auto-merge was turned off or the PR was dequeued; the user decides."])
    if armed:
        state["automerge"] = "on"
    elif state["automerge"] is None:
        state["automerge"] = "off"
    state["gated_head"] = head


def earliest_suite(state, sha):
    """About when the head was pushed: its first check suite's `created_at` (ISO-8601 compares as text)."""
    path = f"repos/{state['owner']}/{state['repo']}/commits/{sha}/check-suites"
    return min(run(["gh", "api", "--paginate", path, "-q", ".check_suites[].created_at"]).stdout.split(), default=None)


def check_declines(state, snap):
    """Only the user can confirm a decline, in their own words."""
    n = str(state["pr"])
    lines = rules.unconfirmed_declines(run(["gh", "pr", "view", n, "--json", "body", "-q", ".body"]).stdout)
    if not lines:
        return
    if snap["pr"]["autoMergeRequest"] is not None:
        run(["gh", "pr", "merge", n, "--disable-auto"])
        snap["pr"]["autoMergeRequest"] = None  # the stop reports auto-merge off
    raise Stop(
        "STOP_UNCONFIRMED_DECLINE",
        True,
        ["Declined findings tagged (unconfirmed); remove the tag in your own words, then re-run /shepherd-pr:", *lines],
    )


def wait_unknown(state, head, budget_end):
    """GitHub is still computing mergeability: poll up to 30 s, then pass again or wait resumably."""
    for _ in range(UNKNOWN_WAIT // POLL):
        sleep_within(POLL, budget_end)
        now = gh_json(["pr", "view", str(state["pr"]), "--json", "mergeStateStatus,headRefOid"])
        if now["mergeStateStatus"] != "UNKNOWN" or now["headRefOid"] != head:
            return
    raise Resumable()


def codex_info():
    """`codex_loop.py mode`: the mode and the bot's wait in minutes."""
    try:
        proc = run([sys.executable, CODEX_LOOP, "mode"], check=False)
        out = json.loads(proc.stdout) if proc.returncode == 0 else None
        mode = out.get("mode") if isinstance(out, dict) else None
    except (GhError, ValueError) as e:
        raise Stop("STOP_CODEX_MODE", True, ["`codex_loop.py mode` failed:", str(e)]) from None
    if mode not in ("off", "local", "github"):
        raise Stop("STOP_CODEX_MODE", True, ["`codex_loop.py mode` failed:", proc.stdout, proc.stderr])
    minutes = (out.get("bot_wait") or {}).get("minutes")
    return {"mode": mode, "minutes": minutes if isinstance(minutes, int) else None}


def codex_mode():
    return codex_info()["mode"]


def repair_action(state, cause, evidence_dir=None):
    """Hand out a repair: counted, auto-merge off by this run (the skill disables it before pushing), pending."""
    if state["repairs"] >= rules.MAX_REPAIRS:
        raise Stop("STOP_REPAIR_CAP", True, [f"{rules.MAX_REPAIRS} repairs didn't converge; a person looks."])
    action = {
        "action": "repair", "cause": cause, "head": state["gated_head"], "branch": state["branch"],
        "default": state["default"], "codex_mode": codex_mode(),
    }  # fmt: skip
    if evidence_dir:
        action["evidence_dir"] = evidence_dir
    state["repairs"] += 1
    return hand_out(state, action)


def hand_out(state, action):
    """A repair, new or re-issued: auto-merge off by this run (the skill disables it before pushing), pending."""
    state.update(automerge="off-by-run", pending=action)
    return dict(action)


# Steps 2-6, filled in by later tasks; each returns an action or None to go on.


def gh_wait(state, head, timeout, trigger=None, windows=1):
    """`codex_loop.py gh-wait`: its JSON result, or a Stop, or a GhError for a failed `gh` inside it."""
    cmd = [sys.executable, CODEX_LOOP, "gh-wait", "--pr", str(state["pr"]), "--sha", head, "--timeout", str(timeout)]
    cmd += ["--interval", str(POLL)]
    if trigger:
        cmd += ["--trigger-comment", trigger, "--windows", str(windows)]
    proc = run(cmd, check=False, timeout=max(CALL_TIMEOUT, timeout + 30))
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = None
    if proc.returncode == 2 or not isinstance(out, dict) or "status" not in out:
        error = out.get("error") if isinstance(out, dict) else None
        failed = re.match(r"gh .* failed \((\d+)\): (.*)", error, re.S) if isinstance(error, str) else None
        if failed:  # a `gh` call inside gh-wait: resumable or terminal as any failed `gh`
            raise GhError(["gh"], int(failed[1]), failed[2])
        raise Stop("STOP_CODEX_ERROR", True, ["`codex_loop.py gh-wait` failed:", proc.stdout, proc.stderr])
    return out


def post_trigger(state, head):
    """The one comment this script posts; returns its id."""
    body = f"@codex review\n\nReview of {head}\n\n🤖 Review by [Claude Code](https://claude.com/claude-code) · {state['model']}"
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "codex-trigger.md")
        with open(path, "w") as f:
            f.write(body)
        url = run(["gh", "pr", "comment", str(state["pr"]), "--body-file", path]).stdout.strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    found = re.search(r"issuecomment-([0-9]+)$", url)
    if not found:
        raise Stop("STOP_CODEX_TRIGGER", True, ["`gh pr comment` printed no comment id:", url])
    return found[1]


def codex_pass(state, head, gate, note):
    state["codex_passed"].append(head)
    gate["note"] = note


def codex_gate(state, snap, budget_end):
    """Step 2. None: passed (or skipped); else an action. A wait longer than the budget is sliced across calls."""
    head = snap["pr"]["headRefOid"]
    if head in state["codex_passed"]:
        return None
    gate = state.get("codex")
    if not gate or gate["head"] != head:
        gate = state["codex"] = {"head": head, "trigger": None, "windows": 1, "final": False, "note": None}
    info = codex_info()
    if info["mode"] != "github":
        return codex_pass(state, head, gate, f"Codex gate not checked (mode `{info['mode']}`)")
    while True:
        if gate["trigger"] is None:
            result = gh_wait(state, head, 0)  # a check of existing reviews
        else:
            seconds = int(budget_end - time.time()) - GH_WAIT_MARGIN
            if seconds < MIN_SLICE:
                raise OutOfBudget()
            result = gh_wait(state, head, seconds, gate["trigger"], gate["windows"])
        status = result.get("status")
        if status == "clean":
            return codex_pass(state, head, gate, "Codex gate: clean")
        if status == "findings":
            if snap["pr"]["autoMergeRequest"] is not None:
                run(["gh", "pr", "merge", str(state["pr"]), "--disable-auto"])
                snap["pr"]["autoMergeRequest"] = None
            return repair_action(state, "codex")
        if status == "pending":
            return {"action": "next"}
        if status != "timeout":
            raise Stop("STOP_CODEX_ERROR", True, ["`codex_loop.py gh-wait` returned:", json.dumps(result)])
        if gate["trigger"] is None:  # no review of this head yet: wait on its trigger, or post one
            gate["final"] = result.get("triggers", 0) >= 2  # a resumed run's last wait
            gate["trigger"] = result.get("trigger") and str(result["trigger"]) or post_trigger(state, head)
            continue
        if not gate["final"]:
            if result.get("acknowledged"):  # the bot is reviewing: one more window
                gate.update(windows=2, final=True)
                continue
            if result.get("action") == "stop" and result.get("triggers") == 1:
                gate.update(trigger=post_trigger(state, head), windows=1, final=True)
                continue
        if result.get("action") == "proceed":
            minutes = info["minutes"]
            window = f"{minutes * gate['windows']} min" if minutes else "the bot window"
            return codex_pass(state, head, gate, f"Codex gate: no review within {window}; passed by codexTimeoutAction=proceed")
        raise Stop(
            "STOP_CODEX_TIMEOUT", True,
            ["The Codex bot hasn't reviewed this head; a silent bot is not approval.",
             "Run /shepherd-pr again once it has, or to re-trigger."],
        )  # fmt: skip


def show_and_act(state, snap):
    return None


def watch(state, snap, budget_end):
    return None


def pass_once(state, snap, budget_end):
    """One pass of today's steps 1-6: an action for the agent, or None to pass again."""
    pr = snap["pr"]
    if pr["state"] == "MERGED":
        return {"action": "done", "merged": True}
    check_limits(state, snap)
    reissue = handle_pending(state, snap) if state["pending"] else None  # may adopt a pushed head first
    step1_checks(state, snap)
    check_declines(state, snap)
    if reissue:
        return hand_out(state, reissue)  # step 1 may have re-synced automerge from the still-armed PR
    drop_evidence(state)  # after a re-issue's return: its repair still reads that directory
    if pr["mergeStateStatus"] == "UNKNOWN":
        wait_unknown(state, pr["headRefOid"], budget_end)
        return None
    if pr["mergeStateStatus"] in ("DIRTY", "BEHIND") and not snap["queue"]["isInMergeQueue"]:
        return repair_action(state, "rebase")  # in the queue: the queue tests against the base itself
    return codex_gate(state, snap, budget_end) or show_and_act(state, snap) or watch(state, snap, budget_end)


def _pr_or_stop():
    n, error = find_pr()
    if n is None:
        raise Stop("STOP_NO_PR", True, ["No PR for this branch; run /shepherd-pr.", error])
    return n


def cmd_next(_args):
    n = _pr_or_stop()
    with locked(n):
        state = live_state(n)
        try:
            action = next_loop(state, time.time() + BUDGET)
        except Exception:  # every stop, and a tool error: the agent ends the run on both
            finish(state)
            raise
        if action["action"] == "done":
            finish(state)
        else:
            save_state(n, state)
        return emit(action)


# --- record --------------------------------------------------------------------


def record_repair_pushed(state, _args):
    if (state["pending"] or {}).get("action") != "repair":
        return {"action": "next"}  # nothing handed out (or `next` already adopted it): the pass re-reads
    try:
        snap, local = read_pr(state), local_head()
    except GhError as e:
        if not rules.is_resumable_gh_error(e.cmd, e.stderr):
            raise Stop("STOP_GH_FAILED", True, [str(e)]) from None
        state["wait_first"] = True  # `pending` stays, so the next pass adopts the push
        return {"action": "next"}
    head = snap["pr"]["headRefOid"]
    if head == state["pending"]["head"]:  # the skill said it pushed, but GitHub has no new head
        raise Stop("STOP_NO_NEW_HEAD", True, [f"The PR's head is still {head}; the repair's push didn't land."], stop_fields(snap))
    if head != local:  # never take a SHA from the agent
        raise Stop("STOP_PUSH_MISMATCH", True, [f"The PR's head {head} is not local HEAD."], stop_fields(snap))
    adopt(state, head)
    return with_status({"action": "next"}, state, snap)


def record_repair_stopped(state, args):
    pending = state["pending"] if (state["pending"] or {}).get("action") == "repair" else None
    if args.resumable:
        if pending:
            state.update(repairs=max(0, state["repairs"] - 1), pending=None)
        state["wait_first"] = True
        return {"action": "next"}
    lines, fields = ["The repair stopped; run /shepherd-pr once its report is dealt with."], {}
    # The hints and fields are extras: no failure may keep this stop from ending the run.
    try:
        if pending and pending["cause"] == "checks" and local_head() == state["gated_head"]:
            lines += rerun_hints(state["gated_head"])
    except Exception:  # noqa: BLE001
        pass
    try:
        fields = stop_fields(read_pr(state))
    except Exception:  # noqa: BLE001
        pass
    raise Stop("STOP_REPAIR_STOPPED", True, lines, fields)


def rerun_hints(sha):
    """Runs the user can re-run first; a failed lookup leaves them out."""
    proc = run(["gh", "run", "list", "--commit", sha, "--limit", "100", "--json", "databaseId,conclusion"], check=False)
    try:
        runs = json.loads(proc.stdout) if proc.returncode == 0 else []
    except ValueError:
        runs = []
    failed = ("failure", "timed_out", "startup_failure", "cancelled")
    ids = [str(r["databaseId"]) for r in runs if r.get("conclusion") in failed and rules.valid_id(str(r.get("databaseId")))]
    return ["Re-run these first:", *(f"gh run rerun {i}" for i in ids)] if ids else []


def record_triage(state, args):
    if (state["pending"] or {}).get("action") == "triage":
        state.update(triage_verdict=args.verdict, pending=None)
    return {"action": "next"}


RECORDERS = {"repair-pushed": record_repair_pushed, "repair-stopped": record_repair_stopped, "triage": record_triage}


def cmd_record(args):
    if (args.event == "repair-stopped") != (args.resumable or args.terminal) or (args.event == "triage") != bool(args.verdict):
        raise ValueError("repair-stopped takes --resumable or --terminal; triage takes --verdict")
    n = _pr_or_stop()
    with locked(n):
        state = live_state(n)
        try:
            action = RECORDERS[args.event](state, args)
        except Exception:  # every stop, and a tool error: the agent ends the run on both
            finish(state)
            raise
        save_state(n, state)
        return emit(action)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--model", required=True)
    s.set_defaults(func=cmd_start)
    sub.add_parser("next").set_defaults(func=cmd_next)
    r = sub.add_parser("record")
    r.add_argument("event", choices=sorted(RECORDERS))
    how = r.add_mutually_exclusive_group()
    how.add_argument("--resumable", action="store_true")
    how.add_argument("--terminal", action="store_true")
    r.add_argument("--verdict", choices=("infra", "not-infra"))
    r.set_defaults(func=cmd_record)
    args = p.parse_args(argv)
    global hard_end
    hard_end = time.time() + HARD_CAP
    try:
        return args.func(args)
    except Busy:
        return emit({"action": "busy"})
    except Stop as stop:
        return emit_stop(stop)
    except Exception as e:  # noqa: BLE001 - every call must print one JSON object
        return _tool_error("CMD_FAILED", f"{type(e).__name__}: {e}")


def _tool_error(code, detail):
    print(json.dumps({"code": code, "report": write_report([detail])}, separators=(",", ":")))
    return 2


if __name__ == "__main__":
    sys.exit(main())
