#!/usr/bin/env python3
"""Decide, apply and verify the least-privilege-gh-actions edits for one workflow.

  check_workflow.py [--apply] [--verify] [--cannot-tell JOB]... [--untrusted JOB]... FILE

Prints a JSON verdict {file, action, edits, reports, violations}. `action` is
`skip` (a --cannot-tell job: no edits anywhere in the file), `edit` or
`unchanged`. Each report and violation is {code, job, step, severity, text}:
job and step are null for a file-level item, step is a 0-based index into the
job's `steps:`, and `text` is the line to relay, built only from the file path,
job keys, step indices and fixed wording, never from other workflow content.
Reports and their severities describe the file as given, before --apply.

--apply writes the edits as text, keeping comments and layout, and writes
nothing unless the result parses and a second pass finds nothing left to edit.
--verify fills `violations` (after --apply when both are given).

Exit 0 when done; 1 when --verify finds violations; 2 when the file can't be
read, parsed or edited, or a JOB is not a key under `jobs:`.
"""

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass

import yaml

CHECKOUT = "actions/checkout@"
PRIVILEGED = {"pull_request_target", "workflow_run", "issue_comment"}
# These push with the checkout's persisted token unless given their own token input.
PUSH_ACTIONS = ("stefanzweifel/git-auto-commit-action@", "peter-evans/create-pull-request@", "EndBug/add-and-commit@")
GIT_REMOTE = re.compile(r"\bgit\s+(?:push|fetch|pull)\b")
GIT_GET = re.compile(r"\bgit\s+(?:checkout|fetch|switch)\b")
GH_PR_CHECKOUT = re.compile(r"\bgh\s+pr\s+checkout\b")
GH_RUN_DOWNLOAD = re.compile(r"\bgh\s+run\s+download\b")
PR_EXPR = re.compile(
    r"github\.event\.pull_request\.head\.|github\.event\.pull_request\.merge_commit_sha|github\.head_ref|GITHUB_HEAD_REF"
    r"|github\.event\.workflow_run\.(?:head_|pull_requests\[[^\]]*\]\.head\.)"
)
PULL_REF = re.compile(r"\bpull/[^/\n]+/(?:head|merge)\b")
DEFAULT_TOKEN = re.compile(r"^\$\{\{\s*(?:secrets\.GITHUB_TOKEN|github\.token)\s*\}\}$")

NOTES = {
    "top-level-drift": "top-level permissions grant more than read; left as is",
    "push-checkout": "a later step pushes with the persisted token; checkout left as is",
    "cannot-tell": "a step runs a tool whose token needs can't be read; file skipped whole. "
    "Set persist-credentials: false and pass the token via env: only to the step that needs it",
    "untrusted-checkout": "a privileged trigger checks out or downloads PR-controlled content; not fixed, no write scope added",
    "top-level-permissions": "top-level permissions missing, or lacking the contents: read an inheriting checkout job needs",
    "persist-credentials": "checkout does not set persist-credentials: false",
    "contents-scope": "job runs actions/checkout but resolves no contents: read or write",
    "untrusted-write": "job with an untrusted checkout resolves a write scope",
}


class Unsupported(Exception):
    """The file can't be checked or edited safely; the message is fixed text."""


@dataclass
class Job:
    key: str
    node: yaml.MappingNode
    perm: yaml.Node | None  # job-level permissions:
    steps: list
    checkouts: list  # step indices
    pushes: list  # checkout step indices a later step pushes from
    flag_step: int | None  # first step matching an untrusted-checkout pattern
    flagged: bool


def item(node, key):
    """(key node, value node) for key in a mapping node, else (None, None)."""
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                return k, v
    return None, None


def get(node, key):
    """The scalar string under key, or ''."""
    v = item(node, key)[1]
    return v.value if isinstance(v, yaml.ScalarNode) else ""


def scalars(node):
    if isinstance(node, yaml.ScalarNode):
        yield node.value
    elif isinstance(node, yaml.SequenceNode):
        for n in node.value:
            yield from scalars(n)
    elif isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            yield from scalars(k)
            yield from scalars(v)


def level(perm, scope):
    """The level a permissions node grants scope; None when there is no node."""
    if perm is None:
        return None
    if isinstance(perm, yaml.MappingNode):
        return get(perm, scope) or "none"
    return {"write-all": "write", "read-all": "read"}.get(perm.value, "none")


def grants_write(perm):
    # No permissions: block anywhere gets the repo default, which may be write-all.
    if perm is None:
        return True
    if isinstance(perm, yaml.MappingNode):
        return any(isinstance(v, yaml.ScalarNode) and v.value == "write" for _, v in perm.value)
    return perm.value == "write-all"


def drift(top):
    if top is None:
        return False
    if not isinstance(top, yaml.MappingNode):
        return True
    return any(not isinstance(v, yaml.ScalarNode) or v.value not in ("read", "none") for _, v in top.value)


