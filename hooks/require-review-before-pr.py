#!/usr/bin/env python3
"""Multi-event hook: require `/code-review-intense-flow` before opening a PR.

Purpose
-------
The fix-gh-issue workflow requires `/code-review-intense-flow` against the
current HEAD before a PR is opened or marked ready. Prose instructions kept
getting skipped, so this hook adds a mechanical gate. One script handles three
events, dispatching on ``hook_event_name`` in the payload:

- ``PostToolUse`` (matcher ``Skill``): when the Skill tool invokes
  ``code-review-intense-flow`` (or ``kitchen-sink:code-review-intense-flow``),
  RECORD a marker for the current HEAD SHA.
- ``UserPromptSubmit``: when the user's prompt starts with
  ``/code-review-intense-flow`` (or ``/kitchen-sink:code-review-intense-flow``),
  RECORD the same marker. Never prints anything (UserPromptSubmit stdout is
  added to the model's context) and never blocks the prompt.
- ``PreToolUse`` (matcher ``Bash``): GATE ``gh pr create`` / ``gh pr ready``
  (but not ``gh pr ready --undo``) on ``fix-NNN`` branches. Denies when the
  current HEAD has no complete marker, or when the same command also runs
  ``git commit`` (HEAD at PreToolUse time is the pre-commit SHA, so the marker
  check would be checking the wrong commit).

Incremental reviews: a review invoked with ``scope=<path>``, where the path is
this worktree's ``<git-dir>/kitchen-sink/scope/scope.json`` (written by
``skills/shepherd-pr-repair/review_scope.py``) and its ``mode`` is
``incremental``, covers only ``<since>..HEAD``. Its marker reads
``<stamp> <source> incremental <since> complete`` when ``since`` has a
complete marker and is an ancestor of HEAD and the scope's ``head`` is HEAD,
else ``... partial``; any other ``scope=`` the hook can't verify records
``partial`` too. A ``full`` or ``rebase-delta`` scope, or none, records the
two-token full marker ``<stamp> <source>``. Each link is checked once, when
recorded, so the gate reads only HEAD's marker. A not-complete result never
overwrites a complete marker and writes no patch marker.

Markers live at ``<git-common-dir>/kitchen-sink/reviewed/<full-sha>``, so they
are shared across worktrees of the same repository and never tracked by git.
A new commit moves HEAD, so any review-fix commit requires a re-review.

Rebases: on a ``fix-NNN`` branch, recording also writes
``reviewed/patch/<branch>/<patch-id>``, where the
patch-id is ``git patch-id --stable`` of the branch's cumulative diff against
its merge-base with the default branch (``origin/HEAD``, then ``origin/main``,
``origin/master``, ``main``, ``master``). When HEAD has no complete marker, the
gate allows the command if the current diff has a patch-id recorded for the
same branch, so another branch with an identical diff does not inherit the
review. A clean
rebase (or a squash/reword) leaves the diff unchanged and passes; resolving a
conflict changes the diff and requires a re-review. ``patch-id`` ignores line
numbers and whitespace but not context lines, so a rebase where upstream edited
lines next to a hunk also changes the fingerprint and needs a re-review.

Escape hatch: ``KITCHEN_SINK_ALLOW_UNREVIEWED_PR=1`` in the hook's OWN
environment (i.e. the environment Claude Code was launched from) allows the
command. An inline ``KITCHEN_SINK_ALLOW_UNREVIEWED_PR=1 gh pr create`` prefix in
the command string does NOT bypass — that is something the model could type.

Fail-open contract
------------------
Anything uncertain results in ALLOW / no-op (print nothing, exit 0): bad JSON,
missing fields, not a git repo, git errors or timeouts, detached HEAD, a branch
that is not ``fix-NNN``, or any exception whatsoever. Invoked as
``python3 <path>``.

Known accepted gaps (fail-open by design)
-----------------------------------------
- The marker records that the review was *invoked* on that HEAD, not that it
  passed clean. The fix-and-re-review loop is still the workflow's job.
- A complete chain is checked against plain files like the marker itself:
  the scope file and the ``since`` marker, not what the reviewers read.
- Detection is a simple regex over the command string; shell aliases, wrapper
  scripts, ``eval``, ``gh api`` calls that create PRs, or a ``cd`` to another
  repo earlier in the chain evade or confuse it. ``gh`` invoked by path
  (``/usr/bin/gh``, ``./gh``) or via an alias/wrapper is not detected.
- Quoted mentions such as ``echo 'gh pr create'`` are allowed (the quote, not
  whitespace, precedes ``gh``). An unquoted mention such as
  ``echo gh pr create`` false-positives (deny), which is harmless.
- The marker is a plain file: anything that writes a complete
  ``<git-common-dir>/kitchen-sink/reviewed/<sha>`` satisfies the gate. This is
  a drift guardrail against skipped reviews, not a security boundary.
- Only ``fix-<digits>`` branches are gated; the repo checked is the payload
  ``cwd``, regardless of ``gh -R`` / ``git -C`` targets in the command.
- A patch-id match proves the diff is textually the same as a reviewed one,
  not that it still behaves the same: an upstream change that breaks the branch
  without a textual conflict (a renamed callee, say) is not caught. That is
  CI's job. The patch-id fallback is skipped (no patch marker written, no
  match, so the gate denies) when no default-branch ref resolves, the branch
  diff is empty, or a git call in it fails (including a diff that is not
  valid in the locale encoding); it allows only if the shared
  TIME_BUDGET runs out.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import time

ENV_BYPASS = "KITCHEN_SINK_ALLOW_UNREVIEWED_PR"
# Each git call gets at most GIT_TIMEOUT, and all calls together share
# TIME_BUDGET, which must stay well below every hooks.json timeout for this
# script (10s). Once the budget runs out, git() returns None and the hook
# fails open; if the harness kills the hook instead, it also allows silently.
GIT_TIMEOUT = 2  # seconds
TIME_BUDGET = 7  # seconds
_deadline = None

BASE_REFS = (
    "refs/remotes/origin/HEAD",
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
    "refs/heads/main",
    "refs/heads/master",
)

REVIEW_SKILLS = {"code-review-intense-flow", "kitchen-sink:code-review-intense-flow"}

PROMPT_RE = re.compile(r"^/(?:kitchen-sink:)?code-review-intense-flow(?:\s|$)")
SCOPE_RE = re.compile(r"(?:^|\s)scope=(\S+)")
SHA_RE = re.compile(r"[0-9a-f]{40,64}")

FIX_BRANCH_RE = re.compile(r"^fix-\d+$")

# Copy of GIT_COMMIT_RE in suggest-review-after-commit.py (hyphenated filename
# blocks import); test_suggest_review_after_commit.py asserts they stay identical.
GIT_COMMIT_RE = re.compile(
    r"""(?:^|[;&|]|\bthen\b|\bdo\b|&&|\|\|)   # statement boundary
        \s*git\b                               # the git binary
        (?:\s+-{1,2}[^\s]+(?:\s+[^\s-][^\s]*)?)*  # optional global flags/args
        \s+commit(?![-\w])                     # the commit subcommand (not commit-tree)
    """,
    re.VERBOSE,
)

# `gh [global flags] pr create|ready`, e.g. `gh -R o/r pr create`.
GH_PR_RE = re.compile(
    r"""(?:^|[\s(])gh
        (?:\s+-{1,2}[^\s]+(?:\s+[^\s-][^\s]*)?)*  # optional global flags/args
        \s+pr\s+(create|ready)(?![-\w])
    """,
    re.VERBOSE,
)

SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;&|\n]")
UNDO_RE = re.compile(r"(?<!\S)--undo(?!\S)")

CHAINED_REASON = (
    "This command chains `git commit` with `gh pr create`/`gh pr ready`. "
    "The require-review-before-pr hook checks the review marker at PreToolUse "
    "time, when HEAD is still the pre-commit SHA, so it cannot verify the "
    "commit you are about to create. Commit in a separate Bash call, run "
    "`/code-review-intense-flow` (via the Skill tool) against the new HEAD, "
    "then open or ready the PR in its own call."
)

UNREVIEWED_REASON = (
    "No `/code-review-intense-flow` run is recorded for the current HEAD ({sha}) "
    "on this fix-NNN branch. The fix-gh-issue workflow requires it before "
    "`gh pr create` / `gh pr ready`. Run `/code-review-intense-flow` via the "
    "Skill tool against the current HEAD first. Any review-fix commit moves "
    "HEAD and needs a re-review before the PR. An incremental review whose "
    "chain doesn't reach a full review needs a full `/code-review-intense-flow` "
    "run (no `scope=`). A clean rebase of a reviewed "
    "branch passes automatically; this branch's diff differs from every "
    "reviewed one (e.g. a resolved conflict). Only the user (not the model) "
    "can bypass this, by setting KITCHEN_SINK_ALLOW_UNREVIEWED_PR=1 in the "
    "environment Claude Code was launched from."
)


def git(cwd, *args, stdin=None):
    """Run git in cwd; return stripped stdout, or None on any failure."""
    timeout = GIT_TIMEOUT
    if _deadline is not None:
        timeout = min(timeout, _deadline - time.monotonic())
        if timeout <= 0:
            return None
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def head_sha(cwd):
    sha = git(cwd, "rev-parse", "--verify", "HEAD")
    if sha and re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return sha
    return None


def marker_dir(cwd):
    common = git(cwd, "rev-parse", "--git-common-dir")
    if not common:
        return None
    if not os.path.isabs(common):
        common = os.path.join(cwd, common)
    return os.path.join(common, "kitchen-sink", "reviewed")


def base_ref(cwd):
    """First BASE_REFS entry that exists, or None."""
    out = git(cwd, "for-each-ref", "--format=%(refname)", *BASE_REFS)
    if not out:
        return None
    present = set(out.splitlines())
    return next((ref for ref in BASE_REFS if ref in present), None)


def branch_patch_id(cwd):
    """Stable patch-id of the diff from the default-branch merge-base to HEAD."""
    base = base_ref(cwd)
    if not base:
        return None
    mb = git(cwd, "merge-base", base, "HEAD")
    if not mb:
        return None
    diff = git(cwd, "diff", "--no-color", "--no-ext-diff", "--no-textconv", mb, "HEAD")
    if not diff:
        return None
    out = git(cwd, "patch-id", "--stable", stdin=diff + "\n")
    pid = out.split()[0] if out else None
    if pid and re.fullmatch(r"[0-9a-f]{40,64}", pid):
        return pid
    return None


# skills/shepherd-pr-repair/review_scope.py loads this module for complete().
def complete(path):
    """True if the direct marker at path records a full review or a complete chain."""
    try:
        with open(path, encoding="utf-8") as fh:
            tokens = fh.read().split()
    except (OSError, UnicodeError):
        return False
    return len(tokens) == 2 or (len(tokens) == 5 and tokens[2] == "incremental" and tokens[4] == "complete")


def scope_suffix(cwd, sha, mdir, args):
    """(marker text after `<stamp> <source>`, complete?) for a review invoked with args."""
    m = SCOPE_RE.search(args) if isinstance(args, str) else None
    if not m:
        return "", True
    gdir = git(cwd, "rev-parse", "--git-dir")
    if not gdir:
        return " partial", False
    # Resolve only the directory: a scope.json symlinked elsewhere must not pass as the canonical file.
    canonical = os.path.join(os.path.realpath(os.path.join(cwd, gdir, "kitchen-sink", "scope")), "scope.json")
    if os.path.realpath(os.path.join(cwd, m.group(1))) != canonical:
        return " partial", False
    try:
        with open(canonical, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return " partial", False
    mode = data.get("mode") if isinstance(data, dict) else None
    if mode in ("full", "rebase-delta"):
        return "", True
    since = data.get("since") if mode == "incremental" else None
    if not isinstance(since, str) or not SHA_RE.fullmatch(since):
        return " partial", False
    ok = (data.get("head") == sha and complete(os.path.join(mdir, since))
          and git(cwd, "merge-base", since, "HEAD") == since)
    return f" incremental {since} {'complete' if ok else 'partial'}", ok


def record(cwd, source, args=None):
    sha = head_sha(cwd)
    mdir = marker_dir(cwd)
    if not sha or not mdir:
        return
    os.makedirs(mdir, exist_ok=True)
    suffix, ok = scope_suffix(cwd, sha, mdir, args)
    path = os.path.join(mdir, sha)
    if not ok and complete(path):
        return  # never downgrade a complete marker
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"{stamp} {source}{suffix}\n")
    if not ok:
        return
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or not FIX_BRANCH_RE.match(branch):
        return
    pid = branch_patch_id(cwd)
    if not pid:
        return
    pdir = os.path.join(mdir, "patch", branch)
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, pid), "w", encoding="utf-8") as fh:
        fh.write(f"{stamp} {source} {sha}\n")


def gated_pr_command(command):
    """True if any segment runs `gh pr create` or `gh pr ready` (not --undo)."""
    for segment in SEGMENT_SPLIT_RE.split(command):
        m = GH_PR_RE.search(segment)
        if not m:
            continue
        if m.group(1) == "ready" and UNDO_RE.search(segment):
            continue
        return True
    return False


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def handle_skill(payload, cwd):
    if payload.get("tool_name") not in (None, "Skill"):
        return
    skill = (payload.get("tool_input") or {}).get("skill")
    if not isinstance(skill, str):
        return
    if skill.strip().lstrip("/") in REVIEW_SKILLS:
        record(cwd, "skill", payload["tool_input"].get("args"))


def handle_prompt(payload, cwd):
    prompt = payload.get("prompt")
    m = PROMPT_RE.match(prompt.lstrip()) if isinstance(prompt, str) else None
    if m:
        record(cwd, "prompt", prompt.lstrip()[m.end():])


def handle_bash(payload, cwd):
    if payload.get("tool_name") not in (None, "Bash"):
        return
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not gated_pr_command(command):
        return
    if os.environ.get(ENV_BYPASS) == "1":
        return
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or not FIX_BRANCH_RE.match(branch):
        return
    if GIT_COMMIT_RE.search(command):
        deny(CHAINED_REASON)
        return
    sha = head_sha(cwd)
    mdir = marker_dir(cwd)
    if not sha or not mdir:
        return
    if complete(os.path.join(mdir, sha)):
        return
    pid = branch_patch_id(cwd)
    if pid is None and _deadline is not None and time.monotonic() >= _deadline:
        return  # out of time budget: fail open rather than deny unverified
    if pid and os.path.isfile(os.path.join(mdir, "patch", branch, pid)):
        return
    deny(UNREVIEWED_REASON.format(sha=sha))


HANDLERS = {
    "PostToolUse": handle_skill,
    "UserPromptSubmit": handle_prompt,
    "PreToolUse": handle_bash,
}


def main():
    global _deadline
    _deadline = time.monotonic() + TIME_BUDGET
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    handler = HANDLERS.get(payload.get("hook_event_name"))
    cwd = payload.get("cwd")
    if handler is None or not isinstance(cwd, str) or not os.path.isdir(cwd):
        return
    handler(payload, cwd)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open on any unexpected error.
        pass
    sys.exit(0)
