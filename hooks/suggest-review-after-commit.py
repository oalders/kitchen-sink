#!/usr/bin/env python3
"""PostToolUse Bash hook: suggest reviews after a successful git commit.

This replaces an earlier ``prompt``-type hook that ran an LLM evaluation after
*every* Bash command. Even when that hook correctly decided a command was not a
commit and "stayed silent", the harness still surfaced a
"PostToolUse:Bash hook stopped continuation" notice, which interrupted every
multi-step workflow (fix-gh-issue, debugging sweeps, etc.) after each Bash call.

The gate is now deterministic and cheap: this script reads the PostToolUse
payload on stdin and, for anything that is not a *successful* ``git commit``,
exits silently with no output (zero interruption). Only on a real commit does it
emit ``additionalContext`` asking the model to categorize the changed files and
offer the relevant ``/*-review`` commands via AskUserQuestion, with
``/code-review-intense-flow`` listed first as the default. On ``fix-NNN``
branches (the fix-gh-issue workflow) it instead points only at
``/code-review-intense-flow``, which that workflow requires before a PR and the
require-review-before-pr hook enforces. If the branch cannot be determined it
falls back to the generic menu.

Bias: when in doubt, stay silent. A missed suggestion is harmless; a false
positive re-introduces the interruption this hook exists to remove.
"""

import json
import os
import re
import subprocess
import sys

FIX_BRANCH_RE = re.compile(r"^fix-\d+$")

# A `git commit` invocation: `git` (with optional global flags like -C path,
# -c key=val, --git-dir=...) followed by the `commit` subcommand. Anchored so it
# does not match `commit` appearing inside a commit message or an unrelated
# string. Word-boundary on `commit` so `git commit-tree` does not match.
GIT_COMMIT_RE = re.compile(
    r"""(?:^|[;&|]|\bthen\b|\bdo\b|&&|\|\|)   # statement boundary
        \s*git\b                               # the git binary
        (?:\s+-{1,2}[^\s]+(?:\s+[^\s-][^\s]*)?)*  # optional global flags/args
        \s+commit(?![-\w])                     # the commit subcommand (not commit-tree)
    """,
    re.VERBOSE,
)

# Flags that mean "not an actual commit was created", so we skip the suggestion.
NON_COMMITTING = re.compile(r"(?<!\S)(--help|-h|--dry-run)(?!\S)")

# Substrings in git output that indicate the commit did not happen.
FAILURE_MARKERS = (
    "nothing to commit",
    "no changes added to commit",
    "nothing added to commit",
    "fatal:",
    "error:",
)


def is_successful_commit(command: str, response) -> bool:
    """True only when the command created a commit that appears to have succeeded."""
    if not command or not GIT_COMMIT_RE.search(command):
        return False
    if NON_COMMITTING.search(command):
        return False

    # tool_response may be a dict (Bash) or a string; normalize to text we scan.
    text = ""
    if isinstance(response, dict):
        if response.get("interrupted"):
            return False
        text = f"{response.get('stdout', '')}\n{response.get('stderr', '')}"
    elif isinstance(response, str):
        text = response

    lowered = text.lower()
    if any(marker in lowered for marker in FAILURE_MARKERS):
        return False
    return True


SUGGESTION = """A git commit just succeeded. Suggest relevant reviews before moving on:

1. Run `git diff HEAD~1 --name-only` to list the committed files.
2. Categorize them:
   - frontend: `.tsx`/`.jsx`/`.vue`/`.svelte`/`.css`/`.scss`/`.sass`/`.less`/`.html`, or under `components/`/`pages/`/`app/`/`assets/`/`src/components/`/`public/`/`static/`;
   - security: paths with `auth`/`login`/`password`/`token`/`session`/`crypto`/`api/`/`permissions`/`roles`, plus `.env*`/`secrets.*`/`credentials.*`/`.htaccess`/`security.txt`/`.env.example`;
   - playwright/e2e: `.spec.`/`.test.` files or `e2e/`/`playwright/`/`__tests__/e2e/` dirs;
   - agent-instructions: `CLAUDE.md`/`AGENTS.md`/`.cursorrules`/`.github/copilot-instructions.md`, or under `.cursor/rules/`/`.claude/` (any `.md`), or `.md` under `commands/`/`skills/`/`agents/` when the repo has `.claude-plugin/plugin.json`;
   - other: everything else.
3. Use the AskUserQuestion tool (multiSelect: true). List Intense-flow `/code-review-intense-flow` FIRST as the default option (it routes to the general reviewer, security, and the path-matched specialists automatically), then ONLY the specialist review types whose files are present, plus Generic as a fallback: Frontend `/frontend-review`, Playwright `/playwright-review`, Security `/security-review`, Agent-Instructions `/agent-instructions-review`, Generic `/request-review`.
4. Run each selected review sequentially and summarize the findings afterward.
5. List file categories, not every file. If the user declines, drop it and continue — do not nag.

If you are in the middle of another workflow (e.g. fix-gh-issue) that has its own review step, defer to that workflow instead of interrupting it here."""


FIX_BRANCH_SUGGESTION = """A git commit just succeeded on a fix-NNN branch (the fix-gh-issue workflow).

That workflow requires `/code-review-intense-flow` (run it via the Skill tool) against the current HEAD before `gh pr create` / `gh pr ready`, and the require-review-before-pr hook enforces it: the PR command is denied until intense-flow has been run on this exact HEAD SHA. Any later review-fix commit moves HEAD and needs a re-review. Do not substitute a single specialist review (e.g. `/security-review`) or offer a menu of reviewers — intense-flow already routes to them.

If you are mid-way through the workflow's own review step, continue it; otherwise run `/code-review-intense-flow` before opening or readying the PR."""


def on_fix_branch(cwd) -> bool:
    """True only when git positively reports a fix-<digits> branch in cwd."""
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    return bool(FIX_BRANCH_RE.match(proc.stdout.strip()))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # fail silent

    command = (payload.get("tool_input") or {}).get("command", "")
    response = payload.get("tool_response")

    if not is_successful_commit(command, response):
        return 0  # silent no-op for everything that is not a successful commit

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    FIX_BRANCH_SUGGESTION
                    if on_fix_branch(payload.get("cwd"))
                    else SUGGESTION
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
