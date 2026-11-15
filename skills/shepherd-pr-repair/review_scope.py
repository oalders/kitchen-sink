#!/usr/bin/env python3
"""Scope a /shepherd-pr rebase re-review to what the rebase changed.

  review_scope.py --old-head SHA --rebased SHA --base REF

Run in the repo after the rebase: SHA is the pre-rebase PR head, --rebased the
HEAD right after the rebase. Writes the scope files to
<git-dir>/kitchen-sink/scope/ (per worktree, replaced on each run) and prints the
path of its scope.json, whose `mode` is `rebase-delta` or `full` (with a
`reason`). See docs/superpowers/specs/2026-11-14-rebase-scoped-review-design.md.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

MAX_LINES = 300  # kept range-diff plus fix diff; past this a full review is as cheap
# Same order as BASE_REFS in hooks/require-review-before-pr.py, whose patch markers we match.
BASE_REFS = (
    "refs/remotes/origin/HEAD",
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
    "refs/heads/main",
    "refs/heads/master",
)
# A pair header; range-diff indents its body by four spaces, so a diff line can't pass as one.
PAIR_RE = re.compile(r"^ {0,3}(?:\d+|-):\s+([0-9a-f]+|-+)\s+([=!<>])\s+(?:\d+|-):\s+([0-9a-f]+|-+)\s")


class Full(Exception):
    """Fall back to a full review, for the reason given."""


def git(*args, stdin=None):
    try:
        # --literal-pathspecs: a file name like ':(exclude)x' must not act as pathspec magic.
        proc = subprocess.run(["git", "--literal-pathspecs", *args], input=stdin, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise Full(f"git {args[0]} failed: {exc}") from None
    if proc.returncode != 0:
        raise Full(f"git {args[0]} failed: {proc.stderr.strip()}")
    return proc.stdout


def patch_id(sha):
    """The hook's branch_patch_id(), for sha instead of HEAD; None where it would be None."""
    present = set(git("for-each-ref", "--format=%(refname)", *BASE_REFS).split())
    base = next((ref for ref in BASE_REFS if ref in present), None)
    if not base:
        return None
    mb = git("merge-base", base, sha).strip()
    diff = git("diff", "--no-color", "--no-ext-diff", "--no-textconv", mb, sha).strip()
    if not diff:
        return None
    out = git("patch-id", "--stable", stdin=diff + "\n").split()
    return out[0] if out else None


def reviewed(mdir, sha):
    if os.path.isfile(os.path.join(mdir, sha)):
        return True
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    pid = patch_id(sha)
    return bool(pid) and os.path.isfile(os.path.join(mdir, "patch", branch, pid))


def commit(rev):
    """rev's commit SHA; --end-of-options keeps a rev like '--output=x' from parsing as an option."""
    return git("rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}").strip()


def names(cmd, *args):
    """File names from a git --name-only call, NUL-split so non-ASCII names aren't quoted."""
    return git(cmd, "-z", "--name-only", *args).split("\0")


def scope(old_head, rebased, base, kdir, out):
    """Write the rebase-delta files into out and return scope.json's fields; raise Full to fall back."""
    old_head, rebased, base = commit(old_head), commit(rebased), commit(base)
    if not reviewed(os.path.join(kdir, "reviewed"), old_head):
        raise Full(f"no review recorded for {old_head}")
    old_base = git("merge-base", old_head, base).strip()
    old_range, new_range = f"{old_base}..{old_head}", f"{base}..{rebased}"
    if git("rev-list", "--count", old_range) != git("rev-list", "--count", new_range):
        raise Full("the rebase changed the number of commits")
    # The default creation factor shows a rewritten resolution as a dropped plus an added commit.
    range_diff = git("range-diff", "--no-color", "--creation-factor=100", old_range, new_range)
    kept, commits, keep = [], [], False
    for line in range_diff.splitlines(keepends=True):
        m = PAIR_RE.match(line)
        if m:
            if m.group(2) in "<>":
                raise Full("a commit has no counterpart across the rebase")
            keep = m.group(2) == "!"
            if keep:
                commits += [m.group(1), m.group(3)]
        if keep:
            kept.append(line)
    if not commits:
        raise Full("no commit changed in the rebase")
    fixes = git("diff", "--no-color", f"{rebased}..HEAD")
    if len(kept) + len(fixes.splitlines()) > MAX_LINES:
        raise Full(f"the rebase delta is over {MAX_LINES} lines")
    fixed = names("diff", f"{rebased}..HEAD")
    touched = names("show", "--no-color", "--format=", *commits)
    files = sorted(set(touched + fixed) - {""})
    # An empty pathspec would list every upstream commit.
    upstream = git("log", "--no-color", "--stat", f"{old_base}..{base}", "--", *files) if files else ""
    paths = {}
    for key, name, text in (("range_diff", "range-diff.txt", "".join(kept)),
                            ("fixes", "fixes.diff", fixes), ("upstream", "upstream.txt", upstream)):
        paths[key] = os.path.join(out, name)
        with open(paths[key], "w", encoding="utf-8") as fh:
            fh.write(text)
    return {"mode": "rebase-delta", "reason": "only the rebase delta changed", "old_head": old_head,
            "files": files, **paths}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-head", required=True)
    ap.add_argument("--rebased", required=True)
    ap.add_argument("--base", required=True)
    args = ap.parse_args()
    try:
        kdir = os.path.join(os.path.abspath(git("rev-parse", "--git-common-dir").strip()), "kitchen-sink")
        # Per-worktree, so concurrent /shepherd-pr runs in other worktrees don't clobber it.
        out = os.path.join(os.path.abspath(git("rev-parse", "--git-dir").strip()), "kitchen-sink", "scope")
    except Full as exc:
        sys.exit(f"review_scope: {exc}")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    try:
        result = scope(args.old_head, args.rebased, args.base, kdir, out)
    except Full as exc:
        result = {"mode": "full", "reason": str(exc)}
    path = os.path.join(out, "scope.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"old_head": args.old_head, **result}, fh, indent=2)
    print(path)


if __name__ == "__main__":
    main()
