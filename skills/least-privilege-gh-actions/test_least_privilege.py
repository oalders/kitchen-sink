#!/usr/bin/env python3
"""Workflow templates and this repo's workflows use a least-privilege token.

Run: python3 skills/least-privilege-gh-actions/test_least_privilege.py

Agents copy the YAML templates in tune-precious, tune-perl-ci,
tune-dependabot-config and pin-gh-actions verbatim, so a template without
these settings spreads to every repo they touch.
Scans fenced ```yaml blocks in those skills and least-privilege-gh-actions
(skipping "Before" examples) plus every .github/workflows/*.yml and *.yaml
file. A full workflow (one with a column-0 `jobs:`) must have exactly `permissions:` / `contents: read`
at top level, and every actions/checkout step must set
`persist-credentials: false`; a block whose checkouts all do must not run
`git fetch`, `git push` or `git pull`, which need the persisted token.
Requiring exactly `contents: read` is deliberately stricter than the skill,
which also accepts narrower blocks.
Stdlib only: CI runs plain python3.
"""

import glob
import os
import re
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = [os.path.join(ROOT, "skills", s, "SKILL.md") for s in ("least-privilege-gh-actions", "tune-precious", "tune-perl-ci", "tune-dependabot-config", "pin-gh-actions")]
# Skills whose templates show only a step, not a full workflow.
CHECKOUT_ONLY = {"pin-gh-actions"}
FENCE = re.compile(r"^\s*```")
LABEL = re.compile(r"^(?:#{1,6}\s|\*\*)")
# "**Before:**", "### Before", "### Before (x)" -- not "**Before emitting the file**".
BEFORE = re.compile(r"^(?:#{1,6}\s+|\*\*)Before\b(?:\s*\(|:|\*\*|\s*$)")
CHECKOUT = re.compile(r"""^\s*(?:-\s+)?uses:\s*["']?actions/checkout@""")
STEP = re.compile(r"^(\s*)-\s")
GIT_REMOTE = re.compile(r"\bgit\s+(?:fetch|push|pull)\b")


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


def bare(line):
    return line.split("#", 1)[0].strip()


def top_permissions_ok(lines):
    top = [n for n, l in enumerate(lines) if l.startswith("permissions:")]
    if len(top) != 1 or bare(lines[top[0]]) != "permissions:":
        return False
    body = []
    for l in lines[top[0] + 1 :]:
        if l and not l[0].isspace():
            break
        if bare(l):
            body.append(bare(l))
    return body == ["contents: read"]


def problems(name, start, lines):
    bad = []
    checkouts = 0
    if "jobs:" in lines and not top_permissions_ok(lines):
        bad.append(f"{name}:{start}: top-level permissions is not exactly `contents: read`")
    for n, line in enumerate(lines):
        if not CHECKOUT.match(line):
            continue
        checkouts += 1
        # The step starts at the nearest `- ` at or above the uses: line.
        first = next(k for k in range(n, -1, -1) if STEP.match(lines[k]))
        dash = len(STEP.match(lines[first]).group(1))
        step = [bare(lines[first][dash + 1 :])]
        for l in lines[first + 1 :]:
            if l.strip() and len(l) - len(l.lstrip()) <= dash:
                break
            step.append(bare(l))
        if "persist-credentials: false" not in step:
            bad.append(f"{name}:{start + n}: checkout without persist-credentials: false")
    if checkouts and not bad:
        for n, line in enumerate(lines):
            if GIT_REMOTE.search(bare(line)):
                bad.append(f"{name}:{start + n}: git remote command without persisted credentials")
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
                "t:14: checkout without persist-credentials: false",
            ],
        )
        self.assertEqual(problems("t", *blocks[1]), ["t:31: git remote command without persisted credentials"])
        self.assertEqual(problems("t", *blocks[2]), ["t:34: checkout without persist-credentials: false"])


if __name__ == "__main__":
    unittest.main()
