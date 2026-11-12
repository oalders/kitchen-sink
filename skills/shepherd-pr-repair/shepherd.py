#!/usr/bin/env python3
"""State machine for /shepherd-pr: carries the current branch's PR to merged.

Subcommands print exactly one JSON object on stdout (exit 0 for an action, 1
for a refused claim, 2 for a tool error):

  start --model NAME   Check the branch and PR, then write a fresh state file.
                       Returns next, handoff, busy or stop.
  next                 Pass over the PR until the agent is needed or about 9
                       minutes are used. Returns any action.
  record EVENT         Report what only the agent knows: repair-pushed,
                       repair-stopped --resumable|--terminal, or
                       triage --verdict infra|not-infra.
  claim --head SHA --cause CAUSE
                       A repair subagent's step 1: claim the live run's pending,
                       unclaimed repair of that head and cause. Exit 0 with
                       {"ok":true} (claimed) or {"action":"busy"}; exit 1 with
                       {"ok":false,"reason":...} (refused, nothing written;
                       "already-claimed" when another subagent holds it).

A `next` or `record` on a run that a stop, tool error or `done` ended prints
that same object again.

State lives in `<git-dir>/kitchen-sink/shepherd/<n>.json`; see
docs/superpowers/specs/2026-11-12-shepherd-pr-script-design.md.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # sibling module, however we're loaded
import shepherd_rules as rules  # noqa: E402

TIMEOUT_KEY = "kitchen-sink.shepherdTimeoutMinutes"
CODEX_LOOP = os.path.join(HERE, "..", "codex-review-loop", "codex_loop.py")
CI_REMEDIATION = os.path.join(HERE, "ci_remediation.py")
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
MAX_UNCLAIMED = 2  # hand-outs of one repair no subagent claimed (a compaction re-issues once); a third would loop
ALREADY_CLAIMED = "already-claimed"  # `claim`'s refusal for a held repair: a stable reason for the subagent's report
MATCH_TIMEOUT = 30  # the remediation regexes are user-supplied
LOG_LINES, LOG_BYTES = 300, 65536  # an evidence log's tail
REPORT_LOG_LINES = 20
FAILED_RUNS = ("failure", "timed_out", "startup_failure")  # runs with a `--log-failed`; cancelled-only queue evidence never passes
RUN_FIELDS = "databaseId,attempt,conclusion,name,event,headSha"
JOBS_JQ = '.jobs[] | select(.conclusion != "success" and .conclusion != "skipped") | .databaseId'
REGISTER_WAIT = 60  # checks register late
SUITES_JQ = ".check_suites[].created_at"
STATUS_JQ = '.statuses[]|select(.state=="failure" or .state=="error")|"x"'
CHECK_RUNS_JQ = (
    '.check_runs[] | select(.conclusion != null and (.conclusion | IN("success","neutral","skipped") | not))'
    ' | "\\(.app.slug) \\(.name)"'
)
HIDDEN = ("Cc", "Cf", "Zl", "Zp")  # control, format (bidi overrides, zero-width), line and paragraph separators
# /fix-gh-issue step 11's sensitive surfaces, by path; the marks are for the record and block nothing.
SENSITIVE = re.compile(
    r"(^|/)(\.github/workflows/|(package(-lock)?|npm-shrinkwrap|composer)\.json$|yarn\.lock$|pnpm-lock\.yaml$"
    r"|Gemfile(\.lock)?$|go\.(mod|sum)$|Cargo\.(toml|lock)$|requirements[^/]*\.txt$|pyproject\.toml$|(poetry|uv|composer)\.lock$"
    r"|Pipfile(\.lock)?$|cpanfile(\.snapshot)?$|(Makefile|Build)\.PL$|dist\.ini$|\.env)|secret|credential|auth|permission|access",
    re.IGNORECASE,
)
DECISIONS = {
    "guard": "guard: a check failed after this run's repair, so auto-merge stays off and a draft stays draft",
    "keep-queue": "in the merge queue: keep it",
    "ready": "draft: the agent marks it ready, then auto-merge is enabled",
    "enable": "enable auto-merge",
    "keep": "auto-merge already on: keep it",
}
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


class Replay(Stop):
    """An ended run's stored `final` object, printed again as it was (its report file is the script's own)."""

    def __init__(self, final):
        super().__init__(final.get("code") or final["action"], True, [])  # `done` has no code
        self.final = final


class Resumable(Exception):
    """Wait RESUMABLE_WAIT and pass again; never reaches the agent."""


class OutOfBudget(Exception):
    """A wait would overrun this `next` call; return `next` and let the agent call again."""


def run(cmd, check=True, timeout=CALL_TIMEOUT, **kw):
    """A hung call becomes a GhError ("timed out", resumable for `gh`) and never runs past HARD_CAP.

    A call cut short by HARD_CAP raises OutOfBudget instead: it is this process running out, not the
    command failing, so no caller that treats a failed command as a failed check may swallow it."""
    capped = hard_end is not None and hard_end - time.time() < timeout
    if capped:
        timeout = hard_end - time.time()
    try:
        if timeout <= 0:
            raise subprocess.TimeoutExpired(cmd, timeout)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        if capped:
            raise OutOfBudget() from None
        raise GhError(cmd, "timeout", "timed out") from None
    if check and proc.returncode != 0:
        raise GhError(cmd, proc.returncode, proc.stderr)
    return proc


def gh_json(args):
    cmd = ["gh", *args]
    try:
        return json.loads(run(cmd).stdout)
    except ValueError as e:  # exit 0 with truncated stdout is a blip like a non-zero exit: let the classifier decide
        raise GhError(cmd, 0, f"unexpected EOF: stdout is not JSON ({e})") from None


# --- state and lock ----------------------------------------------------------


def state_dir():
    git_dir = run(["git", "rev-parse", "--git-dir"]).stdout.strip()
    path = os.path.join(git_dir, "kitchen-sink", "shepherd")
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)  # makedirs leaves an existing directory's mode alone
    return path


def _state_path(n):
    return os.path.join(state_dir(), f"{n}.json")


def load_state(n):
    try:
        with open(_state_path(n)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _write_json(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))  # mkstemp creates 0600
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def save_state(n, state):
    _write_json(_state_path(n), state)


def _pointer_path():
    return os.path.join(state_dir(), "pointer.json")


def save_pointer(n, branch):
    """Which PR this branch's run is on, so `next` and `record` need no `gh` lookup. Left behind when the run ends:
    the state it names is then ended, and every `next` stops NO_RUN as before."""
    _write_json(_pointer_path(), {"branch": branch, "pr": n})


def load_pointer():
    try:
        with open(_pointer_path()) as f:
            pointer = json.load(f)
        if isinstance(pointer["branch"], str) and type(pointer["pr"]) is int and pointer["pr"] > 0:
            return pointer
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None  # missing or corrupt: the caller looks the PR up


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


def write_report(lines, name="report.txt"):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def end_state(n):
    """Mark an existing state file ended; the caller holds the lock."""
    state = load_state(n)
    if state is not None:
        state.update(ended=True, final=None)  # an earlier run's `final` would replay over this stop
        save_state(n, state)


def stop_object(stop):
    report = write_report(stop.report)
    return {"action": "stop", "terminal": stop.terminal, "code": stop.code, "report": report, **stop.fields}


def emit_stop(stop):
    return emit(stop_object(stop))


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
    if state is not None and state["ended"] and state.get("final"):
        raise Replay(state["final"])  # e.g. `next` after a repair subagent's `record` ended the run
    if state is None or state["ended"]:
        raise Stop("STOP_NO_RUN", True, [f"No live /shepherd-pr run for PR #{n}; run /shepherd-pr."])
    return state


def claimed(state):
    return bool((state["pending"] or {}).get("claimed"))


def finish(state, keep_evidence=False, final=None):
    """End the run: every stop and done. `final` is the stop, tool error or done printed, which `live_state` replays."""
    if keep_evidence:
        state["evidence_dir"] = None  # a claimed repair's subagent may still read it: leave it in the temp dir
    drop_evidence(state)
    state.update(ended=True, final=final)
    save_state(state["pr"], state)


def end_on_failure(state, step, keep_claimed=False):
    """Run `step`; a stop or tool error ends the run with that object stored as `final`, then prints it."""
    try:
        return step()
    except Stop as stop:
        final = stop_object(stop)
    except Exception as e:  # noqa: BLE001 - a tool error ends the run too
        final = tool_error_object("CMD_FAILED", f"{type(e).__name__}: {e}")
    finish(state, keep_evidence=keep_claimed and claimed(state), final=final)
    raise Replay(final)


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
        raise Stop("STOP_NO_PR", True, [f"No PR for {branch!r} and it is not a fix-NNN branch.", fence(pr_view_error)])
    count = run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number", "-q", "length"]).stdout.strip()
    if count != "0":
        raise Stop("STOP_PR_EXISTS", True, [f"`gh pr view` did not pick a PR, but {count!r} exist for {branch}.", fence(pr_view_error)])
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


def claimed_stop(n):
    """STOP_REPAIR_CLAIMED when PR n's live run has a claimed repair (a reset would hand out a second), else None."""
    old = load_state(n)
    if old and not old["ended"] and claimed(old):
        pending = old["pending"]
        return Stop("STOP_REPAIR_CLAIMED", True, [
            f"A repair subagent claimed this run's {pending['cause']} repair of {pending['head']} and may still be running.",
            "If none is running in any session, run"
            f" `python3 {shlex.quote(os.path.abspath(__file__))} record repair-stopped --terminal` to end the run,"
            " then /shepherd-pr again.",
        ])  # fmt: skip
    return None


