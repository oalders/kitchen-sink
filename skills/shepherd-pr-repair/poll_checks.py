#!/usr/bin/env python3
"""Poll a PR's checks for /poll-ci until they settle for HEAD_SHA.

Usage: poll_checks.py PR HEAD_SHA

Prints one `CHECK state=<STATE> name=<name> link=<url>` line per failing or cancelled check, then
`FAILED_CHECKS=` (on FAILED), `CANCELLED_CHECKS=` (when any were cancelled), `PR_HEAD=` (on STALL, when
the PR's head isn't HEAD_SHA) and `LAST_GH_ERROR=` (on STALL or TIMEOUT, after a `gh` error), and last
`VERDICT=GREEN|FAILED|STALL|TIMEOUT`. Exit 0, 1, 2 or 3 to match; 64 for a usage error.

Env: POLL_INTERVAL (20), POLL_TIMEOUT (1780) and POLL_STALL_AFTER (300) seconds. POLL_REQUIRE_CHECK, a
regex some check's name must match before GREEN, is env-only, for project monitor commands.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shepherd  # noqa: E402

EXIT = {"GREEN": 0, "FAILED": 1, "STALL": 2, "TIMEOUT": 3}
FAILED_STATES = ("STALE", "STARTUP_FAILURE")  # gh buckets these as pending, but they never finish


def env_seconds(name, default):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def snapshot(pr, head):
    """The PR's head and its checks; checks on another head aren't HEAD's, so they count as none yet."""
    view = shepherd.run(["gh", "pr", "view", pr, "--json", "headRefOid"])
    pr_head = json.loads(view.stdout)["headRefOid"]
    return pr_head, (shepherd.read_checks(pr) if pr_head == head else [])


def verdict(checks, require):
    """GREEN, FAILED or None (keep polling), with the failing and the cancelled checks."""
    failing = [c for c in checks if c["bucket"] == "fail" or c["state"] in FAILED_STATES]
    # cancel is neutral here on purpose (#231 item 6), unlike shepherd_rules.FAILED_BUCKETS: a newer push cancels runs
    cancelled = [c for c in checks if c["bucket"] == "cancel"]
    if failing:
        return "FAILED", failing, cancelled
    if not checks or any(c["bucket"] == "pending" for c in checks):
        return None, [], []
    if not any(c["bucket"] == "pass" for c in checks):  # all cancelled or skipped: nothing ran green
        return "FAILED", cancelled, cancelled
    if require and not any(require.search(c["name"]) for c in checks):
        return None, [], []
    return "GREEN", [], cancelled


def poll(pr, head, interval, timeout, stall_after, require):
    pr_head, last_error = None, None
    elapsed = 0
    while True:
        checks = None
        try:
            pr_head, checks = snapshot(pr, head)
        except shepherd.GhError as e:  # retried next poll
            last_error = str(e).splitlines()[0]
        if checks is not None:
            result, failing, cancelled = verdict(checks, require)
            if result:
                for c in failing + [c for c in cancelled if c not in failing]:
                    print(f"CHECK state={c['state']} name={c['name']} link={c['link']}")
                if result == "FAILED":
                    print("FAILED_CHECKS=" + "; ".join(c["name"] for c in failing))
                if cancelled:
                    print("CANCELLED_CHECKS=" + "; ".join(c["name"] for c in cancelled))
                return result
            if not checks and elapsed >= stall_after:
                if pr_head != head:
                    print(f"PR_HEAD={pr_head}")
                return gave_up("STALL", last_error)
        if elapsed >= timeout:
            return gave_up("TIMEOUT", last_error)
        time.sleep(interval)
        elapsed += interval  # counted, not clocked, so tests need no fake clock


def gave_up(result, last_error):
    if last_error:
        print(f"LAST_GH_ERROR={last_error}")
    return result


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