def pushes(step):
    if get(step, "uses").startswith(PUSH_ACTIONS):
        w = item(step, "with")[1]
        return not (isinstance(w, yaml.MappingNode) and any("token" in k.value for k, _ in w.value))
    return bool(GIT_REMOTE.search(get(step, "run")))


def own_token(checkout):
    token = get(item(checkout, "with")[1], "token").strip()
    return bool(token) and not DEFAULT_TOKEN.match(token)


def pr_content(text):
    return bool(PR_EXPR.search(text) or PULL_REF.search(text))


def flag_step(steps, triggers):
    if not triggers & PRIVILEGED:
        return None
    for i, step in enumerate(steps):
        uses, run = get(step, "uses"), get(step, "run")
        w = item(step, "with")[1]
        if uses.startswith(CHECKOUT) and (pr_content(get(w, "ref")) or pr_content(get(w, "repository"))):
            return i
        if GH_PR_CHECKOUT.search(run) or (GIT_GET.search(run) and pr_content(run)):
            return i
        if "workflow_run" in triggers and (uses.startswith("actions/download-artifact@") or GH_RUN_DOWNLOAD.search(run)):
            return i
    return None


def triggers(root):
    on = item(root, "on")[1]
    if isinstance(on, yaml.ScalarNode):
        return {on.value}
    if isinstance(on, yaml.SequenceNode):
        return {n.value for n in on.value if isinstance(n, yaml.ScalarNode)}
    if isinstance(on, yaml.MappingNode):
        return {k.value for k, _ in on.value}
    return set()


def analyse(text, untrusted=()):
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise Unsupported(f"YAML does not parse (line {mark.line + 1})" if mark else "YAML does not parse") from None
    jobs_node = item(root, "jobs")[1]
    if not isinstance(jobs_node, yaml.MappingNode):
        raise Unsupported("no jobs: mapping")
    trig = triggers(root)
    jobs = []
    for k, node in jobs_node.value:
        if not isinstance(node, yaml.MappingNode):
            raise Unsupported("a job is not a mapping")
        steps = item(node, "steps")[1]
        steps = steps.value if isinstance(steps, yaml.SequenceNode) else []
        checkouts = [i for i, s in enumerate(steps) if get(s, "uses").startswith(CHECKOUT)]
        pushing = [i for i in checkouts if any(pushes(s) for s in steps[i + 1 :])]
        flag = flag_step(steps, trig)
        jobs.append(Job(k.value, node, item(node, "permissions")[1], steps, checkouts, pushing, flag, flag is not None or k.value in untrusted))
    return root, item(root, "permissions")[1], jobs


def line_start(text, mark):
    """Index of the start of mark's line; the mark must be first on its line."""
    at = mark.index - mark.column
    if text[at : mark.index].strip(" "):
        raise Unsupported("a key to edit next to is not first on its line")
    return at


def set_key(text, mapping, key, value):
    """Text op setting key: value in a mapping node, replacing or adding the entry."""
    cur = item(mapping, key)[1]
    if isinstance(cur, yaml.ScalarNode):
        return cur.start_mark.index, cur.end_mark.index, value
    if cur is not None:
        raise Unsupported(f"{key} is not a scalar")
    if mapping.flow_style:
        at = mapping.start_mark.index + 1
        return at, at, f"{key}: {value}" + (", " if mapping.value else "")
    first = mapping.value[0][0].start_mark
    at = line_start(text, first)
    return at, at, f"{' ' * first.column}{key}: {value}\n"


def persist_false(text, step):
    if step.flow_style:
        raise Unsupported("a checkout step is a flow mapping")
    w = item(step, "with")[1]
    if w is None:
        uses = item(step, "uses")[1]
        at = text.find("\n", uses.end_mark.index)
        at = len(text) if at < 0 else at
        col = step.start_mark.column
        return at, at, f"\n{' ' * col}with:\n{' ' * (col + 2)}persist-credentials: false"
    if not isinstance(w, yaml.MappingNode):
        raise Unsupported("a checkout with: is not a mapping")
    if get(w, "persist-credentials").lower() == "false":
        return None
    return set_key(text, w, "persist-credentials", "false")


def new_job_block(text, job, top):
    first = job.node.value[0][0].start_mark
    at = line_start(text, first)
    pad = " " * first.column
    # A job-level block replaces the top-level one, so carry its other scopes over.
    keep = [(k.value, v.value) for k, v in top.value if k.value != "contents"] if isinstance(top, yaml.MappingNode) else []
    lines = [f"{pad}permissions:", f"{pad}  contents: write"] + [f"{pad}  {k}: {v}" for k, v in keep]
    return at, at, "\n".join(lines) + "\n"


