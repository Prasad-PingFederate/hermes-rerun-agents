"""Hermes AST Surgical Patcher (AST-Healer Engine).

Parses tracebacks to identify specific failing functions within target files,
cuts and replaces only that function using Python's AST node spans, preserves
exact indentation, and leaves the rest of the file untouched.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FunctionSpan:
    name: str
    start_line: int  # 1-indexed inclusive
    end_line: int    # 1-indexed inclusive
    indentation: str
    is_async: bool = False
    original_text: str = ""


class ASTSurgicalPatcher:
    """Performs surgical function-level patch splicing on source code."""

    @staticmethod
    def parse_traceback_location(traceback_text: str) -> Optional[Dict[str, Any]]:
        """Extract failing file, line number, and function name from traceback."""
        if not traceback_text:
            return None

        # Pattern 1: Standard Python traceback: File "path/to/file.py", line 12, in func_name
        pattern_std = re.compile(
            r'File\s+["\'](?P<file>[^"\']+)["\'],\s+line\s+(?P<line>\d+),\s+in\s+(?P<func>\w+)',
            re.IGNORECASE,
        )
        matches = list(pattern_std.finditer(traceback_text))
        if matches:
            # Prefer last frame not in site-packages or test runner
            for m in reversed(matches):
                f_path = m.group("file").replace("\\", "/")
                if "site-packages" not in f_path and not f_path.startswith("<"):
                    return {
                        "file": f_path,
                        "line": int(m.group("line")),
                        "function": m.group("func"),
                    }
            last = matches[-1]
            return {
                "file": last.group("file").replace("\\", "/"),
                "line": int(last.group("line")),
                "function": last.group("func"),
            }

        # Pattern 2: Pytest traceback line: path/to/file.py:12: in func_name
        pattern_pytest = re.compile(
            r'(?P<file>[a-zA-Z0-9_\-\.\/\\]+\.py):(?P<line>\d+):\s+in\s+(?P<func>\w+)',
            re.IGNORECASE,
        )
        matches_pytest = list(pattern_pytest.finditer(traceback_text))
        if matches_pytest:
            for m in reversed(matches_pytest):
                f_path = m.group("file").replace("\\", "/")
                if "site-packages" not in f_path:
                    return {
                        "file": f_path,
                        "line": int(m.group("line")),
                        "function": m.group("func"),
                    }
            last = matches_pytest[-1]
            return {
                "file": last.group("file").replace("\\", "/"),
                "line": int(last.group("line")),
                "function": last.group("func"),
            }

        # Pattern 3: AssertionError in func_name: File ...
        return None

    @classmethod
    def locate_function_span(
        cls,
        source_code: str,
        function_name: Optional[str] = None,
        line_number: Optional[int] = None,
    ) -> Optional[FunctionSpan]:
        """Find the exact AST span of the target function in source code."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return None

        lines = source_code.splitlines(keepends=False)
        target_node: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None

        # Pass 1: If line_number is provided, find the innermost function enclosing it
        if line_number is not None:
            innermost_span = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno
                    end = getattr(node, "end_lineno", node.lineno)
                    if start <= line_number <= end:
                        span_len = end - start
                        if innermost_span is None or span_len < innermost_span:
                            innermost_span = span_len
                            target_node = node

        # Pass 2: If not found by line, match by function_name
        if target_node is None and function_name:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                    target_node = node
                    break

        if target_node is None:
            return None

        start = target_node.lineno
        end = getattr(target_node, "end_lineno", target_node.lineno)

        # Detect base indentation of the def line
        def_line = lines[start - 1] if 0 <= start - 1 < len(lines) else ""
        indentation = def_line[: len(def_line) - len(def_line.lstrip())]

        span_lines = lines[start - 1 : end]
        original_text = "\n".join(span_lines)

        return FunctionSpan(
            name=target_node.name,
            start_line=start,
            end_line=end,
            indentation=indentation,
            is_async=isinstance(target_node, ast.AsyncFunctionDef),
            original_text=original_text,
        )

    @classmethod
    def splice_function_patch(
        cls,
        source_code: str,
        span: FunctionSpan,
        replacement_function_code: str,
    ) -> str:
        """Replace the target function span with replacement code at the exact indentation."""
        lines = source_code.splitlines(keepends=False)
        rep_lines = replacement_function_code.strip("\n").splitlines()

        if not rep_lines:
            return source_code

        # Determine existing indentation of replacement's first line
        first_rep = rep_lines[0]
        rep_base_indent_len = len(first_rep) - len(first_rep.lstrip())

        # Align replacement indentation to span.indentation
        aligned_rep_lines = []
        for line in rep_lines:
            if not line.strip():
                aligned_rep_lines.append("")
            else:
                # Strip replacement base indent, add span indentation
                line_content = line[rep_base_indent_len:] if len(line) >= rep_base_indent_len else line.lstrip()
                aligned_rep_lines.append(span.indentation + line_content)

        # Splice lines
        before = lines[: span.start_line - 1]
        after = lines[span.end_line :]
        new_lines = before + aligned_rep_lines + after
        new_source = "\n".join(new_lines)
        if source_code.endswith("\n"):
            new_source += "\n"

        # Validate syntax
        ast.parse(new_source)
        return new_source

