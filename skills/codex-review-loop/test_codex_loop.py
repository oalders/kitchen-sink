#!/usr/bin/env python3
"""Tests for codex_loop.py parsing and classification.

Run: python3 skills/codex-review-loop/test_codex_loop.py
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
            self.assertEqual(cl.resolve_mode(value), (value.strip().lower(), "git-config"))

    def test_invalid_value_errors(self):
        with self.assertRaises(cl.ToolError):
            cl.resolve_mode("true")

    def test_unset_defaults_to_off(self):
        self.assertEqual(cl.resolve_mode(""), ("off", "default"))


BLOCKED_OUTPUT = (
    'Review blocked: attempts to run the requested git diff failed with "error building '
    'bubblewrap command: Permission denied". The verdict is not a confirmed defect '
    "assessment; I could not inspect the changes or verify correctness.\n"
)


class BlindReview(unittest.TestCase):
    def reason(self, text, stderr=""):
        return cl.blind_review_reason(text, stderr, cl.parse_local_review(text))

    def test_review_blocked_summary_is_blind(self):
        self.assertIsNotNone(self.reason(BLOCKED_OUTPUT))
        self.assertIsNotNone(self.reason("\nreview BLOCKED: no access\n"))

    def test_bubblewrap_in_stderr_is_blind(self):
        stderr = "exec failed: error building bubblewrap command: Permission denied"
        self.assertIsNotNone(self.reason(CLEAN_OUTPUT, stderr))

    def test_clean_review_is_not_blind(self):
        self.assertIsNone(self.reason(CLEAN_OUTPUT, "WARNING: something"))

    def test_findings_mentioning_bubblewrap_not_blind(self):
        text = FINDINGS_OUTPUT + "Mentions error building bubblewrap command in a string.\n"
        self.assertIsNone(self.reason(text, "error building bubblewrap command"))


class OuterSandbox(unittest.TestCase):
    def test_config_overrides_nono(self):
        self.assertEqual(cl.resolve_outer_sandbox("false", "/x/cap"), (False, "git-config"))
        self.assertEqual(cl.resolve_outer_sandbox("true", ""), (True, "git-config"))

    def test_unset_follows_nono_env(self):
        self.assertEqual(cl.resolve_outer_sandbox("", "/x/cap"), (True, "nono"))
        self.assertEqual(cl.resolve_outer_sandbox("", None), (False, "default"))
        self.assertEqual(cl.resolve_outer_sandbox("", ""), (False, "default"))

    def test_review_command_bypass_flag(self):
        cmd = cl.review_command("/usr/bin/codex", "origin/main", "/o.txt", "T", True)
        self.assertEqual(cmd[0], "/usr/bin/codex")
        self.assertEqual(cmd[-1], cl.BYPASS_FLAG)
        self.assertIn("--title", cmd)
        cmd = cl.review_command("/usr/bin/codex", "origin/main", "/o.txt", None, False)
        self.assertNotIn(cl.BYPASS_FLAG, cmd)
        self.assertNotIn("--title", cmd)

    def test_config_read_is_local_only(self):
        calls = []

        def fake_run(cmd, check=True, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, "", "")

        with mock.patch.object(cl, "run", fake_run), mock.patch.dict(os.environ, {"NONO_CAP_FILE": ""}):
            self.assertEqual(cl.outer_sandbox(), {"enabled": False, "source": "default"})
        self.assertEqual(calls[0][:3], ["git", "config", "--local"])
        self.assertIn(cl.OUTER_SANDBOX_KEY, calls[0])


FAKE_CODEX = """#!{python}
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "argv.json"), "w") as fh:
    json.dump(sys.argv[1:], fh)
with open(os.path.join(here, "summary.txt")) as fh:
    summary = fh.read()
args = sys.argv[1:]
with open(args[args.index("-o") + 1], "w") as fh:
    fh.write(summary)
"""


class LocalReviewIntegration(unittest.TestCase):
    """Run `local-review` end to end against a fake `codex` on PATH."""

    def setUp(self):
        key = subprocess.run(
            ["git", "config", "--local", "--get", cl.OUTER_SANDBOX_KEY], capture_output=True, text=True
        )
        if key.returncode == 0:
            self.skipTest(f"{cl.OUTER_SANDBOX_KEY} is set in this repo's local config")
        self.tmp = tempfile.TemporaryDirectory(prefix="fake-codex-")
        self.addCleanup(self.tmp.cleanup)
        codex = os.path.join(self.tmp.name, "codex")
        with open(codex, "w") as fh:
            fh.write(FAKE_CODEX.format(python=sys.executable))
        os.chmod(codex, 0o755)

    def run_review(self, summary, nono_cap_file):
        with open(os.path.join(self.tmp.name, "summary.txt"), "w") as fh:
            fh.write(summary)
        env = {"PATH": self.tmp.name + os.pathsep + os.environ.get("PATH", ""), "TMPDIR": self.tmp.name}
        env["NONO_CAP_FILE"] = nono_cap_file
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
            rc = cl.main(["local-review", "--base", "HEAD"])
        with open(os.path.join(self.tmp.name, "argv.json")) as fh:
            argv = json.load(fh)
        return rc, json.loads(out.getvalue()), argv

    def test_blocked_review_is_tool_error(self):
        rc, out, argv = self.run_review(BLOCKED_OUTPUT, "")
        self.assertEqual(rc, 2)
        self.assertIn("could not inspect the diff", out["error"])
        self.assertIn("ask the user to run", out["error"])
        self.assertNotIn(cl.BYPASS_FLAG, argv)

    def test_blocked_review_with_bypass_needs_investigation(self):
        rc, out, argv = self.run_review(BLOCKED_OUTPUT, "/x/cap")
        self.assertEqual(rc, 2)
        self.assertIn("could not inspect the diff", out["error"])
        self.assertIn("already on (source: nono)", out["error"])
        self.assertIn(cl.BYPASS_FLAG, argv)

    def test_clean_review_under_nono_passes_bypass(self):
        rc, out, argv = self.run_review(CLEAN_OUTPUT, "/x/cap")
        self.assertEqual(rc, 0)
        self.assertTrue(out["clean"])
        self.assertEqual(out["outer_sandbox"], {"enabled": True, "source": "nono"})
        self.assertEqual(argv[:2], ["exec", "review"])
        self.assertIn(cl.BYPASS_FLAG, argv)


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
