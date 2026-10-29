#!/usr/bin/env python3
"""Tests for ci_remediation.py, against real git config in a scratch repo.

Run: python3 skills/shepherd-pr-repair/test_ci_remediation.py
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest

_MOD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_remediation.py")
_spec = importlib.util.spec_from_file_location("ci_remediation", _MOD_PATH)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


class RepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self._cwd = os.getcwd()
        subprocess.run(["git", "init", "-q", self.dir], check=True)
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def add(self, name, field, value, scope=("--local",)):
        key = f"kitchen-sink.remediation.{name}.{field}"
        subprocess.run(["git", "config", *scope, "--add", key, value], check=True)

    def entry(self, name, match, run, reads=()):
        self.add(name, "match", match)
        self.add(name, "run", run)
        for value in reads:
            self.add(name, "reads", value)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cr.main(argv)
        return rc, json.loads(out.getvalue())


class ListEntries(RepoTest):
    def test_none_set(self):
        self.assertEqual(self.main(["list"]), (0, {"entries": []}))

    def test_valid_entry_with_multi_valued_reads(self):
        self.entry("ci-bundle", "bundle .* is missing", "make rebuild", ["./Makefile", "script/ci/"])
        self.entry("evidence", "no evidence", "rerun-full")
        rc, out = self.main(["list"])
        self.assertEqual(rc, 0)
        self.assertEqual(
            out["entries"],
            [
                {"name": "ci-bundle", "match": "bundle .* is missing", "run": "make rebuild", "reads": ["Makefile", "script/ci/"]},
                {"name": "evidence", "match": "no evidence", "run": "rerun-full", "reads": []},
            ],
        )

    def assertInvalid(self, fragment):
        rc, out = self.main(["list"])
        self.assertEqual(rc, 2)
        [entry] = out["entries"]
        self.assertIn(fragment, entry["error"])

    def test_bad_name(self):
        self.entry("ci_bundle", "x", "rerun-full")
        self.assertInvalid("bad name")

    def test_missing_run(self):
        self.add("a", "match", "x")
        self.assertInvalid("exactly one run")

    def test_duplicate_match(self):
        self.entry("a", "x", "rerun-full")
        self.add("a", "match", "y")
        self.assertInvalid("exactly one match")

    def test_unknown_field(self):
        self.entry("a", "x", "make it")
        self.add("a", "read", "Makefile")
        self.assertInvalid("unknown field 'read'")

    def test_shell_run_without_reads(self):
        self.entry("a", "x", "make it")
        self.assertInvalid("needs at least one reads")

    def test_bad_reads_paths(self):
        for value in ("", "/etc/passwd", "../x", "a/../b", "a/./b"):
            with self.subTest(value=value):
                self.assertIn("bad reads path", cr.validate("a", {"match": ["x"], "run": ["make"], "reads": [value]}))

    def test_bad_regex(self):
        self.entry("a", "(", "rerun-full")
        self.assertInvalid("bad match regex")

    def test_file_option_reads_scratch_config(self):
        scratch = os.path.join(self.dir, "scratch")
        self.add("a", "match", "x", scope=("--file", scratch))
        self.add("a", "run", "rerun-full", scope=("--file", scratch))
        self.entry("b", "(", "rerun-full")  # invalid --local entry is not read
        rc, out = self.main(["list", "--file", scratch])
        self.assertEqual(rc, 0)
        self.assertEqual([e["name"] for e in out["entries"]], ["a"])


class MatchLogs(RepoTest):
    def test_invalid_entry_fails_lookup(self):
        self.entry("good", "boom", "rerun-full")
        self.entry("bad", "(", "rerun-full")
        rc, out = self.main(["match", "--log", self.write("l", "boom")])
        self.assertEqual(rc, 2)
        self.assertEqual(out["status"], "invalid")

    def test_first_entry_in_config_order_wins(self):
        self.entry("first", "^boom$", "rerun-full")
        self.entry("second", "boom", "rerun-full")
        rc, out = self.main(["match", "--log", self.write("l", "a\nboom\nb")])
        self.assertEqual((rc, out["status"], out["name"]), (0, "match", "first"))

    def test_all_logs_same_entry(self):
        self.entry("a", "boom", "rerun-full")
        logs = ["--log", self.write("l1", "boom 1"), "--log", self.write("l2", "boom 2")]
        rc, out = self.main(["match", *logs])
        self.assertEqual(rc, 0)
        self.assertEqual(out, {"status": "match", "name": "a", "run": "rerun-full", "reads": [], "blocked_by": []})

    def test_mixed_entries_is_none(self):
        self.entry("a", "boom", "rerun-full")
        self.entry("b", "bang", "rerun-full")
        rc, out = self.main(["match", "--log", self.write("l1", "boom"), "--log", self.write("l2", "bang")])
        self.assertEqual((rc, out), (1, {"status": "none", "unmatched": [], "names": ["a", "b"]}))

    def test_unmatched_log_is_none(self):
        self.entry("a", "boom", "rerun-full")
        l2 = self.write("l2", "other")
        rc, out = self.main(["match", "--log", self.write("l1", "boom"), "--log", l2])
        self.assertEqual((rc, out), (1, {"status": "none", "unmatched": [l2], "names": ["a"]}))

    def test_blocked_by(self):
        self.entry("a", "boom", "make it", ["Makefile", "script/ci/", "tools", "lib/conf/x.mk"])
        changed = {
            "./Makefile": True,  # exact, after ./ normalisation
            "GNUmakefile": True,  # sibling of a top-level reads file
            "script/ci/run": True,  # under a directory with trailing slash
            "tools/a/b": True,  # under a directory without trailing slash
            "lib/conf/y.mk": True,  # sibling of a nested reads file
            "lib/other.py": False,
            "script/cid": False,
            "toolsx": True,  # top-level sibling of "tools" read as a file
        }
        path = self.write("changed", "\n".join(changed) + "\n")
        rc, out = self.main(["match", "--log", self.write("l", "boom"), "--changed", path])
        self.assertEqual(rc, 0)
        expected = [cr.normalise(p) for p, hit in changed.items() if hit]
        self.assertEqual(out["blocked_by"], expected)

    def test_unrelated_path_not_blocked(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        path = self.write("changed", "src/app.py\nscript/other\n")
        rc, out = self.main(["match", "--log", self.write("l", "boom"), "--changed", path])
        self.assertEqual((rc, out["blocked_by"]), (0, []))


if __name__ == "__main__":
    unittest.main()
