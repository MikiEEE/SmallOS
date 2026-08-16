"""Validate release-bearing pull request titles.

The release workflow uses Python Semantic Release's Conventional Commit parser.
Keeping this check dependency-free lets pull requests reject an incompatible
title before merge without exposing release credentials or installing release
tooling.
"""

from __future__ import annotations

import os
import re
import sys


ALLOWED_TYPES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "style",
    "test",
)

_TITLE_PATTERN = re.compile(
    r"^(?P<type>" + "|".join(ALLOWED_TYPES) + r")"
    r"(?:\((?P<scope>[A-Za-z0-9][A-Za-z0-9._/-]*)\))?"
    r"(?P<breaking>!)?: (?P<summary>\S(?:.*\S)?)$"
)


def validate_title(title: str) -> str | None:
    """Return an actionable error for an invalid title, otherwise ``None``."""

    if "\n" in title or "\r" in title:
        return "pull request titles must be a single line"

    match = _TITLE_PATTERN.fullmatch(title)
    if match is None:
        allowed = ", ".join(ALLOWED_TYPES)
        return (
            "title must follow '<type>(optional-scope)!: summary'; "
            f"allowed types: {allowed}"
        )

    return None


def main() -> int:
    """Validate ``SMALL_OS_PR_TITLE`` and return a process exit status."""

    title = os.environ.get("SMALL_OS_PR_TITLE")
    if title is None:
        print("SMALL_OS_PR_TITLE is required", file=sys.stderr)
        return 2

    error = validate_title(title)
    if error is not None:
        print(f"Invalid pull request title: {error}", file=sys.stderr)
        return 1

    print(f"Release-compatible pull request title: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