def plan(text, analysis, cannot_tell):
    """(edits, text ops) for the file; nothing when a job is cannot-tell."""
    root, top, jobs = analysis
    edits, ops = [], []
    if cannot_tell:
        return edits, ops

    def edit(kind, op, job=None, step=None):
        if op:
            edits.append({"edit": kind, "job": job, "step": step})
            ops.append(op)

    if top is None:
        key = item(root, "jobs")[0].start_mark
        at = line_start(text, key)
        pad = " " * key.column
        edit("top-permissions", (at, at, f"{pad}permissions:\n{pad}  contents: read\n\n"))
    elif not drift(top) and level(top, "contents") != "read" and any(j.perm is None and j.checkouts for j in jobs):
        edit("top-contents-read", set_key(text, top, "contents", "read"))
    for j in jobs:
        for i in j.checkouts:
            # An untrusted checkout loses its persisted token even when a later step pushes.
            if i not in j.pushes or j.flagged:
                edit("persist-credentials", persist_false(text, j.steps[i]), j.key, i)
        grant = j.pushes and not j.flagged and not any(own_token(j.steps[i]) for i in j.pushes)
        if grant and level(j.perm if j.perm is not None else top, "contents") != "write":
            if j.perm is None:
                edit("job-contents-write", new_job_block(text, j, top), j.key)
            elif isinstance(j.perm, yaml.MappingNode):
                edit("job-contents-write", set_key(text, j.perm, "contents", "write"), j.key)
    return edits, ops


def item_dict(code, job=None, step=None, severity="important"):
    return {"code": code, "job": job, "step": step, "severity": severity}


def reports(analysis, cannot_tell):
    _, top, jobs = analysis
    out = [item_dict("top-level-drift")] if drift(top) else []
    for j in jobs:
        if j.key in cannot_tell:
            out.append(item_dict("cannot-tell", j.key))
        out += [item_dict("push-checkout", j.key, i) for i in j.pushes]
        if j.flagged:
            later = j.steps if j.flag_step is None else j.steps[j.flag_step + 1 :]
            critical = (
                any(item(s, "run")[1] is not None for s in later)
                or any("secrets." in s for s in scalars(j.node))
                or grants_write(j.perm if j.perm is not None else top)
            )
            out.append(item_dict("untrusted-checkout", j.key, j.flag_step, "critical" if critical else "important"))
    return out


def verify(analysis, cannot_tell):
    if cannot_tell:
        return []
    _, top, jobs = analysis
    bad = []
    if not drift(top) and (top is None or (level(top, "contents") != "read" and any(j.perm is None and j.checkouts for j in jobs))):
        bad.append(item_dict("top-level-permissions"))
    for j in jobs:
        for i in j.checkouts:
            persisted = get(item(j.steps[i], "with")[1], "persist-credentials").lower() != "false"
            if persisted and (i not in j.pushes or j.flagged):
                bad.append(item_dict("persist-credentials", j.key, i))
        perm = j.perm if j.perm is not None else top
        if j.checkouts and not (j.perm is None and drift(top)) and level(perm, "contents") not in ("read", "write"):
            bad.append(item_dict("contents-scope", j.key))
        if j.flagged and grants_write(perm):
            bad.append(item_dict("untrusted-write", j.key))
    return bad


def fence(value):
    """An untrusted value as inline code: control characters become spaces."""
    value = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in value)
    ticks = "`" * (max(map(len, re.findall("`+", value)), default=0) + 1)
    pad = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{ticks}{pad}{value}{pad}{ticks}"


def render(path, entry):
    where = fence(path)
    if entry["job"] is not None:
        where += f" job {fence(entry['job'])}"
    if entry["step"] is not None:
        where += f" steps[{entry['step']}]"
    return dict(entry, text=f"{where}: {entry['code']} ({entry['severity']}): {NOTES[entry['code']]}")


def check(path, apply=False, verify_=False, cannot_tell=(), untrusted=()):
    """The verdict dict for path, applying edits first when asked."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    analysis = analyse(text, untrusted)
    unknown = (set(cannot_tell) | set(untrusted)) - {j.key for j in analysis[2]}
    if unknown:
        raise Unsupported("a --cannot-tell or --untrusted JOB is not a job key")
    edits, ops = plan(text, analysis, cannot_tell)
    found = reports(analysis, cannot_tell)
    if apply and ops:
        for start, end, new in sorted(ops, key=lambda op: op[0], reverse=True):
            text = text[:start] + new + text[end:]
        after = analyse(text, untrusted)
        if plan(text, after, cannot_tell)[0]:
            raise Unsupported("edits did not converge; file not written")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        analysis = after
    action = "skip" if cannot_tell else "edit" if edits else "unchanged"
    violations = verify(analysis, cannot_tell) if verify_ else []
    return {
        "file": path,
        "action": action,
        "edits": edits,
        "reports": [render(path, r) for r in found],
        "violations": [render(path, v) for v in violations],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--cannot-tell", action="append", default=[], metavar="JOB")
    ap.add_argument("--untrusted", action="append", default=[], metavar="JOB")
    ap.add_argument("file")
    args = ap.parse_args(argv)
    try:
        verdict = check(args.file, args.apply, args.verify, args.cannot_tell, args.untrusted)
    except (OSError, UnicodeError, Unsupported) as exc:
        detail = str(exc) if isinstance(exc, Unsupported) else "can't read or write the file"
        print(f"check_workflow: {fence(args.file)}: {detail}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2))
    return 1 if verdict["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
