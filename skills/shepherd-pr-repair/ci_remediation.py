#!/usr/bin/env python3
"""CI remediation entries for the shepherd-pr-repair skill.

Entries are per-clone git config sections, set only by the user:

  [kitchen-sink "remediation.<name>"]
      match = <Python regex, re.MULTILINE, searched over the last 300 lines of each failed log>

A match's only action is a full re-run of the head's workflow runs; any other
field makes the entry invalid.

Subcommands (all print JSON on stdout):

  list [--file PATH]        Parse and validate every entry (--local config, or
                            PATH, a scratch config being checked before it is
                            written).
  match --log FILE [--log FILE ...]
                            The one entry every log matches (each log takes its
                            first matching entry in config order; review-config
                            appends new ones last). Any invalid entry fails the
                            whole lookup. Each log is searched whole: the caller
                            passes its last 300 lines.

Log text is only searched, never executed or echoed into a command.

Exit codes: 0 = success / match, 1 = no match, 2 = usage, tool or config error.
"""

import argparse
import json
import re
import subprocess
import sys

PREFIX = "kitchen-sink.remediation."
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")


class ToolError(Exception):
    pass


def read_config(path=None):
    """Return [(key, value)] in config order; value is None for a bare key."""
    scope = ["--file", path] if path else ["--local"]
    cmd = ["git", "config", *scope, "--null", "--get-regexp", r"^kitchen-sink\.remediation\."]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 1:  # no matching key
        return []
    if proc.returncode != 0:
        raise ToolError(f"git config failed ({proc.returncode}): {proc.stderr.strip()}")
    pairs = []
    for record in proc.stdout.split("\0")[:-1]:
        key, sep, value = record.partition("\n")
        pairs.append((key, value if sep else None))
    return pairs


def validate(name, fields):
    if not NAME_RE.fullmatch(name):
        return f"bad name {name!r}"
    unknown = sorted(set(fields) - {"match"})
    if unknown:
        return f"unknown field {unknown[0]!r} (an entry has only match)"
    if len(fields["match"]) != 1:
        return "needs exactly one match"
    # An empty match would match every log; a bare key (None) has no value at all.
    if not fields["match"][0]:
        return "empty value"
    try:
        re.compile(fields["match"][0], re.MULTILINE)
    except re.error as exc:
        return f"bad match regex: {exc}"
    return None


def parse_entries(pairs):
    grouped = {}
    for key, value in pairs:
        name, _, field = key[len(PREFIX) :].rpartition(".")
        grouped.setdefault(name, {}).setdefault(field, []).append(value)
    entries = []
    for name, fields in grouped.items():
        entry = {"name": name, "match": (fields.get("match") or [None])[0]}
        err = validate(name, fields)
        if err:
            entry["error"] = err
        entries.append(entry)
    return entries


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
    print(json.dumps({"status": "match", "name": found[0]["name"]}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list")
    p.add_argument("--file", help="read this config file instead of --local")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("match")
    p.add_argument("--log", action="append", required=True, help="failed-run log file (repeatable)")
    p.set_defaults(func=cmd_match)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