def _start_with_pr(n, branch, model, minutes):
    stop = claimed_stop(n)
    if stop:
        return emit_stop(stop)  # returned, not raised: `cmd_start` must not end the claimed run
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
            "shown": None, "summary": None, "triage_verdict": None,
            "disabled_at": (load_state(n) or {}).get("disabled_at"),  # the last run's dequeue is no ejection either
        },
    )  # fmt: skip
    save_pointer(n, branch)
    return emit({"action": "next"})


def cmd_start(args):
    detached = Stop("STOP_DETACHED", True, ["HEAD is detached; check out the PR's branch."])
    if not rules.valid_model(args.model):
        raise Stop("STOP_BAD_MODEL", True, ["--model must match ^[A-Za-z0-9. -]{1,40}$."])
    proc = run(["git", "config", "--local", "--get", TIMEOUT_KEY], check=False)
    if proc.returncode not in (0, 1):  # 1 means the key is unset
        raise GhError(proc.args, proc.returncode, proc.stderr)
    try:
        minutes = rules.timeout_minutes(proc.stdout.strip() if proc.returncode == 0 else None)
    except rules.RuleError as e:
        raise Stop("STOP_BAD_TIMEOUT", True, [str(e), "Fix or unset the key."]) from None
    branch, rebasing = current_branch()
    pointer = load_pointer()
    if rebasing and pointer and pointer["branch"] == branch:
        raise claimed_stop(pointer["pr"]) or detached  # a claimed repair's subagent may be mid-rebase
    if not branch or rebasing:
        raise detached
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
    snap = reread(state)
    snap["viewer"] = run(["gh", "api", "user", "-q", ".login"]).stdout.strip()
    snap["repo"] = gh_json(
        ["repo", "view", "--json", "owner,name,defaultBranchRef,visibility,squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed"]
    )
    return snap


