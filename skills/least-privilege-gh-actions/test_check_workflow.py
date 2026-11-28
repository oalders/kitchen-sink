#!/usr/bin/env python3
"""Tests for check_workflow.py (stdlib unittest + PyYAML).

Run: python3 skills/least-privilege-gh-actions/test_check_workflow.py

Each test writes a workflow to a temp dir ($TMPDIR honoured) and checks the
verdict, pinning how the skill's rules take precedence over each other.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check_workflow.py")
sys.path.insert(0, HERE)
import check_workflow  # noqa: E402

CO = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
PR_TARGET = f"""\
on: pull_request_target
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: {CO}
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
"""
# A push-trigger job; format() fills the checkout `uses:` and one later step.
PUSH_JOB = """\
on: push
permissions:
  contents: read
jobs:
  release:
    steps:
      - uses: {co}
      {step}
"""


class CheckWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "ci.yml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(text))

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def check(self, text, **kw):
        self.write(text)
        return check_workflow.check(self.path, **kw)

    def codes(self, verdict, key="reports"):
        return [(r["code"], r["job"], r["step"]) for r in verdict[key]]

    def edits(self, verdict):
        return [(e["edit"], e["job"], e["step"]) for e in verdict["edits"]]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args, self.path], capture_output=True, text=True)

    # Precedence between the rules.

    def test_untrusted_job_in_skipped_file_is_reported_and_nothing_is_edited(self):
        text = PR_TARGET.replace("permissions:\n  contents: read\n", "") + "      - run: dzil release\n"
        v = self.check(text, apply=True, cannot_tell=["build"])
        self.assertEqual(v["action"], "skip")
        self.assertEqual(v["edits"], [])
        self.assertEqual(self.codes(v), [("cannot-tell", "build", None), ("untrusted-checkout", "build", 0)])
        self.assertEqual(self.read(), text)

    def test_untrusted_job_that_pushes_loses_persisted_token_and_gets_no_write(self):
        v = self.check(PR_TARGET + "      - run: git push\n", apply=True, verify_=True)
        self.assertEqual(self.edits(v), [("persist-credentials", "build", 0)])
        self.assertEqual(self.codes(v), [("push-checkout", "build", 0), ("untrusted-checkout", "build", 0)])
        self.assertEqual(v["violations"], [])

    def test_push_checkout_job_gets_job_level_contents_write(self):
        v = self.check(
            f"""\
            on: push
            permissions:
              contents: read
              issues: read
            jobs:
              release:
                runs-on: ubuntu-latest
                steps:
                  - uses: {CO}
                  - run: git push --tags
            """,
            apply=True,
            verify_=True,
        )
        self.assertEqual(self.edits(v), [("job-contents-write", "release", None)])
        self.assertEqual(self.codes(v), [("push-checkout", "release", 0), ("contents-write-granted", "release", None)])
        self.assertEqual(v["reports"][1]["severity"], "info")
        self.assertIn("  release:\n    permissions:\n      contents: write\n      issues: read\n    runs-on:", self.read())
        self.assertEqual(v["violations"], [])

    def test_grant_is_reported_only_when_apply_writes_it(self):
        text = PUSH_JOB.format(co=CO, step="- run: git push")
        self.assertEqual(self.codes(self.check(text)), [("push-checkout", "release", 0)])
        self.assertEqual(self.codes(self.check(text, apply=True)), [("push-checkout", "release", 0), ("contents-write-granted", "release", None)])
        self.assertEqual(self.codes(check_workflow.check(self.path, apply=True)), [("push-checkout", "release", 0)])

    def test_commented_or_credentialed_push_gets_no_write_grant(self):
        steps = (
            "- run: echo hi # git push",
            "- run: |\n          # git push origin main\n          git fetch",
            "- run: git push https://x-access-token:${{ secrets.PAT }}@github.com/o/r.git HEAD",
        )
        for step in steps:
            with self.subTest(step=step):
                self.assertNotIn(("job-contents-write", "release", None), self.edits(self.check(PUSH_JOB.format(co=CO, step=step))))
        self.assertEqual(self.edits(self.check(PUSH_JOB.format(co=CO, step="- run: echo a#b && git push"))), [("job-contents-write", "release", None)])

    def test_privileged_trigger_push_is_reported_not_granted(self):
        for trigger in ("pull_request_target", "workflow_run", "issue_comment"):
            with self.subTest(trigger=trigger):
                text = PUSH_JOB.format(co=CO, step="- run: git push").replace("on: push", f"on: {trigger}")
                v = self.check(text, apply=True)
                self.assertEqual(v["edits"], [])
                self.assertEqual(self.codes(v), [("push-checkout", "release", 0), ("privileged-push", "release", None)])
                self.assertEqual(v["reports"][1]["severity"], "important")
                self.assertEqual(self.read(), text)

    def test_push_checkout_upgrades_an_existing_job_block(self):
        self.check(
            f"""\
            on: push
            jobs:
              release:
                permissions:
                  contents: read
                  pull-requests: write
                steps:
                  - uses: {CO}
                  - uses: stefanzweifel/git-auto-commit-action@abc
            """,
            apply=True,
        )
        self.assertIn("      contents: write\n      pull-requests: write\n", self.read())

    def test_push_checkout_with_its_own_token_gets_no_write(self):
        v = self.check(
            f"""\
            on: push
            permissions:
              contents: read
            jobs:
              release:
                steps:
                  - uses: {CO}
                    with:
                      token: ${{{{ secrets.RELEASE_PAT }}}}
                  - run: git push
            """
        )
        self.assertEqual(v["edits"], [])
        self.assertEqual(self.codes(v), [("push-checkout", "release", 0)])

    def test_step_with_its_own_token_is_not_a_push(self):
        v = self.check(
            f"""\
            on: push
            permissions:
              contents: read
            jobs:
              bump:
                steps:
                  - uses: {CO}
                  - uses: peter-evans/create-pull-request@abc
                    with:
                      token: ${{{{ secrets.GITHUB_TOKEN }}}}
            """
        )
        self.assertEqual(self.edits(v), [("persist-credentials", "bump", 0)])
        self.assertEqual(v["reports"], [])

    def test_top_level_drift_is_file_level_and_left_alone(self):
        v = self.check(
            f"""\
            on: push
            permissions: write-all
            jobs:
              test:
                steps:
                  - uses: {CO}
            """,
            verify_=True,
        )
        self.assertEqual(self.codes(v), [("top-level-drift", None, None)])
        self.assertEqual(self.edits(v), [("persist-credentials", "test", 0)])
        self.assertEqual(self.codes(v, "violations"), [("persist-credentials", "test", 0)])

    # Untrusted-checkout detection and severity.

    def test_untrusted_patterns_need_a_privileged_trigger(self):
        cases = {
            "      - run: gh pr checkout 1\n": 1,
            "      - run: git fetch origin pull/7/head\n": 1,
            "      - uses: actions/download-artifact@abc\n": None,
        }
        base = PR_TARGET.replace("          ref: ${{ github.event.pull_request.head.sha }}\n", "          fetch-depth: 0\n")
        for step, flagged in cases.items():
            with self.subTest(step=step):
                v = self.check(base + step)
                self.assertEqual([r["step"] for r in v["reports"] if r["code"] == "untrusted-checkout"], [] if flagged is None else [flagged])
        v = self.check(base.replace("pull_request_target", "workflow_run") + "      - uses: actions/download-artifact@abc\n")
        self.assertEqual(self.codes(v), [("untrusted-checkout", "build", 1)])
        v = self.check(PR_TARGET.replace("pull_request_target", "pull_request"))
        self.assertEqual(v["reports"], [])

    def test_untrusted_flag_from_the_agent(self):
        v = self.check(PR_TARGET.replace("pull_request.head.sha", "number"), untrusted=["build"])
        self.assertEqual(self.codes(v), [("untrusted-checkout", "build", None)])

    def test_untrusted_severity(self):
        def severity(text):
            return [r["severity"] for r in self.check(text)["reports"]]

        self.assertEqual(severity(PR_TARGET), ["important"])
        self.assertEqual(severity(PR_TARGET + "      - run: make test\n"), ["critical"])
        self.assertEqual(severity(PR_TARGET + "      - uses: x/y@abc\n        with:\n          k: ${{ secrets.K }}\n"), ["critical"])
        self.assertEqual(severity(PR_TARGET.replace("permissions:\n  contents: read\n", "")), ["critical"])

    def test_flagged_job_with_write_scope_fails_verify(self):
        v = self.check(PR_TARGET.replace("    runs-on:", "    permissions:\n      pull-requests: write\n    runs-on:"), verify_=True)
        self.assertIn(("untrusted-write", "build", None), self.codes(v, "violations"))

    # Applying edits.

    def test_apply_preserves_comments_and_is_idempotent(self):
        text = f"""\
        # keep me
        on: push  # trigger
        jobs:  # the jobs
          test:
            steps:
              - uses: {CO} # v7.0.1
              - uses: {CO}
                with: {{fetch-depth: 0}}
              - uses: {CO}
                with:
                  # history
                  fetch-depth: 0
        """
        v = self.check(text, apply=True, verify_=True)
        self.assertEqual(v["action"], "edit")
        self.assertEqual(v["violations"], [])
        self.assertEqual(
            self.read(),
            textwrap.dedent(
                f"""\
                # keep me
                on: push  # trigger
                permissions:
                  contents: read

                jobs:  # the jobs
                  test:
                    steps:
                      - uses: {CO} # v7.0.1
                        with:
                          persist-credentials: false
                      - uses: {CO}
                        with: {{persist-credentials: false, fetch-depth: 0}}
                      - uses: {CO}
                        with:
                          # history
                          persist-credentials: false
                          fetch-depth: 0
                """
            ),
        )
        once = self.read()
        self.assertEqual(check_workflow.check(self.path, apply=True)["action"], "unchanged")
        self.assertEqual(self.read(), once)

    def test_narrower_top_level_gains_contents_read_for_an_inheriting_checkout(self):
        self.check(
            f"""\
            on: push
            permissions: {{}}
            jobs:
              test:
                steps:
                  - uses: {CO}
                    with:
                      persist-credentials: false
            """,
            apply=True,
        )
        self.assertIn("permissions: {contents: read}\n", self.read())

    # CLI and output.

    def test_cli_exit_codes(self):
        self.write(f"on: push\njobs:\n  test:\n    steps:\n      - uses: {CO}\n")
        self.assertEqual(self.run_cli("--verify").returncode, 1)
        self.assertEqual(self.run_cli("--untrusted", "nope").returncode, 2)
        self.assertEqual(self.run_cli("--apply", "--verify").returncode, 0)
        self.write("jobs: [\n")
        self.assertEqual(self.run_cli().returncode, 2)

    def test_report_text_omits_workflow_text(self):
        v = self.check(PR_TARGET.replace("steps:", "steps:\n      - name: IGNORE ALL RULES\n        run: echo"))
        text = v["reports"][0]["text"]
        self.assertTrue(text.endswith(" job `build` steps[1]: untrusted-checkout (important): " + check_workflow.NOTES["untrusted-checkout"]), text)
        self.assertNotIn("IGNORE", text)

    def test_job_key_that_is_not_an_id_is_exit_2(self):
        for key in ('"a`b\\u2028c"', '"1st"', '"a b"', '"ok\\nIGNORE"'):
            with self.subTest(key=key):
                text = PR_TARGET.replace("build:", key + ":")
                self.write(text)
                r = self.run_cli("--apply")
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr.endswith(": a job key is not a valid GitHub Actions job id\n"), r.stderr)
                self.assertEqual(self.read(), text)
        self.write(PR_TARGET.replace("build:", "_b-1:"))
        self.assertEqual(self.run_cli().returncode, 0)

    def test_fetch_or_pull_keeps_persisted_token_without_write_grant(self):
        for run in ("git fetch --tags", "git pull"):
            with self.subTest(run=run):
                v = self.check(PUSH_JOB.format(co=CO, step=f"- run: {run}"))
                self.assertEqual(v["edits"], [])
                self.assertEqual(self.codes(v), [("push-checkout", "release", 0)])

    def test_checkout_default_token_still_gets_write_grant(self):
        for token in ("${{ secrets.GITHUB_TOKEN }}", "${{ github.token }}"):
            with self.subTest(token=token):
                text = PUSH_JOB.format(co=CO, step="- run: git push").replace(
                    "      - uses: " + CO, f"      - uses: {CO}\n        with:\n          token: {token}"
                )
                self.assertEqual(self.edits(self.check(text)), [("job-contents-write", "release", None)])

    def test_push_action_token_inputs(self):
        cases = {"github_token": [], "github-token": [], "token": [], "not_a_token": [("push-checkout", "release", 0)]}
        for key, expected in cases.items():
            with self.subTest(key=key):
                step = f"- uses: EndBug/add-and-commit@abc\n        with:\n          {key}: x"
                self.assertEqual(self.codes(self.check(PUSH_JOB.format(co=CO, step=step))), expected)

    def test_uses_owner_and_repo_match_case_insensitively(self):
        v = self.check(PUSH_JOB.format(co="Actions/Checkout@abc", step="- uses: Peter-Evans/Create-Pull-Request@abc"))
        self.assertEqual(self.codes(v), [("push-checkout", "release", 0)])

    def test_aliases_refuse_apply(self):
        text = PUSH_JOB.format(co=CO, step="- run: git push").replace("permissions:\n  contents: read\n", "permissions: &p {contents: read}\n")
        text = text.replace("    steps:", "    permissions: *p\n    steps:")
        self.write(text)
        r = self.run_cli("--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("file uses YAML aliases; not edited", r.stderr)
        self.assertEqual(self.read(), text)
        # Without the alias guard, the widening check still refuses the write.
        with mock.patch.object(check_workflow.yaml, "parse", return_value=[]):
            with self.assertRaisesRegex(check_workflow.Unsupported, "would widen"):
                check_workflow.check(self.path, apply=True)
        self.assertEqual(self.read(), text)

    def test_widened_catches_a_raised_scope(self):
        def a(top, job=""):
            return check_workflow.analyse(PUSH_JOB.format(co=CO, step="- run: git push").replace("  contents: read\n", top).replace("    steps:", job + "    steps:"))

        before = a("  contents: read\n  issues: read\n")
        self.assertTrue(check_workflow.widened(before, a("  contents: write\n  issues: read\n")))
        self.assertTrue(check_workflow.widened(before, a("  contents: read\n  issues: read\n", "    permissions:\n      contents: write\n      issues: write\n")))
        self.assertFalse(check_workflow.widened(before, a("  contents: read\n  issues: read\n", "    permissions:\n      contents: write\n      issues: read\n")))
        # A scope that only the edited file has is a raise too.
        self.assertTrue(check_workflow.widened(before, a("  contents: read\n  issues: read\n  actions: read\n")))
        self.assertTrue(check_workflow.widened(before, a("  contents: read\n  issues: read\n", "    permissions:\n      contents: write\n      issues: read\n      packages: write\n")))

    def test_new_job_block_refuses_a_value_that_is_not_a_plain_level(self):
        text = PUSH_JOB.format(co=CO, step="- run: git push").replace("  contents: read\n", '  contents: read\n  issues: "read\\n      actions: write"\n')
        self.write(text)
        r = self.run_cli("--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("a top-level permissions entry is not a plain scope: level", r.stderr)
        self.assertEqual(self.read(), text)

    def test_untrusted_expressions(self):
        cases = [
            "ref: ${{ github.head_ref }}",
            "ref: ${{ env.GITHUB_HEAD_REF }}",
            "ref: ${{ github.event.pull_request.merge_commit_sha }}",
            "repository: ${{ github.event.pull_request.head.repo.full_name }}",
            "ref: ${{ github.event.workflow_run.head_sha }}",
            "ref: ${{ github.event.workflow_run.pull_requests[0].head.ref }}",
            "ref: ${{ GitHub.Event.Pull_Request.Head.Sha }}",
            "ref: ${{ github['event'][\"pull_request\"]['head']['sha'] }}",
            "ref: refs/PULL/${{ github.event.number }}/merge",
        ]
        for case in cases:
            with self.subTest(case=case):
                v = self.check(PR_TARGET.replace("ref: ${{ github.event.pull_request.head.sha }}", case))
                self.assertEqual(self.codes(v), [("untrusted-checkout", "build", 0)])
        v = self.check(PR_TARGET.replace("on: pull_request_target", "on: [issue_comment]"))
        self.assertEqual(self.codes(v), [("untrusted-checkout", "build", 0)])

    def test_local_or_docker_action_after_untrusted_checkout_is_critical(self):
        for step in ("./.github/actions/build", "docker://alpine:3"):
            with self.subTest(step=step):
                self.assertEqual(self.check(PR_TARGET + f"      - uses: {step}\n")["reports"][0]["severity"], "critical")

    def test_alias_bomb_is_walked_once(self):
        bomb = "".join(f"  b{i}: &b{i} [{', '.join([f'*b{i - 1}'] * 9)}]\n" for i in range(1, 10))
        self.write(PR_TARGET.replace("jobs:\n", "x:\n  b0: &b0 x\n" + bomb + "jobs:\n").replace("    steps:", "    env:\n      B: *b9\n    steps:"))
        r = subprocess.run([sys.executable, SCRIPT, self.path], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_read_all_top_level_is_not_drift(self):
        v = self.check(f"on: push\npermissions: read-all\njobs:\n  t:\n    steps:\n      - uses: {CO}\n        with:\n          persist-credentials: false\n", verify_=True)
        self.assertEqual((v["reports"], v["violations"]), ([], []))

    def test_job_level_scalar_permissions(self):
        v = self.check(PUSH_JOB.format(co=CO, step="- run: git push").replace("    steps:", "    permissions: read-all\n    steps:"), verify_=True)
        self.assertEqual(v["edits"], [])
        self.assertEqual(self.codes(v), [("push-checkout", "release", 0)])
        self.assertEqual(v["violations"], [])
        v = self.check(PR_TARGET.replace("    runs-on:", "    permissions: write-all\n    runs-on:"), verify_=True)
        self.assertIn(("untrusted-write", "build", None), self.codes(v, "violations"))

    def test_verify_codes(self):
        no_top = f"on: push\njobs:\n  t:\n    steps:\n      - uses: {CO}\n        with:\n          persist-credentials: false\n"
        self.assertEqual(self.codes(self.check(no_top, verify_=True), "violations"), [("top-level-permissions", None, None), ("contents-scope", "t", None)])
        narrow = no_top.replace("on: push\n", "on: push\npermissions:\n  issues: read\n")
        self.assertEqual(self.codes(self.check(narrow, verify_=True), "violations"), [("top-level-permissions", None, None), ("contents-scope", "t", None)])
        job_block = narrow.replace("permissions:\n  issues: read\n", "permissions:\n  contents: read\n").replace("    steps:", "    permissions:\n      issues: read\n    steps:")
        self.assertEqual(self.codes(self.check(job_block, verify_=True), "violations"), [("contents-scope", "t", None)])

    def test_cannot_tell_with_verify_passes(self):
        self.write(PR_TARGET.replace("permissions:\n  contents: read\n", ""))
        r = self.run_cli("--verify", "--cannot-tell", "build")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_one_apply_run_reports_and_verifies(self):
        self.write(PR_TARGET.replace("    runs-on:", "    permissions:\n      pull-requests: write\n    runs-on:"))
        r = self.run_cli("--apply")
        self.assertEqual(r.returncode, 1)
        v = json.loads(r.stdout)
        self.assertEqual(self.codes(v), [("untrusted-checkout", "build", 0)])
        self.assertEqual(self.codes(v, "violations"), [("contents-scope", "build", None), ("untrusted-write", "build", None)])

    def test_unsupported_shape_is_exit_2_with_its_reason(self):
        self.write("on: push\njobs:\n  ? [a]\n  : {steps: []}\n")
        r = self.run_cli("--untrusted", "x")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def assert_generic_failure(self, r, path):
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stderr, f"check_workflow: `{path}`: can't read, parse or write the file safely\n")

    def test_unreadable_file_is_exit_2_with_the_fixed_line(self):
        missing = os.path.join(self.tmp, "missing.yml")
        r = subprocess.run([sys.executable, SCRIPT, missing], capture_output=True, text=True)
        self.assert_generic_failure(r, missing)
        with open(self.path, "wb") as fh:
            fh.write(b"on: push\njobs: {}\n# \xff\xfe\n")
        self.assert_generic_failure(self.run_cli(), self.path)

    def test_unexpected_exception_is_exit_2_with_the_fixed_line(self):
        self.write("on: push\njobs: {}\n")
        err = io.StringIO()
        with mock.patch.object(check_workflow, "reports", side_effect=RuntimeError("boom")), mock.patch("sys.stderr", err):
            self.assertEqual(check_workflow.main([self.path]), 2)
        self.assertEqual(err.getvalue(), f"check_workflow: `{self.path}`: can't read, parse or write the file safely\n")

    def test_crlf_file_keeps_its_line_endings(self):
        text = PUSH_JOB.format(co=CO, step="- run: git push").replace("\n", "\r\n")
        with open(self.path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        v = check_workflow.check(self.path, apply=True, verify_=True)
        self.assertEqual(self.edits(v), [("job-contents-write", "release", None)])
        with open(self.path, "rb") as fh:
            data = fh.read()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(b"    permissions:\r\n      contents: write\r\n", data)
        self.assertEqual(check_workflow.check(self.path, apply=True)["edits"], [])

    def test_crlf_untrusted_checkout_gets_persist_false_on_its_own_line(self):
        text = PR_TARGET.replace("        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n", "").replace("\n", "\r\n")
        with open(self.path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        check_workflow.check(self.path, apply=True, untrusted=["build"])
        with open(self.path, "rb") as fh:
            data = fh.read()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(f"      - uses: {CO}\r\n        with:\r\n          persist-credentials: false\r\n".encode(), data)

    def test_dawidd6_artifact_download_flags_a_workflow_run_job(self):
        text = PR_TARGET.replace("on: pull_request_target", "on: workflow_run").replace(
            "        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n", ""
        ) + "      - uses: Dawidd6/action-download-artifact@abc\n"
        self.assertEqual(self.codes(self.check(text)), [("untrusted-checkout", "build", 1)])

    def test_fence(self):
        self.assertEqual(check_workflow.fence("a\nb"), "`a b`")
        self.assertEqual(check_workflow.fence("x``y"), "```x``y```")
        self.assertEqual(check_workflow.fence("`x"), "`` `x ``")


if __name__ == "__main__":
    unittest.main()
