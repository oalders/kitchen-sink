#!/usr/bin/env python3
"""Decide, apply and verify the least-privilege-gh-actions edits for one workflow.

  check_workflow.py [--apply] [--verify] [--cannot-tell JOB]... [--untrusted JOB]... FILE

Prints a JSON verdict {file, action, edits, reports, violations, drift}.
`action` is `skip` (a --cannot-tell job: no edits anywhere in the file),
`edit` or `unchanged`. Each report and violation is {code, job, step, severity, text}:
job and step are null for a file-level item, step is a 0-based index into the
job's `steps:`, and `text` is the line to relay, built only from the file path,
job keys, step indices and fixed wording, never from other workflow content.
Severity is `critical`, `important`, `minor` or `info`. `drift` counts the
reports that are not `info` plus the violations. Reports describe the file as
given, before any edit, except `contents-write-granted` (`info`), which --apply
adds for each job it gave job-level `contents: write`. NOTES below lists every
code.

--apply writes the edits as text, keeping comments and layout, then fills
`violations` from the edited file. It writes nothing when there are edits and
the file uses YAML aliases, when the result doesn't parse, when a second pass
finds more to edit, or when the edits would raise any scope beyond the
intended `contents:` grant. That grant is never added on a privileged trigger
(`privileged-push`), after a persist-credentials: false checkout
(`push-own-credentials`) or to a one-value permissions: block
(`scalar-permissions-push`); the report names it instead. --verify fills
`violations` without editing.

Exit 0 when done; 1 when `violations` is non-empty; 2, with one fixed line on
stderr, when the file can't be read, parsed or edited safely, a job key is not a
valid job id, or a JOB is not a key under `jobs:`.
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
PUSH_ACTIONS = ("stefanzweifel/git-auto-commit-action@", "peter-evans/create-pull-request@", "endbug/add-and-commit@")
TOKEN_INPUTS = {"token", "github_token", "github-token"}
# `git`, then any global options (-C dir, -c k=v, --opt[=val]), then the subcommand.
GIT = r"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?))*\s+"
GIT_PUSH = re.compile(GIT + r"push\b")
GIT_READ = re.compile(GIT + r"(?:fetch|pull)\b")
GIT_GET = re.compile(GIT + r"(?:checkout|fetch|switch|clone)\b")
GH_PR_CHECKOUT = re.compile(r"\bgh\s+pr\s+checkout\b")
GH_RUN_DOWNLOAD = re.compile(r"\bgh\s+run\s+download\b")
# A workflow_run job fetching the triggering run's artifacts through the REST API.
ARTIFACTS_API = re.compile(r"/actions/artifacts/|/actions/runs/[^\n]*/artifacts")
API_CLIENT = re.compile(r"\bgh\s+api\b|\bcurl\b")
GITHUB_SCRIPT = "actions/github-script@"
# Later steps that run none of the checked-out code, for the untrusted-checkout severity.
NON_EXECUTING = ("actions/upload-artifact@", CHECKOUT)
PR_EXPR = re.compile(
    r"github\.event\.pull_request\.head\.|github\.event\.pull_request\.merge_commit_sha|github\.head_ref|GITHUB_HEAD_REF"
    r"|github\.event\.workflow_run\.(?:head_|pull_requests\[[^\]]*\]\.head\.)",
    re.I,
)
PULL_REF = re.compile(r"\bpull/[^/\n]+/(?:head|merge)\b", re.I)
# github['event']["head_ref"] is the same expression as github.event.head_ref.
INDEX = re.compile(r"""\[\s*['"]([^'"\]]+)['"]\s*\]""")
DEFAULT_TOKEN = re.compile(r"^\$\{\{\s*(?:secrets\.GITHUB_TOKEN|github\.token)\s*\}\}$")
# A push to such a URL uses the token in it, not the persisted one.
CRED_URL = re.compile(r"https?://[^/\n]*@")
JOB_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
ARTIFACT_ACTIONS = ("actions/download-artifact@", "dawidd6/action-download-artifact@")
SCOPE_KEY = re.compile(r"^[a-z][a-z-]*$")
RANK = {"none": 0, "read": 1, "write": 2}

NOTES = {
    "top-level-drift": "top-level permissions grant more than read; left as is",
    "push-checkout": "a later step pushes, fetches or pulls with the persisted token; checkout left as is",
    "cannot-tell": "a step runs a tool whose token needs can't be read; file skipped whole. "
    "Set persist-credentials: false and pass the token via env: only to the step that needs it",
    "untrusted-checkout": "a privileged trigger checks out or downloads PR-controlled content; not fixed, no write scope added",
    "top-level-permissions": "top-level permissions missing, or lacking the contents: read an inheriting checkout job needs",
    "persist-credentials": "checkout does not set persist-credentials: false",
    "contents-scope": "job runs actions/checkout but resolves no contents: read or write",
    "untrusted-write": "job with an untrusted checkout resolves a write scope",
    "privileged-push": "job on a privileged trigger pushes with the default token; contents: write not added",
    "contents-write-granted": "job-level contents: write added for a later step's push",
    "push-own-credentials": "a later step pushes after a checkout with persist-credentials: false; no contents: write added",
    "scalar-permissions-push": "a later step pushes but the job's permissions: is one value, not a scope map; contents: write not added",
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
    pushes: list  # checkout step indices a later step pushes, fetches or pulls from
    writes: list  # the subset a later step pushes from
    own_pushes: list  # persist-credentials: false checkouts a later step still pushes after
    flag_step: int | None  # first step matching an untrusted-checkout pattern
    flagged: bool
    privileged: bool  # the workflow has a pull_request_target, workflow_run or issue_comment trigger


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


def uses(step):
    # GitHub matches owner/repo case-insensitively.
    return get(step, "uses").lower()


def keys(node):
    """A mapping node's key strings; non-scalar keys are refused."""
    if any(not isinstance(k, yaml.ScalarNode) for k, _ in node.value):
        raise Unsupported("a mapping key is not a scalar")
    return [k.value for k, _ in node.value]