def reread(state):
    """Step 5's re-read: the PR, its checks and the merge-queue GraphQL `pullRequest`."""
    n = str(state["pr"])
    pr = gh_json(["pr", "view", n, "--json", PR_FIELDS])
    checks = read_checks(n)
    query = ["api", "graphql", "-f", f"owner={state['owner']}", "-f", f"name={state['repo']}", "-F", f"number={n}"]
    queue = gh_json([*query, "-f", f"query={QUEUE_QUERY}"])["data"]["repository"]["pullRequest"]
    return {"pr": pr, "checks": checks, "queue": queue}


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
    if state["summary"]:  # the step 3 block, on the first return after it was written
        action["summary"], state["summary"] = state["summary"], None
    return action


def stop_fields(snap):
    return {"automerge": "on" if snap["pr"]["autoMergeRequest"] else "off", "queued": bool(snap["queue"]["isInMergeQueue"])}


def sleep_within(seconds, budget_end):
    if time.time() + seconds > budget_end:
        raise OutOfBudget()
    time.sleep(seconds)


def check_deadline(state, snap=None):
    """The run's soft deadline: before each resumable wait, each watch poll and after each Codex wait."""
    if time.time() >= state["deadline"]:
        lines = ["The run's deadline passed; run /shepherd-pr again to continue."]
        if claimed(state):
            lines.append("A repair subagent may still be running and push; check `git log` and the PR before re-running.")
        raise Stop("STOP_DEADLINE", True, lines + ([status(state, snap)] if snap is not None else []))


def resumable_wait(state, budget_end):
    """The 120 s wait; False when it doesn't fit this call, so the next call does it first."""
    check_deadline(state)
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
                state["triage_verdict"] = None  # a verdict serves only the first pass to run through after its `record`
            except OutOfBudget:
                action = {"action": "next"}  # a cut-off pass keeps the verdict for the next call's
            except (GhError, Resumable) as e:
                if isinstance(e, GhError) and not rules.is_resumable_gh_error(e.cmd, e.stderr):
                    raise Stop("STOP_GH_FAILED", True, [fence(str(e))]) from None
                if isinstance(e, Resumable):  # the pass ran through; a failed `gh` is retried with the verdict
                    state["triage_verdict"] = None
                action = None if resumable_wait(state, budget_end) else {"action": "next"}
            if action:
                return with_status(action, state, snap)
            save_state(state["pr"], state)
        return with_status({"action": "next"}, state, snap)
    except Stop as stop:
        if snap is not None and not stop.fields:
            stop.fields = stop_fields(snap)
        if state["summary"]:
            stop.fields["summary"] = state["summary"]
        raise


def local_head():
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def rebase_dir():
    """The state directory of the rebase in progress, else None."""
    for name in ("rebase-merge", "rebase-apply"):
        path = run(["git", "rev-parse", "--git-path", name]).stdout.strip()
        if os.path.exists(path):
            return path
    return None


def current_branch():
    """(branch, rebasing): the checked-out branch, or, while a rebase has HEAD detached, the branch it rebases."""
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    path = None if branch else rebase_dir()
    if path:
        with contextlib.suppress(OSError), open(os.path.join(path, "head-name")) as f:
            head = f.read().strip()
            name = head.removeprefix("refs/heads/")
            if head.startswith("refs/heads/") and rules.valid_ref(name):  # the file is git's, but checked as any ref is
                return name, True
    return branch, False


def local_work_guard(head):
    """Pending work the agent may have abandoned (compaction): stop rather than build on or lose it."""
    if not rules.valid_sha(head):
        raise Stop("STOP_BAD_SHA", True, ["headRefOid is not a 40-hex SHA."])
    if rebase_dir():
        raise Stop("STOP_LOCAL_WORK", True, ["A rebase is in progress, possibly the repair's; `git rebase --abort` ends it."])
    cmd = ["git", "fetch", "origin"]
    try:
        proc = run(cmd, check=False)
        failure = proc.stderr if proc.returncode else None
    except GhError as e:  # timed out
        failure = e.stderr
    if failure is not None:
        if not rules.is_permanent_fetch_error(failure):
            raise Resumable()  # git's transient errors have no stable wording, so wait unless clearly permanent; the deadline bounds it
        raise Stop("STOP_FETCH_FAILED", True, ["`git fetch origin` failed for a reason waiting won't fix.", fence(failure)])
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
        if find_removal(state, snap)[0] is None:
            raise Stop("STOP_AUTOMERGE_OFF", True, ["Auto-merge was turned off or the PR was dequeued; the user decides."])
    if armed:
        state["automerge"] = "on"
    elif state["automerge"] is None:
        state["automerge"] = "off"
    state["gated_head"] = head


def find_removal(state, snap):
    """Step 3's ejection test: (the head's unhandled queue removal or None, the head's earliest suite)."""
    pr, queue = snap["pr"], snap["queue"]
    if queue["isInMergeQueue"] or pr["autoMergeRequest"] is not None:
        return None, None  # not ejected, without the suites lookup
    earliest = earliest_suite(state, pr["headRefOid"])
    nodes = queue["timelineItems"]["nodes"]
    return rules.ejection({**pr, **queue}, nodes, earliest, state["requeued"], state["disabled_at"]), earliest


def earliest_suite(state, sha):
    """About when the head was pushed: its first check suite's `created_at` (ISO-8601 compares as text)."""
    path = f"repos/{state['owner']}/{state['repo']}/commits/{sha}/check-suites"
    return min(run(["gh", "api", "--paginate", path, "-q", SUITES_JQ]).stdout.split(), default=None)


def disable_auto(state, snap):
    """Auto-merge off, timed first so the queue removal it causes is not read as an ejection."""
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()))
    run(["gh", "pr", "merge", str(state["pr"]), "--disable-auto"])
    state["disabled_at"] = at  # only once it succeeded: a failed disable must not mask a later ejection
    snap["pr"]["autoMergeRequest"] = None


