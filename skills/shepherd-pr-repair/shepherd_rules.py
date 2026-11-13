"""Validators for shepherd.py: every value that reaches a command line or the agent passes one."""

import re

DEFAULT_TIMEOUT_MINUTES = 180


class RuleError(Exception):
    pass


def valid_sha(s):
    return re.fullmatch(r"[0-9a-f]{40}", s) is not None


def valid_ref(s):
    return re.fullmatch(r"[A-Za-z0-9._/-]+", s) is not None and ".." not in s and not s.startswith("-")


def valid_name(s):
    """An owner or repo name."""
    return re.fullmatch(r"[A-Za-z0-9._-]+", s) is not None and ".." not in s


def valid_id(s):
    return re.fullmatch(r"[0-9]+", s) is not None


def valid_model(s):
    """The model version (e.g. `Opus 5.5`), not the ID: it goes into the public
    `@codex review` footer, whose shape the gh wrapper enforces."""
    return re.fullmatch(r"(Claude )?(Opus|Sonnet|Haiku|Fable) [0-9]+(\.[0-9]+)?", s) is not None


def timeout_minutes(raw):
    if raw is None:
        return DEFAULT_TIMEOUT_MINUTES
    if re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise RuleError(f"shepherdTimeoutMinutes={raw!r} is not a positive integer")
    return int(raw)


# --- Decision rules: pure functions of what GitHub reported, ported from /shepherd-pr's steps 3-6. ---

FAILED_BUCKETS = ("fail", "cancel")
KNOWN_BUCKETS = ("pass", "fail", "pending", "skipping", "cancel")
REVIEW_BLOCKED = ("REVIEW_REQUIRED", "CHANGES_REQUESTED")
MAX_REPAIRS = 3


def buckets(checks):
    counts = {}
    for c in checks:
        counts[c["bucket"]] = counts.get(c["bucket"], 0) + 1
    return counts


def _has(checks, *names):
    return any(c["bucket"] in names for c in checks)


def pick_method(repo):
    for method, key in (("squash", "squashMergeAllowed"), ("merge", "mergeCommitAllowed"), ("rebase", "rebaseMergeAllowed")):
        if repo.get(key):
            return method
    return None


def _is_add(node):
    return node["__typename"] == "AddedToMergeQueueEvent"


def _is_removal(node):
    return node["__typename"] == "RemovedFromMergeQueueEvent"


def is_head_removal(nodes, removal_index, earliest_suite):
    """A removal belongs to the head unless the add before it predates the head's first check suite."""
    adds = [n for n in nodes[:removal_index] if _is_add(n)]
    if earliest_suite is None or not adds:
        return True
    return adds[-1]["createdAt"] >= earliest_suite  # ISO-8601 UTC strings compare as text


def _own_removal(nodes, index, disabled_at):
    """A shepherd run's `--disable-auto` dequeued the head: the removal follows it, with no re-enqueue in between."""
    if disabled_at is None or nodes[index]["createdAt"] < disabled_at:
        return False
    before = [n for n in nodes[:index] if _is_add(n) or _is_removal(n)]
    return not before or before[-1]["createdAt"] < disabled_at


def ejection(pr, nodes, earliest_suite, requeued, disabled_at):
    """The removal node when the head was ejected from the queue and not yet handled, else None."""
    if pr["isInMergeQueue"] or pr["autoMergeRequest"] is not None:
        return None
    events = [(i, n) for i, n in enumerate(nodes) if _is_add(n) or _is_removal(n)]
    if not events or not _is_removal(events[-1][1]):
        return None
    index, node = events[-1]
    if (
        not is_head_removal(nodes, index, earliest_suite)
        or node["createdAt"] == requeued
        or _own_removal(nodes, index, disabled_at)
    ):
        return None
    return node


def may_requeue(nodes, removal, earliest_suite, disabled_at):
    """One re-enqueue per head, across runs: no other removal of this head, the run's own dequeues aside."""
    return not any(
        _is_removal(n)
        and n is not removal
        and is_head_removal(nodes, i, earliest_suite)
        and not _own_removal(nodes, i, disabled_at)
        for i, n in enumerate(nodes)
    )


def queue_deadline(start, now, queued, eta):
    if not queued:
        return start + 300
    if isinstance(eta, int) and not isinstance(eta, bool) and eta >= 0:
        return now + eta + 900
    return start + 3600


def rerun_choice(fail_checks, runs, gated_sha, rerun):
    """Step 6 for cause `checks`: ("repair", []) or (rerun | infra-rerun | stop, run ids)."""
    if any(c["state"] not in ("CANCELLED", "TIMED_OUT") for c in fail_checks):
        return "repair", []
    workflows = {c["workflow"] for c in fail_checks}
    picked = [
        r
        for r in runs
        if r["event"] == "pull_request"
        and r["headSha"] == gated_sha
        and r["name"] in workflows
        and r["conclusion"] in ("failure", "timed_out", "cancelled")
        and valid_id(str(r["databaseId"]))
    ]
    ids = [int(r["databaseId"]) for r in picked]
    covered = bool(ids) and workflows <= {r["name"] for r in picked}
    top = max((r["attempt"] for r in picked), default=0)
    if covered and rerun == 0 and top <= 1:
        return "rerun", ids
    if covered and rerun < 2 and top <= 2:
        return "infra-rerun", ids
    return "stop", ids


