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

    def entry(self, name, match):
        self.add(name, "match", match)

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

    def test_valid_entries(self):
        # Config order, not alphabetical: review-config relies on new entries listing last.
        self.entry("zeta", "bundle .* is missing")
        self.entry("alpha", "no evidence")
        rc, out = self.main(["list"])
        self.assertEqual(rc, 0)
        self.assertEqual(
            out["entries"],
            [{"name": "zeta", "match": "bundle .* is missing"}, {"name": "alpha", "match": "no evidence"}],
        )

    def assertInvalid(self, fragment):
        rc, out = self.main(["list"])
        self.assertEqual(rc, 2)
        [entry] = out["entries"]
        self.assertIn(fragment, entry["error"])

    def test_bad_names(self):
        self.entry("ci_bundle", "x")
        self.entry("-lead", "x")
        self.entry("a.b", "x")
        rc, out = self.main(["list"])
        self.assertEqual(rc, 2)
        self.assertEqual([e["name"] for e in out["entries"]], ["ci_bundle", "-lead", "a.b"])
        for entry in out["entries"]:
            self.assertIn("bad name", entry["error"])

    def test_trailing_newline_name(self):
        # git config can't store this name today; validate must not rely on that.
        self.assertIn("bad name", cr.validate("a\n", {"match": ["x"]}))

    def test_bare_key(self):
        path = self.write("bare", '[kitchen-sink "remediation.a"]\n\tmatch\n')
        rc, out = self.main(["list", "--file", path])
        self.assertEqual(rc, 2)
        [entry] = out["entries"]
        self.assertIn("empty value", entry["error"])

    def test_empty_match(self):
        self.entry("m", "")
        self.assertInvalid("empty value")

    def test_duplicate_match(self):
        self.entry("a", "x")
        self.add("a", "match", "y")
        self.assertInvalid("exactly one match")

    def test_unknown_field(self):
        # A leftover key is flagged, not silently ignored.
        self.entry("a", "x")
        self.add("a", "run", "make it")
        self.assertInvalid("unknown field 'run'")

    def test_bad_regex(self):
        self.entry("a", "(")
        self.assertInvalid("bad match regex")

    def test_empty_log_match(self):
        self.entry("caret", "^")
        self.entry("star", "x*")
        rc, out = self.main(["list"])
        self.assertEqual(rc, 2)
        self.assertEqual([e["name"] for e in out["entries"]], ["caret", "star"])
        for entry in out["entries"]:
            self.assertIn("must not match an empty log", entry["error"])

    def test_file_option_reads_scratch_config(self):
        scratch = os.path.join(self.dir, "scratch")
        self.add("a", "match", "x", scope=("--file", scratch))
        self.entry("b", "(")  # invalid --local entry is not read
        rc, out = self.main(["list", "--file", scratch])
        self.assertEqual(rc, 0)
        self.assertEqual([e["name"] for e in out["entries"]], ["a"])


class MatchLogs(RepoTest):
    def match(self, *logs):
        argv = ["match"]
        for i, text in enumerate(logs):
            argv += ["--log", self.write(f"log{i}", text)]
        return self.main(argv)

    def test_invalid_entry_fails_lookup(self):
        self.entry("good", "boom")
        self.entry("bad", "(")
        rc, out = self.match("boom")
        self.assertEqual((rc, out["status"]), (2, "invalid"))

    def test_no_entries_is_none(self):
        self.assertEqual(self.match("boom"), (1, {"status": "none"}))

    def test_first_entry_in_config_order_wins(self):
        self.entry("zeta", "^boom$")
        self.entry("alpha", "boom")
        self.assertEqual(self.match("a\nboom\nb"), (0, {"status": "match", "name": "zeta"}))

    def test_entry_covering_every_log_wins(self):
        self.entry("z-narrow", "boom")
        self.entry("a-wide", "boom|bang")
        self.assertEqual(self.match("boom", "bang"), (0, {"status": "match", "name": "a-wide"}))

    def test_no_entry_covers_every_log_is_none(self):
        self.entry("a", "boom")
        self.entry("b", "bang")
        self.assertEqual(self.match("boom", "bang"), (1, {"status": "none"}))

    def test_unmatched_log_is_none(self):
        self.entry("a", "boom")
        self.assertEqual(self.match("boom", "other"), (1, {"status": "none"}))

    def test_unreadable_log_is_error(self):
        self.entry("a", "boom")
        rc, out = self.main(["match", "--log", os.path.join(self.dir, "missing")])
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", out["error"])


if __name__ == "__main__":
    unittest.main()
