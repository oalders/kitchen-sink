#!/usr/bin/env python3
"""Helpers for the codex-review-loop skill.

Subcommands (all print JSON on stdout):

  mode                      Effective Codex review mode for this repo, plus
                            the codex version and outer-sandbox state.
  local-review --base REF   Run `codex exec review` and classify its findings.
                            A review that could not read the diff (Codex's
                            own sandbox failed) is a tool error, not a pass.
  gh-wait --sha SHA         Wait for the Codex GitHub bot to review SHA
                            (--trigger-comment ID to count its +1 reaction and
                            time the window from it; --timeout then only caps
                            the call, reporting `pending` if the window is open).
  gh-threads                List unresolved review threads opened by the bot.
  gh-resolve ID [ID ...]    Resolve review threads by GraphQL node id.

Posting comments (`@codex review`, thread replies) is deliberately NOT done
here: those go through plain `gh` calls in the skill so the attribution hook
can see them.

Outer-sandbox bypass policy: see SKILL.md.

Exit codes: 0 = clean / success, 1 = blocking findings (or timeout or
pending for gh-wait), 2 = usage or tool error.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

CONFIG_KEY = "kitchen-sink.codexReview"
OUTER_SANDBOX_KEY = "kitchen-sink.codexOuterSandbox"
TIMEOUT_MINUTES_KEY = "kitchen-sink.codexTimeoutMinutes"
TIMEOUT_ACTION_KEY = "kitchen-sink.codexTimeoutAction"
TIMEOUT_ACTIONS = ("stop", "proceed")
ROUNDS_KEY = "kitchen-sink.codexRounds"
ROUNDS_RANGE = range(1, 6)
ROUNDS_DEFAULT = 3
BYPASS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
BWRAP_MARKER = "error building bubblewrap command"
MODES = ("off", "local", "github")
BOT_LOGIN = "chatgpt-codex-connector[bot]"
BLOCKING = {"P0", "P1", "P2"}

# Local `codex exec review` output: "- [P1] Title — /abs/path.py:3-3"
LOCAL_FINDING_RE = re.compile(r"^- \[(P\d)\] (.+?)(?: — (\S+?):(\d+)(?:-(\d+))?)?\s*$")
# Bot inline comment: "**<sub><sub>![P1 Badge](...)</sub></sub>  Title**"
BOT_BADGE_RE = re.compile(r"!\[(P\d) Badge\]\([^)]*\)(?:</sub>)*\s*(.*?)\*\*", re.S)
BOT_REVIEWED_COMMIT_RE = re.compile(r"\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`")
BOT_CLEAN_MARKER = "Didn't find any major issues"


class ToolError(Exception):
    pass


def run(cmd, check=True, **kw):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and proc.returncode != 0:
        raise ToolError(f"{' '.join(cmd)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


# --- mode -------------------------------------------------------------------


def resolve_mode(configured):
    """Return (mode, source). Unset means off: Codex runs only when opted in."""
    if configured:
        value = configured.strip().lower()
        if value not in MODES:
            raise ToolError(f"{CONFIG_KEY}={configured!r} is not one of {', '.join(MODES)}")
        return value, "git-config"
    return "off", "default"


def resolve_outer_sandbox(configured, under_nono):
    """Return (enabled, source). Config wins; unset means on under nono."""
    if configured in ("true", "false"):
        return configured == "true", "git-config"
    return (True, "nono") if under_nono else (False, "default")


def resolve_bot_wait(minutes, action):
    """Return how long gh-wait polls and what a timeout means. Unset keeps 30 min / stop."""
    out = {"minutes": 30, "action": "stop", "source": "default"}
    if minutes:
        try:
            out["minutes"] = int(minutes)
        except ValueError:
            out["minutes"] = 0
        if out["minutes"] <= 0:
            raise ToolError(f"{TIMEOUT_MINUTES_KEY}={minutes!r} is not a positive integer")
        out["source"] = "git-config"
    if action:
        out["action"] = action.strip().lower()
        if out["action"] not in TIMEOUT_ACTIONS:
            raise ToolError(f"{TIMEOUT_ACTION_KEY}={action!r} is not one of {', '.join(TIMEOUT_ACTIONS)}")
        out["source"] = "git-config"
    return out


def resolve_rounds(rounds):
    """Return the fix-round cap. Unset keeps the default; anything outside 1-5 fails closed."""
    if not rounds:
        return {"value": ROUNDS_DEFAULT, "source": "default"}
    try:
        value = int(rounds)
    except ValueError:
        value = 0
    if value not in ROUNDS_RANGE:
        raise ToolError(f"{ROUNDS_KEY}={rounds!r} is not an integer from 1 to 5")
    return {"value": value, "source": "git-config"}


def nono_detected(cap_file, proc_status):
    """Best-effort check that nono really confines this process.

    Landlock offers no way to ask "am I confined?", so this only raises the bar
    above a bare NONO_CAP_FILE=x: the variable must name nono's capability file
    (JSON with an `fs` list) and, on Linux, the kernel must report NoNewPrivs,
    which Landlock requires of an unprivileged process. proc_status is None
    where /proc/self/status does not exist (macOS).
    """
    if not cap_file:
        return False
    try:
        with open(cap_file) as fh:
            caps = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(caps, dict) or not isinstance(caps.get("fs"), list):
        return False
    if proc_status is None:
        return True
    return re.search(r"^NoNewPrivs:\s*1\s*$", proc_status, re.M) is not None


def read_proc_status():
    if not sys.platform.startswith("linux"):
        return None
    try:
        with open("/proc/self/status") as fh:
            return fh.read()
    except OSError:
        return ""


def outer_sandbox():
    # --local only: global, system, or included config must not enable the bypass.
    proc = run(["git", "config", "--local", "--type=bool", "--get", OUTER_SANDBOX_KEY], check=False)
    if proc.returncode not in (0, 1):
        raise ToolError(f"{OUTER_SANDBOX_KEY} is not a boolean: {proc.stderr.strip()}")
    # nono sets NONO_CAP_FILE for sandboxed processes; `nono why --self` uses it
    # to decide whether it is running inside a sandbox.
    under_nono = nono_detected(os.environ.get("NONO_CAP_FILE"), read_proc_status())
    enabled, source = resolve_outer_sandbox(proc.stdout.strip(), under_nono)
    return {"enabled": enabled, "source": source}


def local_config(key):
    proc = run(["git", "config", "--local", "--get", key], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def bot_wait():
    return resolve_bot_wait(local_config(TIMEOUT_MINUTES_KEY), local_config(TIMEOUT_ACTION_KEY))


def cmd_mode(_args):
    configured = local_config(CONFIG_KEY)
    codex = shutil.which("codex")
    mode, source = resolve_mode(configured)
    out = {"mode": mode, "source": source, "codex": codex, "outer_sandbox": outer_sandbox()}
    out["bot_wait"] = bot_wait()
    out["rounds"] = resolve_rounds(local_config(ROUNDS_KEY))
    if mode != "off" and not codex:
        out["error"] = f"mode is {mode} but the codex CLI is not on PATH"
    elif mode != "off":
        try:
            ver = run([codex, "--version"], timeout=30)
            out["codex_version"] = ([l.strip() for l in ver.stdout.splitlines() if l.strip()] or [""])[-1]
        except (ToolError, OSError, subprocess.TimeoutExpired) as exc:
            out["error"] = f"{codex} is on PATH but cannot be executed here: {str(exc)[-500:]}"
    print(json.dumps(out))
    return 2 if "error" in out else 0


# --- local review -----------------------------------------------------------


def parse_local_review(text):
    findings = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = LOCAL_FINDING_RE.match(line)
        if not m:
            continue
        body = []
        for follow in lines[i + 1 :]:
            if LOCAL_FINDING_RE.match(follow):
                break
            body.append(follow.strip())
        findings.append(
            {
                "priority": m.group(1),
                "title": m.group(2).strip(),
                "path": m.group(3),
                "line": int(m.group(4)) if m.group(4) else None,
                "body": " ".join(b for b in body if b),
            }
        )
    blocking = [f for f in findings if f["priority"] in BLOCKING]
    advisory = [f for f in findings if f["priority"] not in BLOCKING]
    return {"clean": not blocking, "blocking": blocking, "advisory": advisory}


def blind_review_reason(text, stderr, result):
    """Return why a findings-free review never actually saw the diff, else None."""
    if result["blocking"] or result["advisory"]:
        return None
    if BWRAP_MARKER in f"{text}\n{stderr}".lower():
        return f"Codex's sandbox failed to start ({BWRAP_MARKER})"
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if first.lower().startswith("review blocked"):
        return f"Codex reported: {first}"
    return None


def review_command(codex, base, out_path, title, bypass):
    cmd = [codex, "exec", "review", "--base", base, "--ephemeral", "-o", out_path]
    if title:
        cmd += ["--title", title]
    return (cmd + [BYPASS_FLAG]) if bypass else cmd


def cmd_local_review(args):
    codex = shutil.which("codex")
    if not codex:
        raise ToolError("codex CLI is not on PATH")
    sandbox = outer_sandbox()
    out_dir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    fd, out_path = tempfile.mkstemp(prefix="codex-review-", suffix=".txt", dir=out_dir)
    os.close(fd)
    cmd = review_command(codex, args.base, out_path, args.title, sandbox["enabled"])
    try:
        proc = run(cmd, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"codex review timed out after {args.timeout}s") from exc
    with open(out_path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        raise ToolError(f"codex review produced no output ({out_path})")
    result = parse_local_review(text)
    reason = blind_review_reason(text, proc.stderr, result)
    if reason:
        msg = f"codex review could not inspect the diff: {reason} (raw output: {out_path})"
        if sandbox["enabled"]:
            msg += (
                f"; the outer-sandbox bypass was already on (source: {sandbox['source']}),"
                " so this needs investigation"
            )
        else:
            msg += (
                "; if an outer sandbox confines this process, ask the user to run:"
                f" git config --local {OUTER_SANDBOX_KEY} true (do not run it yourself)"
            )
        raise ToolError(msg)
    result["outer_sandbox"] = sandbox
    result["raw_output"] = out_path
    result["summary"] = text.strip().splitlines()[0]
    print(json.dumps(result, indent=2))
    return 0 if result["clean"] else 1


# --- GitHub bot -------------------------------------------------------------


def classify_bot_activity(head_sha, reviews, issue_comments, trigger_reactions=()):
    """Decide whether the bot has reviewed head_sha, and how it went.

    A findings review is a PR review whose commit_id is head_sha. A clean pass
    is either an issue comment carrying the clean marker and a Reviewed commit
    that prefixes head_sha, or the bot's +1 reaction on the `@codex review`
    trigger comment (which carries no sha -- the caller guarantees nothing was
    pushed after triggering).
    """
    for review in reviews:
        if review.get("user", {}).get("login") != BOT_LOGIN:
            continue
        if review.get("commit_id") == head_sha:
            return {"status": "findings", "review_id": review.get("id")}
    for comment in issue_comments:
        if comment.get("user", {}).get("login") != BOT_LOGIN:
            continue
        body = comment.get("body") or ""
        m = BOT_REVIEWED_COMMIT_RE.search(body)
        if m and head_sha.startswith(m.group(1)) and BOT_CLEAN_MARKER in body:
            return {"status": "clean", "comment_id": comment.get("id")}
    bot_reactions = {
        r.get("content") for r in trigger_reactions if r.get("user", {}).get("login") == BOT_LOGIN
    }
    if "+1" in bot_reactions:
        return {"status": "clean", "via": "reaction"}
    return {"status": "pending", "acknowledged": "eyes" in bot_reactions}


def gh_json(path):
    return json.loads(run(["gh", "api", "--paginate", "--slurp", path]).stdout or "[]")


def flatten(pages):
    return [item for page in pages for item in page]


def pr_number(override=None):
    if override:
        return str(override)
    return run(["gh", "pr", "view", "--json", "number", "-q", ".number"]).stdout.strip()


def own_triggers(sha, comments, viewer):
    """Ids of the viewer's `@codex review` comments tagged `Review of <sha>`, oldest first.

    Anyone can post a trigger on a public PR, so only the viewer's own count.
    """
    ids = []
    for c in comments:
        lines = (c.get("body") or "").splitlines()
        if c.get("user", {}).get("login") != viewer:
            continue
        if lines[:1] == ["@codex review"] and f"Review of {sha}" in lines:
            ids.append(c.get("id"))
    return ids


def poll_seconds(args, comments, window, now):
    """Return (seconds to poll, window end as epoch or None).

    With --trigger-comment the window runs from the trigger's created_at, so a
    re-run resumes it and an old trigger times out at once.
    """
    if not args.trigger_comment:
        return (args.timeout if args.timeout is not None else window), None
    trigger = next((c for c in comments if c.get("id") == args.trigger_comment), None)
    if trigger is None:
        raise ToolError(f"comment {args.trigger_comment} is not on this PR")
    created = datetime.fromisoformat(trigger["created_at"].replace("Z", "+00:00")).timestamp()
    ends = created + window
    return min(max(ends - now, 0), window), ends


def cmd_gh_wait(args):
    wait = bot_wait()
    window = args.windows * wait["minutes"] * 60
    pr = pr_number(args.pr)
    viewer = run(["gh", "api", "user", "-q", ".login"]).stdout.strip()
    deadline = None
    while True:
        reviews = flatten(gh_json(f"repos/{{owner}}/{{repo}}/pulls/{pr}/reviews"))
        comments = flatten(gh_json(f"repos/{{owner}}/{{repo}}/issues/{pr}/comments"))
        if deadline is None:
            seconds, ends = poll_seconds(args, comments, window, time.time())
            # A --timeout shorter than the trigger's window only caps this call.
            capped = ends is not None and args.timeout is not None and args.timeout < seconds
            deadline = time.monotonic() + (args.timeout if capped else seconds)
        reactions = []
        if args.trigger_comment:
            path = f"repos/{{owner}}/{{repo}}/issues/comments/{args.trigger_comment}/reactions"
            reactions = flatten(gh_json(path))
        result = classify_bot_activity(args.sha, reviews, comments, reactions)
        triggers = own_triggers(args.sha, comments, viewer)
        found = {"pr": int(pr), "sha": args.sha}
        found.update(trigger=(triggers or [None])[-1], triggers=len(triggers))
        if result["status"] != "pending":
            result.update(found)
            print(json.dumps(result))
            return 0 if result["status"] == "clean" else 1
        if time.monotonic() >= deadline:
            out = {"status": "pending" if capped else "timeout", **found}
            out["acknowledged"] = result["acknowledged"]
            if capped:
                out["window_ends"] = datetime.fromtimestamp(ends, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                out["action"] = wait["action"]
            print(json.dumps(out))
            return 1
        time.sleep(args.interval)


THREADS_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          comments(first: 1) { nodes { author { login } body url } }
        }
      }
    }
  }
}
"""


