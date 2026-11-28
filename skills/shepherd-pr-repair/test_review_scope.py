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


class RepoCase(unittest.TestCase):
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
        env = dict(os.environ, GIT_EDITOR="true", GIT_LITERAL_PATHSPECS="1")
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

    def review(self, args=None, cwd=None):
        """Record a review of HEAD the way the hook does; return HEAD."""
        tool_input = {"skill": "code-review-intense-flow"}
        if args is not None:
            tool_input["args"] = args
        subprocess.run([sys.executable, HOOK], check=True, text=True, input=json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Skill",
            "tool_input": tool_input, "cwd": cwd or self.repo,
        }))
        return self.git("-C", cwd or self.repo, "rev-parse", "HEAD")

    def marker(self, sha):
        return os.path.join(self.repo, ".git", "kitchen-sink", "reviewed", sha)

    def since(self, rev, cwd=None):
        """Run --since rev; return (scope.json path, its data)."""
        out = subprocess.run([sys.executable, SCRIPT, "--since", rev], cwd=cwd or self.repo, check=True,
                             capture_output=True, text=True).stdout.strip()
        with open(out, encoding="utf-8") as fh:
            return out, json.load(fh)

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

class ReviewScope(RepoCase):
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
        self.assertIn("upstream and branch", self.read(data["range_diff"]))

    def test_non_ascii_file_name(self):
        self.odd_name("\u00e9.txt")

    def test_pathspec_magic_file_name(self):
        self.odd_name(":(literal)x.txt")

    def odd_name(self, name):
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
        data = self.scope(old, rebased)
        self.assertEqual(data["mode"], "rebase-delta")
        self.assertIn("rewritten 0", self.read(data["range_diff"]))

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

    def test_partial_old_head_falls_back(self):
        old, rebased = self.conflicting_rebase(self.resolved())
        shutil.rmtree(os.path.join(self.repo, ".git", "kitchen-sink", "reviewed"))
        os.makedirs(os.path.dirname(self.marker(old)))
        with open(self.marker(old), "w", encoding="utf-8") as fh:
            fh.write("2026-01-01T00:00:00+00:00 skill partial\n")
        self.assertFull(self.scope(old, rebased), "no review recorded")


class Since(RepoCase):
    """--since: rounds 2+ of /fix-gh-issue review only R..HEAD."""

    def setUp(self):
        super().setUp()
        self.edit("branch\n", "feat")
        self.r = self.review()

    def test_full_marker_gives_incremental(self):
        self.change("fix.txt", ["fixed\n"], "review fix")
        _, data = self.since(self.r)
        self.assertEqual(data["mode"], "incremental")
        self.assertEqual(data["since"], self.r)
        self.assertEqual(data["head"], self.git("rev-parse", "HEAD"))

    def test_chain_of_increments(self):
        self.change("fix.txt", ["fixed\n"], "review fix")
        path, _ = self.since(self.r)
        r2 = self.review(f"scope={path}")
        self.assertEqual(self.read(self.marker(r2)).split()[2:], ["incremental", self.r, "complete"])
        self.change("fix2.txt", ["fixed again\n"], "second fix")
        _, data = self.since(r2)
        self.assertEqual(data["mode"], "incremental")
        self.assertEqual(data["since"], r2)

    def test_unresolvable_since_falls_back(self):
        self.assertFull(self.since("no-such-ref")[1], "git rev-parse failed")

    def test_unreviewed_since_falls_back(self):
        os.remove(self.marker(self.r))
        self.change("fix.txt", ["fixed\n"], "review fix")
        self.assertFull(self.since(self.r)[1], "no complete review")

    def test_partial_since_falls_back(self):
        with open(self.marker(self.r), "w", encoding="utf-8") as fh:
            fh.write(f"2026-01-01T00:00:00+00:00 skill incremental {self.r} partial\n")
        self.change("fix.txt", ["fixed\n"], "review fix")
        self.assertFull(self.since(self.r)[1], "no complete review")

    def test_non_ancestor_since_falls_back(self):
        self.git("commit", "-q", "--amend", "-m", "reworded")
        self.assertFull(self.since(self.r)[1], "not an ancestor")

    def test_since_at_head_falls_back(self):
        self.assertFull(self.since(self.r)[1], "no commits since")

    def test_since_excludes_rebase_flags(self):
        proc = subprocess.run([sys.executable, SCRIPT, "--since", self.r, "--base", "main"],
                              cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--since excludes --old-head, --rebased and --base", proc.stderr)

    def test_partial_rebase_flags_rejected(self):
        proc = subprocess.run([sys.executable, SCRIPT, "--old-head", self.r],
                              cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("give --since, or all of --old-head, --rebased and --base", proc.stderr)

    def test_linked_worktree(self):
        wt = os.path.join(self.tmp, "wt")
        self.git("worktree", "add", "-q", "-b", "fix-456", wt)
        self.git("-C", wt, "commit", "-q", "--allow-empty", "-m", "review fix")
        path, data = self.since(self.r, cwd=wt)
        self.assertEqual(data["mode"], "incremental")
        git_dir = self.git("-C", wt, "rev-parse", "--absolute-git-dir")
        self.assertEqual(os.path.realpath(path),
                         os.path.realpath(os.path.join(git_dir, "kitchen-sink", "scope", "scope.json")))
        head = self.review(f"scope={path}", cwd=wt)
        # The marker lands in the common dir, shared with the main worktree.
        self.assertEqual(self.read(self.marker(head)).split()[2:], ["incremental", self.r, "complete"])


if __name__ == "__main__":
    unittest.main()
