#!/usr/bin/env python3
"""Scope a re-review to what changed since a reviewed head.

  review_scope.py --old-head SHA --rebased SHA --base REF
  review_scope.py --since SHA

Rebase mode (/shepherd-pr): run in the repo after the rebase; SHA is the
pre-rebase PR head, --rebased the HEAD right after the rebase; `mode` is
`rebase-delta` or `full`. See
docs/superpowers/specs/2026-11-14-rebase-scoped-review-design.md.

Since mode (/fix-gh-issue rounds 2+): SHA is the head the last round reviewed;
`mode` is `incremental` (review SHA..HEAD) or `full`. See
docs/superpowers/specs/2026-11-28-incremental-review-rounds-design.md.

Writes the scope files to <git-dir>/kitchen-sink/scope/ (per worktree, replaced
on each run) and prints the path of its scope.json, which carries a `reason`.
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


# Copy of complete() in hooks/require-review-before-pr.py (hyphenated filename
# blocks import); test_review_scope.py pins them to the same answers.
def complete(path):
    """True if the direct marker at path records a full review or a complete chain."""
    try:
        with open(path, encoding="utf-8") as fh:
            tokens = fh.read().split()
    except (OSError, UnicodeError):
        return False
    return len(tokens) == 2 or (len(tokens) == 5 and tokens[2] == "incremental" and tokens[4] == "complete")


def reviewed(mdir, sha):
    if complete(os.path.join(mdir, sha)):
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


def since_scope(since, kdir):
    """scope.json's fields for an incremental review of since..HEAD; raise Full to fall back."""
    since, head = commit(since), commit("HEAD")
    if not complete(os.path.join(kdir, "reviewed", since)):
        raise Full(f"no complete review recorded for {since}")
    if since == head:
        raise Full("no commits since the reviewed head")
    if git("merge-base", since, head).strip() != since:
        raise Full(f"{since} is not an ancestor of HEAD")
    return {"mode": "incremental", "reason": "only commits since the reviewed head", "since": since, "head": head}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--old-head")
    ap.add_argument("--rebased")
    ap.add_argument("--base")
    args = ap.parse_args()
    rebase = (args.old_head, args.rebased, args.base)
    if args.since is not None and rebase != (None, None, None):
        ap.error("--since excludes --old-head, --rebased and --base")
    if args.since is None and None in rebase:
        ap.error("give --since, or all of --old-head, --rebased and --base")
    try:
        kdir = os.path.join(os.path.abspath(git("rev-parse", "--git-common-dir").strip()), "kitchen-sink")
        # Per-worktree, so concurrent /shepherd-pr runs in other worktrees don't clobber it.
        out = os.path.join(os.path.abspath(git("rev-parse", "--git-dir").strip()), "kitchen-sink", "scope")
    except Full as exc:
        sys.exit(f"review_scope: {exc}")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    given = {"since": args.since} if args.since is not None else {"old_head": args.old_head}
    try:
        if args.since is not None:
            result = since_scope(args.since, kdir)
        else:
            result = scope(args.old_head, args.rebased, args.base, kdir, out)
    except Full as exc:
        result = {"mode": "full", "reason": str(exc)}
    path = os.path.join(out, "scope.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({**given, **result}, fh, indent=2)
    print(path)


if __name__ == "__main__":
    main()
