#!/usr/bin/env python3
"""CI remediation entries for the shepherd-pr-repair skill.

Entries are per-clone git config sections, set only by the user:

  [kitchen-sink "remediation.<name>"]
      match = <Python regex, searched over the whole failed-run log>
      run   = rerun-full | <shell command>
      reads = <repo path the command executes; a trailing / means a directory>

Subcommands (all print JSON on stdout):

  list [--file PATH]        Parse and validate every entry (--local config, or
                            PATH, a scratch config being checked before it is
                            written).
  match --log FILE [--log FILE ...] --range BASE...SHA
                            The one entry every log matches (each log takes its
                            first matching entry in config order), plus, in
                            `blocked_by`, the paths that make its `run` unsafe.
                            Any invalid entry fails the whole lookup.

Security model (the one authoritative statement): a shell `run` executes in the
PR checkout, so the caller refuses it when `blocked_by` is non-empty. That lists
every path `git diff BASE...SHA` changes that equals, is under, or shares a
directory with a `reads` file (compared case-insensitively), plus every tracked
symlink under a `reads` path at SHA (its target may lie outside `reads`). So
`reads` must list every file the command executes, including ones tools resolve
on their own (Makefile includes, `package.json` scripts, `PATH` entries such as
`bin/`). Every infra fix ends with a full re-run, so the command must not call
`gh run rerun` or trigger workflows.

Log text is only searched, never executed or echoed into a command; the caller
runs only the configured `run` value, read from git config itself.

Exit codes: 0 = success / match, 1 = no match, 2 = usage, tool or config error.
"""

import argparse
import json
import posixpath
import re
import subprocess
import sys

PREFIX = "kitchen-sink.remediation."
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
RERUN_FULL = "rerun-full"


class ToolError(Exception):
    pass


def run(cmd, check=True, **kw):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and proc.returncode != 0:
        raise ToolError(f"{' '.join(cmd)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


def read_config(path=None):
    """Return [(key, value)] in config order; value is None for a bare key."""
    scope = ["--file", path] if path else ["--local"]
    proc = run(["git", "config", *scope, "--null", "--get-regexp", r"^kitchen-sink\.remediation\."], check=False)
    if proc.returncode == 1:  # no matching key
        return []
    if proc.returncode != 0:
        raise ToolError(f"git config failed ({proc.returncode}): {proc.stderr.strip()}")
    pairs = []
    for record in proc.stdout.split("\0")[:-1]:
        key, sep, value = record.partition("\n")
        pairs.append((key, value if sep else None))
    return pairs


def normalise(path):
    return path[2:] if path.startswith("./") else path


def reads_error(value):
    """Why a reads path is unusable, or None. Odd components would never match a changed path."""
    path = normalise(value)
    parts = path[:-1].split("/") if path.endswith("/") else path.split("/")
    if not path or path.startswith("/") or any(p in ("", ".", "..") for p in parts):
        return f"bad reads path {value!r}"
    return None


def validate(name, fields):
    if not NAME_RE.fullmatch(name):
        return f"bad name {name!r}"
    unknown = sorted(set(fields) - {"match", "run", "reads"})
    if unknown:
        return f"unknown field {unknown[0]!r}"
    for field in ("match", "run"):
        if len(fields.get(field, [])) != 1:
            return f"needs exactly one {field}"
    # An empty match would match every log; a bare key (None) has no value at all.
    if not fields["match"][0] or not fields["run"][0] or None in fields.get("reads", []):
        return "empty value"
    try:
        re.compile(fields["match"][0], re.MULTILINE)
    except re.error as exc:
        return f"bad match regex: {exc}"
    reads = fields.get("reads", [])
    if fields["run"][0] != RERUN_FULL and not reads:
        return "a shell run needs at least one reads"
    for value in reads:
        err = reads_error(value)
        if err:
            return err
    return None


def parse_entries(pairs):
    grouped = {}
    for key, value in pairs:
        name, _, field = key[len(PREFIX) :].rpartition(".")
        grouped.setdefault(name, {}).setdefault(field, []).append(value)
    entries = []
    for name, fields in grouped.items():
        entry = {
            "name": name,
            "match": (fields.get("match") or [None])[0],
            "run": (fields.get("run") or [None])[0],
            "reads": [normalise(v) for v in fields.get("reads", []) if v],
        }
        err = validate(name, fields)
        if err:
            entry["error"] = err
        entries.append(entry)
    return entries


def blocked_by(reads, changed):
    """Changed paths equal to, under, or beside (same directory as a file) a reads path."""
    hits = []
    for path in changed:
        folded = path.casefold()  # case-insensitive filesystems map Script/CI/x onto script/ci/x
        for value in reads:
            base = value.rstrip("/").casefold()
            if folded == base or folded.startswith(base + "/"):
                hits.append(path)
                break
            if not value.endswith("/") and posixpath.dirname(folded) == posixpath.dirname(base):
                hits.append(path)
                break
    return hits


def changed_paths(rng):
    # -z: unquoted paths, so non-ASCII or quoted names still compare against reads.
    out = run(["git", "diff", "-z", "--no-renames", "--name-only", rng]).stdout
    return [p for p in out.split("\0") if p]


def symlinks(reads, sha):
    """Tracked symlinks under any reads path at sha."""
    hits = []
    for value in reads:
        out = run(["git", "ls-tree", "-r", "-z", sha, "--", value.rstrip("/")]).stdout
        for record in out.split("\0"):
            meta, _, path = record.partition("\t")
            if meta.startswith("120000 "):
                hits.append(path)
    return hits


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        raise ToolError(f"cannot read {path}: {exc}")


def cmd_list(args):
    entries = parse_entries(read_config(args.file))
    print(json.dumps({"entries": entries}, indent=2))
    return 2 if any("error" in e for e in entries) else 0


def cmd_match(args):
    entries = parse_entries(read_config())
    errors = [f"{e['name']}: {e['error']}" for e in entries if "error" in e]
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}))
        return 2
    found = []
    for log in args.log:
        text = read_text(log)
        found.append(next((e for e in entries if re.search(e["match"], text, re.MULTILINE)), None))
    if None in found or len({e["name"] for e in found}) != 1:
        print(json.dumps({"status": "none"}))
        return 1
    entry = found[0]
    sha = args.range.rpartition("...")[2]
    if not sha:
        raise ToolError(f"--range {args.range!r} is not BASE...SHA")
    hits = blocked_by(entry["reads"], changed_paths(args.range)) + symlinks(entry["reads"], sha)
    # run picks rerun-full vs shell; the caller still executes the git config value, not this copy.
    out = {"status": "match", "name": entry["name"], "run": entry["run"], "blocked_by": hits}
    print(json.dumps(out, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list")
    p.add_argument("--file", help="read this config file instead of --local")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("match")
    p.add_argument("--log", action="append", required=True, help="failed-run log file (repeatable)")
    p.add_argument("--range", required=True, help="BASE...SHA, the PR diff to check against reads")
    p.set_defaults(func=cmd_match)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
