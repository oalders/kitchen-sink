#!/usr/bin/env python3
"""Workflow templates and this repo's workflows use a least-privilege token.

Run: python3 skills/least-privilege-gh-actions/test_least_privilege.py

Agents copy the YAML templates in tune-precious, tune-perl-ci,
tune-dependabot-config and pin-gh-actions verbatim, so a template without
these settings spreads to every repo they touch.
Scans fenced ```yaml blocks in those skills and least-privilege-gh-actions
(skipping "Before" examples) plus every .github/workflows/*.yml and *.yaml
file; pin-gh-actions need only show a checkout step, not a full workflow.
Each block must get no report and no Verify failure from check_workflow.py
(a checkout-only block is checked inside a conforming workflow), and a full
workflow (one with a column-0 `jobs:`) must have exactly `permissions:` /
`contents: read` at top level: deliberately stricter than the skill, which
also accepts narrower blocks.
Needs PyYAML, which check_workflow.py uses.
"""

import glob
import os
import re
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_workflow  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = [os.path.join(ROOT, "skills", s, "SKILL.md") for s in ("least-privilege-gh-actions", "tune-precious", "tune-perl-ci", "tune-dependabot-config", "pin-gh-actions")]
# Skills whose templates show only a step, not a full workflow.
CHECKOUT_ONLY = {"pin-gh-actions"}
FENCE = re.compile(r"^\s*```")
LABEL = re.compile(r"^(?:#{1,6}\s|\*\*)")
# "**Before:**", "### Before", "### Before (x)" -- not "**Before emitting the file**".
BEFORE = re.compile(r"^(?:#{1,6}\s+|\*\*)Before\b(?:\s*\(|:|\*\*|\s*$)")
CHECKOUT = re.compile(r"""^\s*(?:-\s+)?uses:\s*["']?actions/checkout@""")


def yaml_blocks(path):
    """Yield (start_lineno, lines) for each ```yaml block not labelled Before."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    label = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            lang = line.strip()[3:].strip()
            end = i + 1
            while end < len(lines) and not FENCE.match(lines[end]):
                end += 1
            if lang == "yaml" and not BEFORE.match(label):
                yield i + 2, lines[i + 1 : end]
            i = end + 1
            continue
        if LABEL.match(line):
            label = line
        i += 1


def problems(name, start, lines):
    """check_workflow.py's reports and Verify failures for one block, as `name:line: code`."""
    full = "jobs:" in lines
    # A checkout-only block is a step list: check it inside a conforming workflow.
    head = [] if full else ["permissions:", "  contents: read", "jobs:", "  t:", "    steps:"]
    text = "\n".join(head + (lines if full else ["      " + l for l in lines])) + "\n"
    try:
        analysis = check_workflow.analyse(text)
    except check_workflow.Unsupported as exc:
        return [f"{name}:{start}: {exc}"]
    _, top, jobs = analysis
    bad = []
    if full and not (isinstance(top, yaml.MappingNode) and [(k.value, v.value) for k, v in top.value] == [("contents", "read")]):
        bad.append(f"{name}:{start}: top-level permissions is not exactly `contents: read`")
    if sum(map(bool, map(CHECKOUT.match, lines))) != sum(len(j.checkouts) for j in jobs):
        bad.append(f"{name}:{start}: a checkout sits outside a job's steps list, so it went unchecked")
    steps = {j.key: j.steps for j in jobs}
    for r in check_workflow.reports(analysis, ()) + check_workflow.verify(analysis, ()):
        line = start if r["step"] is None else start + steps[r["job"]][r["step"]].start_mark.line - len(head)
        bad.append(f"{name}:{line}: {r['code']}")
    return bad


def scanned():
    for path in SKILLS:
        for start, lines in yaml_blocks(path):
            yield os.path.relpath(path, ROOT), start, lines
    workflows = os.path.join(ROOT, ".github", "workflows")
    for path in sorted(glob.glob(os.path.join(workflows, "*.yml")) + glob.glob(os.path.join(workflows, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            yield os.path.relpath(path, ROOT), 1, fh.read().splitlines()


class TestLeastPrivilege(unittest.TestCase):
    def test_templates_and_workflows_are_least_privilege(self):
        items = list(scanned())
        self.assertTrue(items)
        bad = [hit for item in items for hit in problems(*item)]
        self.assertFalse(bad, "least-privilege violations:\n" + "\n".join(bad))

    def test_each_skill_has_a_scanned_workflow_or_checkout(self):
        for path in SKILLS:
            skill = os.path.basename(os.path.dirname(path))
            if skill in CHECKOUT_ONLY:
                hits = [b for _, b in yaml_blocks(path) if any(CHECKOUT.match(l) for l in b)]
                self.assertTrue(hits, f"{path}: no scanned block has a checkout")
            else:
                hits = [b for _, b in yaml_blocks(path) if "jobs:" in b]
                self.assertTrue(hits, f"{path}: no scanned block has a full workflow")

    def test_checker_flags_bad_block(self):
        md = [
            "**Before:**",
            "```yaml",
            "jobs:",
            "  a:",
            "    steps:",
            "      - uses: actions/checkout@x",
            "```",
            "**Before emitting the file, check:**",
            "```yaml",
            "permissions: write-all",
            "jobs:",
            "  a:",
            "    steps:",
            "      - uses: actions/checkout@x",
            "        with:",
            "          fetch-depth: 0",
            "      - name: second checkout",
            "        uses: actions/checkout@x",
            "        with:",
            "          persist-credentials: false",
            "```",
            "```yaml",
            "permissions:",
            "  contents: read",
            "jobs:",
            "  a:",
            "    steps:",
            "      - uses: actions/checkout@x",
            "        with:",
            "          persist-credentials: false",
            "      - run: git push origin HEAD",
            "```",
            "```yaml",
            "- uses: actions/checkout@x",
            "  with:",
            "    fetch-depth: 0",
            "```",
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write("\n".join(md) + "\n")
        try:
            blocks = list(yaml_blocks(fh.name))
        finally:
            os.unlink(fh.name)
        self.assertEqual(len(blocks), 3, "the Before block is skipped, the others are scanned")
        self.assertEqual(
            problems("t", *blocks[0]),
            [
                "t:10: top-level permissions is not exactly `contents: read`",
                "t:10: top-level-drift",
                "t:14: persist-credentials",
            ],
        )
        self.assertEqual(problems("t", *blocks[1]), ["t:28: push-own-credentials"])
        self.assertEqual(problems("t", *blocks[2]), ["t:34: persist-credentials"])


if __name__ == "__main__":
    unittest.main()
