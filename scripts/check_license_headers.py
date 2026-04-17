#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Verify every Python file in the repo starts with the Oracle UPL license header.

Empty files (e.g. package marker ``__init__.py``) are skipped. A single leading
``#!`` shebang is tolerated before the header.

Exit code:
    0 — all files OK
    1 — one or more files missing/incorrect header
"""

from __future__ import annotations

import sys
from pathlib import Path

HEADER_LINES: tuple[str, ...] = (
    "# Copyright (c) 2026, Oracle and/or its affiliates.",
    "# Licensed under the Universal Permissive License v 1.0 "
    "as shown at https://oss.oracle.com/licenses/upl.",
)

EXCLUDED_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        ".git",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
    }
)


def _file_has_header(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return True
    lines = text.splitlines()
    offset = 1 if lines and lines[0].startswith("#!") else 0
    for i, expected in enumerate(HEADER_LINES):
        idx = offset + i
        if idx >= len(lines) or lines[idx] != expected:
            return False
    return True


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
            continue
        yield path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    files = list(_iter_python_files(root))
    missing = [p for p in files if not _file_has_header(p)]

    if missing:
        print("Missing or incorrect Oracle UPL license header in:", file=sys.stderr)
        for path in missing:
            print(f"  {path.relative_to(root)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Expected header (after an optional shebang):", file=sys.stderr)
        for line in HEADER_LINES:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"Checked {len(files)} Python files — all have the correct license header.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
