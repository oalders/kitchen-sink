#!/usr/bin/env python3
"""Tests for the suggest-review-after-commit PostToolUse hook.

Run: python3 hooks/test_suggest_review_after_commit.py
"""

import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stdout

_MOD_PATH = os.path.join(os.path.dirname(__file__), "suggest-review-after-commit.py")
_spec = importlib.util.spec_from_file_location("suggest_review", _MOD_PATH)
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def ok(stdout="", stderr="", interrupted=False):
    return {"stdout": stdout, "stderr": stderr, "interrupted": interrupted}


class IsSuccessfulCommit(unittest.TestCase):
    def test_plain_commit(self):
        self.assertTrue(sr.is_successful_commit('git commit -m "x"', ok()))

    def test_commit_with_global_flags(self):
        self.assertTrue(sr.is_successful_commit('git -C /repo commit -m "x"', ok()))
        self.assertTrue(sr.is_successful_commit('git --no-pager commit -am "x"', ok()))

    def test_commit_in_compound_command(self):
        self.assertTrue(sr.is_successful_commit('git add -A && git commit -m "x"', ok()))
        self.assertTrue(sr.is_successful_commit('git add . ; git commit -m "x"', ok()))

    def test_non_commit_commands_silent(self):
        for cmd in [
            "git status",
            "git diff HEAD~1 --name-only",
            "git log --oneline",
            "top -l 2 -o cpu",
            "iostat -d -w 1",
            'echo "run git commit later"',
            "gh issue view 3739",
        ]:
            self.assertFalse(sr.is_successful_commit(cmd, ok()), cmd)

    def test_commit_help_and_dry_run_skipped(self):
        self.assertFalse(sr.is_successful_commit("git commit --help", ok()))
        self.assertFalse(sr.is_successful_commit("git commit -h", ok()))
        self.assertFalse(sr.is_successful_commit('git commit --dry-run', ok()))

    def test_commit_tree_not_matched(self):
        self.assertFalse(sr.is_successful_commit("git commit-tree abc123", ok()))

    def test_failed_commit_skipped(self):
        self.assertFalse(
            sr.is_successful_commit('git commit -m "x"', ok(stdout="nothing to commit, working tree clean"))
        )
        self.assertFalse(
            sr.is_successful_commit('git commit -m "x"', ok(stderr="error: pathspec did not match"))
        )
        self.assertFalse(
            sr.is_successful_commit('git commit -m "x"', ok(stderr="fatal: not a git repository"))
        )

    def test_interrupted_commit_skipped(self):
        self.assertFalse(sr.is_successful_commit('git commit -m "x"', ok(interrupted=True)))

    def test_string_response_supported(self):
        self.assertTrue(sr.is_successful_commit('git commit -m "x"', "[main abc123] x"))
        self.assertFalse(sr.is_successful_commit('git commit -m "x"', "nothing to commit"))

    def test_empty_command(self):
        self.assertFalse(sr.is_successful_commit("", ok()))
        self.assertFalse(sr.is_successful_commit(None, ok()))


class MainOutput(unittest.TestCase):
    def _run(self, payload):
        stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        old = sr.sys.stdin
        sr.sys.stdin = stdin
        try:
            with redirect_stdout(out):
                rc = sr.main()
        finally:
            sr.sys.stdin = old
        return rc, out.getvalue()

    def test_silent_on_non_commit(self):
        rc, out = self._run(
            {"tool_input": {"command": "top -l 2"}, "tool_response": ok()}
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_emits_context_on_commit(self):
        rc, out = self._run(
            {"tool_input": {"command": 'git commit -m "x"'}, "tool_response": ok(stdout="[main abc] x")}
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("AskUserQuestion", data["hookSpecificOutput"]["additionalContext"])

    def test_bad_json_fails_silent(self):
        sr.sys.stdin = io.StringIO("not json{")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = sr.main()
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
