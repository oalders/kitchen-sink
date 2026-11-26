#!/usr/bin/env python3
"""Poll a PR's checks for /poll-ci until they settle for HEAD_SHA.

Usage: poll_checks.py PR HEAD_SHA

Prints one `CHECK <json>` line per failing or cancelled check, with keys state, name, link, run_id (the
Actions run id from a link to this PR's repo, else null) and step (a failed check's first failed step, read through
its job link, else null); then JSON arrays of names in `FAILED_CHECKS=` (on FAILED) and
`CANCELLED_CHECKS=` (when any were cancelled); `FORK_PR=1` on GREEN for a PR from a fork, whose author controls
its workflows and check names; `NEEDS_ATTENTION=1` on GREEN with a cancelled check or from a fork, or on
FAILED when nothing failed for real (every failure is ACTION_REQUIRED, or nothing passed: then the cancelled
and skipped checks are the failing ones); `PR_HEAD=` (on STALL, when the PR's head isn't HEAD_SHA; else
`MERGE_STATE=`, the PR's mergeStateStatus, and `DRAFT=1` for a draft) and
`LAST_GH_ERROR=` (on TIMEOUT, after a `gh` error since the last good read, and on ERROR, a `gh` error that retrying
won't fix); and last `VERDICT=GREEN|FAILED|STALL|TIMEOUT|ERROR`. Exit 0-4 to match; 64 for a usage error.

Env: POLL_INTERVAL (20), POLL_TIMEOUT (1780) and POLL_STALL_AFTER (300) seconds. POLL_REQUIRE_CHECK, a
regex some passing check's name must match before GREEN, is env-only, for project monitor commands.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shepherd  # noqa: E402
import shepherd_rules  # noqa: E402

EXIT = {"GREEN": 0, "FAILED": 1, "STALL": 2, "TIMEOUT": 3, "ERROR": 4}
FAILED_STATES = ("STALE", "STARTUP_FAILURE")  # gh buckets these as pending, but they never finish
RUN_LINK = re.compile(r"^https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)(?:/job/(\d+))?")
PR_URL = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/pull/\d+$")
# gh's network errors have no stable wording, so only clearly permanent ones stop the poll; the rest are retried
PERMANENT = re.compile(
    r"HTTP 40[14]\b|gh auth login|Could not resolve to a PullRequest|no pull requests found"
    r"|a bucket this script doesn't know",  # shepherd.read_checks
    re.IGNORECASE,
)


def env_seconds(name, default):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def pr_view(pr):
    args = ["pr", "view", pr, "--json", "headRefOid,isCrossRepository,url,mergeStateStatus,isDraft"]
    view = shepherd.gh_json(args)
    view = view if isinstance(view, dict) else {}
    pr_head, fork, url = view.get("headRefOid"), view.get("isCrossRepository"), view.get("url")
    # worded like gh_json's blip, so poll retries it
    if not (isinstance(pr_head, str) and shepherd_rules.valid_sha(pr_head) and isinstance(fork, bool)):
        raise shepherd.GhError(["gh", *args], 0, "unexpected EOF: reply has no valid headRefOid or isCrossRepository")
    repo = PR_URL.match(url) if isinstance(url, str) else None  # None (e.g. on GHES): no run_id, polling still works
    # these only explain a STALL, so unlike the fields above a bad one counts as absent rather than being retried
    merge_state = view.get("mergeStateStatus")
    merge_state = merge_state if isinstance(merge_state, str) and re.fullmatch(r"[A-Z_]+", merge_state) else None
    return pr_head, fork, repo and repo[1].lower(), merge_state, view.get("isDraft") is True


def snapshot(pr, head):
    """pr_view's fields, then the PR's checks. `gh pr checks` reads the PR's current head,
    so checks count as none yet unless the head is HEAD both before and after them."""
    pr_head, *view = pr_view(pr)
    checks = shepherd.read_checks(pr) if pr_head == head else []
    if checks:
        pr_head = pr_view(pr)[0]
        checks = checks if pr_head == head else []
    return pr_head, *view, checks


def verdict(checks, require):
    """GREEN, FAILED or None (keep polling), with the failing and the cancelled checks and whether it needs attention."""
    failing = [c for c in checks if c["bucket"] == "fail" or c["state"] in FAILED_STATES]
    # cancel is neutral here on purpose (#231 item 6), unlike shepherd_rules.FAILED_BUCKETS: a newer push cancels runs
    cancelled = [c for c in checks if c["bucket"] == "cancel"]
    if failing:
        return "FAILED", failing, cancelled, all(c["state"] == "ACTION_REQUIRED" for c in failing)
    if not checks or any(c["bucket"] == "pending" for c in checks):
        return None, [], [], False
    if not any(c["bucket"] == "pass" for c in checks):  # all cancelled or skipped: nothing ran green
        return "FAILED", checks, cancelled, True
    if require and not any(c["bucket"] == "pass" and require.search(c["name"]) for c in checks):
        return None, [], [], False
    return "GREEN", [], cancelled, bool(cancelled)


def failed_steps(run_id):
    """{job id: its first failed step's name, or None} for a run, or None when the lookup failed."""
    try:
        jobs = json.loads(shepherd.lookup(["gh", "run", "view", str(run_id), "--json", "jobs"]) or "null")["jobs"]
        return {
            str(j["databaseId"]): next((s["name"] for s in j["steps"] if s["conclusion"] == "failure"), None)
            for j in jobs
        }
    # the step is only a hint: failing to read it, a malformed reply included, must not change the verdict
    except (shepherd.OutOfBudget, ValueError, LookupError, TypeError):
        return None


def check_line(c, repo, steps):
    """`steps` caches failed_steps by run id, so each run is looked up once."""
    link = c.get("link")
    m = RUN_LINK.match(link) if isinstance(link, str) else None
    run_id = int(m[2]) if m and repo and m[1].lower() == repo else None  # a link to another repo's run would show the wrong logs
    step = None
    if run_id and m[3] and c["bucket"] == "fail":
        if run_id not in steps:
            steps[run_id] = failed_steps(run_id)
        step = (steps[run_id] or {}).get(m[3])
    # json.dumps escapes newlines, so an untrusted name, link or step can't start a protocol line of its own
    return "CHECK " + json.dumps({"state": c["state"], "name": c["name"], "link": link, "run_id": run_id, "step": step})


def poll(pr, head, interval, timeout, stall_after, require):
    pr_head, last_error = None, None
    elapsed = 0
    shepherd.hard_end = time.time() + timeout + shepherd.CALL_TIMEOUT  # hung gh calls can't stretch the poll past it
    while True:
        checks = None
        try:
            pr_head, fork, repo, merge_state, draft, checks = snapshot(pr, head)
            last_error = None  # an error a good read followed isn't why we give up
        except shepherd.OutOfBudget:
            elapsed = timeout
        except shepherd.GhError as e:  # retried next poll, unless retrying can't help
            last_error = str(e).splitlines()[0]
            if PERMANENT.search(e.stderr):
                print(f"LAST_GH_ERROR={last_error}")
                return "ERROR"
        if checks is not None:
            result, failing, cancelled, needs_attention = verdict(checks, require)
            if result:
                # when nothing passed, failing already holds the cancelled checks: print each once
                steps = {}
                for c in failing + [c for c in cancelled if c not in failing]:
                    print(check_line(c, repo, steps))
                if result == "FAILED":
                    print("FAILED_CHECKS=" + json.dumps([c["name"] for c in failing]))
                if cancelled:
                    print("CANCELLED_CHECKS=" + json.dumps([c["name"] for c in cancelled]))
                fork = fork and result == "GREEN"  # a fork's author controls its workflows and check names
                if fork:
                    print("FORK_PR=1")
                if needs_attention or fork:
                    print("NEEDS_ATTENTION=1")
                return result
            if not checks and elapsed >= stall_after:
                if pr_head != head:
                    print(f"PR_HEAD={pr_head}")
                else:
                    if merge_state:
                        print(f"MERGE_STATE={merge_state}")
                    if draft:
                        print("DRAFT=1")
                return "STALL"
        if elapsed >= timeout:
            if last_error:
                print(f"LAST_GH_ERROR={last_error}")
            return "TIMEOUT"
        time.sleep(interval)
        elapsed += interval  # counted, not clocked, so tests need no fake clock


def main(argv):
    if len(argv) != 2 or not shepherd_rules.valid_id(argv[0]) or not shepherd_rules.valid_sha(argv[1]):
        print("usage: poll_checks.py PR HEAD_SHA", file=sys.stderr)
        return 64
    try:
        require = re.compile(os.environ["POLL_REQUIRE_CHECK"]) if os.environ.get("POLL_REQUIRE_CHECK") else None
    except re.error as e:
        print(f"POLL_REQUIRE_CHECK is not a valid regex: {e}", file=sys.stderr)
        return 64
    result = poll(
        argv[0], argv[1],
        env_seconds("POLL_INTERVAL", 20), env_seconds("POLL_TIMEOUT", 1780), env_seconds("POLL_STALL_AFTER", 300),
        require,
    )  # fmt: skip
    print(f"VERDICT={result}")
    return EXIT[result]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
