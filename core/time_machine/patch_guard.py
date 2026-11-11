"""
AST Test-Tampering Guard & Blast-Radius Analyzer
Analyzes code changes for syntax validity, test suite tampering, and blast-radius metrics.
Zero external dependencies (uses standard library: ast, difflib, pathlib).
"""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def is_test_file(rel_path: str) -> bool:
    """Returns True if the file path represents a Python test file."""
    norm = rel_path.replace("\\", "/")
    name = Path(norm).name
    return (name.startswith("test_") or name.endswith("_test.py")) and name.endswith(".py")


def extract_test_functions(tree: ast.AST) -> Set[str]:
    """Extract names of all test functions (starting with 'test_') from an AST."""
    test_funcs: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_") or node.name.startswith("test"):
                test_funcs.add(node.name)
    return test_funcs


def extract_skip_indicators(tree: ast.AST) -> List[str]:
    """Detect skip decorators (@unittest.skip, @pytest.mark.skip) or skip calls."""
    skips: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                try:
                    dec_str = ast.unparse(dec)
                except Exception:
                    dec_str = ""
                dec_lower = dec_str.lower()
                if any(k in dec_lower for k in ("skip", "skipif")):
                    skips.append(f"{node.name}:{dec_str}")
        if isinstance(node, ast.Call):
            try:
                call_str = ast.unparse(node.func)
            except Exception:
                call_str = ""
            call_lower = call_str.lower()
            if "skip" in call_lower:
                skips.append(f"call:{call_str}")
    return skips


def count_assertions_and_check_weakened(tree: ast.AST) -> Tuple[int, bool]:
    """Counts assert statements and checks if any assertion is weakened to assert True or 1."""
    assert_count = 0
    has_trivial_assert = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assert_count += 1
            if isinstance(node.test, ast.Constant) and node.test.value in (True, 1):
                has_trivial_assert = True
        elif isinstance(node, ast.Call):
            try:
                call_func = ast.unparse(node.func)
            except Exception:
                call_func = ""
            if "assert" in call_func.lower():
                assert_count += 1
                if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in (True, 1):
                    has_trivial_assert = True

    return assert_count, has_trivial_assert


def extract_all_function_names(tree: ast.AST) -> Set[str]:
    """Extract all function/method names defined in an AST."""
    funcs: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
    return funcs


def analyze_proposed_changes(
    workspace_root: Path,
    proposed_changes: Dict[str, str],
    allow_test_modification: bool = False,
) -> Dict[str, Any]:
    """Analyzes proposed file modifications.

    1. Checks Python syntax on every .py file using ast.parse(), raising ValueError on SyntaxError.
    2. Compares AST for test files against existing files to detect deleted tests, added skips, or weakened assertions.
    3. Computes blast-radius metrics (files_changed, lines_added, lines_removed, functions_modified, risk_level).
    """
    workspace_root = Path(workspace_root).resolve()
    tampering_detected = False
    tampering_reasons: List[str] = []

    total_lines_added = 0
    total_lines_removed = 0
    functions_modified_count = 0

    # 1. Parse and validate syntax on every .py file
    for rel_path, proposed_content in proposed_changes.items():
        if rel_path.endswith(".py"):
            try:
                ast.parse(proposed_content, filename=rel_path)
            except SyntaxError as e:
                raise ValueError(f"Syntax error in {rel_path} at line {e.lineno}: {e.msg}")

    # 2. Analyze test tampering & blast radius
    for rel_path, proposed_content in proposed_changes.items():
        existing_path = workspace_root / rel_path
        existing_content = ""
        if existing_path.is_file():
            try:
                existing_content = existing_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                existing_content = ""

        # Line diff calculation
        old_lines = existing_content.splitlines(keepends=True)
        new_lines = proposed_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines))
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                total_lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_lines_removed += 1

        # Function modifications
        if rel_path.endswith(".py"):
            try:
                prop_tree = ast.parse(proposed_content, filename=rel_path)
                exist_tree = ast.parse(existing_content, filename=rel_path) if existing_content else None

                prop_funcs = extract_all_function_names(prop_tree)
                exist_funcs = extract_all_function_names(exist_tree) if exist_tree else set()
                diff_funcs = (prop_funcs - exist_funcs) | (exist_funcs - prop_funcs)
                functions_modified_count += len(diff_funcs)

                # Test tampering checks if this is a test file
                if is_test_file(rel_path) and exist_tree:
                    # Check deleted tests
                    exist_tests = extract_test_functions(exist_tree)
                    prop_tests = extract_test_functions(prop_tree)
                    deleted_tests = exist_tests - prop_tests
                    if deleted_tests:
                        tampering_detected = True
                        tampering_reasons.append(
                            f"Deleted test function(s) in {rel_path}: {sorted(list(deleted_tests))}"
                        )

                    # Check added skips
                    exist_skips = set(extract_skip_indicators(exist_tree))
                    prop_skips = set(extract_skip_indicators(prop_tree))
                    new_skips = prop_skips - exist_skips
                    if new_skips:
                        tampering_detected = True
                        tampering_reasons.append(
                            f"Added skip decorator/call in {rel_path}: {sorted(list(new_skips))}"
                        )

                    # Check weakened assertions
                    exist_asserts, _ = count_assertions_and_check_weakened(exist_tree)
                    prop_asserts, prop_trivial = count_assertions_and_check_weakened(prop_tree)

                    if prop_asserts < exist_asserts:
                        tampering_detected = True
                        tampering_reasons.append(
                            f"Weakened assertions in {rel_path}: assert count decreased from {exist_asserts} to {prop_asserts}"
                        )

                    if prop_trivial:
                        tampering_detected = True
                        tampering_reasons.append(
                            f"Weakened assertions in {rel_path}: trivial assert True / assert 1 detected"
                        )
            except Exception as e:
                if isinstance(e, ValueError):
                    raise

    files_changed_count = len(proposed_changes)

    # Determine risk level
    if tampering_detected:
        risk_level = "HIGH"
    elif files_changed_count > 3 or (total_lines_added + total_lines_removed) > 100 or functions_modified_count > 5:
        risk_level = "HIGH"
    elif files_changed_count > 1 or (total_lines_added + total_lines_removed) > 30 or functions_modified_count > 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    blast_radius = {
        "files_changed": files_changed_count,
        "lines_added": total_lines_added,
        "lines_removed": total_lines_removed,
        "functions_modified": functions_modified_count,
        "risk_level": risk_level,
    }

    is_valid = True
    if tampering_detected and not allow_test_modification:
        is_valid = False

    return {
        "valid": is_valid,
        "tampering_detected": tampering_detected,
        "tampering_reasons": tampering_reasons,
        "blast_radius": blast_radius,
    }