def reread_outcome(pr, checks, gated_sha, ejected):
    """Step 5 items 1-3, first match wins (a push also logs an ejection, so new-head beats ejected)."""
    if pr["state"] == "MERGED":
        return "merged"
    if pr["state"] == "CLOSED":
        return "closed"
    if pr["headRefOid"] != gated_sha:
        return "new-head"
    if _has(checks, *FAILED_BUCKETS):
        return "failed"
    return "ejected" if ejected else "continue"


def in_queue_watch(pr, checks):
    queued = pr["isInMergeQueue"]
    if pr["state"] != "OPEN" or pr["mergeStateStatus"] == "DIRTY" or _has(checks, "pending"):
        return False
    if pr["mergeStateStatus"] == "BEHIND" and not queued:
        return False
    return queued or (pr["autoMergeRequest"] is not None and pr["reviewDecision"] not in REVIEW_BLOCKED)


def open_outcome(pr, checks, automerge):
    """Step 5 item 5, first match wins."""
    queued = pr["isInMergeQueue"]
    if pr["reviewDecision"] in REVIEW_BLOCKED:
        return "review-required"
    if pr["mergeStateStatus"] == "DIRTY" and queued:
        return "dirty-queued"
    if pr["mergeStateStatus"] in ("DIRTY", "BEHIND") and not queued:
        return "rebase"
    if _has(checks, "pending"):
        return "pending"
    if not queued and pr["autoMergeRequest"] is None:
        return "resumable-off-by-run" if automerge == "off-by-run" else "turned-off"
    raise RuleError("no open outcome matched")  # the queue watch takes everything else; never pass silently


def decide(pr, checks, automerge):
    if automerge == "off-by-run" and _has(checks, *FAILED_BUCKETS):
        return "guard"
    if pr["isInMergeQueue"]:
        return "keep-queue"
    if pr["isDraft"]:
        return "ready"
    return "enable" if pr["autoMergeRequest"] is None else "keep"


def unconfirmed_declines(body):
    """Lines tagged `(unconfirmed)` between `## Declined findings` and the next heading."""
    found, inside = [], False
    for line in body.splitlines():
        if line.startswith("#"):
            inside = line.strip() == "## Declined findings"
        elif inside and "(unconfirmed)" in line:
            found.append(line)
    return found


def status_line(state, pr, checks):
    """Built only from validated fields; check names never appear."""
    if not valid_sha(pr["headRefOid"]):
        raise RuleError("headRefOid is not a SHA")
    counts = buckets(checks)
    shown = ", ".join(f"{b} {counts[b]}" for b in KNOWN_BUCKETS if b in counts) or "-"
    automerge = {"on": "on", "off": "off", "off-by-run": "off by this run"}[state["automerge"]]
    position = (pr.get("mergeQueueEntry") or {}).get("position")
    queue = "no" if not pr["isInMergeQueue"] else str(position) if isinstance(position, int) else "yes"
    infra = ",".join(state["infra"]) or "-"
    return (
        f"#{int(state['pr'])} head {pr['headRefOid'][:7]} · checks {shown} · auto-merge {automerge} · queue {queue}"
        f" · repairs {int(state['repairs'])}/{MAX_REPAIRS} · rerun {int(state['rerun'])} · infra {infra}"
        f" · deadline {int(state['deadline'])}"
    )


# skills/shepherd-pr-repair/SKILL.md (Rules) lists these in prose; keep the two in sync.
_RESUMABLE = re.compile(
    r"HTTP 5\d\d\b|secondary rate limit|\btimeout\b|timed out|connection reset|connection refused"
    r"|no such host|could not resolve host|\bTLS\b|unexpected EOF",
    re.IGNORECASE,
)


# Git's transient failures have no stable wording, so only clearly permanent ones stop a `git fetch`.
_FETCH_PERMANENT = re.compile(
    r"does not appear to be a git repository|Repository not found|Authentication failed|Permission denied"
    r"|could not read Username|No such remote|not a git repository|returned error: 40[134]|Host key verification failed",
    re.IGNORECASE,
)


def is_permanent_fetch_error(stderr):
    return _FETCH_PERMANENT.search(stderr) is not None


def is_resumable_gh_error(cmd, stderr):
    """A failed `gh` is worth waiting out unless repeating it could do harm."""
    if cmd[:1] != ["gh"] or "--disable-auto" in cmd or cmd[:3] == ["gh", "run", "rerun"]:
        return False
    return _RESUMABLE.search(stderr) is not None
