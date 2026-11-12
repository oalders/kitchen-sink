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
import sys
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
        self.calls, self.clock = [], NOW
        for target, name, fake in (
            (sh, "run", self.fake_run),
            (sh.time, "time", lambda: self.clock),
            (sh.time, "sleep", self.fake_sleep),
        ):
            p = mock.patch.object(target, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def fake_sleep(self, seconds):
        self.calls.append(f"sleep {seconds}")
        self.clock += seconds

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
        self.calls.append(line)
        key = max((k for k in self.replies if line.startswith(k)), key=len, default=None)
        self.assertIsNotNone(key, f"unexpected command: {line}")
        reply = self.replies[key]
        if isinstance(reply, list):  # a sequence: one reply per call, the last one repeats
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if callable(reply):  # sees the command, e.g. to read a file the script deletes afterwards
            reply = reply(cmd)
        if isinstance(reply, Exception):
            raise reply
        rc, out, err = reply if isinstance(reply, tuple) else (0, reply, "")
        if check and rc != 0:
            raise sh.GhError(cmd, rc, err)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def main(self, *argv):
        code, out = self.main_raw(*argv)
        return code, json.loads(out)

    def main_raw(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sh.main(list(argv))
        return code, buf.getvalue()

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


class TestRun(unittest.TestCase):
    """The real `run`: every call has a timeout, capped by the process's hard end."""

    def test_timeout_is_a_resumable_gh_error(self):
        cmd = ["gh", "pr", "view", "7"]
        with mock.patch.object(sh.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd, 60)) as fake, \
                mock.patch.object(sh, "hard_end", None):  # fmt: skip
            with self.assertRaises(sh.GhError) as caught:
                sh.run(cmd)
        self.assertEqual(fake.call_args.kwargs["timeout"], sh.CALL_TIMEOUT)
        self.assertTrue(rules.is_resumable_gh_error(cmd, caught.exception.stderr))

    def test_timeout_capped_by_hard_end(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(sh.subprocess, "run", return_value=ok) as fake, \
                mock.patch.object(sh.time, "time", return_value=NOW), mock.patch.object(sh, "hard_end", NOW + 5):  # fmt: skip
            sh.run(["gh"])
            self.assertEqual(fake.call_args.kwargs["timeout"], 5)
            with mock.patch.object(sh, "hard_end", NOW), self.assertRaises(sh.GhError):
                sh.run(["gh"])  # past the hard end: no call at all
        self.assertEqual(fake.call_count, 1)


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


OTHER = "b" * 40
THIRD = "d" * 40
CODEX_MODE = " ".join([sys.executable, sh.CODEX_LOOP, "mode"])


def pr_full(**over):
    pr = {
        "number": 7, "title": "t", "state": "OPEN", "createdAt": "2026-11-12T00:00:00Z", "isDraft": False,
        "isCrossRepository": False, "author": {"login": "me"}, "baseRefName": "main", "headRefName": "fix-174",
        "headRefOid": SHA, "autoMergeRequest": {"enabledBy": {"login": "me"}}, "mergeStateStatus": "CLEAN",
        "reviewDecision": None,
    }  # fmt: skip
    pr.update(over)
    return json.dumps(pr)


def queue(nodes=(), queued=False):
    pull = {"isInMergeQueue": queued, "mergeQueueEntry": None, "timelineItems": {"nodes": list(nodes)}}
    return json.dumps({"data": {"repository": {"pullRequest": pull}}})


class NextBase(Env):
    """A live run on PR 7 at gated head SHA; the later steps (Tasks 4-6) are stubs, and `watch` ends each pass."""

    def setUp(self):
        super().setUp()
        self.reset_next_replies()
        p = mock.patch.object(sh, "watch", side_effect=lambda *a: {"action": "next"})
        p.start()
        self.addCleanup(p.stop)

    def reset_next_replies(self):
        self.reset_replies()
        self.replies.update(
            {
                "gh pr view 7": pr_full(),
                "gh pr view 7 --json body": "",
                "gh pr checks 7": "[]",
                "gh api graphql": queue(),
                "gh api --paginate repos/o/r/commits/": "",
                "git rev-parse HEAD": SHA + "\n",
                "git rev-parse --git-path rebase-merge": os.path.join(self.git_dir, "rebase-merge"),
                "git rev-parse --git-path rebase-apply": os.path.join(self.git_dir, "rebase-apply"),
                "git fetch origin": "",
                "git merge-base --is-ancestor HEAD ": "",  # local HEAD is on the PR's head; any other ancestry is unexpected
                "git status --porcelain --untracked-files=no": "",
                CODEX_MODE: json.dumps({"mode": "off"}),
            }
        )

    def live(self, **over):
        state = {
            "pr": 7, "branch": "fix-174", "owner": "o", "repo": "r", "default": "main", "model": "X",
            "deadline": NOW + 3600, "gated_head": SHA, "codex_passed": [], "automerge": "on", "repairs": 0,
            "rerun": 0, "infra": [], "requeued": None, "wait_first": False, "pending": None, "ended": False,
            "evidence_dir": None,
        }  # fmt: skip
        state.update(over)
        sh.save_state(7, state)
        return state

    def repair(self, cause="checks", head=SHA):
        return {"action": "repair", "cause": cause, "head": head, "branch": "fix-174", "default": "main", "codex_mode": "off"}

    def assert_stop(self, out, code):
        self.assertEqual((out["action"], out["terminal"], out["code"]), ("stop", True, code))
        self.assertTrue(sh.load_state(7) is None or sh.load_state(7)["ended"])

    def report(self, out):
        with open(out["report"]) as f:
            return f.read()


class Next(NextBase):
    def test_next_missing_or_ended(self):
        self.assert_stop(self.main("next")[1], "STOP_NO_RUN")
        self.live(ended=True)
        self.assert_stop(self.main("next")[1], "STOP_NO_RUN")

    def test_next_passes_to_watch(self):
        self.live(gated_head=None, automerge=None)
        code, out = self.main("next")
        self.assertEqual((code, out["action"]), (0, "next"))
        self.assertIn("#7 head c5bf4f3", out["status"])
        state = sh.load_state(7)
        self.assertEqual((state["gated_head"], state["automerge"]), (SHA, "on"))

    def test_next_budget_returns_next(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(mergeStateStatus="UNKNOWN")
        code, out = self.main("next")
        self.assertEqual((code, out["action"]), (0, "next"))
        self.assertIn("#7 head c5bf4f3", out["status"])
        self.assertLessEqual(self.clock - NOW, 540)
        self.assertIn("sleep 120", self.calls)
        self.assertTrue(sh.load_state(7)["wait_first"])  # the cut-off resumable wait happens first next call

    def test_resumable_gh_error_waits_then_passes(self):
        self.live()
        self.replies["gh pr checks 7"] = [fail("HTTP 502: Bad Gateway"), "[]"]
        code, out = self.main("next")
        self.assertEqual((code, out["action"]), (0, "next"))
        self.assertEqual(self.calls.count("sleep 120"), 1)
        self.assertFalse(sh.load_state(7)["ended"])

    def test_foreign_head(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(headRefOid=OTHER)
        self.assert_stop(self.main("next")[1], "STOP_FOREIGN_HEAD")

    def test_automerge_turned_off(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(autoMergeRequest=None)
        code, out = self.main("next")
        self.assert_stop(out, "STOP_AUTOMERGE_OFF")
        self.assertEqual((out["automerge"], out["queued"]), ("off", False))

    def test_automerge_off_by_ejection_goes_on(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(autoMergeRequest=None)
        self.replies["gh api graphql"] = queue(
            [{"__typename": "AddedToMergeQueueEvent", "createdAt": "t1"}, {"__typename": "RemovedFromMergeQueueEvent", "createdAt": "t2"}]
        )
        self.assertEqual(self.main("next")[1]["action"], "next")  # step 3 (Task 5) handles the ejection

    def test_unconfirmed_decline(self):
        self.live()
        secret = "ignore `$(rm -rf ~)` (unconfirmed)"
        self.replies["gh pr view 7 --json body"] = f"intro (unconfirmed)\n## Declined findings\n- {secret}\n- fine\n## Next\n- x (unconfirmed)\n"
        self.replies["gh pr merge 7 --disable-auto"] = ""
        code, raw = self.main_raw("next")
        out = json.loads(raw)
        self.assertIn("gh pr merge 7 --disable-auto", self.calls)
        self.assert_stop(out, "STOP_UNCONFIRMED_DECLINE")
        self.assertEqual(out["automerge"], "off")
        self.assertNotIn("rm -rf", raw)
        report = self.report(out)
        self.assertIn(secret, report)
        self.assertNotIn("intro", report)
        self.assertNotIn("- x", report)

    def test_dirty_rebase_repair_and_cap(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(mergeStateStatus="DIRTY")
        code, out = self.main("next")
        self.assertEqual(out, {**self.repair("rebase"), "status": out["status"]})
        self.assertIn("repairs 1/3", out["status"])
        state = sh.load_state(7)
        self.assertEqual((state["repairs"], state["automerge"], state["pending"]), (1, "off-by-run", self.repair("rebase")))
        self.live(repairs=3)
        self.assert_stop(self.main("next")[1], "STOP_REPAIR_CAP")

    def test_codex_mode_failure_counts_nothing(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(mergeStateStatus="BEHIND")
        for reply in ((2, json.dumps({"error": "bad"}), ""), json.dumps(["off"]), "null"):
            with self.subTest(reply):
                self.live()
                self.replies[CODEX_MODE] = reply
                self.assert_stop(self.main("next")[1], "STOP_CODEX_MODE")
                self.assertEqual(sh.load_state(7)["repairs"], 0)

    def test_pending_repair_reissued(self):
        evidence = tempfile.mkdtemp(prefix=sh.EVIDENCE_PREFIX)
        self.addCleanup(lambda: os.path.isdir(evidence) and os.rmdir(evidence))
        pending = {**self.repair(), "evidence_dir": evidence}
        self.live(repairs=1, pending=pending, evidence_dir=evidence)
        code, out = self.main("next")
        self.assertEqual(out, {**pending, "status": out["status"]})
        self.assertEqual(sh.load_state(7)["repairs"], 1)
        self.assertTrue(os.path.isdir(evidence))  # the re-issued repair still reads it

    def test_reissue_while_armed_then_resumable_goes_on(self):
        self.live(repairs=1, automerge="off-by-run", pending=self.repair())
        out = self.main("next")[1]  # the PR is still armed: the skill never got to --disable-auto
        self.assertEqual(out["action"], "repair")
        self.assertIn("auto-merge off by this run", out["status"])
        self.assertEqual(sh.load_state(7)["automerge"], "off-by-run")
        self.main("record", "repair-stopped", "--resumable")
        self.replies["gh pr view 7"] = pr_full(autoMergeRequest=None)  # the skill disabled it, then stopped
        self.assertEqual(self.main("next")[1]["action"], "next")

    def test_pending_repair_not_reissued_past_step1(self):
        cases = {
            "merged": ({"gh pr view 7": pr_full(state="MERGED")}, "done"),
            "closed": ({"gh pr view 7": pr_full(state="CLOSED")}, "STOP_CLOSED"),
            "declined": ({"gh pr view 7 --json body": "## Declined findings\n- a (unconfirmed)\n", "gh pr merge 7 --disable-auto": ""}, "STOP_UNCONFIRMED_DECLINE"),
        }
        for name, (replies, want) in cases.items():
            with self.subTest(name):
                self.reset_next_replies()
                self.replies.update(replies)
                self.live(automerge="off-by-run", pending=self.repair())
                out = self.main("next")[1]
                if want == "done":
                    self.assertEqual(out["action"], "done")
                else:
                    self.assert_stop(out, want)

    def test_pending_rebase_adopted(self):
        self.live(repairs=1, rerun=1, infra=["flaky"], automerge="off-by-run", pending=self.repair("rebase"))
        self.replies["gh pr view 7"] = pr_full(headRefOid=OTHER, autoMergeRequest=None)
        self.replies["git rev-parse HEAD"] = OTHER + "\n"
        self.replies[f"git merge-base --is-ancestor {SHA} {OTHER}"] = fail("")  # a rebase: OTHER doesn't descend from SHA
        code, out = self.main("next")
        self.assertEqual(out["action"], "next")
        state = sh.load_state(7)
        self.assertEqual(
            (state["gated_head"], state["rerun"], state["infra"], state["automerge"], state["pending"], state["repairs"]),
            (OTHER, 0, [], "off-by-run", None, 1),
        )

    def test_pending_repair_other_head_is_foreign(self):
        self.live(pending=self.repair())
        self.replies["gh pr view 7"] = pr_full(headRefOid=OTHER)
        self.assert_stop(self.main("next")[1], "STOP_FOREIGN_HEAD")

    def test_pending_local_work(self):
        rebase_dir = os.path.join(self.git_dir, "rebase-merge")
        cases = {
            "rebase": lambda: os.mkdir(rebase_dir),
            "local commits": lambda: self.replies.update({"git merge-base --is-ancestor HEAD ": fail("")}),
            "dirty tree": lambda: self.replies.update({"git status --porcelain --untracked-files=no": " M x\n"}),
            "fetch timed out": lambda: self.replies.update({"git fetch origin": sh.GhError(["git"], "timeout", "timed out")}),
        }
        for name, setup in cases.items():
            with self.subTest(name):
                self.assert_local_work_stops(setup, "STOP_FETCH_FAILED" if name.startswith("fetch") else "STOP_LOCAL_WORK")
                if os.path.isdir(rebase_dir):
                    os.rmdir(rebase_dir)

    def assert_local_work_stops(self, setup, code):
        self.reset_next_replies()
        self.live(pending=self.repair())
        setup()
        self.assert_stop(self.main("next")[1], code)

    def test_pending_ready_still_draft(self):
        self.live(pending={"action": "ready", "pr": 7})
        self.replies["gh pr view 7"] = pr_full(isDraft=True)
        code, out = self.main("next")
        self.assert_stop(out, "STOP_READY_FAILED")

    def test_pending_ready_done_goes_on(self):
        self.live(pending={"action": "ready", "pr": 7})
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertIsNone(sh.load_state(7)["pending"])

    def test_record_repair_pushed(self):
        self.live(repairs=1, rerun=1, pending=self.repair())
        self.replies["gh pr view 7"] = pr_full(headRefOid=OTHER)
        self.replies["git rev-parse HEAD"] = OTHER + "\n"
        code, out = self.main("record", "repair-pushed")
        self.assertEqual(out["action"], "next")
        self.assertIn("head bbbbbbb", out["status"])
        state = sh.load_state(7)
        self.assertEqual((state["gated_head"], state["rerun"], state["pending"], state["automerge"]), (OTHER, 0, None, "off-by-run"))

    def test_record_repair_pushed_needs_new_head(self):
        self.live(rerun=1, infra=["flaky"], pending=self.repair())
        code, out = self.main("record", "repair-pushed")
        self.assert_stop(out, "STOP_NO_NEW_HEAD")
        state = sh.load_state(7)
        self.assertEqual((state["rerun"], state["infra"]), (1, ["flaky"]))  # nothing adopted

    def test_record_repair_pushed_checks_head(self):
        self.live(pending=self.repair())
        self.replies["gh pr view 7"] = pr_full(headRefOid=OTHER)
        self.replies["git rev-parse HEAD"] = THIRD + "\n"
        code, out = self.main("record", "repair-pushed")
        self.assert_stop(out, "STOP_PUSH_MISMATCH")
        self.assertEqual(sh.load_state(7)["gated_head"], SHA)

    def test_record_resumable_refunds(self):
        self.live(repairs=2, pending=self.repair())
        self.assertEqual(self.main("record", "repair-stopped", "--resumable")[1], {"action": "next"})
        state = sh.load_state(7)
        self.assertEqual((state["repairs"], state["wait_first"], state["pending"]), (1, True, None))
        self.calls.clear()
        self.assertEqual(self.main("next")[1]["action"], "next")
        first_read = next(i for i, c in enumerate(self.calls) if c.startswith("gh pr view 7"))
        self.assertLess(self.calls.index("sleep 120"), first_read)

    def test_record_terminal_reports_reruns(self):
        self.live(pending=self.repair("checks"))
        self.replies["gh run list --commit " + SHA] = json.dumps(
            [{"databaseId": 11, "conclusion": "failure"}, {"databaseId": 12, "conclusion": "success"}, {"databaseId": "x;y", "conclusion": "failure"}]
        )
        code, out = self.main("record", "repair-stopped", "--terminal")
        self.assert_stop(out, "STOP_REPAIR_STOPPED")
        self.assertEqual((out["automerge"], out["queued"]), ("on", False))
        report = self.report(out)
        self.assertIn("gh run rerun 11", report)
        self.assertNotIn("gh run rerun 12", report)
        self.assertNotIn("x;y", report)

    def test_record_terminal_ends_run_when_git_fails(self):
        self.live(pending=self.repair("checks"))
        self.replies["git rev-parse HEAD"] = (128, "", "fatal: not a git repository")
        self.replies["gh pr view 7"] = sh.GhError(["gh"], 1, "HTTP 404")
        self.assert_stop(self.main("record", "repair-stopped", "--terminal")[1], "STOP_REPAIR_STOPPED")

    def test_tool_error_in_next_ends_run(self):
        self.live()
        self.replies["gh api graphql"] = "not json"
        code, out = self.main("next")
        self.assertEqual((code, out["code"]), (2, "CMD_FAILED"))
        self.assertTrue(sh.load_state(7)["ended"])

    def test_codex_mode_timeout_counts_nothing(self):
        self.live()
        self.replies["gh pr view 7"] = pr_full(mergeStateStatus="DIRTY")
        self.replies[CODEX_MODE] = sh.GhError(["python3"], "timeout", "timed out")
        self.assert_stop(self.main("next")[1], "STOP_CODEX_MODE")
        self.assertEqual(sh.load_state(7)["repairs"], 0)

    def test_gh_timeout_is_resumable(self):
        self.live()
        self.replies["gh pr checks 7"] = [sh.GhError(["gh", "pr", "checks"], "timeout", "timed out"), "[]"]
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(self.calls.count("sleep 120"), 1)

    def test_record_triage(self):
        self.live(pending={"action": "triage", "evidence_dir": "/x"})
        self.assertEqual(self.main("record", "triage", "--verdict", "infra")[1], {"action": "next"})
        state = sh.load_state(7)
        self.assertEqual((state["triage_verdict"], state["pending"]), ("infra", None))

    def test_gh_stderr_not_on_stdout(self):
        self.live()
        hostile = "```$(rm -rf ~)```"
        self.replies["gh pr checks 7"] = fail(hostile)
        code, raw = self.main_raw("next")
        out = json.loads(raw)
        self.assert_stop(out, "STOP_GH_FAILED")
        self.assertNotIn("rm -rf", raw)
        self.assertIn(hostile, self.report(out))

    def test_evidence_dir_replaced(self):
        state = self.live()
        first = sh.new_evidence_dir(state)
        second = sh.new_evidence_dir(state)
        self.assertFalse(os.path.exists(first))
        self.assertTrue(os.path.isdir(second))
        self.assertEqual(state["evidence_dir"], second)
        sh.drop_evidence(state)
        self.assertFalse(os.path.exists(second))

class Codex(NextBase):
    """Step 2 in `github` mode; `gh-wait` replies are sequences, the last one repeating."""

    GHWAIT = " ".join([sys.executable, sh.CODEX_LOOP, "gh-wait --pr 7 --sha " + SHA])

    def setUp(self):
        super().setUp()
        self.live(model="Opus 5.5")
        self.replies[CODEX_MODE] = json.dumps({"mode": "github", "bot_wait": {"minutes": 30, "action": "stop"}})
        self.bodies = []

    def waits(self, *results):
        self.replies[self.GHWAIT] = [(0 if r["status"] == "clean" else 1, json.dumps(r), "") for r in results]

    def comments(self, *ids):
        urls = [f"https://github.com/o/r/pull/7#issuecomment-{i}\n" for i in ids]

        def post(cmd):
            with open(cmd[cmd.index("--body-file") + 1]) as f:
                self.bodies.append(f.read())
            return urls[len(self.bodies) - 1]

        self.replies["gh pr comment 7 --body-file"] = post

    def posts(self):
        return [c for c in self.calls if c.startswith("gh pr comment")]

    def gh_waits(self):
        return [c.split(f"--sha {SHA} ")[1] for c in self.calls if " gh-wait " in c]

    def timeout(self, trigger=None, triggers=0, ack=False, action="stop"):
        return {"status": "timeout", "trigger": trigger, "triggers": triggers, "acknowledged": ack, "action": action}

    def test_codex_mode_not_github(self):
        self.replies[CODEX_MODE] = json.dumps({"mode": "local", "bot_wait": {"minutes": 30, "action": "stop"}})
        self.assertEqual(self.main("next")[1]["action"], "next")
        state = sh.load_state(7)
        self.assertEqual(state["codex_passed"], [SHA])
        self.assertEqual(state["codex"]["note"], "Codex gate not checked (mode `local`)")
        self.assertEqual(self.gh_waits(), [])

    def test_codex_clean(self):
        self.waits({"status": "clean"})
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(self.gh_waits(), [f"--timeout 0 --interval 15"])
        self.assertEqual(sh.load_state(7)["codex_passed"], [SHA])
        self.assertEqual(self.posts(), [])
        self.main("next")  # a head that passed isn't gated again
        self.assertEqual(len(self.gh_waits()), 1)

    def test_codex_trigger_posted_once(self):
        self.comments(555)
        self.waits(self.timeout(), {"status": "clean"})
        self.main("next")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(
            self.bodies, [f"@codex review\n\nReview of {SHA}\n\n🤖 Review by [Claude Code](https://claude.com/claude-code) · Opus 5.5"]
        )
        self.assertEqual(self.gh_waits()[1], f"--timeout {540 - sh.GH_WAIT_MARGIN} --interval 15 --trigger-comment 555 --windows 1")
        self.assertEqual(sh.load_state(7)["codex_passed"], [SHA])

    def test_codex_wait_sliced(self):
        self.comments(555)
        self.waits(self.timeout(), {"status": "pending", "acknowledged": False, "window_ends": "2026-11-12T10:00:00Z"}, {"status": "clean"})
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(sh.load_state(7)["codex_passed"], [])
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(sh.load_state(7)["codex_passed"], [SHA])
        self.assertEqual(len(self.posts()), 1)
        self.assertIn("--trigger-comment 555", self.gh_waits()[2])
        self.assertEqual(len(self.gh_waits()), 3)

    def test_codex_wait_needs_room(self):
        self.comments(555)
        check = (1, json.dumps(self.timeout()), "")

        def late(cmd):  # the check and the trigger take most of the budget
            self.clock += 520
            return check

        self.replies[self.GHWAIT] = late
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(len(self.gh_waits()), 1)  # no room for a wait
        self.assertEqual(sh.load_state(7)["codex"]["trigger"], "555")

    def test_codex_proceed_acknowledged(self):
        self.replies[CODEX_MODE] = json.dumps({"mode": "github", "bot_wait": {"minutes": 30, "action": "proceed"}})
        self.comments(555)
        self.waits(self.timeout(), self.timeout(555, 1, True, "proceed"), self.timeout(555, 1, True, "proceed"))
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(len([w for w in self.gh_waits() if "--windows 2" in w]), 1)
        self.assertEqual(len(self.gh_waits()), 3)
        state = sh.load_state(7)
        self.assertEqual(state["codex_passed"], [SHA])
        self.assertEqual(state["codex"]["note"], "Codex gate: no review within 60 min; passed by codexTimeoutAction=proceed")

    def test_codex_proceed_unacknowledged_passes(self):
        self.comments(555)
        self.waits(self.timeout(), self.timeout(555, 1, False, "proceed"))
        self.main("next")
        self.assertEqual(len(self.gh_waits()), 2)
        self.assertEqual(sh.load_state(7)["codex_passed"], [SHA])

    def test_codex_stop_retrigger(self):
        self.comments(555, 556)
        self.waits(self.timeout(), self.timeout(555, 1), self.timeout(556, 2))
        out = self.main("next")[1]
        self.assert_stop(out, "STOP_CODEX_TIMEOUT")
        self.assertEqual(len(self.posts()), 2)  # never a third
        self.assertIn("--trigger-comment 556 --windows 1", self.gh_waits()[2])
        self.assertEqual(len(self.gh_waits()), 3)
        self.assertEqual(sh.load_state(7)["codex_passed"], [])

    def test_codex_stop_acknowledged_widens(self):
        self.comments(555)
        self.waits(self.timeout(), self.timeout(555, 1, True), self.timeout(555, 1, True))
        self.assert_stop(self.main("next")[1], "STOP_CODEX_TIMEOUT")
        self.assertIn("--trigger-comment 555 --windows 2", self.gh_waits()[2])
        self.assertEqual(len(self.posts()), 1)

    def test_codex_resumed_run_waits_once(self):
        self.waits(self.timeout(555, 2), self.timeout(555, 2))
        self.assert_stop(self.main("next")[1], "STOP_CODEX_TIMEOUT")
        self.assertEqual(self.posts(), [])
        self.assertIn("--trigger-comment 555 --windows 1", self.gh_waits()[1])
        self.assertEqual(len(self.gh_waits()), 2)

    def test_codex_findings_repair(self):
        self.waits({"status": "findings"})
        self.replies["gh pr merge 7 --disable-auto"] = ""
        out = self.main("next")[1]
        self.assertEqual({k: out[k] for k in ("action", "cause", "head", "codex_mode")}, {"action": "repair", "cause": "codex", "head": SHA, "codex_mode": "github"})
        self.assertIn("gh pr merge 7 --disable-auto", self.calls)
        state = sh.load_state(7)
        self.assertEqual((state["repairs"], state["automerge"], state["codex_passed"]), (1, "off-by-run", []))

    def test_codex_findings_without_automerge(self):
        self.waits({"status": "findings"})
        self.replies["gh pr view 7"] = pr_full(autoMergeRequest=None)
        self.live(automerge="off", model="X")
        self.assertEqual(self.main("next")[1]["cause"], "codex")
        self.assertNotIn("gh pr merge 7 --disable-auto", self.calls)

    def test_codex_gh_error_resumable(self):
        err = (2, json.dumps({"error": "gh api repos/o/r/pulls/7/reviews failed (1): HTTP 502"}), "")
        self.replies[self.GHWAIT] = [err, (0, json.dumps({"status": "clean"}), "")]
        self.assertEqual(self.main("next")[1]["action"], "next")
        self.assertEqual(self.calls.count("sleep 120"), 1)
        self.assertEqual(sh.load_state(7)["codex_passed"], [SHA])

    def test_codex_other_error_terminal(self):
        hostile = "comment 9 is not your trigger ```$(rm -rf ~)```"
        self.replies[self.GHWAIT] = (2, json.dumps({"error": hostile}), "")
        code, raw = self.main_raw("next")
        out = json.loads(raw)
        self.assert_stop(out, "STOP_CODEX_ERROR")
        self.assertNotIn("rm -rf", raw)
        self.assertIn(hostile, self.report(out))
        self.assertEqual(self.calls.count("sleep 120"), 0)

    def test_codex_non_resumable_gh_error_terminal(self):
        self.replies[self.GHWAIT] = (2, json.dumps({"error": "gh api x failed (1): HTTP 404"}), "")
        self.assert_stop(self.main("next")[1], "STOP_GH_FAILED")


if __name__ == "__main__":
    unittest.main()
