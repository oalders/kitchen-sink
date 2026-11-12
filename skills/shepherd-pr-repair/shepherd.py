#!/usr/bin/env python3
"""State machine for /shepherd-pr: carries the current branch's PR to merged.

Subcommands print exactly one JSON object on stdout (exit 0 for an action, 2
for a tool error):

  start --model NAME   Check the branch and PR, then write a fresh state file.
                       Returns next, handoff, busy or stop.

State lives in `<git-dir>/kitchen-sink/shepherd/<n>.json`; see
docs/superpowers/specs/2026-11-12-shepherd-pr-script-design.md.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling module, however we're loaded
import shepherd_rules as rules  # noqa: E402

TIMEOUT_KEY = "kitchen-sink.shepherdTimeoutMinutes"


class GhError(Exception):
    def __init__(self, cmd, returncode, stderr):
        super().__init__(f"{' '.join(cmd)} failed ({returncode}): {stderr.strip()}")
        self.cmd, self.returncode, self.stderr = cmd, returncode, stderr


class Busy(Exception):
    pass


class Stop(Exception):
    def __init__(self, code, terminal, report, pr=None):
        super().__init__(code)
        self.code, self.terminal, self.report, self.pr = code, terminal, report, pr


def run(cmd, check=True, **kw):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
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
    with open(os.path.join(state_dir(), f"{n}.lock"), "w") as f:
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


def emit_stop(stop):
    if stop.pr is not None:
        state = load_state(stop.pr)
        if state is not None:
            state["ended"] = True
            save_state(stop.pr, state)
    return emit({"action": "stop", "terminal": stop.terminal, "code": stop.code, "report": write_report(stop.report)})


# --- start -------------------------------------------------------------------


def _first_failure(checks):
    """Return the (code, message) of the first (failed, code, message) triple that failed."""
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


def _start_with_pr(n, branch, model, minutes):
    pr = gh_json(
        ["pr", "view", str(n), "--json", "number,state,isCrossRepository,author,baseRefName,headRefName,headRefOid"]
    )
    viewer = run(["gh", "api", "user", "-q", ".login"]).stdout.strip()
    repo = gh_json(["repo", "view", "--json", "owner,name,defaultBranchRef"])
    owner, name, default = repo["owner"]["login"], repo["name"], repo["defaultBranchRef"]["name"]
    if pr["state"] == "MERGED":
        return emit({"action": "done", "merged": True})
    failure = _first_failure(
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
    if failure:
        raise Stop(failure[0], True, [failure[1]])
    save_state(
        n,
        {
            "pr": n, "branch": branch, "owner": owner, "repo": name, "default": default, "model": model,
            "deadline": int(time.time()) + minutes * 60,
            "gated_head": None, "codex_passed": [], "automerge": None, "repairs": 0, "rerun": 0, "infra": [],
            "requeued": None, "wait_first": False, "pending": None, "ended": False,
        },
    )  # fmt: skip
    return emit({"action": "next"})


def cmd_start(args):
    if not rules.valid_model(args.model):
        raise Stop("STOP_BAD_MODEL", True, ["--model must match ^[A-Za-z0-9. -]{1,40}$."])
    proc = run(["git", "config", "--local", "--get", TIMEOUT_KEY], check=False)
    try:
        minutes = rules.timeout_minutes(proc.stdout.strip() if proc.returncode == 0 else None)
    except rules.RuleError as e:
        raise Stop("STOP_BAD_TIMEOUT", True, [str(e), "Fix or unset the key."]) from None
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    if not branch:
        raise Stop("STOP_DETACHED", True, ["HEAD is detached; check out the PR's branch."])
    lookup = run(["gh", "pr", "view", "--json", "number", "-q", ".number"], check=False)
    if lookup.returncode != 0:
        return _handoff(branch, lookup.stderr.strip())
    if not rules.valid_id(lookup.stdout.strip()):
        raise Stop("STOP_BAD_PR", True, ["`gh pr view` returned a non-numeric PR number."])
    n = int(lookup.stdout)
    with locked(n):
        try:
            return _start_with_pr(n, branch, args.model, minutes)
        except Stop as stop:
            stop.pr = n
            raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--model", required=True)
    s.set_defaults(func=cmd_start)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except Busy:
        return emit({"action": "busy"})
    except Stop as stop:
        return emit_stop(stop)
    except GhError as e:
        return _tool_error("GH_FAILED", str(e))


def _tool_error(code, detail):
    print(json.dumps({"code": code, "report": write_report([detail])}, separators=(",", ":")))
    return 2


if __name__ == "__main__":
    sys.exit(main())
