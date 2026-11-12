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
    return re.fullmatch(r"[A-Za-z0-9._-]+", s) is not None


def valid_id(s):
    return re.fullmatch(r"[0-9]+", s) is not None


def valid_model(s):
    """The model name goes into the public `@codex review` footer."""
    return re.fullmatch(r"[A-Za-z0-9. -]{1,40}", s) is not None


def timeout_minutes(raw):
    if raw is None:
        return DEFAULT_TIMEOUT_MINUTES
    if re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise RuleError(f"shepherdTimeoutMinutes={raw!r} is not a positive integer")
    return int(raw)
