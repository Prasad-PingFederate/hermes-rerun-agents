"""
Semantic Assertion Weakening Guard (AST v2)
Owner: TestCaseWriterAgent & QACriticAgent
Phase: Option 4 (Zero False-Green Verification)

Prevents subtle test neutering and false greens by scoring assertion specificity:
1. Value Dilution:
   - Python: assert x == 200 -> assert x is not None / assert bool(x) / assert x
   - JS/TS: .toBe(200) / .toEqual(...) -> .toBeTruthy() / .toBeDefined() / .not.toBeNull()
2. Exception Broadening:
   - Python: with pytest.raises(PermissionError) -> with pytest.raises(Exception)
   - JS/TS: expect(...).toThrow(CustomAuthError) -> expect(...).toThrow() / toThrow(Error)
3. Timeout Masking:
   - Playwright / Jest: Increasing timeouts (e.g. 5000 -> 60000 ms) to mask latency regressions.

Zero external dependencies (uses standard library: ast, re, pathlib).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class DowngradeFinding:
    """Represents a specific semantic assertion downgrade."""
    category: str  # "VALUE_DILUTION", "EXCEPTION_BROADENING", "TIMEOUT_MASKING"
    file_path: str
    message: str
    line_number: Optional[int] = None
    original_snippet: str = ""
    proposed_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "file_path": self.file_path,
            "message": self.message,
            "line_number": self.line_number,
            "original_snippet": self.original_snippet,
            "proposed_snippet": self.proposed_snippet,
        }


@dataclass
class SemanticGuardResult:
    """Overall outcome of semantic assertion validation."""
    valid: bool
    dilution_detected: bool
    findings: List[DowngradeFinding] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "dilution_detected": self.dilution_detected,
            "findings": [f.to_dict() for f in self.findings],
            "reasons": self.reasons,
        }


class SemanticAssertionGuard:
    """Deterministic static guard inspecting ASTs for assertion weakening, broad catches, and timeout inflation."""

    # Specificity scores for Python AST assertions
    SPECIFICITY_EXACT_EQUALITY = 10     # assert x == 200, assert x is False
    SPECIFICITY_MEMBERSHIP = 8          # assert x in [1, 2], assert "foo" in x
    SPECIFICITY_TYPE_CHECK = 5          # assert isinstance(x, MyClass)
    SPECIFICITY_NON_NULL = 3            # assert x is not None
    SPECIFICITY_BARE_TRUTHY = 1         # assert x, assert bool(x)
    SPECIFICITY_TRIVIAL = 0             # assert True, assert 1

    # Generic exceptions considered broad when replacing specific ones
    BROAD_EXCEPTION_NAMES = {"Exception", "BaseException"}

    # JS/TS loose matchers
    JS_LOOSE_MATCHERS = {
        "toBeTruthy",
        "toBeDefined",
        "toBeFalsy",
        "toBeNull",
        "not.toBeNull",
        "not.toBeUndefined",
        "toBeInstanceOf",
    }

    JS_EXACT_MATCHERS = {
        "toBe",
        "toEqual",
        "toStrictEqual",
        "toBeCloseTo",
    }

    @classmethod
    def strip_comments(cls, code: str) -> str:
        """Strip comments while preserving string literals and URLs."""
        if not code:
            return ""
        pattern = re.compile(
            r'("(?:\\.|[^"\\])*"'
            r"|'(?:\\.|[^'\\])*'"
            r'|`(?:\\.|[^`\\])*`'
            r'|/\*[\s\S]*?\*/'
            r'|//[^\r\n]*)'
        )

        def replacer(match: re.Match) -> str:
            s = match.group(0)
            if s.startswith("/*") or s.startswith("//"):
                return " "
            return s

        return pattern.sub(replacer, code)

    @classmethod
    def evaluate_changes(
        cls,
        proposed_changes: Dict[str, str],
        workspace_root: Optional[Path | str] = None,
        existing_files: Optional[Dict[str, str]] = None,
    ) -> SemanticGuardResult:
        """Evaluate a full proposal dictionary against semantic assertion weakening rules."""
        findings: List[DowngradeFinding] = []
        root = Path(workspace_root).resolve() if workspace_root else None

        for rel_path, proposed_content in proposed_changes.items():
            norm_path = rel_path.replace("\\", "/").lstrip("/")
            existing_content = ""
            if existing_files and rel_path in existing_files:
                existing_content = existing_files[rel_path]
            elif existing_files and norm_path in existing_files:
                existing_content = existing_files[norm_path]
            elif root:
                candidate = root / norm_path
                if candidate.is_file():
                    try:
                        existing_content = candidate.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        existing_content = ""

            if not existing_content:
                # If new file, check for baseline anti-patterns (e.g. pure loose assertions)
                file_findings = cls.check_new_file(norm_path, proposed_content)
                findings.extend(file_findings)
                continue

            if norm_path.endswith(".py"):
                file_findings = cls.check_python_diff(norm_path, existing_content, proposed_content)
                findings.extend(file_findings)
            elif cls.is_js_ts_test(norm_path):
                file_findings = cls.check_js_ts_diff(norm_path, existing_content, proposed_content)
                findings.extend(file_findings)

        dilution_detected = len(findings) > 0
        reasons = [f"{f.file_path} [{f.category}]: {f.message}" for f in findings]

        return SemanticGuardResult(
            valid=not dilution_detected,
            dilution_detected=dilution_detected,
            findings=findings,
            reasons=reasons,
        )

    @classmethod
    def is_js_ts_test(cls, file_path: str) -> bool:
        lower = file_path.lower().replace("\\", "/")
        return (
            lower.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js", ".spec.tsx", ".test.tsx", ".spec.jsx", ".test.jsx"))
            or (("tests/" in lower or "test/" in lower or "__tests__/" in lower) and lower.endswith((".ts", ".js", ".tsx", ".jsx")))
        )

    # -------------------------------------------------------------------------
    # Python AST Analysis
    # -------------------------------------------------------------------------

    @classmethod
    def check_python_diff(
        cls,
        rel_path: str,
        existing_code: str,
        proposed_code: str,
    ) -> List[DowngradeFinding]:
        """Perform differential AST inspection on Python test files."""
        findings: List[DowngradeFinding] = []

        try:
            exist_tree = ast.parse(existing_code, filename=rel_path)
            prop_tree = ast.parse(proposed_code, filename=rel_path)
        except SyntaxError:
            # Syntax errors are handled upstream by ASTPatchGuard
            return findings

        # 1. Check Exception Broadening in pytest.raises(...)
        exist_raises = cls._extract_pytest_raises(exist_tree)
        prop_raises = cls._extract_pytest_raises(prop_tree)

        for exc_name, line_no in prop_raises:
            if exc_name in cls.BROAD_EXCEPTION_NAMES:
                # Check if existing code used a specific exception that is now broadened
                specific_exist = [e for e, _ in exist_raises if e not in cls.BROAD_EXCEPTION_NAMES]
                if specific_exist:
                    findings.append(
                        DowngradeFinding(
                            category="EXCEPTION_BROADENING",
                            file_path=rel_path,
                            message=(
                                f"pytest.raises({exc_name}) broadens exception catch from specific type(s): "
                                f"{', '.join(sorted(set(specific_exist)))}. Replaces strict contract with blanket catch."
                            ),
                            line_number=line_no,
                            original_snippet=f"pytest.raises({specific_exist[0]})",
                            proposed_snippet=f"pytest.raises({exc_name})",
                        )
                    )

        # 2. Check Value Dilution in Assertions
        exist_asserts = cls._extract_assert_descriptors(exist_tree)
        prop_asserts = cls._extract_assert_descriptors(prop_tree)

        # Map targets to their highest existing specificity score
        exist_target_scores: Dict[str, Tuple[int, str]] = {}
        for target, score, snippet, _ in exist_asserts:
            if target not in exist_target_scores or score > exist_target_scores[target][0]:
                exist_target_scores[target] = (score, snippet)

        for target, prop_score, prop_snippet, line_no in prop_asserts:
            if target in exist_target_scores:
                exist_score, exist_snippet = exist_target_scores[target]
                # If previously exact equality (10) and now downgraded to non-null (3) or bare truthy (1)
                if exist_score >= cls.SPECIFICITY_MEMBERSHIP and prop_score <= cls.SPECIFICITY_NON_NULL:
                    findings.append(
                        DowngradeFinding(
                            category="VALUE_DILUTION",
                            file_path=rel_path,
                            message=(
                                f"Assertion on '{target}' diluted from exact match ({exist_snippet}) "
                                f"to loose check ({prop_snippet}). Value specificity degraded from {exist_score} to {prop_score}."
                            ),
                            line_number=line_no,
                            original_snippet=exist_snippet,
                            proposed_snippet=prop_snippet,
                        )
                    )

        # 3. Check Python Playwright/Async Timeout Masking
        exist_timeout_map = {target: ms for target, ms, _ in cls._extract_python_timeouts(exist_tree)}
        prop_timeouts = cls._extract_python_timeouts(prop_tree)

        for prop_target, prop_val, line_no in prop_timeouts:
            exist_val = exist_timeout_map.get(prop_target)
            if exist_val is not None:
                # If increased by >= 3x or inflated from <= 10s to >= 30s
                if prop_val >= max(30000, exist_val * 3) or (exist_val <= 10000 and prop_val >= 30000):
                    findings.append(
                        DowngradeFinding(
                            category="TIMEOUT_MASKING",
                            file_path=rel_path,
                            message=(
                                f"Timeout on '{prop_target}' inflated from {exist_val}ms to {prop_val}ms "
                                f"({round(prop_val / max(1, exist_val), 1)}x). Masks latency or async race regressions."
                            ),
                            line_number=line_no,
                            original_snippet=f"{prop_target}(timeout={exist_val})",
                            proposed_snippet=f"{prop_target}(timeout={prop_val})",
                        )
                    )
            elif prop_val >= 45000:
                # Arbitrary excessive timeout in proposed code
                findings.append(
                    DowngradeFinding(
                        category="TIMEOUT_MASKING",
                        file_path=rel_path,
                        message=f"Excessive timeout of {prop_val}ms set on '{prop_target}'. Masks slow operations.",
                        line_number=line_no,
                        proposed_snippet=f"{prop_target}(timeout={prop_val})",
                    )
                )

        # 4. Check Dead-Code Assertion Bypasses (early return, dead branch, blanket exception swallow)
        dead_code_findings = cls.check_dead_code_assertion_bypasses(rel_path, prop_tree)
        findings.extend(dead_code_findings)

        return findings

    @classmethod
    def _extract_pytest_raises(cls, tree: ast.AST) -> List[Tuple[str, int]]:
        """Extract exception class names passed to pytest.raises(...)."""
        raises_found: List[Tuple[str, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    expr = item.context_expr
                    if isinstance(expr, ast.Call):
                        func_str = cls._unparse_safe(expr.func)
                        if "pytest.raises" in func_str or "raises" in func_str:
                            if expr.args:
                                first_arg = expr.args[0]
                                if isinstance(first_arg, ast.Name):
                                    raises_found.append((first_arg.id, getattr(node, "lineno", 1)))
                                elif isinstance(first_arg, ast.Attribute):
                                    raises_found.append((first_arg.attr, getattr(node, "lineno", 1)))
                                elif isinstance(first_arg, (ast.Tuple, ast.List)):
                                    for elt in first_arg.elts:
                                        elt_name = cls._unparse_safe(elt)
                                        raises_found.append((elt_name, getattr(node, "lineno", 1)))
        return raises_found

    @classmethod
    def _extract_assert_descriptors(
        cls, tree: ast.AST
    ) -> List[Tuple[str, int, str, int]]:
        """Extract (target_expr, specificity_score, unparsed_snippet, line_number) from assert statements."""
        descriptors: List[Tuple[str, int, str, int]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue

            test_node = node.test
            lineno = getattr(node, "lineno", 1)
            snippet = cls._unparse_safe(test_node)

            # Case A: Comparison (e.g. assert x == 200, assert x is not None)
            if isinstance(test_node, ast.Compare):
                left_str = cls._unparse_safe(test_node.left).strip()
                if test_node.ops:
                    op = test_node.ops[0]
                    comparator = test_node.comparators[0] if test_node.comparators else None
                    comp_str = cls._unparse_safe(comparator).strip() if comparator else ""

                    if isinstance(op, ast.Eq):
                        descriptors.append((left_str, cls.SPECIFICITY_EXACT_EQUALITY, snippet, lineno))
                    elif isinstance(op, ast.In):
                        descriptors.append((left_str, cls.SPECIFICITY_MEMBERSHIP, snippet, lineno))
                    elif isinstance(op, ast.IsNot) and comp_str == "None":
                        descriptors.append((left_str, cls.SPECIFICITY_NON_NULL, snippet, lineno))
                    elif isinstance(op, ast.Is) and comp_str in ("True", "False"):
                        descriptors.append((left_str, cls.SPECIFICITY_EXACT_EQUALITY, snippet, lineno))
                    else:
                        descriptors.append((left_str, 5, snippet, lineno))
                continue

            # Case B: Call (e.g. assert isinstance(x, Foo), assert bool(x))
            if isinstance(test_node, ast.Call):
                func_name = cls._unparse_safe(test_node.func).strip()
                if func_name == "isinstance" and test_node.args:
                    arg_str = cls._unparse_safe(test_node.args[0]).strip()
                    descriptors.append((arg_str, cls.SPECIFICITY_TYPE_CHECK, snippet, lineno))
                elif func_name == "bool" and test_node.args:
                    arg_str = cls._unparse_safe(test_node.args[0]).strip()
                    descriptors.append((arg_str, cls.SPECIFICITY_BARE_TRUTHY, snippet, lineno))
                else:
                    descriptors.append((func_name, 4, snippet, lineno))
                continue

            # Case C: Bare Name or Attribute (e.g. assert user.role, assert user)
            if isinstance(test_node, (ast.Name, ast.Attribute)):
                target_str = cls._unparse_safe(test_node).strip()
                descriptors.append((target_str, cls.SPECIFICITY_BARE_TRUTHY, snippet, lineno))
                continue

            # Case D: Constant (assert True, assert 1)
            if isinstance(test_node, ast.Constant):
                descriptors.append(("__constant__", cls.SPECIFICITY_TRIVIAL, snippet, lineno))

        return descriptors

    @classmethod
    def _extract_python_timeouts(cls, tree: ast.AST) -> List[Tuple[str, int, int]]:
        """Extract timeout values in milliseconds from Playwright/async calls."""
        timeouts: List[Tuple[str, int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_str = cls._unparse_safe(node.func)
                for kw in node.keywords:
                    if kw.arg == "timeout" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                        # If value < 100, might be seconds, convert to ms
                        ms = int(kw.value.value * 1000) if kw.value.value < 100 else int(kw.value.value)
                        target = func_str.split(".")[-1]
                        timeouts.append((target, ms, getattr(node, "lineno", 1)))

        return timeouts

    # -------------------------------------------------------------------------
    # JS / TS Analysis
    # -------------------------------------------------------------------------

    @classmethod
    def check_js_ts_diff(
        cls,
        rel_path: str,
        existing_code: str,
        proposed_code: str,
    ) -> List[DowngradeFinding]:
        """Perform regex and token-based AST v2 inspection on JS/TS test files."""
        findings: List[DowngradeFinding] = []

        clean_exist = cls.strip_comments(existing_code)
        clean_prop = cls.strip_comments(proposed_code)

        # 1. Value Dilution: .toBe(x) / .toEqual(x) replaced with .toBeTruthy() / .toBeDefined()
        exist_exact_count = len(re.findall(r"\.(?:toBe|toEqual|toStrictEqual)\s*\(", clean_exist))
        prop_exact_count = len(re.findall(r"\.(?:toBe|toEqual|toStrictEqual)\s*\(", clean_prop))

        exist_loose_count = len(re.findall(r"\.(?:toBeTruthy|toBeDefined|not\.toBeNull)\s*\(", clean_exist))
        prop_loose_count = len(re.findall(r"\.(?:toBeTruthy|toBeDefined|not\.toBeNull)\s*\(", clean_prop))

        # If exact matcher count dropped while loose matcher count increased
        if exist_exact_count > 0 and prop_exact_count < exist_exact_count and prop_loose_count > exist_loose_count:
            findings.append(
                DowngradeFinding(
                    category="VALUE_DILUTION",
                    file_path=rel_path,
                    message=(
                        f"Exact matchers (toBe/toEqual) reduced from {exist_exact_count} to {prop_exact_count} "
                        f"while loose matchers (toBeTruthy/toBeDefined) increased from {exist_loose_count} to {prop_loose_count}. "
                        "Dilutes assertion specificity."
                    ),
                    original_snippet=f"{exist_exact_count} exact / {exist_loose_count} loose matchers",
                    proposed_snippet=f"{prop_exact_count} exact / {prop_loose_count} loose matchers",
                )
            )

        # 2. Exception Broadening in toThrow()
        # Look for: expect(...).toThrow(SpecificError) -> expect(...).toThrow() or expect(...).toThrow(Error)
        exist_specific_throw = re.findall(r"\.toThrow\s*\(\s*([A-Za-z0-9_]+)\s*\)", clean_exist)
        exist_specific_throw = [e for e in exist_specific_throw if e not in ("Error", "")]

        prop_bare_throw = re.findall(r"\.toThrow\s*\(\s*(?:Error)?\s*\)", clean_prop)
        if exist_specific_throw and len(prop_bare_throw) > len(re.findall(r"\.toThrow\s*\(\s*(?:Error)?\s*\)", clean_exist)):
            findings.append(
                DowngradeFinding(
                    category="EXCEPTION_BROADENING",
                    file_path=rel_path,
                    message=(
                        f"expect(...).toThrow() broadened from specific error class(es) "
                        f"({', '.join(sorted(set(exist_specific_throw)))}) to bare/generic Error catch."
                    ),
                    original_snippet=f".toThrow({exist_specific_throw[0]})",
                    proposed_snippet=".toThrow()",
                )
            )

        # 3. Timeout Masking: Playwright / Jest timeout inflation
        exist_timeouts = [int(m) for m in re.findall(r"timeout\s*:\s*(\d+)", clean_exist)]
        prop_timeouts = [int(m) for m in re.findall(r"timeout\s*:\s*(\d+)", clean_prop)]

        max_exist_t = max(exist_timeouts) if exist_timeouts else 5000
        for pt in prop_timeouts:
            if (pt >= max(30000, max_exist_t * 3)) or (max_exist_t <= 10000 and pt >= 30000):
                findings.append(
                    DowngradeFinding(
                        category="TIMEOUT_MASKING",
                        file_path=rel_path,
                        message=(
                            f"Playwright/Jest timeout increased to {pt}ms (was {max_exist_t}ms). "
                            "Inflated timeout masks async races or performance regressions."
                        ),
                        original_snippet=f"timeout: {max_exist_t}",
                        proposed_snippet=f"timeout: {pt}",
                    )
                )

        return findings

    @classmethod
    def check_new_file(cls, rel_path: str, content: str) -> List[DowngradeFinding]:
        """Verify newly authored test files meet minimum specificity standards."""
        findings: List[DowngradeFinding] = []
        if rel_path.endswith(".py"):
            try:
                tree = ast.parse(content, filename=rel_path)
            except SyntaxError:
                return findings
            raises_found = cls._extract_pytest_raises(tree)
            for exc_name, line_no in raises_found:
                if exc_name in cls.BROAD_EXCEPTION_NAMES:
                    findings.append(
                        DowngradeFinding(
                            category="EXCEPTION_BROADENING",
                            file_path=rel_path,
                            message=f"New test uses blanket pytest.raises({exc_name}). Require specific exception type.",
                            line_number=line_no,
                            proposed_snippet=f"pytest.raises({exc_name})",
                        )
                    )
            findings.extend(cls.check_dead_code_assertion_bypasses(rel_path, tree))
        return findings

    @classmethod
    def check_dead_code_assertion_bypasses(
        cls, rel_path: str, tree: ast.AST
    ) -> List[DowngradeFinding]:
        """Detect dead-branch bypasses in Python tests: early returns before asserts,
        asserts in statically dead branches, and try/except swallows of assertions."""
        findings: List[DowngradeFinding] = []

        def _contains_assert(nodes: List[ast.stmt]) -> Tuple[bool, Optional[int], Optional[str]]:
            for n in nodes:
                for sub in ast.walk(n):
                    if isinstance(sub, ast.Assert):
                        lineno = getattr(sub, "lineno", getattr(n, "lineno", 1))
                        return True, lineno, cls._unparse_safe(sub)
                    if isinstance(sub, ast.Call):
                        func_name = cls._unparse_safe(sub.func).lower()
                        if "assert" in func_name:
                            lineno = getattr(sub, "lineno", getattr(n, "lineno", 1))
                            return True, lineno, cls._unparse_safe(sub)
            return False, None, None

        # 1. Early return preceding assertions in test functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not (node.name.startswith("test_") or node.name.startswith("test")):
                    continue

                return_seen = False
                return_lineno = None
                for stmt in node.body:
                    if isinstance(stmt, ast.Return):
                        return_seen = True
                        return_lineno = getattr(stmt, "lineno", getattr(node, "lineno", 1))
                    elif return_seen:
                        has_assert, assert_lineno, assert_snippet = _contains_assert([stmt])
                        if has_assert:
                            findings.append(
                                DowngradeFinding(
                                    category="DEAD_CODE_ASSERTION_BYPASS",
                                    file_path=rel_path,
                                    message=(
                                        f"In '{node.name}': Early return at line {return_lineno} "
                                        f"precedes unreachable assertion at line {assert_lineno} ({assert_snippet}). "
                                        "Dead-code bypasses test verification unconditionally."
                                    ),
                                    line_number=return_lineno,
                                    original_snippet="",
                                    proposed_snippet=f"return ... {assert_snippet}",
                                )
                            )
                            break

        # 2. Dead conditionals containing assertions (if False:, if 0:, if None:, if not True:)
        def _is_statically_false(expr: ast.expr) -> bool:
            if isinstance(expr, ast.Constant):
                return not bool(expr.value)
            if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
                if isinstance(expr.operand, ast.Constant):
                    return bool(expr.operand.value)
            return False

        def _is_statically_true(expr: ast.expr) -> bool:
            if isinstance(expr, ast.Constant):
                return bool(expr.value)
            if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
                if isinstance(expr.operand, ast.Constant):
                    return not bool(expr.operand.value)
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # Body is dead if condition is statically false
                if _is_statically_false(node.test):
                    has_assert, assert_lineno, assert_snippet = _contains_assert(node.body)
                    if has_assert:
                        cond_str = cls._unparse_safe(node.test)
                        findings.append(
                            DowngradeFinding(
                                category="DEAD_CODE_ASSERTION_BYPASS",
                                file_path=rel_path,
                                message=(
                                    f"Assertion ({assert_snippet}) placed inside statically dead branch "
                                    f"'if {cond_str}:' at line {getattr(node, 'lineno', 1)}. Test will never execute."
                                ),
                                line_number=assert_lineno,
                                proposed_snippet=f"if {cond_str}: {assert_snippet}",
                            )
                        )
                # Else body is dead if condition is statically true
                if _is_statically_true(node.test) and node.orelse:
                    has_assert, assert_lineno, assert_snippet = _contains_assert(node.orelse)
                    if has_assert:
                        cond_str = cls._unparse_safe(node.test)
                        findings.append(
                            DowngradeFinding(
                                category="DEAD_CODE_ASSERTION_BYPASS",
                                file_path=rel_path,
                                message=(
                                    f"Assertion ({assert_snippet}) placed inside dead else branch of "
                                    f"'if {cond_str}:' at line {getattr(node, 'lineno', 1)}. Test will never execute."
                                ),
                                line_number=assert_lineno,
                                proposed_snippet=f"else: {assert_snippet}",
                            )
                        )

        # 3. Blanket suppression: try: ... assert ... except: pass
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                has_assert, assert_lineno, assert_snippet = _contains_assert(node.body)
                if has_assert:
                    for handler in node.handlers:
                        catches_broadly = False
                        if handler.type is None:  # bare except:
                            catches_broadly = True
                        else:
                            type_str = cls._unparse_safe(handler.type)
                            if any(e in type_str for e in ("Exception", "BaseException", "AssertionError")):
                                catches_broadly = True

                        if catches_broadly:
                            swallows = False
                            if not handler.body:
                                swallows = True
                            elif len(handler.body) == 1:
                                h_stmt = handler.body[0]
                                if isinstance(h_stmt, ast.Pass):
                                    swallows = True
                                elif isinstance(h_stmt, ast.Return) and h_stmt.value is None:
                                    swallows = True
                                elif isinstance(h_stmt, ast.Expr) and isinstance(h_stmt.value, ast.Constant):
                                    swallows = True

                            if swallows:
                                handler_type_str = cls._unparse_safe(handler.type) or "bare"
                                findings.append(
                                    DowngradeFinding(
                                        category="DEAD_CODE_ASSERTION_BYPASS",
                                        file_path=rel_path,
                                        message=(
                                            f"Assertion at line {assert_lineno} ({assert_snippet}) wrapped in "
                                            f"try block with swallowing 'except {handler_type_str}: pass'. "
                                            "Silently masks test failures."
                                        ),
                                        line_number=assert_lineno,
                                        proposed_snippet=f"try: {assert_snippet} except: pass",
                                    )
                                )
                                break

        return findings

    @classmethod
    def _unparse_safe(cls, node: Optional[ast.AST]) -> str:
        if node is None:
            return ""
        try:
            return ast.unparse(node).strip()
        except Exception:
            return ""
