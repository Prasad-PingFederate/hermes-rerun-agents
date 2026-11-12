"""
Zero Assertion Erosion Guard (Multi-Runner: Pytest, Jest, Playwright).
Owner: TestCaseWriterAgent & TestHealerAgent, TIER_2

Strictly enforces that AI agents never weaken test suites:
- Strips single-line and block comments so commented-out assertions are caught as deletions.
- Enforces non-decreasing assertion counts across Python (assert) and JS/TS (expect, assert, should).
- Hard-blocks newly introduced skip/weakening modifiers:
  @pytest.mark.skip, @unittest.skip, test.skip, it.skip, describe.skip, xit, xtest, xdescribe, test.todo, page.pause().
- Rejects trivial / tautological assertions (assert True, expect(true).toBe(true), etc.).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ts_playwright_ast_guard import PlaywrightASTGuard


@dataclass
class AssertionErosionReport:
    valid: bool
    tampering_detected: bool
    reasons: List[str] = field(default_factory=list)
    existing_assertions: int = 0
    proposed_assertions: int = 0
    assertion_delta: int = 0
    file_type: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "tampering_detected": self.tampering_detected,
            "reasons": self.reasons,
            "existing_assertions": self.existing_assertions,
            "proposed_assertions": self.proposed_assertions,
            "assertion_delta": self.assertion_delta,
            "file_type": self.file_type,
        }


class ZeroAssertionErosionGuard:
    """Unified Zero Assertion Erosion guard across Python and TypeScript/JavaScript test suites."""

    # Python skip patterns
    PY_SKIP_DECORATORS = [
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "unittest.skip",
        "unittest.skipIf",
        "unittest.skipUnless",
    ]

    @classmethod
    def is_test_file(cls, rel_path: str) -> bool:
        """Determines if the given path is a test/spec file in Python or JS/TS."""
        norm = rel_path.lower().replace("\\", "/")
        if norm.endswith(".py"):
            name = Path(norm).name
            return name.startswith("test_") or name.endswith("_test.py") or "tests/" in norm
        return PlaywrightASTGuard.is_supported(rel_path)

    @classmethod
    def strip_comments(cls, code: str, is_python: bool = False) -> str:
        """Strip single-line and block comments to avoid false-positive assertion counts."""
        if not code:
            return ""
        if is_python:
            # Strip # comments in Python
            lines = []
            for line in code.splitlines():
                stripped = re.sub(r"#.*$", "", line)
                lines.append(stripped)
            return "\n".join(lines)
        else:
            return PlaywrightASTGuard.strip_comments(code)

    @classmethod
    def count_python_assertions(cls, code: str) -> Tuple[int, bool]:
        """Count Python AST assertions and check for trivial assertions."""
        if not code.strip():
            return 0, False
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fallback regex count
            clean = cls.strip_comments(code, is_python=True)
            matches = re.findall(r"\bassert\b", clean)
            return len(matches), False

        assert_count = 0
        has_trivial = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                assert_count += 1
                if isinstance(node.test, ast.Constant) and node.test.value in (True, 1):
                    has_trivial = True
                elif isinstance(node.test, ast.Compare):
                    try:
                        expr = ast.unparse(node.test).strip()
                        if expr in ("1 == 1", "True is not False", "True == True", "0 == 0"):
                            has_trivial = True
                    except Exception:
                        pass
            elif isinstance(node, ast.Call):
                try:
                    call_name = ast.unparse(node.func).lower()
                except Exception:
                    call_name = ""
                if "assert" in call_name:
                    assert_count += 1
                    if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in (True, 1):
                        has_trivial = True

        return assert_count, has_trivial

    @classmethod
    def verify(
        cls,
        rel_path: str,
        proposed_content: str,
        existing_content: Optional[str] = None,
        allow_test_modification: bool = False,
    ) -> AssertionErosionReport:
        """Verify that proposed changes do not erode test assertions or inject skip modifiers."""
        reasons: List[str] = []
        norm = rel_path.lower().replace("\\", "/")

        # 1. TypeScript / JavaScript file (Jest / Playwright)
        if PlaywrightASTGuard.is_supported(rel_path):
            ts_res = PlaywrightASTGuard.verify_spec_content(
                rel_path=rel_path,
                proposed_content=proposed_content,
                existing_content=existing_content,
                allow_test_modification=allow_test_modification,
            )
            return AssertionErosionReport(
                valid=ts_res.valid,
                tampering_detected=ts_res.tampering_detected,
                reasons=ts_res.reasons,
                existing_assertions=ts_res.existing_expect_count,
                proposed_assertions=ts_res.proposed_expect_count,
                assertion_delta=ts_res.expect_count_delta,
                file_type="javascript_typescript",
            )

        # 2. Python test file
        if norm.endswith(".py"):
            # Check Python skips
            clean_prop = cls.strip_comments(proposed_content, is_python=True)
            clean_exist = cls.strip_comments(existing_content, is_python=True) if existing_content else ""

            for skip_pat in cls.PY_SKIP_DECORATORS:
                if skip_pat in clean_prop and skip_pat not in clean_exist:
                    reasons.append(f"{rel_path}: Prohibited skip decorator '{skip_pat}' injected.")

            prop_asserts, prop_trivial = cls.count_python_assertions(proposed_content)
            exist_asserts, _ = cls.count_python_assertions(existing_content) if existing_content else (0, False)
            delta = prop_asserts - exist_asserts

            if existing_content and prop_asserts < exist_asserts:
                reasons.append(
                    f"{rel_path}: Zero Assertion Erosion: Healer cannot reduce assertions from {exist_asserts} to {prop_asserts} (delta: {delta})."
                )

            if prop_trivial:
                reasons.append(f"{rel_path}: Zero Assertion Erosion: Trivial assertion (assert True / assert 1 == 1) detected.")

            tampering = len(reasons) > 0
            return AssertionErosionReport(
                valid=not tampering,
                tampering_detected=tampering,
                reasons=reasons,
                existing_assertions=exist_asserts,
                proposed_assertions=prop_asserts,
                assertion_delta=delta,
                file_type="python",
            )

        # Non-test file
        return AssertionErosionReport(
            valid=True,
            tampering_detected=False,
            reasons=[],
            file_type="other",
        )
