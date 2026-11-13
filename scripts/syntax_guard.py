"""
Preflight Syntax Guard: Enforces strict Python 3.10 syntax compatibility across the repository.
Detects backslashes inside f-string expressions without relying on Python 3.12+ tokenize.FSTRING_* tokens.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".tm_snapshots", "reports", ".rerun_tasks"}


def check_py310_compatibility(file_path: Path) -> List[Tuple[int, str]]:
    """Check if file parses cleanly under Python 3.10 rules."""
    src = file_path.read_text(encoding="utf-8", errors="replace")
    errors: List[Tuple[int, str]] = []

    # 1. Standard ast parse with feature_version=(3, 10)
    try:
        tree = ast.parse(src, feature_version=(3, 10))
    except SyntaxError as e:
        errors.append((e.lineno or 0, f"SyntaxError under Python 3.10: {e.msg}"))
        return errors

    # 2. Walk AST to detect PEP 701 backslashes inside f-string expressions on any Python runtime
    for node in ast.walk(tree):
        if isinstance(node, ast.FormattedValue):
            segment = ast.get_source_segment(src, node.value)
            if segment and "\\" in segment:
                errors.append(
                    (node.lineno, "Backslash inside f-string expression (disallowed in Python 3.10)")
                )
            if node.format_spec:
                # Walk format_spec nodes to avoid CPython 3.10/3.11 ast.get_source_segment offset issues
                for sub in ast.walk(node.format_spec):
                    if isinstance(sub, ast.FormattedValue):
                        sub_seg = ast.get_source_segment(src, sub.value)
                        if sub_seg and "\\" in sub_seg:
                            errors.append(
                                (node.lineno, "Backslash inside nested f-string expression (disallowed in Python 3.10)")
                            )
                    elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and "\\" in sub.value:
                        errors.append(
                            (node.lineno, "Backslash inside f-string format_spec (disallowed in Python 3.10)")
                        )

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

    # 3. Root shim integrity check (Deliverable 1): ensure root .py files do not define duplicate classes
    root_shims = [
        "ast_patch_guard.py", "ci_failure_ingestor.py", "console_demo_manager.py",
        "console_ui.py", "context_slicer.py", "hermes_cli.py", "hermes_workers.py",
        "llm_provider_adapter.py", "qa_critic_reviewer.py", "sandbox_executor.py",
        "scrum_master_orchestrator.py", "security_blast_radius.py", "server.py",
        "sprint_dag_scheduler.py", "sprint_state_store.py", "ticket_router.py",
        "ts_playwright_ast_guard.py", "workspace_patch_applier.py", "write_gate_controller.py",
    ]
    for shim in root_shims:
        shim_path = REPO_ROOT / shim
        if shim_path.is_file():
            tree = ast.parse(shim_path.read_text(encoding="utf-8"), filename=str(shim_path))
            classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
            if classes:
                all_errors.append((shim, 1, f"Root shim defines duplicate standalone classes: {classes}"))

    if all_errors:
        print(f"\n[SYNTAX GUARD FAILED] Found {len(all_errors)} Python 3.10 syntax error(s).")
        return 1

    print(f"✅ [SYNTAX GUARD PASSED] All {len(py_files)} files are 100% Python 3.10 compatible with clean root shims.")
    return 0


if __name__ == "__main__":
    sys.exit(run_guard())