def check_declines(state, snap):
    """Only the user can confirm a decline, in their own words."""
    n = str(state["pr"])
    lines = rules.unconfirmed_declines(run(["gh", "pr", "view", n, "--json", "body", "-q", ".body"]).stdout)
    if not lines:
        return
    if snap["pr"]["autoMergeRequest"] is not None:
        disable_auto(state, snap)  # the stop reports auto-merge off
    raise Stop(
        "STOP_UNCONFIRMED_DECLINE",
        True,
        ["Declined findings tagged (unconfirmed); remove the tag in your own words, then re-run /shepherd-pr:", fence("\n".join(lines))],
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
        raise Stop("STOP_CODEX_MODE", True, ["`codex_loop.py mode` failed:", fence(str(e))]) from None
    if mode not in ("off", "local", "github"):
        raise Stop("STOP_CODEX_MODE", True, ["`codex_loop.py mode` failed:", fence(f"{proc.stdout}\n{proc.stderr}")])
    minutes = (out.get("bot_wait") or {}).get("minutes")
    return {"mode": mode, "minutes": minutes if isinstance(minutes, int) else None}


def codex_mode():
    return codex_info()["mode"]


def check_cap(state):
    if state["repairs"] >= rules.MAX_REPAIRS:
        raise Stop("STOP_REPAIR_CAP", True, [f"{rules.MAX_REPAIRS} repairs didn't converge; a person looks."])


def repair_action(state, cause, evidence_dir=None):
    """Hand out a repair: counted, auto-merge off by this run (the skill disables it before pushing), pending."""
    check_cap(state)
    action = {
        "action": "repair", "pr": state["pr"], "cause": cause, "head": state["gated_head"], "branch": state["branch"],
        "default": state["default"], "codex_mode": codex_mode(),
    }  # fmt: skip
    if evidence_dir:
        action["evidence_dir"] = evidence_dir
    state["repairs"] += 1
    return hand_out(state, action)


def hand_out(state, action):
    """A repair, new or re-issued: auto-merge off by this run (the skill disables it before pushing), pending."""
    issued = action.pop("issued", 0) + 1  # a re-issue carries pending's count; a claim clears it
    if issued > MAX_UNCLAIMED:
        raise Stop("STOP_REPAIR_UNCLAIMED", True, [
            f"The repair subagent stopped before claiming this run's {action['cause']} repair of {action['head']} twice.",
            "Check the subagent's reported reason, then run /shepherd-pr again.",
        ])  # fmt: skip
    state.update(automerge="off-by-run", pending={**action, "issued": issued}, queue_watch=None)  # the repair's push starts the watch over
    return dict(action)


# Steps 2-6; each returns an action or None to go on.


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
        raise Stop("STOP_CODEX_ERROR", True, ["`codex_loop.py gh-wait` failed:", fence(f"{proc.stdout}\n{proc.stderr}")])
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
        raise Stop("STOP_CODEX_TRIGGER", True, ["`gh pr comment` printed no comment id:", fence(url)])
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
            if result.get("status") not in ("clean", "findings"):
                check_deadline(state, snap)
        status = result.get("status")
        if status == "clean":
            return codex_pass(state, head, gate, "Codex gate: clean")
        if status == "findings":
            if snap["pr"]["autoMergeRequest"] is not None:
                disable_auto(state, snap)
            return repair_action(state, "codex")
        if status == "pending":
            return {"action": "next"}
        if status != "timeout":
            raise Stop("STOP_CODEX_ERROR", True, ["`codex_loop.py gh-wait` returned:", fence(json.dumps(result))])
        if gate["trigger"] is None:  # no review of this head yet: wait on its trigger, or post one
            gate["final"] = result.get("triggers", 0) >= 2  # a resumed run's last wait
            trigger = str(result.get("trigger") or "")  # it goes to `gh-wait` as an argument
            gate["trigger"] = trigger if rules.valid_id(trigger) else post_trigger(state, head)
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


def fence(text):
    """Untrusted text for a file: control characters removed, in a fence longer than any backtick run in it."""
    clean = "".join(c for c in text if c in "\t\n" or unicodedata.category(c) not in HIDDEN).rstrip("\n")
    bar = "`" * max(3, 1 + max(map(len, re.findall("`+", clean)), default=0))
    return f"{bar}\n{clean}\n{bar}"


def write_summary(state, snap):
    """Step 3's block for a head new to the run; returns the path of its summary.txt."""
    pr, repo, default = snap["pr"], snap["repo"], state["default"]
    decision = rules.decide({**pr, **snap["queue"]}, snap["checks"], state["automerge"])
    github = [f"mergeStateStatus {pr['mergeStateStatus']}", f"reviewDecision {pr['reviewDecision']}"]
    if pr["autoMergeRequest"]:
        github.append(f"auto-merge enabled by {(pr['autoMergeRequest'].get('enabledBy') or {}).get('login')}")
    diff = run(["gh", "pr", "diff", str(state["pr"]), "--name-only"], check=False)  # for the record: never ends the run
    files = diff.stdout.splitlines()
    lines = [
        f"PR #{state['pr']} · branch {pr['headRefName']} · head {pr['headRefOid']}",
        "Title (untrusted):", fence(pr["title"]),
        "From GitHub (untrusted):", fence("\n".join(github)),
        f"Merge method: {rules.pick_method(repo) or 'none allowed'}",
        f"Private repo: {'no' if repo['visibility'] == 'PUBLIC' else 'yes'}",
        (state.get("codex") or {}).get("note") or "Codex gate: no result recorded",
        f"Decision: {DECISIONS[decision]}",
        "Changed files (untrusted; [sensitive] marks /fix-gh-issue step 11's list, for the record only):",
        fence("\n".join(f"{f}  [sensitive]" if SENSITIVE.search(f) else f for f in files) or "(none)"),
    ]  # fmt: skip
    if diff.returncode != 0:
        lines += ["`gh pr diff` failed, so the list above is incomplete:", fence(diff.stderr)]
    if pr["isDraft"]:
        grep = run(["git", "grep", "-l", "-e", "pull_request_target", f"origin/{default}", "--", ".github/workflows"], check=False)
        if grep.returncode == 0:
            lines += [f"pull_request_target workflows on origin/{default}: marking it ready may run a privileged workflow"
                      " (it is marked ready anyway):", fence(grep.stdout)]  # fmt: skip
        elif grep.returncode == 1:
            lines.append(f"No pull_request_target workflow on origin/{default}.")
        else:
            lines += ["`git grep` for pull_request_target failed:", fence(grep.stderr)]
    return write_report(lines, "summary.txt")


def lookup(cmd):
    """An evidence lookup: its stdout, or None when it failed (that fails the evidence, not the run)."""
    try:
        proc = run(cmd, check=False)
    except GhError:  # timed out
        return None
    return proc.stdout if proc.returncode == 0 else None


def queue_checks(state, oid):
    """The queue commit's failed check runs as `<app> <name>` lines, or None when the lookup failed."""
    path = f"repos/{state['owner']}/{state['repo']}/commits/{oid}/check-runs?filter=latest"
    out = lookup(["gh", "api", "--paginate", path, "-q", CHECK_RUNS_JQ])
    return None if out is None else out.splitlines()


def removal_oid(removal):
    oid = (removal.get("beforeCommit") or {}).get("oid")
    return oid if isinstance(oid, str) and rules.valid_sha(oid) else None


def parse_runs(listed, keys=("databaseId", "conclusion", "event")):
    """`gh run list` output, or None (failing the evidence) when it isn't a list of whole run objects."""
    try:
        runs = json.loads(listed) if listed is not None else None
    except ValueError:
        return None
    if not isinstance(runs, list) or not all(isinstance(r, dict) and all(k in r for k in keys) for r in runs):
        return None
    return runs


def write_tail(out, name, log):
    """A log's tail as file `name` in `out`; None, and no file, for a failed fetch or an empty log."""
    tail = "".join((log or "").splitlines(keepends=True)[-LOG_LINES:]).encode()[-LOG_BYTES:]
    if not tail:
        return None
    path = os.path.join(out, name)
    with open(path, "wb") as f:
        f.write(tail)
    return path


def queue_evidence(state, snap, removal):
    """The ejection's evidence, in a new evidence dir: (passes, log paths)."""
    oid = removal_oid(removal)
    if oid is None:
        return False, []
    out = new_evidence_dir(state)
    listed = lookup(["gh", "run", "list", "--commit", oid, "--limit", "100", "--json", "databaseId,conclusion,event"])
    runs = parse_runs(listed)
    ids = [
        str(r["databaseId"]) for r in runs or []
        if r["event"] == "merge_group" and r["conclusion"] in FAILED_RUNS and rules.valid_id(str(r["databaseId"]))
    ]  # fmt: skip
    logs = [write_tail(out, run_id, lookup(["gh", "run", "view", run_id, "--log-failed"])) for run_id in ids]
    paths = [p for p in logs if p]  # a missing one fails the evidence
    status = lookup(["gh", "api", "--paginate", f"repos/{state['owner']}/{state['repo']}/commits/{oid}/status", "--jq", STATUS_JQ])
    checks = queue_checks(state, oid)
    passes = (
        runs is not None and bool(ids) and len(paths) == len(ids)
        and status is not None and not status.strip()  # no failing third-party status
        and bool(checks) and all(c.startswith("github-actions ") for c in checks)
    )  # fmt: skip
    return passes, paths


def judge_logs(paths):
    """`ci_remediation.py match`: (`match:<name>` | `none` | `invalid` | `error`, detail for the report or None)."""
    cmd = [sys.executable, CI_REMEDIATION, "match", *(a for p in paths for a in ("--log", p))]
    try:
        proc = run(cmd, check=False, timeout=MATCH_TIMEOUT)
    except GhError as e:  # its own 30 s timeout (the hard end's cut is OutOfBudget)
        return "error", str(e)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = None
    out = out if isinstance(out, dict) else {}
    status, name = out.get("status"), out.get("name")
    if (proc.returncode, status) == (0, "match") and isinstance(name, str) and rules.valid_name(name):
        return f"match:{name}", None
    if (proc.returncode, status) == (1, "none"):
        return "none", None
    if (proc.returncode, status) == (2, "invalid"):
        return "invalid", "\n".join(map(str, out.get("errors") or []))
    return "error", f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"


def ejected_stop(state, snap, removal, paths, method, why):
    """Step 3's "Otherwise": what the queue reported, all fenced, and how to re-enqueue by hand."""
    oid = removal_oid(removal)
    checks = queue_checks(state, oid) if oid else None
    if oid is None:
        found = "no lookup was made: the removal's beforeCommit.oid is not a SHA"
    else:
        found = "the failed-checks lookup failed" if checks is None else "\n".join(checks) or "none"
    lines = [
        "Removed from merge queue (untrusted):", fence(f"createdAt {removal.get('createdAt')}\nreason {removal.get('reason')}"),
        *([why] if why else []),
        "Failed checks (untrusted):", fence(found),
    ]  # fmt: skip
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            tail = "".join(f.readlines()[-REPORT_LOG_LINES:])
        lines += [f"Run {os.path.basename(path)}, last {REPORT_LOG_LINES} lines of its failed log (untrusted):", fence(tail)]
    if oid is None:
        lines.append("No merge_group run was looked up either, for the same reason.")
    elif not paths:
        lines.append("No failed merge_group run log was found: it was likely dequeued by hand or by a conflict.")
    head = snap["pr"]["headRefOid"]
    lines.append(f"Run `gh pr merge {state['pr']} --auto --{method} --match-head-commit {head}` before /shepherd-pr.")
    return Stop("STOP_EJECTED", True, lines)


def handle_ejection(state, snap, method):
    """Step 3's ejection test: None (no ejection, or re-enqueue it), a `triage` action, or a Stop."""
    removal, earliest = find_removal(state, snap)
    if removal is None:
        return None
    passes, paths = queue_evidence(state, snap, removal)
    why = None
    nodes = snap["queue"]["timelineItems"]["nodes"]
    if passes and rules.may_requeue(nodes, removal, earliest, state["disabled_at"]):  # once per head, across runs
        verdict = use_verdict(state, "ejection")  # `record triage` answered the last pass's `none`
        judged, detail = verdict or judge_logs(paths)
        if judged == "infra" or judged.startswith("match:"):
            state["requeued"] = removal["createdAt"]  # handled; the decide below re-enables auto-merge
            return None
        if judged == "invalid":
            raise invalid_remediation(detail)
        if judged == "none":
            return triage_action(state, "ejection", state["evidence_dir"])
        why = "The log triage judged it not infrastructure."
        if not verdict:
            why = "`ci_remediation.py match` failed (untrusted):\n" + fence(detail)
    elif passes:
        why = "This head was already re-enqueued once after an ejection (one re-enqueue per head, across runs)."
    raise ejected_stop(state, snap, removal, paths, method, why)


def triage_action(state, cause, evidence_dir):
    """Hand out a log triage; `cause` (ejection or checks), kept in the state only, binds its verdict to it."""
    state["pending"] = {"action": "triage", "evidence_dir": evidence_dir, "cause": cause}
    return {"action": "triage", "evidence_dir": evidence_dir}


def use_verdict(state, cause):
    """`(verdict, None)` from `record triage` for this cause, used up; None when there is none for it."""
    recorded = state["triage_verdict"]
    if not recorded or recorded.get("cause") != cause:
        return None  # another cause's verdict is left for it (and dropped after this pass)
    state["triage_verdict"] = None
    return recorded["verdict"], None


def invalid_remediation(detail):
    return Stop(
        "STOP_REMEDIATION_INVALID", True,
        ["A remediation entry is invalid; fix it, then re-run /shepherd-pr. `ci_remediation.py match` said (untrusted):",
         fence(detail)],
    )  # fmt: skip


def show_and_act(state, snap):
    """Steps 3-4: the block for a new head, the method, the ejection, then ready or enable. None: on to the watch."""
    pr, head = snap["pr"], snap["pr"]["headRefOid"]
    if state["shown"] != head:
        state.update(summary=write_summary(state, snap), shown=head)
    method = rules.pick_method(snap["repo"])
    if method is None:
        raise Stop("STOP_NO_METHOD", True, ["No merge method is allowed; a repo admin must allow squash, merge or rebase."])
    triage = handle_ejection(state, snap, method)
    if triage:
        return triage
    decision = rules.decide({**pr, **snap["queue"]}, snap["checks"], state["automerge"])
    if decision == "ready":  # the agent runs `gh pr ready`, so the review hook still gates it
        state["pending"] = {"action": "ready", "pr": state["pr"]}
        return dict(state["pending"])
    if decision == "enable":  # with a merge queue this enqueues; a repo without auto-merge fails it (terminal)
        run(["gh", "pr", "merge", str(state["pr"]), "--auto", f"--{method}", "--match-head-commit", head])
        state["automerge"] = "on"
        pr["autoMergeRequest"] = {"enabledBy": {"login": snap["viewer"]}}  # what the watch would read back
    return None


def watch(state, snap, budget_end):
    """Step 5: the check watch, then the re-read and the queue watch. An action, or None to pass again at once.

    `snap` is updated in place with each re-read, so the status line and stop fields show the last one."""
    watch_checks(state, snap, budget_end)
    try:
        action = queue_watch(state, snap, budget_end)
    except (OutOfBudget, GhError):
        raise  # cut off or a failed `gh`: the next pass or call carries this queue watch on, from its start
    except Exception:  # a Stop, or a Resumable that starts the watch over
        state["queue_watch"] = None
        raise
    state["queue_watch"] = None
    return action


def poll(state, snap, budget_end):
    check_deadline(state, snap)
    sleep_within(POLL, budget_end)
    snap.update(reread(state))


def watch_checks(state, snap, budget_end):
    """Poll until the checks have registered (up to 60 s) and none is pending, or the PR moved on."""
    waited = 0
    while snap["pr"]["state"] == "OPEN" and snap["pr"]["headRefOid"] == state["gated_head"]:
        checks = snap["checks"]
        if checks and not rules.buckets(checks).get("pending") or not checks and waited >= REGISTER_WAIT:
            return
        poll(state, snap, budget_end)
        waited += POLL


def queue_watch(state, snap, budget_end):
    """Step 5's re-read (items 1-3), then the queue watch (item 4) until its deadline, or item 5."""
    head = state["gated_head"]
    watching = state.get("queue_watch")
    if watching and watching["head"] != head:
        watching = None
    while True:
        pr, checks = {**snap["pr"], **snap["queue"]}, snap["checks"]
        outcome = rules.reread_outcome(pr, checks, head, False)
        if outcome == "continue" and find_removal(state, snap)[0] is not None:  # only now: the suites lookup needs the gated head
            outcome = "ejected"
        if outcome != "continue":
            return reread_action(state, snap, outcome)
        if watching:  # after a poll (in this call or the last)
            if not pr["isInMergeQueue"] and pr["autoMergeRequest"] is None:
                why = "The PR was taken out of the merge queue or auto-merge was turned off; the user decides."
                raise Stop("STOP_DEQUEUED", True, [why])
            if time.time() > watching["deadline"]:
                raise Resumable()
        if not rules.in_queue_watch(pr, checks):
            return open_action(state, snap)
        now = int(time.time())
        watching = state["queue_watch"] = watching or {"head": head, "start": now}
        eta = (pr.get("mergeQueueEntry") or {}).get("estimatedTimeToMerge")
        watching["deadline"] = rules.queue_deadline(watching["start"], now, pr["isInMergeQueue"], eta)
        poll(state, snap, budget_end)


def reread_action(state, snap, outcome):
    """Step 5 items 1-3 on the re-read."""
    if outcome == "merged":
        return {"action": "done", "merged": True}
    if outcome == "closed":
        raise Stop("STOP_CLOSED", True, ["The PR is closed."])
    if outcome == "ejected":
        return None  # the next pass's step 3 handles it
    if snap["pr"]["autoMergeRequest"] is not None:  # nothing ungated merges; a push also ejects a queued PR
        disable_auto(state, snap)
        state["automerge"] = "off-by-run"
    if outcome == "new-head":
        raise Stop("STOP_FOREIGN_HEAD", True, ["Someone else pushed a new head; decide whether to gate it, then re-run."])
    return checks_failed(state, snap)


OPEN_STOPS = {
    "review-required": ("STOP_REVIEW_REQUIRED", "A reviewer must act: review required or changes requested."),
    "dirty-queued": ("STOP_QUEUE_CONFLICT", "The PR conflicts with its base while queued; a person resolves it."),
    "turned-off": ("STOP_AUTOMERGE_OFF", "Auto-merge was turned off or the PR was dequeued; the user decides."),
}


def open_action(state, snap):
    """Step 5 item 5."""
    outcome = rules.open_outcome({**snap["pr"], **snap["queue"]}, snap["checks"], state["automerge"])
    if outcome == "rebase":
        return None  # the next pass's step 1 rebases it, without waiting
    if outcome in ("pending", "resumable-off-by-run"):  # off by this run: step 4 re-enables it
        raise Resumable()
    code, message = OPEN_STOPS[outcome]
    raise Stop(code, True, [message])


def checks_failed(state, snap):
    """Step 6 for cause `checks`: a rerun, an infra rerun, the remediation match's infra rerun, or a `repair`."""
    head = state["gated_head"]
    failed = [c for c in snap["checks"] if c["bucket"] in rules.FAILED_BUCKETS]
    listed = run(["gh", "run", "list", "--commit", head, "--limit", "100", "--json", RUN_FIELDS]).stdout
    runs = parse_runs(listed, RUN_FIELDS.split(","))
    if runs is None or not all(isinstance(r["attempt"], int) for r in runs):
        raise Stop("STOP_BAD_RUNS", True, ["`gh run list` returned runs in an unexpected shape; a person looks."])
    choice, ids = rules.rerun_choice(failed, runs, head, state["rerun"])
    if choice == "rerun":
        state["rerun"] += 1
        rerun(ids)
    if choice == "infra-rerun":
        return infra_rerun(state, ids)
    if choice == "stop":
        raise reruns_spent(ids, None)
    check_cap(state)  # the match below spends a repair, as the skill's infra fix did
    out, paths, third_party = failure_evidence(state, head, runs)
    if not paths:
        why = "A check failed, but no failed run had a log (a check that isn't an Actions run?); a person looks."
        raise Stop("STOP_NO_LOGS", True, [why])
    judged, detail = judge_logs(paths)
    if judged == "invalid":
        raise invalid_remediation(detail)
    if judged == "error":
        raise Stop("STOP_REMEDIATION_ERROR", True, ["`ci_remediation.py match` failed (untrusted):", fence(detail)])
    name = judged[len("match:") :] if judged.startswith("match:") else None
    if name and third_party:
        why = f"Entry {name} matched, but a third-party status failed too (or couldn't be read); a person looks."
        raise Stop("STOP_THIRD_PARTY", True, [why])
    if name and name not in state["infra"]:  # an entry already applied on this head falls through to the code fix
        selected = [
            str(r["databaseId"]) for r in runs
            if r["event"] == "pull_request" and r["headSha"] == head and r["conclusion"] in (*FAILED_RUNS, "cancelled")
            and rules.valid_id(str(r["databaseId"]))
        ]  # fmt: skip
        if not {os.path.basename(p) for p in paths} <= set(selected):
            why = f"Entry {name} matched, but a failed run isn't this head's pull_request run; a person looks."
            raise Stop("STOP_INFRA_RUNS", True, [why])
        state["repairs"] += 1
        state["infra"].append(name)  # judge_logs passed it through rules.valid_name: the status line prints it
        rerun(selected)
    return repair_action(state, "checks", out)


def rerun(ids):
    """A full re-run (never `--failed`), then the resumable wait and another pass."""
    for run_id in ids:
        run(["gh", "run", "rerun", str(run_id)])
    raise Resumable()


def infra_rerun(state, ids):
    """The second rerun of cancelled or timed-out runs, when their logs are judged infrastructure."""
    out = new_evidence_dir(state)
    paths = job_logs(out, ids)
    if paths is None:
        raise reruns_spent(ids, "The rerun's job logs couldn't all be fetched, so they weren't judged.")
    judged, detail = use_verdict(state, "checks") or judge_logs(paths)
    if judged == "invalid":
        raise invalid_remediation(detail)
    if judged == "none":
        return triage_action(state, "checks", out)
    name = judged[len("match:") :] if judged.startswith("match:") else None
    if judged == "infra" or name and name not in state["infra"]:
        state["rerun"] += 1
        if name:
            state["infra"].append(name)  # validated by judge_logs, as above
        rerun(ids)
    why = {
        "not-infra": "The log triage judged it not infrastructure.",
        "error": "`ci_remediation.py match` failed (untrusted):\n" + fence(detail or ""),
    }.get(judged, f"Entry {name} already ran on this head.")
    raise reruns_spent(ids, why)


def job_logs(out, ids):
    """Each unsuccessful job's full log (`--log-failed` is empty for a cancelled job); None unless all are there."""
    paths = []
    for run_id in ids:
        jobs = lookup(["gh", "run", "view", str(run_id), "--json", "jobs", "-q", JOBS_JQ])
        if jobs is None:
            return None
        for job in filter(rules.valid_id, jobs.split()):
            path = write_tail(out, job, lookup(["gh", "run", "view", "--job", job, "--log"]))
            if path is None:
                return None
            paths.append(path)
    return paths or None


def failure_evidence(state, head, runs):
    """The `checks` evidence in a new evidence dir: (dir, `--log-failed` tails, a third-party status failed or is unknown)."""
    out = new_evidence_dir(state)
    ids = [str(r["databaseId"]) for r in runs if r["conclusion"] in FAILED_RUNS and rules.valid_id(str(r["databaseId"]))]
    paths = [p for p in (write_tail(out, i, lookup(["gh", "run", "view", i, "--log-failed"])) for i in ids) if p]
    status = lookup(["gh", "api", "--paginate", f"repos/{state['owner']}/{state['repo']}/commits/{head}/status", "--jq", STATUS_JQ])
    return out, paths, status is None or bool(status.strip())


def reruns_spent(ids, why):
    lines = [
        *([why] if why else []),
        "The reruns didn't help and the logs weren't judged infrastructure (or couldn't be), or a check isn't an Actions run.",
    ]
    if ids:
        lines += ["Re-run these first:", *(f"gh run rerun {i}" for i in ids)]
    return Stop("STOP_RERUNS_SPENT", True, lines)


def pass_once(state, snap, budget_end):
    """One pass of today's steps 1-6: an action for the agent, or None to pass again."""
    pr = snap["pr"]
    if pr["state"] == "MERGED":
        return {"action": "done", "merged": True}
    check_limits(state, snap)
    if claimed(state):  # its subagent reads evidence_dir and leaves local work: touch neither
        check_deadline(state, snap)
        return {"action": "repairing"}  # until its `record`, whatever the PR's head
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
    pointer = load_pointer()
    if pointer and pointer["branch"] == current_branch()[0]:  # mid-rebase too: a claimed repair's subagent may be in one
        return pointer["pr"]  # `check_limits` re-checks the PR's headRefName against the branch every pass
    n, error = find_pr()
    if n is None:
        raise Stop("STOP_NO_PR", True, ["No PR for this branch; run /shepherd-pr.", fence(error)])
    return n


def cmd_next(_args):
    n = _pr_or_stop()
    with locked(n):
        state = live_state(n)
        action = end_on_failure(state, lambda: next_loop(state, time.time() + BUDGET), keep_claimed=True)
        if action["action"] == "done":
            finish(state, keep_evidence=claimed(state), final=action)  # a lost `done` replays, not STOP_NO_RUN
        else:
            save_state(n, state)
        return emit(action)


# --- record --------------------------------------------------------------------


def record_repair_pushed(state, _args):
    if (state["pending"] or {}).get("action") != "repair":
        return {"action": "next"}  # nothing handed out (or `next` already adopted it): the pass re-reads
    state["pending"].pop("claimed", None)  # its subagent is done: a deferred adopt below falls to the next pass
    for lag in range(3):  # GitHub's headRefOid can trail a push by a moment; `next` would re-issue the repair
        try:
            snap, local = read_pr(state), local_head()
        except GhError as e:
            if not rules.is_resumable_gh_error(e.cmd, e.stderr):
                raise Stop("STOP_GH_FAILED", True, [fence(str(e))]) from None
            state["wait_first"] = True  # `pending` stays, so the next pass adopts the push
            return {"action": "next"}
        head = snap["pr"]["headRefOid"]
        if head != state["pending"]["head"]:
            break
        if lag < 2:
            try:
                sleep_within(5, hard_end)
            except OutOfBudget:  # `pending` stays, so the next pass adopts the push
                state["wait_first"] = True
                return {"action": "next"}
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
        state.update(triage_verdict={"cause": state["pending"].get("cause"), "verdict": args.verdict}, pending=None)
    return {"action": "next"}


RECORDERS = {"repair-pushed": record_repair_pushed, "repair-stopped": record_repair_stopped, "triage": record_triage}


def cmd_record(args):
    if (args.event == "repair-stopped") != (args.resumable or args.terminal) or (args.event == "triage") != bool(args.verdict):
        raise ValueError("repair-stopped takes --resumable or --terminal; triage takes --verdict")
    n = _pr_or_stop()
    with locked(n):
        state = live_state(n)
        action = end_on_failure(state, lambda: RECORDERS[args.event](state, args))
        save_state(n, state)
        return emit(action)


def cmd_claim(args):
    """A repair subagent's step 1: it can't see the conversation that dispatched it, so the state is the check, and
    claiming under the lock lets only one subagent take a handed-out repair."""
    if not rules.valid_sha(args.head):
        emit({"ok": False, "reason": "--head is not a 40-hex SHA"})
        return 1
    try:
        n = _pr_or_stop()
        with locked(n):
            state = live_state(n)
            pending = state["pending"] or {}
            want = {"action": "repair", "head": args.head, "cause": args.cause}
            if {k: pending.get(k) for k in want} != want:
                reason = "no pending repair for this head and cause"
            elif pending.get("claimed"):
                reason = ALREADY_CLAIMED
            else:
                pending.pop("issued", None)  # claimed: only hand-outs since a claim count toward MAX_UNCLAIMED
                pending["claimed"] = True
                save_state(n, state)
                return emit({"ok": True})
    except Stop as stop:
        reason = stop.code
    emit({"ok": False, "reason": reason})
    return 1


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
    c = sub.add_parser("claim")
    c.add_argument("--head", required=True)
    c.add_argument("--cause", required=True, choices=("checks", "codex", "rebase"))
    c.set_defaults(func=cmd_claim)
    args = p.parse_args(argv)
    global hard_end
    hard_end = time.time() + HARD_CAP
    try:
        return args.func(args)
    except Busy:
        return emit({"action": "busy"})
    except Replay as replay:
        emit(replay.final)
        return 0 if "action" in replay.final else 2
    except Stop as stop:
        return emit_stop(stop)
    except Exception as e:  # noqa: BLE001 - every call must print one JSON object
        return _tool_error("CMD_FAILED", f"{type(e).__name__}: {e}")


def tool_error_object(code, detail):
    return {"code": code, "report": write_report([fence(detail)])}


def _tool_error(code, detail):
    emit(tool_error_object(code, detail))
    return 2


if __name__ == "__main__":
    sys.exit(main())
