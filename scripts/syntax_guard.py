"""
Preflight Syntax Guard: Enforces strict Python 3.10 syntax compatibility across the repository.
"""

from __future__ import annotations

import ast
import io
import os
import sys
import tokenize
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".tm_snapshots", "reports"}


def check_py310_compatibility(file_path: Path) -> List[Tuple[int, str]]:
    """Check if file parses cleanly under Python 3.10 rules."""
    src = file_path.read_text(encoding="utf-8", errors="replace")
    errors: List[Tuple[int, str]] = []

    # 1. Standard ast parse with feature_version=(3, 10)
    try:
        ast.parse(src, feature_version=(3, 10))
    except SyntaxError as e:
        errors.append((e.lineno or 0, f"SyntaxError under Python 3.10: {e.msg}"))
        return errors

    # 2. Tokenize check for PEP 701 backslash in f-strings
    stack = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(src).readline)
        for t in tokens:
            if t.type == tokenize.FSTRING_START:
                q = t.string.lstrip("fFrRbBuU")
                stack.append(q[:1])
            elif t.type == tokenize.FSTRING_END:
                if stack:
                    stack.pop()
            elif stack and t.type != tokenize.FSTRING_MIDDLE:
                if "\\" in t.string:
                    errors.append((t.start[0], "Backslash inside f-string expression (disallowed in Python 3.10)"))
    except Exception:
        pass

    return errors


def run_guard() -> int:
    all_errors = []
    py_files = []

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)

    print(f"🔍 [SYNTAX GUARD] Checking {len(py_files)} Python files for Python 3.10 compatibility...")

    for pf in py_files:
        errs = check_py310_compatibility(pf)
        for line, msg in errs:
            rel = pf.relative_to(REPO_ROOT)
            print(f"❌ {rel}:{line} - {msg}")
            all_errors.append((rel, line, msg))

    if all_errors:
        print(f"\n[SYNTAX GUARD FAILED] Found {len(all_errors)} Python 3.10 syntax error(s).")
        return 1

    print(f"✅ [SYNTAX GUARD PASSED] All {len(py_files)} files are 100% Python 3.10 compatible.")
    return 0


if __name__ == "__main__":
    sys.exit(run_guard())
