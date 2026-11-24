#!/usr/bin/env python3
"""Poll a PR's checks for /poll-ci until they settle for HEAD_SHA.

Usage: poll_checks.py PR HEAD_SHA

Prints one `CHECK <json>` line per failing or cancelled check, with keys state, name, link and run_id (the
Actions run id from link, else null); then JSON arrays of names in `FAILED_CHECKS=` (on FAILED) and
`CANCELLED_CHECKS=` (when any were cancelled); `NEEDS_ATTENTION=1` on GREEN with a cancelled check, or on
FAILED when nothing failed for real (every failure is ACTION_REQUIRED, or nothing passed: then the cancelled
and skipped checks are the failing ones); `PR_HEAD=` (on STALL, when the PR's head isn't HEAD_SHA) and
`LAST_GH_ERROR=` (on TIMEOUT, after a `gh` error since the last good read); and last
`VERDICT=GREEN|FAILED|STALL|TIMEOUT`. Exit 0, 1, 2 or 3 to match; 64 for a usage error.

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

EXIT = {"GREEN": 0, "FAILED": 1, "STALL": 2, "TIMEOUT": 3}
FAILED_STATES = ("STALE", "STARTUP_FAILURE")  # gh buckets these as pending, but they never finish
RUN_LINK = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/(\d+)")


def env_seconds(name, default):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def snapshot(pr, head):
    """The PR's head and its checks; checks on another head aren't HEAD's, so they count as none yet."""
    args = ["pr", "view", pr, "--json", "headRefOid"]
    view = shepherd.gh_json(args)
    pr_head = view.get("headRefOid") if isinstance(view, dict) else None
    if not (isinstance(pr_head, str) and shepherd_rules.valid_sha(pr_head)):  # a blip like a non-zero exit: retried
        raise shepherd.GhError(["gh", *args], 0, "reply has no valid headRefOid")
    return pr_head, (shepherd.read_checks(pr) if pr_head == head else [])


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


def check_line(c):
    link = c.get("link")
    m = RUN_LINK.match(link) if isinstance(link, str) else None
    # json.dumps escapes newlines, so an untrusted name or link can't start a protocol line of its own
    return "CHECK " + json.dumps({"state": c["state"], "name": c["name"], "link": link, "run_id": m and int(m[1])})


def poll(pr, head, interval, timeout, stall_after, require):
    pr_head, last_error = None, None
    elapsed = 0
    while True:
        checks = None
        try:
            pr_head, checks = snapshot(pr, head)
            last_error = None  # an error a good read followed isn't why we give up
        except shepherd.GhError as e:  # retried next poll
            last_error = str(e).splitlines()[0]
        if checks is not None:
            result, failing, cancelled, needs_attention = verdict(checks, require)
            if result:
                # when nothing passed, failing already holds the cancelled checks: print each once
                for c in failing + [c for c in cancelled if c not in failing]:
                    print(check_line(c))
                if result == "FAILED":
                    print("FAILED_CHECKS=" + json.dumps([c["name"] for c in failing]))
                if cancelled:
                    print("CANCELLED_CHECKS=" + json.dumps([c["name"] for c in cancelled]))
                if needs_attention:
                    print("NEEDS_ATTENTION=1")
                return result
            if not checks and elapsed >= stall_after:
                if pr_head != head:
                    print(f"PR_HEAD={pr_head}")
                return "STALL"
        if elapsed >= timeout:
            if last_error:
                print(f"LAST_GH_ERROR={last_error}")
            return "TIMEOUT"
        time.sleep(interval)
        elapsed += interval  # counted, not clocked, so tests need no fake clock


def main(argv):
    if len(argv) != 2:
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
