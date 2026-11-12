#!/usr/bin/env python3
"""Tests for shepherd.py and shepherd_rules.py.

Run: python3 skills/shepherd-pr-repair/test_shepherd.py
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_DIR, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rules = _load("shepherd_rules")
sh = _load("shepherd")

SHA = "c5bf4f3aed0123456789abcdef0123456789abcd"
NOW = 1_800_000_000


def pr_view(**over):
    pr = {
        "number": 7, "state": "OPEN", "isCrossRepository": False, "author": {"login": "me"},
        "baseRefName": "main", "headRefName": "fix-174", "headRefOid": SHA,
    }  # fmt: skip
    pr.update(over)
    return json.dumps(pr)


def fail(stderr="boom"):
    return (1, "", stderr)


class Env(unittest.TestCase):
    """A temp git dir plus a fake `run`: replies are matched on the command's leading words, longest first."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.git_dir = tmp.name
        self.reset_replies()
        p = mock.patch.object(sh, "run", self.fake_run)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(sh.time, "time", return_value=NOW)
        p.start()
        self.addCleanup(p.stop)

    def reset_replies(self):
        self.replies = {
            "git rev-parse --git-dir": self.git_dir,
            "git config --local --get": fail(""),
            "git branch --show-current": "fix-174\n",
            "gh pr view --json number": "7\n",
            "gh pr view 7": pr_view(),
            "gh api user": "me\n",
            "gh repo view --json owner": json.dumps(
                {"owner": {"login": "o"}, "name": "r", "defaultBranchRef": {"name": "main"}}
            ),
        }

    def fake_run(self, cmd, check=True, **kw):
        line = " ".join(cmd)
        key = max((k for k in self.replies if line.startswith(k)), key=len, default=None)
        self.assertIsNotNone(key, f"unexpected command: {line}")
        reply = self.replies[key]
        rc, out, err = reply if isinstance(reply, tuple) else (0, reply, "")
        if check and rc != 0:
            raise sh.GhError(cmd, rc, err)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sh.main(list(argv))
        return code, json.loads(buf.getvalue())

    def read_state_bytes(self):
        with open(self.state_file(), "rb") as f:
            return f.read()

    def state_file(self, n=7):
        return os.path.join(self.git_dir, "kitchen-sink", "shepherd", f"{n}.json")


class TestRules(unittest.TestCase):
    def test_timeout_minutes(self):
        self.assertEqual(rules.timeout_minutes(None), 180)
        self.assertEqual(rules.timeout_minutes("5"), 5)
        for bad in ("0", "05", "x"):
            with self.assertRaises(rules.RuleError):
                rules.timeout_minutes(bad)

    def test_valid_ref(self):
        for ok in ("fix-174", "feat/a.b"):
            self.assertTrue(rules.valid_ref(ok), ok)
        for bad in ("a..b", "-x", "a b", "a;b"):
            self.assertFalse(rules.valid_ref(bad), bad)


class TestStart(Env):
    def test_start_writes_state(self):
        code, out = self.main("start", "--model", "Opus 5.5")
        self.assertEqual((code, out), (0, {"action": "next"}))
        self.assertEqual(os.stat(self.state_file()).st_mode & 0o777, 0o600)
        state = sh.load_state(7)
        self.assertEqual((state["repairs"], state["rerun"], state["infra"]), (0, 0, []))
        self.assertEqual(state["deadline"], NOW + 180 * 60)
        self.assertEqual(state["model"], "Opus 5.5")
        self.assertEqual((state["pr"], state["branch"], state["owner"], state["repo"]), (7, "fix-174", "o", "r"))

    def test_start_handoff(self):
        self.replies.update(
            {
                "gh pr view --json number": fail("no pull requests found"),
                "git branch --show-current": "fix-12\n",
                "gh pr list --head fix-12": "0\n",
                "gh repo view --json defaultBranchRef": "main\n",
                "git status --porcelain": "",
                "git rev-list --count origin/main..HEAD": "2\n",
            }
        )
        code, out = self.main("start", "--model", "X")
        self.assertEqual((code, out), (0, {"action": "handoff", "issue": 12}))
        self.assertFalse(os.path.exists(os.path.join(self.git_dir, "kitchen-sink", "shepherd", "12.json")))

    def test_start_rejects(self):
        cases = {
            "cross-repo": {"gh pr view 7": pr_view(isCrossRepository=True)},
            "other author": {"gh pr view 7": pr_view(author={"login": "x"})},
            "non-default base": {"gh pr view 7": pr_view(baseRefName="dev")},
            "bad sha": {"gh pr view 7": pr_view(headRefOid="abc")},
            "branch mismatch": {"gh pr view 7": pr_view(headRefName="other")},
            "detached": {"git branch --show-current": "\n"},
        }
        codes = set()
        for name, replies in cases.items():
            with self.subTest(name):
                self.replies.update(replies)
                code, out = self.main("start", "--model", "X")
                self.assertEqual((code, out["action"], out["terminal"]), (0, "stop", True))
                codes.add(out["code"])
                self.assertFalse(os.path.exists(self.state_file()))
                self.reset_replies()  # fresh replies for the next case
        with self.subTest("bad model"):
            code, out = self.main("start", "--model", "bad;model")
            self.assertEqual((out["action"], out["terminal"]), ("stop", True))
            codes.add(out["code"])
        self.assertEqual(len(codes), len(cases) + 1)

    def test_lock_busy(self):
        self.assertEqual(self.main("start", "--model", "X")[1], {"action": "next"})
        before = self.read_state_bytes()
        with sh.locked(7):
            code, out = self.main("start", "--model", "X")
        self.assertEqual((code, out), (0, {"action": "busy"}))
        self.assertEqual(self.read_state_bytes(), before)


if __name__ == "__main__":
    unittest.main()