def scalars(node, seen=None):
    seen = set() if seen is None else seen
    if id(node) in seen:  # an alias repeats a node; walk it once
        return
    seen.add(id(node))
    if isinstance(node, yaml.ScalarNode):
        yield node.value
    elif isinstance(node, yaml.SequenceNode):
        for n in node.value:
            yield from scalars(n, seen)
    elif isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            yield from scalars(k, seen)
            yield from scalars(v, seen)


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
        return top.value != "read-all"
    return any(not isinstance(v, yaml.ScalarNode) or v.value not in ("read", "none") for _, v in top.value)


def strip_comment(line):
    """line without its shell comment: a # at the start or after whitespace, outside quotes."""
    quote, prev, i = None, " ", 0
    while i < len(line):
        c = line[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            i += 1  # the escaped character is literal
        elif quote == '"':
            quote = None if c == '"' else quote
        elif c in "'\"":
            quote = c
        elif c == "#" and prev.isspace():
            return line[:i]
        prev = line[i] if i < len(line) else ""
        i += 1
    return line


def remote_use(step):
    """'push' for a step pushing with persisted credentials, 'read' for fetch/pull, else None."""
    if uses(step).startswith(PUSH_ACTIONS):
        w = item(step, "with")[1]
        own = isinstance(w, yaml.MappingNode) and any(isinstance(k, yaml.ScalarNode) and k.value in TOKEN_INPUTS for k, _ in w.value)
        return None if own else "push"
    lines = [strip_comment(line) for line in get(step, "run").splitlines()]
    if any(GIT_PUSH.search(line) and not CRED_URL.search(line) for line in lines):
        return "push"
    return "read" if any(GIT_READ.search(line) for line in lines) else None


def persists(checkout):
    return get(item(checkout, "with")[1], "persist-credentials").lower() != "false"


def own_token(checkout):
    token = get(item(checkout, "with")[1], "token").strip()
    return bool(token) and not DEFAULT_TOKEN.match(token)


def pr_content(text):
    text = INDEX.sub(r".\1", text)
    return bool(PR_EXPR.search(text) or PULL_REF.search(text))


def flag_step(steps, triggers):
    if not triggers & PRIVILEGED:
        return None
    for i, step in enumerate(steps):
        used, run = uses(step), get(step, "run")
        w = item(step, "with")[1]
        if used.startswith(CHECKOUT) and (pr_content(get(w, "ref")) or pr_content(get(w, "repository"))):
            return i
        if GH_PR_CHECKOUT.search(run) or (GIT_GET.search(run) and pr_content(run)):
            return i
        if "workflow_run" in triggers and (
            used.startswith(ARTIFACT_ACTIONS)
            or GH_RUN_DOWNLOAD.search(run)
            or (API_CLIENT.search(run) and ARTIFACTS_API.search(run))
            or (used.startswith(GITHUB_SCRIPT) and "downloadArtifact" in get(w, "script"))
        ):
            return i
    return None


def triggers(root):
    on = item(root, "on")[1]
    if isinstance(on, yaml.ScalarNode):
        return {on.value}
    if isinstance(on, yaml.SequenceNode):
        return {n.value for n in on.value if isinstance(n, yaml.ScalarNode)}
    if isinstance(on, yaml.MappingNode):
        return set(keys(on))
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
    privileged = bool(trig & PRIVILEGED)
    for key, (_, node) in zip(keys(jobs_node), jobs_node.value):
        if not JOB_KEY.match(key):
            raise Unsupported("a job key is not a valid GitHub Actions job id")
        if not isinstance(node, yaml.MappingNode):
            raise Unsupported("a job is not a mapping")
        steps = item(node, "steps")[1]
        steps = steps.value if isinstance(steps, yaml.SequenceNode) else []
        checkouts = [i for i, s in enumerate(steps) if uses(s).startswith(CHECKOUT)]
        later = {i: {remote_use(s) for s in steps[i + 1 :]} for i in checkouts}
        # A push after a checkout that persists nothing uses credentials set up another way.
        kept = [i for i in checkouts if persists(steps[i])]
        pushing = [i for i in kept if later[i] - {None}]
        writing = [i for i in kept if "push" in later[i]]
        own = [i for i in checkouts if i not in kept and "push" in later[i]]
        flag = flag_step(steps, trig)
        perm = item(node, "permissions")[1]
        jobs.append(Job(key, node, perm, steps, checkouts, pushing, writing, own, flag, flag is not None or key in untrusted, privileged))
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
        used = item(step, "uses")[1]
        at = text.find("\n", used.end_mark.index)
        at = len(text) if at < 0 else at - (text[at - 1] == "\r")
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
    keep = []
    # A job-level block replaces the top-level one, so carry its other scopes over.
    for k, v in top.value if isinstance(top, yaml.MappingNode) else []:
        if not (isinstance(k, yaml.ScalarNode) and SCOPE_KEY.match(k.value) and isinstance(v, yaml.ScalarNode) and v.value in RANK):
            raise Unsupported("a top-level permissions entry is not a plain scope: level")
        if k.value != "contents":
            keep.append(f"{pad}  {k.value}: {v.value}")
    return at, at, "\n".join([f"{pad}permissions:", f"{pad}  contents: write", *keep]) + "\n"


def default_token_push(job):
    """A later step pushes with the checkout's default token, in a job not flagged untrusted."""
    return bool(job.writes) and not job.flagged and not any(own_token(job.steps[i]) for i in job.writes)


def granted(job):
    # On a privileged trigger a write grant is a judgment call, so it is only reported.
    return default_token_push(job) and not job.privileged


def resolved(job, top):
    return job.perm if job.perm is not None else top


def needs_grant(job, top):
    return granted(job) and level(resolved(job, top), "contents") != "write"


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
        if needs_grant(j, top):
            if j.perm is None and not isinstance(top, yaml.ScalarNode):
                edit("job-contents-write", new_job_block(text, j, top), j.key)
            elif isinstance(j.perm, yaml.MappingNode):
                edit("job-contents-write", set_key(text, j.perm, "contents", "write"), j.key)
            # A read-all block is not split into scopes here; reports() names it instead.
    return edits, ops


def raises(before, after, allowed):
    """True when after grants some scope more than before, beyond allowed {scope: level}."""
    if before is None:  # the repo default, which may be write-all
        return False
    names = {"\0other"}  # stands for every scope neither block names
    for perm in (before, after):
        if isinstance(perm, yaml.MappingNode):
            names.update(k.value for k, _ in perm.value)
    for scope in names:
        new = RANK.get(level(after, scope), 2)
        if new > RANK.get(level(before, scope), 2) and new > RANK[allowed.get(scope, "none")]:
            return True
    return False


def widened(before, after):
    """True when the edited analysis grants any job or the top level more than intended."""
    (_, top0, jobs0), (_, top1, jobs1) = before, after
    if (drift(top1) and not drift(top0)) or raises(top0, top1, {"contents": "read"}):
        return True
    for j0, j1 in zip(jobs0, jobs1):
        allowed = {"contents": "write" if granted(j0) else "read"}
        if raises(j0.perm if j0.perm is not None else top0, j1.perm if j1.perm is not None else top1, allowed):
            return True
    return False


def item_dict(code, job=None, step=None, severity="important"):
    return {"code": code, "job": job, "step": step, "severity": severity}


def runs_code(step):
    used = uses(step)
    return item(step, "run")[1] is not None or (bool(used) and not used.startswith(NON_EXECUTING))


def reports(analysis, cannot_tell):
    _, top, jobs = analysis
    out = [item_dict("top-level-drift")] if drift(top) else []
    for j in jobs:
        if j.key in cannot_tell:
            out.append(item_dict("cannot-tell", j.key))
        out += [item_dict("push-checkout", j.key, i) for i in j.pushes]
        out += [item_dict("push-own-credentials", j.key, i, "minor") for i in j.own_pushes]
        if needs_grant(j, top) and isinstance(resolved(j, top), yaml.ScalarNode):
            out.append(item_dict("scalar-permissions-push", j.key))
        if j.privileged and default_token_push(j):
            out.append(item_dict("privileged-push", j.key))
        if j.flagged:
            later = j.steps if j.flag_step is None else j.steps[j.flag_step + 1 :]
            critical = (
                any(runs_code(s) for s in later)
                or any("secrets." in INDEX.sub(r".\1", s) for s in scalars(j.node))
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
            persisted = persists(j.steps[i])
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
    with open(path, encoding="utf-8", newline="") as fh:  # keep CRLF line endings
        text = fh.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    analysis = analyse(text, untrusted)
    unknown = (set(cannot_tell) | set(untrusted)) - {j.key for j in analysis[2]}
    if unknown:
        raise Unsupported("a --cannot-tell or --untrusted JOB is not a job key")
    edits, ops = plan(text, analysis, cannot_tell)
    found = reports(analysis, cannot_tell)
    if apply and ops:
        # An edit to an anchored node would also change every alias of it.
        if any(isinstance(e, yaml.AliasEvent) for e in yaml.parse(text)):
            raise Unsupported("file uses YAML aliases; not edited")
        for start, end, new in sorted(ops, key=lambda op: op[0], reverse=True):
            text = text[:start] + new.replace("\n", nl) + text[end:]
        after = analyse(text, untrusted)
        if plan(text, after, cannot_tell)[0]:
            raise Unsupported("edits did not converge; file not written")
        if widened(analysis, after):
            raise Unsupported("edits would widen a scope; file not written")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        analysis = after
        found += [item_dict("contents-write-granted", e["job"], severity="info") for e in edits if e["edit"] == "job-contents-write"]
    action = "skip" if cannot_tell else "edit" if edits else "unchanged"
    violations = verify(analysis, cannot_tell) if apply or verify_ else []
    return {
        "file": path,
        "action": action,
        "edits": edits,
        "reports": [render(path, r) for r in found],
        "violations": [render(path, v) for v in violations],
        # Items a caller counts as drift: every non-info report and every violation.
        "drift": sum(r["severity"] != "info" for r in found) + len(violations),
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
    except Exception as exc:  # any failure is exit 2 with fixed text, never a traceback
        detail = str(exc) if isinstance(exc, Unsupported) else "can't read, parse or write the file safely"
        print(f"check_workflow: {fence(args.file)}: {detail}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2))
    return 1 if verdict["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
