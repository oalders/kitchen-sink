#!/usr/bin/env python3
"""Tests for poll_checks.py.

Run: python3 skills/shepherd-pr-repair/test_poll_checks.py
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import unittest
from unittest import mock

_DIR = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("poll_checks", os.path.join(_DIR, "poll_checks.py"))
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

HEAD = "c5bf4f3aed0123456789abcdef0123456789abcd"
CHECKS = "gh pr checks 7"


def check(name="test", bucket="pass", state="SUCCESS"):
    return {"name": name, "bucket": bucket, "state": state, "workflow": "CI", "link": f"https://ci/{name}"}


def checks(*cs):
    return json.dumps(list(cs))


class Poll(unittest.TestCase):
    """A fake `run` keyed on the command's leading words, longest first; a list replies once per call, its last repeating."""

    def setUp(self):
        self.replies = {"gh pr view 7": json.dumps({"headRefOid": HEAD})}
        self.sleeps = []
        for target, name, fake in (
            (pc.shepherd, "run", self.fake_run),
            (pc.time, "sleep", self.sleeps.append),
        ):
            p = mock.patch.object(target, name, fake)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"POLL_INTERVAL": "10", "POLL_TIMEOUT": "100", "POLL_STALL_AFTER": "30"})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("POLL_REQUIRE_CHECK", None)

    def fake_run(self, cmd, check=True, **kw):
        line = " ".join(cmd)
        key = max((k for k in self.replies if line.startswith(k)), key=len, default=None)
        self.assertIsNotNone(key, f"unexpected command: {line}")
        reply = self.replies[key]
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        rc, out, err = reply if isinstance(reply, tuple) else (0, reply, "")
        if check and rc != 0:
            raise pc.shepherd.GhError(cmd, rc, err)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def main(self, *argv):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = pc.main(list(argv or ("7", HEAD)))
        return code, buf.getvalue().splitlines()

    def test_green(self):
        self.replies[CHECKS] = [checks(check(bucket="pending", state="IN_PROGRESS")), checks(check())]
        self.assertEqual(self.main(), (0, ["VERDICT=GREEN"]))
        self.assertEqual(self.sleeps, [10])

    def test_fails_fast_while_siblings_are_pending(self):
        self.replies[CHECKS] = checks(check("lint", "pending", "IN_PROGRESS"), check(bucket="fail", state="FAILURE"))
        self.assertEqual(
            self.main(),
            (1, ["CHECK state=FAILURE name=test link=https://ci/test", "FAILED_CHECKS=test", "VERDICT=FAILED"]),
        )
        self.assertEqual(self.sleeps, [])

    def test_cancelled_is_neutral_but_flagged(self):
        self.replies[CHECKS] = checks(check(), check("old", "cancel", "CANCELLED"))
        self.assertEqual(
            self.main(),
            (0, ["CHECK state=CANCELLED name=old link=https://ci/old", "CANCELLED_CHECKS=old", "VERDICT=GREEN"]),
        )

    def test_all_cancelled_fails(self):
        self.replies[CHECKS] = checks(check("a", "cancel", "CANCELLED"), check("b", "skipping", "SKIPPED"))
        self.assertEqual(
            self.main(),
            (1, ["CHECK state=CANCELLED name=a link=https://ci/a", "FAILED_CHECKS=a", "CANCELLED_CHECKS=a", "VERDICT=FAILED"]),
        )

    def test_stale_and_startup_failure_fail(self):
        for state in ("STALE", "STARTUP_FAILURE"):
            with self.subTest(state):
                self.replies[CHECKS] = checks(check(bucket="pending", state=state))
                self.assertEqual(self.main()[0], 1)

    def test_no_checks_stalls(self):
        self.replies[CHECKS] = (1, "", "no checks reported on the 'fix-232' branch")
        self.assertEqual(self.main(), (2, ["VERDICT=STALL"]))
        self.assertEqual(self.sleeps, [10, 10, 10])

    def test_pr_head_not_head_stalls(self):
        self.replies["gh pr view 7"] = json.dumps({"headRefOid": "0" * 40})
        self.replies[CHECKS] = checks(check())  # the old head's green checks don't count
        self.assertEqual(self.main(), (2, ["PR_HEAD=" + "0" * 40, "VERDICT=STALL"]))

    def test_timeout(self):
        self.replies[CHECKS] = checks(check(bucket="pending", state="QUEUED"))
        self.assertEqual(self.main(), (3, ["VERDICT=TIMEOUT"]))
        self.assertEqual(len(self.sleeps), 10)

    def test_gh_error_retried(self):
        self.replies[CHECKS] = [(1, "", "HTTP 502: Bad Gateway"), checks(check())]
        self.assertEqual(self.main(), (0, ["VERDICT=GREEN"]))

    def test_gh_error_reported_on_timeout(self):
        self.replies["gh pr view 7"] = (1, "", "HTTP 502: Bad Gateway")
        code, out = self.main()
        self.assertEqual(code, 3)
        self.assertIn("HTTP 502: Bad Gateway", out[0])
        self.assertTrue(out[0].startswith("LAST_GH_ERROR="))

    def test_require_check_blocks_green_until_it_attaches(self):
        os.environ["POLL_REQUIRE_CHECK"] = "^deploy$"
        self.replies[CHECKS] = [checks(check()), checks(check(), check("deploy"))]
        self.assertEqual(self.main(), (0, ["VERDICT=GREEN"]))
        self.assertEqual(self.sleeps, [10])

    def test_bad_env_resets_to_default(self):
        for value in ("0", "-5", "junk"):
            with self.subTest(value):
                self.sleeps.clear()
                os.environ["POLL_INTERVAL"] = value
                self.replies[CHECKS] = [checks(check(bucket="pending", state="QUEUED")), checks(check())]
                self.main()
                self.assertEqual(self.sleeps, [20])

    def test_invalid_regex(self):
        os.environ["POLL_REQUIRE_CHECK"] = "("
        self.assertEqual(self.main(), (64, []))

    def test_usage(self):
        self.assertEqual(self.main("7"), (64, []))


if __name__ == "__main__":
    unittest.main()
