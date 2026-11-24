#!/usr/bin/env python3
"""Every `uses:` step line in shipped docs and workflows is SHA-pinned.

Run: python3 skills/pin-gh-actions/test_uses_pinned.py

Agents copy the templates in skills/ and commands/ verbatim, so a tag pin
there spreads to every repo they touch. docs/ is historical plans and is
not scanned.
"""

import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Anchored at line start so prose such as "`uses:` at job level" is ignored.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)(.*)$")
PINNED = re.compile(r"@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s+#\s*\S+")


def unpinned(path):
    bad = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            m = USES.match(line)
            if not m or m.group(1).startswith(("./", "docker://")):
                continue
            if not (PINNED.search(m.group(1)) and VERSION_COMMENT.match(m.group(2))):
                bad.append(f"{os.path.relpath(path, ROOT)}:{lineno}: {line.strip()}")
    return bad


class TestUsesPinned(unittest.TestCase):
    def test_every_uses_ref_is_sha_pinned_with_version_comment(self):
        paths = (
            glob.glob(os.path.join(ROOT, "skills", "**", "*.md"), recursive=True)
            + glob.glob(os.path.join(ROOT, "commands", "**", "*.md"), recursive=True)
            + glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))
        )
        self.assertTrue(paths)
        bad = [hit for path in sorted(paths) for hit in unpinned(path)]
        self.assertFalse(bad, "uses: refs not pinned as @<40-hex sha> # <tag>:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
