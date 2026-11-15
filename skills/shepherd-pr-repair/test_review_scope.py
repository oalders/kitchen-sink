#!/usr/bin/env python3
"""Tests for review_scope.py (stdlib unittest).

Run: python3 skills/shepherd-pr-repair/test_review_scope.py

Each test builds a real git repo in $TMPDIR, rebases a reviewed fix-123 branch
onto a moved main, and runs the script as a subprocess.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "review_scope.py")
HOOK = os.path.join(HERE, "..", "..", "hooks", "require-review-before-pr.py")
LINES = [f"line {i}\n" for i in range(10)]


class ReviewScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()  # honours $TMPDIR
        self.repo = self.tmp
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.change("a.txt", LINES, "one")
        self.git("checkout", "-q", "-b", "fix-123")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, check=True):
        env = dict(os.environ, GIT_EDITOR="true")
        return subprocess.run(["git", "-C", self.repo, *args], check=check,
                              capture_output=True, text=True, env=env).stdout.strip()

    def change(self, name, lines, msg):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        self.git("add", name)
        self.git("commit", "-q", "-m", msg)

    def edit(self, line5, msg, name="a.txt"):
        lines = list(LINES)
        lines[5] = line5
        self.change(name, lines, msg)

    def review(self):
        """Record a review of HEAD the way the hook does; return HEAD."""
        subprocess.run([sys.executable, HOOK], check=True, text=True, input=json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Skill",
            "tool_input": {"skill": "code-review-intense-flow"}, "cwd": self.repo,
        }))
        return self.git("rev-parse", "HEAD")

    def conflicting_rebase(self, resolution):
        """Branch and main both edit line 5; rebase, resolve with `resolution`; return (old head, rebased)."""
        self.edit("branch\n", "feat")
        old = self.review()
        self.git("checkout", "-q", "main")
        self.change("other.txt", ["other\n"], "unrelated upstream")
        self.edit("upstream\n", "upstream edit")
        self.git("checkout", "-q", "fix-123")
        return old, self.resolve(resolution)

    def resolve(self, resolution, name="a.txt"):
        """Rebase onto main, resolve `name`'s conflict with `resolution`; return the rebased HEAD."""
        self.git("rebase", "main", check=False)
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
            fh.writelines(resolution)
        self.git("add", name)
        self.git("rebase", "--continue")
        return self.git("rev-parse", "HEAD")

    def scope(self, old, rebased, base="main", cwd=None):
        out = subprocess.run([sys.executable, SCRIPT, "--old-head", old, "--rebased", rebased, "--base", base],
                             cwd=cwd or self.repo, check=True, capture_output=True, text=True).stdout.strip()
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def resolved(self):
        lines = list(LINES)
        lines[5] = "upstream and branch\n"
        return lines

    def assertFull(self, data, reason):
        self.assertEqual(data["mode"], "full")
        self.assertIn(reason, data["reason"])

    def test_direct_marker_gives_rebase_delta_with_upstream_commits(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        data = self.scope(old, rebased)
        self.assertEqual(data["mode"], "rebase-delta")
        self.assertEqual(data["old_head"], old)
        self.assertEqual(data["files"], ["a.txt"])
        self.assertIn("upstream and branch", self.read(data["range_diff"]))
        self.assertIn("upstream edit", self.read(data["upstream"]))
        self.assertNotIn("unrelated upstream", self.read(data["upstream"]))
        self.assertEqual(self.read(data["fixes"]), "")

    def test_only_the_changed_commit_is_scoped(self):
        self.change("c.txt", ["quiet\n"], "untouched commit")
        self.edit("branch\n", "feat")
        old = self.review()
        self.git("checkout", "-q", "main")
        self.edit("upstream\n", "upstream edit")
        self.git("checkout", "-q", "fix-123")
        data = self.scope(old, self.resolve(self.resolved()))
        self.assertEqual(data["mode"], "rebase-delta")
        self.assertEqual(data["files"], ["a.txt"])
        self.assertNotIn("untouched commit", self.read(data["range_diff"]))
        self.assertIn("feat", self.read(data["range_diff"]))

    def test_non_ascii_file_name(self):
        name = "\u00e9.txt"
        self.git("checkout", "-q", "main")
        self.change(name, LINES, "add")
        self.git("checkout", "-q", "fix-123")
        self.git("rebase", "-q", "main")
        self.edit("branch\n", "feat", name=name)
        old = self.review()
        self.git("checkout", "-q", "main")
        self.edit("upstream\n", "upstream edit", name=name)
        self.git("checkout", "-q", "fix-123")
        data = self.scope(old, self.resolve(self.resolved(), name=name))
        self.assertEqual(data["mode"], "rebase-delta")
        self.assertEqual(data["files"], [name])
        self.assertIn("upstream edit", self.read(data["upstream"]))

    def test_scope_is_per_worktree(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        first = self.scope(old, rebased)
        other = os.path.join(self.tmp, "other")
        self.git("worktree", "add", "-q", "--detach", other, rebased)
        second = self.scope(old, rebased, cwd=other)
        self.assertNotEqual(os.path.dirname(first["range_diff"]), os.path.dirname(second["range_diff"]))
        self.assertTrue(os.path.isfile(first["range_diff"]))

    def test_patch_marker_only_gives_rebase_delta(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        os.remove(os.path.join(self.repo, ".git", "kitchen-sink", "reviewed", old))
        self.assertEqual(self.scope(old, rebased)["mode"], "rebase-delta")

    def test_heavily_rewritten_resolution_gives_rebase_delta(self):
        old, rebased = self.conflicting_rebase([f"rewritten {i}\n" for i in range(10)])
        self.assertEqual(self.scope(old, rebased)["mode"], "rebase-delta")

    def test_later_round_adds_fix_commits(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        self.change("fix.txt", ["fixed\n"], "review fix")
        data = self.scope(old, rebased)
        self.assertEqual(data["mode"], "rebase-delta")
        self.assertEqual(data["files"], ["a.txt", "fix.txt"])
        self.assertIn("+fixed", self.read(data["fixes"]))

    def test_unreviewed_old_head_falls_back(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        shutil.rmtree(os.path.join(self.repo, ".git", "kitchen-sink", "reviewed"))
        self.assertFull(self.scope(old, rebased), "no review recorded")

    def test_changed_commit_count_falls_back(self):
        old, _ = self.conflicting_rebase(self.resolved())
        self.change("extra.txt", ["x\n"], "extra")
        self.assertFull(self.scope(old, self.git("rev-parse", "HEAD")), "number of commits")

    def test_unpaired_commit_falls_back(self):
        old, _ = self.conflicting_rebase(self.resolved())
        self.git("reset", "-q", "--hard", "main")
        self.change("other.txt", [f"other {i}\n" for i in range(20)], "unrelated")
        self.assertFull(self.scope(old, self.git("rev-parse", "HEAD")), "no counterpart")

    def test_large_delta_falls_back(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        self.change("big.txt", [f"{i}\n" for i in range(400)], "big fix")
        self.assertFull(self.scope(old, rebased), "over 300 lines")

    def test_bad_base_ref_falls_back(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        self.assertFull(self.scope(old, rebased, base="no-such-ref"), "git rev-parse failed")

    def test_unchanged_commits_fall_back(self):
        self.edit("branch\n", "feat")
        old = self.review()
        self.git("checkout", "-q", "main")
        self.change("b.txt", ["b\n"], "unrelated upstream")
        self.git("checkout", "-q", "fix-123")
        self.git("rebase", "-q", "main")
        self.assertFull(self.scope(old, self.git("rev-parse", "HEAD")), "no commit changed")


if __name__ == "__main__":
    unittest.main()
