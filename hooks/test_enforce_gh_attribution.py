#!/usr/bin/env python3
"""Tests for enforce-gh-attribution.py (stdlib unittest).

Run: python3 hooks/test_enforce_gh_attribution.py

Each test invokes the hook as a subprocess, feeds a JSON payload on stdin, and
asserts whether a `deny` was emitted (BLOCK) or not (ALLOW).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "enforce-gh-attribution.py")

FOOTER = "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code) · Opus 4.8"


def run(cmd_string, cwd=None):
    """Invoke the hook; return True if it emitted a deny decision."""
    payload = {"tool_input": {"command": cmd_string}}
    if cwd is not None:
        payload["cwd"] = cwd
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    if not out:
        return False
    try:
        data = json.loads(out)
    except ValueError:
        return False
    return data.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class EnforceGhAttributionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, name, contents):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(contents)
        return path

    # --- issue/pr comment ------------------------------------------------
    def test_issue_comment_no_footer_blocks(self):
        self.assertTrue(run("gh issue comment 6 --body 'hi'"))

    def test_issue_comment_with_footer_allows(self):
        self.assertFalse(run(
            "gh issue comment 6 --body 'hi ... "
            "[Claude Code](https://claude.com/claude-code) · Opus 4.8'"))

    def test_pr_comment_with_footer_allows(self):
        self.assertFalse(run(
            "gh pr comment 3 --body 'ok "
            "[Claude Code](https://claude.com/claude-code) · v'"))

    # --- body-file -------------------------------------------------------
    def test_body_file_with_footer_allows(self):
        p = self._write("body.md", "hello\n\n" + FOOTER + "\n")
        self.assertFalse(run("gh issue comment 6 --body-file %s" % p))

    def test_body_file_without_footer_blocks(self):
        p = self._write("body.md", "hello, no attribution\n")
        self.assertTrue(run("gh issue comment 6 --body-file %s" % p))

    def test_body_file_relative_to_cwd(self):
        self._write("body.md", "hi\n\n" + FOOTER + "\n")
        self.assertFalse(run("gh issue comment 6 --body-file body.md",
                            cwd=self.tmp))

    def test_body_file_unreadable_allows(self):
        self.assertFalse(run("gh issue comment 6 --body-file /no/such/file.md"))

    # --- gh api ----------------------------------------------------------
    def test_api_post_field_file_with_footer_allows(self):
        p = self._write("body.md", "hi\n\n" + FOOTER + "\n")
        self.assertFalse(run(
            "gh api -X POST repos/o/r/issues/6/comments -F body=@%s" % p))

    def test_api_patch_inline_no_footer_blocks(self):
        self.assertTrue(run(
            "gh api -X PATCH repos/o/r/issues/comments/123 -f body='no footer'"))

    def test_api_review_reply_footer_allows(self):
        body = ("done\n\n---\n\U0001F916 Review by "
                "[Claude Code](https://claude.com/claude-code) · Opus 4.8")
        self.assertFalse(run(
            "gh api -X POST repos/o/r/pulls/comments/1/replies -f body=%s"
            % json_quote(body)))

    def test_api_get_no_method_allows(self):
        self.assertFalse(run("gh api repos/o/r/issues/6/comments"))

    def test_api_read_repo_allows(self):
        self.assertFalse(run("gh api repos/o/r"))

    # --- pr create -------------------------------------------------------
    def test_pr_create_no_footer_blocks(self):
        self.assertTrue(run("gh pr create --title x --body 'no footer'"))

    # --- read-only -------------------------------------------------------
    def test_issue_view_allows(self):
        self.assertFalse(run("gh issue view 6"))

    def test_issue_list_allows(self):
        self.assertFalse(run("gh issue list"))

    def test_pr_view_allows(self):
        self.assertFalse(run("gh pr view 3"))

    # --- fail-open cases -------------------------------------------------
    def test_heredoc_allows(self):
        self.assertFalse(run("gh issue comment 6 <<'EOF'\nhi\nEOF"))

    def test_dynamic_body_allows(self):
        self.assertFalse(run('gh issue comment 6 --body "$(cat body.md)"'))

    def test_pipe_allows(self):
        self.assertFalse(run("echo hi | gh issue comment 6 --body-file -"))

    # --- non-gh ----------------------------------------------------------
    def test_ls_allows(self):
        self.assertFalse(run("ls -la"))

    def test_git_status_allows(self):
        self.assertFalse(run("git status"))

    # --- issue edit ------------------------------------------------------
    def test_issue_edit_no_body_allows(self):
        self.assertFalse(run("gh issue edit 6 --add-label bug"))

    def test_issue_edit_body_no_footer_blocks(self):
        self.assertTrue(run("gh issue edit 6 --body 'no footer'"))


def json_quote(s):
    """Shell-safe single-quote wrapping (bodies here contain no apostrophes)."""
    return "'" + s + "'"


if __name__ == "__main__":
    unittest.main(verbosity=2)
