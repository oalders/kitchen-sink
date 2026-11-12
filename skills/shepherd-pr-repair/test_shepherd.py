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
        if isinstance(reply, Exception):
            raise reply
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

    # --- decision rules: pure, so tested with literal inputs ---

    @staticmethod
    def add(t):
        return {"__typename": "AddedToMergeQueueEvent", "createdAt": t}

    @staticmethod
    def remove(t):
        return {"__typename": "RemovedFromMergeQueueEvent", "createdAt": t}

    @staticmethod
    def ejected_pr(**over):
        pr = {"isInMergeQueue": False, "autoMergeRequest": None}
        pr.update(over)
        return pr

    def test_buckets_and_pick_method(self):
        self.assertEqual(rules.buckets([{"bucket": "pass"}, {"bucket": "fail"}, {"bucket": "pass"}]), {"pass": 2, "fail": 1})
        self.assertEqual(rules.pick_method({"mergeCommitAllowed": True, "rebaseMergeAllowed": True}), "merge")
        self.assertIsNone(rules.pick_method({"squashMergeAllowed": False}))

    def test_ejection_head_removal(self):
        nodes = [self.add("t1"), self.remove("t2")]
        self.assertEqual(rules.ejection(self.ejected_pr(), nodes, "t0", None), nodes[1])

    def test_ejection_earlier_head(self):
        nodes = [self.add("t1"), self.remove("t2")]
        self.assertIsNone(rules.ejection(self.ejected_pr(), nodes, "t3", None))

    def test_ejection_requeued_handled(self):
        nodes = [self.add("t1"), self.remove("t2")]
        self.assertIsNone(rules.ejection(self.ejected_pr(), nodes, "t0", "t2"))

    def test_ejection_no_suites(self):
        nodes = [self.add("t1"), self.remove("t2")]
        self.assertEqual(rules.ejection(self.ejected_pr(), nodes, None, None), nodes[1])

    def test_ejection_queued_or_automerge(self):
        nodes = [self.add("t1"), self.remove("t2")]
        self.assertIsNone(rules.ejection(self.ejected_pr(isInMergeQueue=True), nodes, "t0", None))
        self.assertIsNone(rules.ejection(self.ejected_pr(autoMergeRequest={"enabledBy": {}}), nodes, "t0", None))

    def test_ejection_last_node_must_be_a_removal(self):
        nodes = [self.add("t1"), self.remove("t2"), self.add("t3")]
        self.assertIsNone(rules.ejection(self.ejected_pr(), nodes, "t0", None))

    def test_may_requeue_once_per_head(self):
        nodes = [self.add("t1"), self.remove("t2"), self.add("t3"), self.remove("t4")]
        self.assertFalse(rules.may_requeue(nodes, nodes[3], "t0"))
        self.assertTrue(rules.may_requeue(nodes, nodes[3], "t3"))  # t2 belongs to an earlier head

    def test_queue_deadline(self):
        self.assertEqual(rules.queue_deadline(100, 200, True, 60), 1160)
        self.assertEqual(rules.queue_deadline(100, 200, True, None), 3700)
        self.assertEqual(rules.queue_deadline(100, 200, True, -1), 3700)
        self.assertEqual(rules.queue_deadline(100, 200, False, None), 400)

    def test_rerun_choice(self):
        def run(id, attempt, **over):
            r = {"databaseId": id, "attempt": attempt, "conclusion": "cancelled", "name": "CI", "event": "pull_request", "headSha": SHA}
            r.update(over)
            return r

        def check(state="CANCELLED"):
            return {"bucket": "cancel", "state": state, "workflow": "CI"}

        self.assertEqual(rules.rerun_choice([check("FAILURE")], [run(11, 1)], SHA, 0), ("repair", []))
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1)], SHA, 0), ("rerun", [11]))
        self.assertEqual(rules.rerun_choice([check()], [run(11, 2)], SHA, 1), ("infra-rerun", [11]))
        self.assertEqual(rules.rerun_choice([check()], [run(11, 3)], SHA, 1)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run(11, 2)], SHA, 0)[0], "infra-rerun")  # attempt 2 after no rerun counted
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1, name="Other")], SHA, 0)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1, headSha="a" * 40)], SHA, 0)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1, event="push")], SHA, 0)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1, conclusion="success")], SHA, 0)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run("x1", 1)], SHA, 0)[0], "stop")
        self.assertEqual(rules.rerun_choice([check()], [run(11, 1)], SHA, 2)[0], "stop")

    def test_reread_order_push_and_ejection(self):
        other = "b" * 40
        self.assertEqual(rules.reread_outcome({"state": "OPEN", "headRefOid": other}, [], SHA, True), "new-head")
        self.assertEqual(rules.reread_outcome({"state": "MERGED", "headRefOid": other}, [], SHA, True), "merged")
        self.assertEqual(rules.reread_outcome({"state": "CLOSED", "headRefOid": SHA}, [], SHA, False), "closed")
        self.assertEqual(rules.reread_outcome({"state": "OPEN", "headRefOid": SHA}, [{"bucket": "cancel"}], SHA, True), "failed")
        self.assertEqual(rules.reread_outcome({"state": "OPEN", "headRefOid": SHA}, [], SHA, True), "ejected")
        self.assertEqual(rules.reread_outcome({"state": "OPEN", "headRefOid": SHA}, [{"bucket": "pass"}], SHA, False), "continue")

    def test_in_queue_watch(self):
        pr = {"state": "OPEN", "mergeStateStatus": "CLEAN", "isInMergeQueue": True}
        self.assertTrue(rules.in_queue_watch(pr, [{"bucket": "pass"}]))
        self.assertFalse(rules.in_queue_watch(pr, [{"bucket": "pending"}]))
        self.assertFalse(rules.in_queue_watch({**pr, "mergeStateStatus": "DIRTY"}, []))
        self.assertTrue(rules.in_queue_watch({**pr, "mergeStateStatus": "BEHIND"}, []))
        armed = {"state": "OPEN", "mergeStateStatus": "CLEAN", "isInMergeQueue": False, "autoMergeRequest": {}, "reviewDecision": None}
        self.assertTrue(rules.in_queue_watch(armed, []))
        self.assertFalse(rules.in_queue_watch({**armed, "mergeStateStatus": "BEHIND"}, []))
        self.assertFalse(rules.in_queue_watch({**armed, "reviewDecision": "CHANGES_REQUESTED"}, []))
        self.assertFalse(rules.in_queue_watch({**armed, "autoMergeRequest": None}, []))

    def test_open_outcome_order(self):
        def pr(**over):
            base = {"mergeStateStatus": "CLEAN", "reviewDecision": None, "isInMergeQueue": False, "autoMergeRequest": {}}
            base.update(over)
            return base

        out = rules.open_outcome
        self.assertEqual(out(pr(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="DIRTY"), [], "on"), "review-required")
        self.assertEqual(out(pr(mergeStateStatus="DIRTY", isInMergeQueue=True), [], "on"), "dirty-queued")
        self.assertEqual(out(pr(mergeStateStatus="BEHIND"), [], "on"), "rebase")
        self.assertEqual(out(pr(mergeStateStatus="DIRTY"), [], "on"), "rebase")
        self.assertEqual(out(pr(), [{"bucket": "pending"}], "on"), "pending")
        self.assertEqual(out(pr(autoMergeRequest=None), [], "off-by-run"), "resumable-off-by-run")
        self.assertEqual(out(pr(autoMergeRequest=None), [], "off"), "turned-off")
        with self.assertRaises(rules.RuleError):  # unreachable by design: never a silent pass
            out(pr(), [], "on")

    def test_decide_guard(self):
        pr = {"isDraft": True, "isInMergeQueue": False, "autoMergeRequest": None}
        self.assertEqual(rules.decide(pr, [{"bucket": "fail"}], "off-by-run"), "guard")
        self.assertEqual(rules.decide(pr, [{"bucket": "pass"}], "off-by-run"), "ready")
        self.assertEqual(rules.decide({**pr, "isDraft": False}, [], "off"), "enable")
        self.assertEqual(rules.decide({**pr, "isDraft": False, "autoMergeRequest": {}}, [], "on"), "keep")
        self.assertEqual(rules.decide({**pr, "autoMergeRequest": {}}, [], "on"), "ready")
        self.assertEqual(rules.decide({**pr, "isDraft": False, "isInMergeQueue": True}, [], "on"), "keep-queue")

    def test_status_line(self):
        state = {"pr": 7, "automerge": "off-by-run", "repairs": 1, "rerun": 0, "infra": ["npm-flake", "dns"], "deadline": NOW}
        pr = {"headRefOid": SHA, "isInMergeQueue": True, "mergeQueueEntry": {"position": 2}}
        checks = [{"bucket": "pass", "name": "`$(x)`"}, {"bucket": "pass"}, {"bucket": "fail"}, {"bucket": "evil\nbucket"}]
        self.assertEqual(
            rules.status_line(state, pr, checks),
            f"#7 head c5bf4f3 · checks pass 2, fail 1 · auto-merge off by this run · queue 2 · repairs 1/3 · rerun 0 · infra npm-flake,dns · deadline {NOW}",
        )
        state.update(automerge="on", infra=[])
        pr = {"headRefOid": SHA, "isInMergeQueue": False}
        self.assertEqual(
            rules.status_line(state, pr, []),
            f"#7 head c5bf4f3 · checks - · auto-merge on · queue no · repairs 1/3 · rerun 0 · infra - · deadline {NOW}",
        )

    def test_resumable_errors(self):
        merge = ["gh", "pr", "merge", "7", "--auto", "--squash"]
        for err in ("HTTP 502", "HTTP 503: Service Unavailable", "You have exceeded a secondary rate limit", "GraphQL: timeout",
                    "dial tcp: i/o timeout", "connection reset by peer", "connection refused", "no such host",
                    "could not resolve host: api.github.com", "TLS handshake timeout", "unexpected EOF"):
            self.assertTrue(rules.is_resumable_gh_error(merge, err), err)
        self.assertFalse(rules.is_resumable_gh_error(["gh", "pr", "merge", "7", "--disable-auto"], "secondary rate limit"))
        self.assertFalse(rules.is_resumable_gh_error(["gh", "run", "rerun", "5"], "HTTP 502"))
        for err in ("HTTP 404", "HTTP 422: nope", "HTTP 5000", "bad flag"):
            self.assertFalse(rules.is_resumable_gh_error(merge, err), err)


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
            self.assertFalse(os.path.exists(self.state_file()))
        self.assertEqual(len(codes), len(cases) + 1)

    def test_rejected_start_ends_live_state(self):
        self.main("start", "--model", "X")
        self.replies["gh pr view 7"] = pr_view(isCrossRepository=True)
        self.assertEqual(self.main("start", "--model", "X")[1]["action"], "stop")
        self.assertTrue(sh.load_state(7)["ended"])
        lock = os.path.join(self.git_dir, "kitchen-sink", "shepherd", "7.lock")
        self.assertEqual(os.stat(lock).st_mode & 0o777, 0o600)

    def test_tool_errors_print_one_json_object(self):
        cases = {
            "non-json gh": {"gh pr view 7": "not json"},
            "git config failure": {"git config --local --get": (128, "", "fatal")},
            "missing gh": {"gh api user": FileNotFoundError("gh")},
        }
        for name, replies in cases.items():
            with self.subTest(name):
                self.reset_replies()
                self.replies.update(replies)
                code, out = self.main("start", "--model", "X")
                self.assertEqual((code, out["code"]), (2, "CMD_FAILED"))
                self.assertFalse(os.path.exists(self.state_file()))

    def test_lock_busy(self):
        self.assertEqual(self.main("start", "--model", "X")[1], {"action": "next"})
        before = self.read_state_bytes()
        with sh.locked(7):
            code, out = self.main("start", "--model", "X")
        self.assertEqual((code, out), (0, {"action": "busy"}))
        self.assertEqual(self.read_state_bytes(), before)


if __name__ == "__main__":
    unittest.main()
