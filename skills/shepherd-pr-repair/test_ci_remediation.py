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

    def test_bad_names(self):
        self.entry("ci_bundle", "x", "rerun-full")
        self.entry("-lead", "x", "rerun-full")
        rc, out = self.main(["list"])
        self.assertEqual((rc, len(out["entries"])), (2, 2))
        for entry in out["entries"]:
            self.assertIn("bad name", entry["error"])

    def test_trailing_newline_name(self):
        # git config can't store this name today; validate must not rely on that.
        self.assertIn("bad name", cr.validate("a\n", {"match": ["x"], "run": ["rerun-full"]}))

    def test_empty_values(self):
        self.entry("m", "", "rerun-full")
        self.entry("r", "x", "")
        rc, out = self.main(["list"])
        self.assertEqual((rc, len(out["entries"])), (2, 2))
        for entry in out["entries"]:
            self.assertIn("empty value", entry["error"])

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
        values = ("/etc/passwd", "../x", "a/../b", "a/./b", "./")
        for i, value in enumerate(values):
            self.entry(f"e{i}", "x", "make", [value])
        rc, out = self.main(["list"])
        self.assertEqual((rc, len(out["entries"])), (2, len(values)))
        for value, entry in zip(values, out["entries"]):
            with self.subTest(value=value):
                self.assertIn("bad reads path", entry["error"])

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
    def setUp(self):
        super().setUp()
        self.commit({"README": "x"})
        subprocess.run(["git", "tag", "base"], check=True)

    def commit(self, files):
        for path, target in files.items():
            os.makedirs(os.path.dirname(os.path.join(self.dir, path)) or self.dir, exist_ok=True)
            if target.startswith("->"):
                os.symlink(target[2:], os.path.join(self.dir, path))
            else:
                self.write(path, target)
        subprocess.run(["git", "add", "--", *files], check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"], check=True)

    def sha(self, rev="HEAD"):
        return subprocess.run(["git", "rev-parse", rev], check=True, capture_output=True, text=True).stdout.strip()

    def match(self, *logs, rng=None):
        argv = ["match", f"--range={rng or f'base...{self.sha()}'}"]
        for i, text in enumerate(logs):
            argv += ["--log", self.write(f"log{i}", text)]
        return self.main(argv)

    def test_invalid_entry_fails_lookup(self):
        self.entry("good", "boom", "rerun-full")
        self.entry("bad", "(", "rerun-full")
        rc, out = self.match("boom")
        self.assertEqual((rc, out["status"]), (2, "invalid"))

    def test_no_entries_is_none(self):
        self.assertEqual(self.match("boom"), (1, {"status": "none"}))

    def test_first_entry_in_config_order_wins(self):
        self.entry("first", "^boom$", "rerun-full")
        self.entry("second", "boom", "rerun-full")
        rc, out = self.match("a\nboom\nb")
        self.assertEqual((rc, out["status"], out["name"]), (0, "match", "first"))

    def test_all_logs_same_entry(self):
        self.entry("a", "boom", "rerun-full")
        self.assertEqual(self.match("boom 1", "boom 2"), (0, {"status": "match", "name": "a", "run": "rerun-full", "blocked_by": []}))

    def test_mixed_entries_is_none(self):
        self.entry("a", "boom", "rerun-full")
        self.entry("b", "bang", "rerun-full")
        self.assertEqual(self.match("boom", "bang"), (1, {"status": "none"}))

    def test_unmatched_log_is_none(self):
        self.entry("a", "boom", "rerun-full")
        self.assertEqual(self.match("boom", "other"), (1, {"status": "none"}))

    def test_blocked_by(self):
        self.commit({"old.sh": "x"})
        subprocess.run(["git", "tag", "-f", "base"], check=True, capture_output=True)
        subprocess.run(["git", "rm", "-q", "old.sh"], check=True)
        self.entry("a", "boom", "make it", ["Makefile", "script/ci/", "tools", "lib/conf/x.mk", "old.sh", "conf/Build.mk"])
        self.commit({
            "CONF/BUILD.MK": "x",  # a reads file, other case
            "Makefile": "x",  # exact
            "GNUmakefile": "x",  # sibling of a top-level reads file
            "Script/CI/run": "x",  # under a directory with trailing slash, other case
            "tools/a/b": "x",  # under a directory without trailing slash
            "lib/conf/y.mk": "x",  # sibling of a nested reads file
            "lib/other.py": "x",
            "script/cid": "x",
            "toolsx": "x",  # top-level sibling of "tools" read as a file
        })
        rc, out = self.match("boom")
        self.assertEqual(rc, 0)
        self.assertCountEqual(
            out["blocked_by"],
            ["CONF/BUILD.MK", "GNUmakefile", "Makefile", "Script/CI/run", "lib/conf/y.mk", "old.sh", "tools/a/b", "toolsx"],
        )

    def test_non_ascii_path_blocked(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        self.commit({"script/ci/caf\u00e9 \"q\".sh": "x"})
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["script/ci/caf\u00e9 \"q\".sh"]))

    def test_symlink_under_reads_blocked(self):
        self.commit({"tools/build.sh": "x", "script/ci/build": "->../../tools/build.sh"})
        subprocess.run(["git", "tag", "-f", "base"], check=True, capture_output=True)
        self.entry("a", "boom", "make it", ["script/ci/"])
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["script/ci/build"]))

    def test_changed_symlink_listed_once(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        self.commit({"script/ci/build": "->../../tools/build.sh"})
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["script/ci/build"]))

    def test_symlinked_ancestor_of_reads_blocked(self):
        self.commit({"ext/c.sh": "x", "a/b": "->../ext"})
        subprocess.run(["git", "tag", "-f", "base"], check=True, capture_output=True)
        self.entry("x", "boom", "make it", ["a/b/c.sh"])
        self.commit({"ext/c.sh": "changed"})
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["a/b"]))

    def test_symlinks_read_at_range_sha_not_head(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        self.commit({"src/app.py": "x"})
        subprocess.run(["git", "tag", "x"], check=True)
        self.commit({"script/ci/build": "->../../tools/build.sh"})
        rc, out = self.match("boom", rng=f"base...{self.sha('x')}")
        self.assertEqual((rc, out["blocked_by"]), (0, []))

    def test_malformed_range(self):
        self.entry("a", "boom", "rerun-full")
        for rng in ("base...", "base", f"...{self.sha()}", "base...HEAD", f"a..b...{self.sha()}"):
            rc, out = self.match("boom", rng=rng)
            self.assertEqual(rc, 2, rng)
            self.assertIn("error", out)

    def test_option_shaped_range_refused(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        out_file = os.path.join(self.dir, "x")
        rc, out = self.match("boom", rng=f"--output={out_file}...{self.sha()}")
        self.assertEqual(rc, 2)
        self.assertIn("error", out)
        self.assertFalse(os.path.exists(out_file))

    def test_symlink_blocked_from_subdirectory(self):
        self.commit({"tools/build.sh": "x", "script/ci/build": "->../../tools/build.sh", "src/app.py": "x"})
        subprocess.run(["git", "tag", "-f", "base"], check=True, capture_output=True)
        self.entry("a", "boom", "make it", ["script/ci/"])
        os.chdir(os.path.join(self.dir, "src"))
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["script/ci/build"]))

    def test_changed_ancestor_of_reads_blocked(self):
        # A submodule bump lists only "vendor" in the diff.
        self.assertEqual(cr.blocked_by(["vendor/bin/ci.sh"], ["Vendor", "vendorx"]), ["Vendor"])

    def test_renamed_reads_file_blocked(self):
        self.commit({"script/ci/run.sh": "x"})
        subprocess.run(["git", "tag", "-f", "base"], check=True, capture_output=True)
        self.entry("a", "boom", "make it", ["script/ci/"])
        subprocess.run(["git", "mv", "script/ci/run.sh", "elsewhere.sh"], check=True)
        self.commit({})
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, ["script/ci/run.sh"]))

    def test_unrelated_path_not_blocked(self):
        self.entry("a", "boom", "make it", ["script/ci/"])
        self.commit({"src/app.py": "x", "script/other": "x"})
        rc, out = self.match("boom")
        self.assertEqual((rc, out["blocked_by"]), (0, []))


if __name__ == "__main__":
    unittest.main()
