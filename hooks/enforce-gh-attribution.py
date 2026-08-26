#!/usr/bin/env python3
"""PreToolUse hook: hard-enforce the `gh` attribution footer.

Purpose
-------
This is a *defense-in-depth backstop* that blocks a mutating `gh` write (issue/PR
comment, issue/PR create, issue/PR edit-with-body, and `gh api` POST/PATCH to a
comment/issue/pull/review/reply endpoint) whose resolved body lacks the plugin's
attribution footer. The skills that build these bodies remain the *primary*
mechanism for adding attribution; this hook only catches the cases they miss.

Fail-open contract
-------------------
The hook emits a `deny` ONLY when it can positively resolve a concrete body that
lacks the footer. ANY uncertainty — unparseable input, compound/redirected
commands, heredocs/stdin bodies, dynamic `$(...)`/backtick substitution,
unreadable body files, an unrecognized subcommand, or any exception whatsoever —
results in ALLOW (print nothing, exit 0). It is invoked as `python3 <path>`.

Decision anchor
---------------
A body is "attributed" if it contains the version-independent substring
`[Claude Code](https://claude.com/claude-code)` — common to both the
`🤖 Generated with ...` footer and the `🤖 Review by ...` review-reply footer.
The running model version is never hardcoded or matched.
"""

import json
import os
import shlex
import sys

ANCHOR = "[Claude Code](https://claude.com/claude-code)"

SHELL_OPERATORS = {"|", "||", "&&", ";", "&", "<", ">", ">>", "2>"}

DENY_REASON = (
    "This gh command posts a body without the required attribution footer. "
    "Append the footer from docs/attribution.md "
    "(\U0001F916 Generated with [Claude Code](https://claude.com/claude-code) "
    "· <running model version>) and retry."
)


def allow():
    """Allow / do nothing: print nothing, exit 0."""
    sys.exit(0)


def deny():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }))
    sys.exit(0)


def is_dynamic(value):
    """A body whose real content is shell-substituted is unknowable."""
    return "$(" in value or "`" in value


def read_body_file(path, cwd):
    """Return file contents, or None if unreadable (fail-open)."""
    try:
        if cwd and not os.path.isabs(path):
            path = os.path.join(cwd, path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None


def resolve_issue_pr_body(args, cwd):
    """Resolve the body for a `gh issue`/`gh pr` subcommand.

    Returns (found, body) where found indicates a body flag was present and
    body is the resolved text, or None if the body is unresolvable (fail-open).
    """
    found = False
    body = None
    i = 0
    while i < len(args):
        tok = args[i]
        inline = None
        file_path = None
        if tok in ("--body", "-b"):
            if i + 1 < len(args):
                inline = args[i + 1]
                i += 1
        elif tok.startswith("--body="):
            inline = tok[len("--body="):]
        elif tok in ("--body-file", "-F"):
            if i + 1 < len(args):
                file_path = args[i + 1]
                i += 1
        elif tok.startswith("--body-file="):
            file_path = tok[len("--body-file="):]
        else:
            i += 1
            continue

        found = True
        if inline is not None:
            if is_dynamic(inline):
                return True, None
            body = inline
        elif file_path is not None:
            contents = read_body_file(file_path, cwd)
            if contents is None:
                return True, None
            body = contents
        i += 1
    return found, body


UNRESOLVABLE = "\0UNRESOLVABLE\0"


def _resolve_api_field(val, is_field, cwd):
    """Resolve a single `gh api` body= field value.

    Only `-F`/`--field` treats a leading `@` as a file. Returns the resolved
    text, or UNRESOLVABLE (fail-open) for unreadable files / dynamic bodies.
    """
    if is_field and val.startswith("@"):
        contents = read_body_file(val[1:], cwd)
        return contents if contents is not None else UNRESOLVABLE
    return UNRESOLVABLE if is_dynamic(val) else val


def resolve_api_body(args, cwd):
    """Resolve method + endpoint + body for a `gh api` invocation.

    Returns (matched, body). matched is True when this is a POST/PATCH to a
    relevant endpoint with a resolvable body; body is the text (or None to
    fail-open when method/endpoint match but body is unresolvable).
    """
    method = None
    endpoint = None
    body = None
    body_found = False

    endpoint_needles = ("/comments", "/issues", "/pulls", "/reviews",
                        "/replies")

    i = 0
    while i < len(args):
        tok = args[i]
        if tok in ("-X", "--method"):
            if i + 1 < len(args):
                method = args[i + 1]
                i += 2
                continue
        elif tok.startswith("--method="):
            method = tok[len("--method="):]
            i += 1
            continue
        elif tok in ("-f", "--raw-field", "-F", "--field"):
            is_field = tok in ("-F", "--field")
            if i + 1 < len(args):
                field = args[i + 1]
                i += 2
                if field.startswith("body="):
                    body_found = True
                    body = _resolve_api_field(field[len("body="):], is_field, cwd)
                continue
        elif tok.split("=", 1)[0] in ("--raw-field", "--field") and "=" in tok:
            # --field=body=... / --raw-field=body=... forms
            key, val = tok.split("=", 1)
            is_field = key == "--field"
            if val.startswith("body="):
                body_found = True
                body = _resolve_api_field(val[len("body="):], is_field, cwd)
            i += 1
            continue

        # positional / other: the endpoint is a positional non-flag arg
        if not tok.startswith("-") and endpoint is None:
            endpoint = tok
        i += 1

    if method is None or method.upper() not in ("POST", "PATCH"):
        return False, None
    if endpoint is None or not any(n in endpoint for n in endpoint_needles):
        return False, None
    if not body_found:
        return False, None
    if body == UNRESOLVABLE or body is None:
        return False, None
    return True, body


def main():
    raw = sys.stdin.read()
    data = json.loads(raw)

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        allow()
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd:
        allow()
    cwd = data.get("cwd")

    # Fast path: not a gh command.
    if "gh" not in cmd:
        allow()

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        allow()

    if not tokens:
        allow()

    # Compound / redirected / heredoc → unresolvable → fail-open.
    for tok in tokens:
        if tok in SHELL_OPERATORS or tok.startswith("<<"):
            allow()

    if os.path.basename(tokens[0]) != "gh":
        allow()

    args = tokens[1:]
    if not args:
        allow()

    # Drop global flags before the subcommand is not needed here; gh's
    # top-level command is the first positional token.
    sub = args[0]

    if sub == "api":
        matched, body = resolve_api_body(args[1:], cwd)
        if not matched:
            allow()
        if ANCHOR in body:
            allow()
        deny()

    if sub in ("issue", "pr"):
        if len(args) < 2:
            allow()
        action = args[1]
        rest = args[2:]

        if action == "comment":
            found, body = resolve_issue_pr_body(rest, cwd)
            if not found or body is None:
                allow()
            if ANCHOR in body:
                allow()
            deny()

        if action == "create":
            found, body = resolve_issue_pr_body(rest, cwd)
            if not found or body is None:
                allow()
            if ANCHOR in body:
                allow()
            deny()

        if action == "edit":
            found, body = resolve_issue_pr_body(rest, cwd)
            if not found or body is None:
                allow()
            if ANCHOR in body:
                allow()
            deny()

        allow()

    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open on any unexpected error.
        sys.exit(0)