def bot_threads(nodes):
    threads = []
    for node in nodes:
        if node.get("isResolved"):
            continue
        first = (node.get("comments", {}).get("nodes") or [{}])[0]
        login = (first.get("author") or {}).get("login", "")
        # GraphQL drops the "[bot]" suffix that REST includes.
        if login not in (BOT_LOGIN, BOT_LOGIN.removesuffix("[bot]")):
            continue
        m = BOT_BADGE_RE.search(first.get("body") or "")
        threads.append(
            {
                "id": node["id"],
                "priority": m.group(1) if m else None,
                "title": m.group(2).strip() if m else None,
                "path": node.get("path"),
                "line": node.get("line"),
                "outdated": node.get("isOutdated", False),
                "url": first.get("url"),
            }
        )
    return threads


def cmd_gh_threads(args):
    owner, repo = (
        run(["gh", "repo", "view", "--json", "owner,name", "-q", '.owner.login + " " + .name'])
        .stdout.strip()
        .split()
    )
    pr = int(pr_number(args.pr))
    nodes, cursor = [], None
    while True:
        cmd = ["gh", "api", "graphql", "-f", f"query={THREADS_QUERY}"]
        cmd += ["-F", f"owner={owner}", "-F", f"repo={repo}", "-F", f"pr={pr}"]
        if cursor:
            cmd += ["-F", f"cursor={cursor}"]
        data = json.loads(run(cmd).stdout)
        conn = data["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes += conn["nodes"]
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    print(json.dumps(bot_threads(nodes), indent=2))
    return 0


RESOLVE_MUTATION = """
mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id isResolved } } }
"""


def cmd_gh_resolve(args):
    resolved = []
    for thread_id in args.ids:
        out = run(["gh", "api", "graphql", "-f", f"query={RESOLVE_MUTATION}", "-F", f"id={thread_id}"])
        thread = json.loads(out.stdout)["data"]["resolveReviewThread"]["thread"]
        resolved.append(thread)
    print(json.dumps(resolved))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("mode").set_defaults(func=cmd_mode)

    p = sub.add_parser("local-review")
    p.add_argument("--base", required=True, help="base ref to diff against, e.g. origin/main")
    p.add_argument("--title", help="optional review title")
    p.add_argument("--timeout", type=int, default=900, help="seconds (default 900)")
    p.set_defaults(func=cmd_local_review)

    p = sub.add_parser("gh-wait")
    p.add_argument("--sha", required=True, help="full HEAD sha the bot must review")
    p.add_argument("--timeout", type=int, help=f"seconds (default: {TIMEOUT_MINUTES_KEY} minutes, else 1800)")
    p.add_argument("--interval", type=int, default=30, help="poll interval seconds (default 30)")
    p.add_argument("--pr", type=int, help="PR number (default: the current branch's PR)")
    p.add_argument("--trigger-comment", type=int, help="`@codex review` comment id; the window starts at it")
    p.add_argument("--windows", type=int, default=1, help="bot windows to wait (default 1)")
    p.set_defaults(func=cmd_gh_wait)

    p = sub.add_parser("gh-threads")
    p.add_argument("--pr", type=int, help="PR number (default: the current branch's PR)")
    p.set_defaults(func=cmd_gh_threads)

    p = sub.add_parser("gh-resolve")
    p.add_argument("ids", nargs="+", help="review thread node ids from gh-threads")
    p.set_defaults(func=cmd_gh_resolve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
