#!/usr/bin/env python3
"""Tests for codex_loop.py parsing and classification.

Run: python3 skills/codex-review-loop/test_codex_loop.py
"""

import importlib.util
import os
import unittest

_MOD_PATH = os.path.join(os.path.dirname(__file__), "codex_loop.py")
_spec = importlib.util.spec_from_file_location("codex_loop", _MOD_PATH)
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)

BOT = cl.BOT_LOGIN
SHA = "c5bf4f3aed0123456789abcdef0123456789abcd"

FINDINGS_OUTPUT = """\
The change introduces a verified arithmetic regression in `avg`.

Review comment:

- [P1] Include the first element in the average — /repo/m.py:3-3
  Starting the loop at index 1 skips `xs[0]`.
  Start at index 0.
- [P2] Handle missing keys — /repo/m.py:8-9
  `d.get` returns None silently.
- [P3] Prefer sum() — /repo/m.py:2
  Style nit.
"""

CLEAN_OUTPUT = (
    "The change adds a straightforward double function without altering existing "
    "behavior. No actionable bugs were identified.\n"
)


class ParseLocalReview(unittest.TestCase):
    def test_findings_split_by_priority(self):
        r = cl.parse_local_review(FINDINGS_OUTPUT)
        self.assertFalse(r["clean"])
        self.assertEqual([f["priority"] for f in r["blocking"]], ["P1", "P2"])
        self.assertEqual([f["priority"] for f in r["advisory"]], ["P3"])

    def test_finding_fields(self):
        f = cl.parse_local_review(FINDINGS_OUTPUT)["blocking"][0]
        self.assertEqual(f["title"], "Include the first element in the average")
        self.assertEqual(f["path"], "/repo/m.py")
        self.assertEqual(f["line"], 3)
        self.assertEqual(f["body"], "Starting the loop at index 1 skips `xs[0]`. Start at index 0.")

    def test_single_line_location(self):
        f = cl.parse_local_review(FINDINGS_OUTPUT)["advisory"][0]
        self.assertEqual(f["line"], 2)

    def test_clean_output(self):
        r = cl.parse_local_review(CLEAN_OUTPUT)
        self.assertTrue(r["clean"])
        self.assertEqual(r["blocking"], [])

    def test_only_p3_is_clean(self):
        r = cl.parse_local_review("- [P3] Nit — /a.py:1\n  meh\n")
        self.assertTrue(r["clean"])
        self.assertEqual(len(r["advisory"]), 1)

    def test_p0_blocks(self):
        self.assertFalse(cl.parse_local_review("- [P0] Data loss — /a.py:1\n")["clean"])


class ResolveMode(unittest.TestCase):
    def test_configured_values(self):
        for value in ("off", "local", "github", "GitHub "):
            self.assertEqual(cl.resolve_mode(value, True), (value.strip().lower(), "git-config"))

    def test_invalid_value_errors(self):
        with self.assertRaises(cl.ToolError):
            cl.resolve_mode("true", True)

    def test_unset_defaults_on_codex_presence(self):
        self.assertEqual(cl.resolve_mode("", True), ("local", "default"))
        self.assertEqual(cl.resolve_mode("", False), ("off", "default"))


def review(login=BOT, commit=SHA, rid=1):
    return {"id": rid, "user": {"login": login}, "commit_id": commit}


def comment(body, login=BOT, cid=9):
    return {"id": cid, "user": {"login": login}, "body": body}


CLEAN_BODY = "Codex Review: Didn't find any major issues. Bravo.\n\n**Reviewed commit:** `c5bf4f3aed`\n"


class ClassifyBotActivity(unittest.TestCase):
    def test_pending_when_nothing(self):
        self.assertEqual(cl.classify_bot_activity(SHA, [], [])["status"], "pending")

    def test_findings_review_on_head(self):
        r = cl.classify_bot_activity(SHA, [review()], [])
        self.assertEqual(r, {"status": "findings", "review_id": 1})

    def test_review_on_older_commit_is_pending(self):
        r = cl.classify_bot_activity(SHA, [review(commit="0" * 40)], [])
        self.assertEqual(r["status"], "pending")

    def test_human_review_ignored(self):
        r = cl.classify_bot_activity(SHA, [review(login="octocat")], [])
        self.assertEqual(r["status"], "pending")

    def test_clean_comment_on_head(self):
        r = cl.classify_bot_activity(SHA, [], [comment(CLEAN_BODY)])
        self.assertEqual(r, {"status": "clean", "comment_id": 9})

    def test_clean_comment_on_older_commit_is_pending(self):
        body = CLEAN_BODY.replace("c5bf4f3aed", "0123456789")
        self.assertEqual(cl.classify_bot_activity(SHA, [], [comment(body)])["status"], "pending")

    def test_summary_comment_without_clean_marker_is_pending(self):
        body = "<!-- codex-pull-request-review-summary -->\n**Reviewed commit:** `c5bf4f3aed`"
        self.assertEqual(cl.classify_bot_activity(SHA, [], [comment(body)])["status"], "pending")

    def test_bot_thumbs_up_on_trigger_is_clean(self):
        reactions = [{"content": "+1", "user": {"login": BOT}}]
        r = cl.classify_bot_activity(SHA, [], [], reactions)
        self.assertEqual(r, {"status": "clean", "via": "reaction"})

    def test_eyes_reaction_is_acknowledged_pending(self):
        reactions = [{"content": "eyes", "user": {"login": BOT}}]
        r = cl.classify_bot_activity(SHA, [], [], reactions)
        self.assertEqual(r, {"status": "pending", "acknowledged": True})

    def test_human_thumbs_up_ignored(self):
        reactions = [{"content": "+1", "user": {"login": "oalders"}}]
        self.assertEqual(cl.classify_bot_activity(SHA, [], [], reactions)["status"], "pending")

    def test_findings_review_beats_reaction(self):
        reactions = [{"content": "+1", "user": {"login": BOT}}]
        r = cl.classify_bot_activity(SHA, [review()], [], reactions)
        self.assertEqual(r["status"], "findings")

    def test_clean_marker_from_human_ignored(self):
        r = cl.classify_bot_activity(SHA, [], [comment(CLEAN_BODY, login="mallory")])
        self.assertEqual(r["status"], "pending")


def thread(login="chatgpt-codex-connector", resolved=False, body=None, tid="T1"):
    if body is None:
        body = (
            "**<sub><sub>![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)</sub></sub>"
            "  Make mutations idempotent**\n\nWhen Domain commits..."
        )
    return {
        "id": tid,
        "isResolved": resolved,
        "isOutdated": True,
        "path": "svc/app.py",
        "line": 12,
        "comments": {"nodes": [{"author": {"login": login}, "body": body, "url": "u"}]},
    }


class BotThreads(unittest.TestCase):
    def test_bot_thread_parsed(self):
        [t] = cl.bot_threads([thread()])
        self.assertEqual(t["id"], "T1")
        self.assertEqual(t["priority"], "P1")
        self.assertEqual(t["title"], "Make mutations idempotent")
        self.assertTrue(t["outdated"])

    def test_rest_style_login_accepted(self):
        self.assertEqual(len(cl.bot_threads([thread(login=BOT)])), 1)

    def test_resolved_and_human_threads_skipped(self):
        nodes = [thread(resolved=True), thread(login="octocat", tid="T2")]
        self.assertEqual(cl.bot_threads(nodes), [])

    def test_unbadged_bot_thread_kept(self):
        [t] = cl.bot_threads([thread(body="plain text")])
        self.assertIsNone(t["priority"])


if __name__ == "__main__":
    unittest.main()
