#!/usr/bin/env python3
"""Every `uses:` step line in shipped docs and workflows is SHA-pinned.

Run: python3 skills/pin-gh-actions/test_uses_pinned.py

Agents copy the templates in the repo's Markdown verbatim, so a tag pin
there spreads to every repo they touch. Scans every *.md outside docs/
(historical plans) and .git, plus .github/workflows/*.yml and *.yaml.
"""

import glob
import os
import re
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Anchored at line start so prose such as "`uses:` at job level" is ignored.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)(.*)$")
QUOTED = re.compile(r"""^(["'])(.*)\1$""")
PINNED = re.compile(r"@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s+#\s*\S+")


def unpinned(path):
    bad = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            m = USES.match(line)
            if not m:
                continue
            ref = m.group(1)
            q = QUOTED.match(ref)
            if q:
                ref = q.group(2)
            if ref.startswith(("./", "docker://")):
                continue
            if not (PINNED.search(ref) and VERSION_COMMENT.match(m.group(2))):
                bad.append(f"{os.path.relpath(path, ROOT)}:{lineno}: {line.strip()}")
    return bad


def scanned_paths():
    md = [
        p
        for p in glob.glob(os.path.join(ROOT, "**", "*.md"), recursive=True)
        if os.path.relpath(p, ROOT).split(os.sep)[0] not in ("docs", ".git")
    ]
    workflows = os.path.join(ROOT, ".github", "workflows")
    return sorted(md + glob.glob(os.path.join(workflows, "*.yml")) + glob.glob(os.path.join(workflows, "*.yaml")))


class TestUsesPinned(unittest.TestCase):
    def test_every_uses_ref_is_sha_pinned_with_version_comment(self):
        paths = scanned_paths()
        self.assertTrue(paths)
        bad = [hit for path in paths for hit in unpinned(path)]
        self.assertFalse(bad, "uses: refs not pinned as @<40-hex sha> # <tag>:\n" + "\n".join(bad))

    def test_unpinned_flags_tag_and_uncommented_sha(self):
        sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
        lines = [
            "      - uses: actions/checkout@v4\n",
            f"      - uses: actions/checkout@{sha}\n",
            f'      - uses: "actions/checkout@{sha}" # v7.0.1\n',
            '      - uses: "./local-action"\n',
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.writelines(lines)
        try:
            bad = unpinned(fh.name)
        finally:
            os.unlink(fh.name)
        self.assertEqual([b.split(": ", 1)[1] for b in bad], [lines[0].strip(), lines[1].strip()])


if __name__ == "__main__":
    unittest.main()
