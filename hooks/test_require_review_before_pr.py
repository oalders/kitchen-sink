#!/usr/bin/env python3
"""Tests for require-review-before-pr.py (stdlib unittest).

Run: python3 hooks/test_require_review_before_pr.py

Each test builds a real temporary git repo, invokes the hook as a subprocess
with a JSON payload on stdin, and asserts on markers written or on whether a
`deny` decision was emitted.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "require-review-before-pr.py")
ENV_BYPASS = "KITCHEN_SINK_ALLOW_UNREVIEWED_PR"


def hook_env(**extra):
    env = {k: v for k, v in os.environ.items() if k != ENV_BYPASS}
    env.update(extra)
    return env


def run_hook(payload, env=None, raw=None):
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env if env is not None else hook_env(),
    )
    return proc


def is_deny(proc):
    out = proc.stdout.strip()
    if not out:
        return False
    data = json.loads(out)
    return data["hookSpecificOutput"]["permissionDecision"] == "deny"


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()  # honours $TMPDIR
        self.repo = os.path.join(self.tmp, "repo")
        os.mkdir(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.commit("one")
        self.git("checkout", "-q", "-b", "fix-123")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(
            ["git", "-C", cwd or self.repo, *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, msg, cwd=None):
        self.git("commit", "-q", "--allow-empty", "-m", msg, cwd=cwd)

    def head(self, cwd=None):
        return self.git("rev-parse", "HEAD", cwd=cwd)

    def marker(self, sha=None):
        return os.path.join(
            self.repo, ".git", "kitchen-sink", "reviewed", sha or self.head()
        )

    def skill(self, name, cwd=None):
        return run_hook({
            "hook_event_name": "PostToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": name},
            "cwd": cwd or self.repo,
        })

    def prompt(self, text, cwd=None):
        return run_hook({
            "hook_event_name": "UserPromptSubmit",
            "prompt": text,
            "cwd": cwd or self.repo,
        })

    def bash(self, command, env=None, cwd=None):
        return run_hook({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": cwd or self.repo,
        }, env=env)


class Record(RepoCase):
    def test_skill_short_name_records(self):
        proc = self.skill("code-review-intense-flow")
        self.assertEqual(proc.stdout, "")
        self.assertTrue(os.path.isfile(self.marker()))

    def test_skill_namespaced_name_records(self):
        self.skill("kitchen-sink:code-review-intense-flow")
        self.assertTrue(os.path.isfile(self.marker()))

    def test_skill_leading_slash_records(self):
        self.skill("/code-review-intense-flow")
        self.assertTrue(os.path.isfile(self.marker()))

    def test_other_skill_records_nothing(self):
        for name in ("code-review-flow", "security-review",
                     "code-review-intense-flow-x"):
            self.skill(name)
        self.assertFalse(os.path.exists(self.marker()))

    def test_prompt_records_and_prints_nothing(self):
        for text in ("/code-review-intense-flow",
                     "  /kitchen-sink:code-review-intense-flow please"):
            proc = self.prompt(text)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
        self.assertTrue(os.path.isfile(self.marker()))

    def test_non_matching_prompt_records_nothing(self):
        for text in ("/code-review-intense-flowx", "/code-review-flow",
                     "please run /code-review-intense-flow", "hello"):
            proc = self.prompt(text)
            self.assertEqual(proc.stdout, "")
        self.assertFalse(os.path.exists(self.marker()))


class Gate(RepoCase):
    def test_denies_without_marker(self):
        for cmd in ("gh pr create --draft --title t --body b",
                    "gh pr ready",
                    "gh pr ready 42",
                    "git push -u origin fix-123 && gh pr create --draft",
                    "gh -R o/r pr create --fill",
                    "gh --repo=o/r pr ready"):
            proc = self.bash(cmd)
            self.assertTrue(is_deny(proc), cmd)
        self.assertIn(self.head(), self.bash("gh pr ready").stdout)

    def test_allows_with_marker(self):
        self.skill("code-review-intense-flow")
        self.assertFalse(is_deny(self.bash("gh pr create --draft")))
        self.assertFalse(is_deny(self.bash("gh pr ready")))

    def test_new_commit_after_marker_denies_again(self):
        self.skill("code-review-intense-flow")
        self.commit("review fix")
        self.assertTrue(is_deny(self.bash("gh pr create --draft")))

    def test_ready_undo_allowed(self):
        self.assertFalse(is_deny(self.bash("gh pr ready --undo")))
        self.assertFalse(is_deny(self.bash("gh pr ready 42 --undo")))

    def test_non_fix_branch_allowed(self):
        for branch in ("main", "fix-123-extra", "feature"):
            self.git("checkout", "-q", "-B", branch)
            self.assertFalse(is_deny(self.bash("gh pr create")), branch)

    def test_detached_head_allowed(self):
        self.git("checkout", "-q", "--detach")
        self.assertFalse(is_deny(self.bash("gh pr create")))

    def test_non_gated_commands_allowed(self):
        for cmd in ("git status", "gh pr view 3", "gh pr list",
                    "gh issue create --title t", "gh pr checks",
                    "gh pr created", 'echo "gh pr create"',
                    "echo 'gh pr create'", "git commit -m x"):
            self.assertFalse(is_deny(self.bash(cmd)), cmd)

    def test_unquoted_mention_false_positive_denied(self):
        # Documented accepted gap: unquoted mentions look like a real call.
        self.assertTrue(is_deny(self.bash("echo gh pr create")))

    def test_chained_commit_and_pr_denied_even_with_marker(self):
        self.skill("code-review-intense-flow")
        proc = self.bash('git commit -am x && git push && gh pr create --draft')
        self.assertTrue(is_deny(proc))
        self.assertIn("pre-commit SHA", proc.stdout)

    def test_env_escape_hatch_allows(self):
        proc = self.bash("gh pr create", env=hook_env(**{ENV_BYPASS: "1"}))
        self.assertFalse(is_deny(proc))

    def test_env_escape_hatch_requires_exactly_one(self):
        proc = self.bash("gh pr create", env=hook_env(**{ENV_BYPASS: "true"}))
        self.assertTrue(is_deny(proc))

    def test_inline_env_prefix_does_not_bypass(self):
        self.assertTrue(is_deny(self.bash(f"{ENV_BYPASS}=1 gh pr create")))
        self.assertTrue(is_deny(self.bash(f"export {ENV_BYPASS}=1; gh pr create")))

    def test_worktree_shares_markers(self):
        wt = os.path.join(self.tmp, "wt")
        self.git("worktree", "add", "-q", "-b", "fix-456", wt)
        self.assertTrue(is_deny(self.bash("gh pr create", cwd=wt)))
        self.skill("code-review-intense-flow", cwd=wt)
        # Marker lands in the common dir, not the worktree's private git dir.
        self.assertTrue(os.path.isfile(self.marker(self.head(cwd=wt))))
        self.assertFalse(is_deny(self.bash("gh pr create", cwd=wt)))


class FailOpen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_not_a_git_repo(self):
        env = hook_env(GIT_CEILING_DIRECTORIES=os.path.dirname(self.tmp))
        for payload in (
            {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": "gh pr create"}, "cwd": self.tmp},
            {"hook_event_name": "PostToolUse", "tool_name": "Skill",
             "tool_input": {"skill": "code-review-intense-flow"}, "cwd": self.tmp},
            {"hook_event_name": "UserPromptSubmit",
             "prompt": "/code-review-intense-flow", "cwd": self.tmp},
        ):
            proc = run_hook(payload, env=env)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
            self.assertEqual(proc.stderr, "")

    def test_bad_json(self):
        for raw in ("not json{", "", "[]", "null"):
            proc = run_hook(None, raw=raw)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")

    def test_missing_fields(self):
        for payload in (
            {},
            {"hook_event_name": "PreToolUse"},
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "gh pr create"}},
            {"hook_event_name": "PreToolUse", "cwd": "/nonexistent/x",
             "tool_input": {"command": "gh pr create"}},
            {"hook_event_name": "PostToolUse", "cwd": self.tmp, "tool_input": None},
        ):
            proc = run_hook(payload)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
