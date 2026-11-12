"""
GAP-07: Playwright / TypeScript AST Patch Guard Extension
Owner: TestCaseWriterAgent, TIER_2

Verifies TypeScript and JavaScript Playwright test diffs (.spec.ts, .test.ts, .spec.js, .test.js):
- Rejects test.skip(), test.fixme(), test.only(), and describe.skip().
- Rejects hardcoded page.waitForTimeout(>0) in favor of web-first assertions.
- Rejects tautological assertions like expect(true).toBe(true).
- Enforces Zero Assertion Erosion: expect(...) count must never decrease.
- Integrates into ASTPatchGuard dispatcher by file extension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TypeScriptGuardResult:
    valid: bool
    tampering_detected: bool
    reasons: List[str]
    existing_expect_count: int = 0
    proposed_expect_count: int = 0
    expect_count_delta: int = 0
    warnings: List[str] = field(default_factory=list)


class PlaywrightASTGuard:
    """Static analysis and integrity guard for TypeScript/JavaScript Playwright test specifications."""

    # Prohibited skipped or focused test decorators
    PROHIBITED_TEST_PATTERNS = [
        (r"\btest\.skip\s*\(", "Prohibited test.skip() detected"),
        (r"\btest\.fixme\s*\(", "Prohibited test.fixme() detected"),
        (r"\btest\.only\s*\(", "Prohibited test.only() detected"),
        (r"\bit\.skip\s*\(", "Prohibited it.skip() detected"),
        (r"\bit\.only\s*\(", "Prohibited it.only() detected"),
        (r"\bdescribe\.skip\s*\(", "Prohibited describe.skip() detected"),
        (r"\bdescribe\.only\s*\(", "Prohibited describe.only() detected"),
    ]

    # Prohibited arbitrary timeout patterns
    PROHIBITED_TIMEOUT_PATTERNS = [
        (r"\bpage\.waitForTimeout\s*\(\s*(?!0\b)[^)]+\)", "Prohibited hardcoded page.waitForTimeout(>0) detected. Use locator-based web-first assertions instead"),
        (r"\bwaitForTimeout\s*\(\s*(?!0\b)[^)]+\)", "Prohibited hardcoded waitForTimeout(>0) detected"),
    ]

    # Prohibited tautological / fake assertions
    TAUTOLOGICAL_ASSERTIONS = [
        (r"\bexpect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)", "Tautological assertion expect(true).toBe(true) detected"),
        (r"\bexpect\s*\(\s*false\s*\)\s*\.\s*toBe\s*\(\s*false\s*\)", "Tautological assertion expect(false).toBe(false) detected"),
        (r"\bexpect\s*\(\s*true\s*\)\s*\.\s*toBeTruthy\s*\(", "Tautological assertion expect(true).toBeTruthy() detected"),
        (r"\bexpect\s*\(\s*1\s*\)\s*\.\s*toBe\s*\(\s*1\s*\)", "Tautological assertion expect(1).toBe(1) detected"),
        (r"\bexpect\s*\(\s*0\s*\)\s*\.\s*toBe\s*\(\s*0\s*\)", "Tautological assertion expect(0).toBe(0) detected"),
        (r"\bexpect\s*\(\s*['\"][^'\"]*['\"]\s*\)\s*\.\s*toBe\s*\(\s*['\"][^'\"]*['\"]\s*\)", "Tautological string identity assertion detected"),
    ]

    # Pattern to detect expect(...) assertions
    EXPECT_PATTERN = re.compile(r"\bexpect\s*\([^;{}()]+\)", re.MULTILINE)

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Return True if file path is a TypeScript/JavaScript test or spec file."""
        lower = file_path.lower().replace("\\", "/")
        return (
            lower.endswith(".spec.ts")
            or lower.endswith(".test.ts")
            or lower.endswith(".spec.js")
            or lower.endswith(".test.js")
            or "/tests/" in lower and (lower.endswith(".ts") or lower.endswith(".js"))
        )

    @classmethod
    def strip_comments(cls, code: str) -> str:
        """Strip block and line comments to avoid false positives on commented-out code."""
        # Strip /* ... */
        code_no_block = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
        # Strip // ...
        code_clean = re.sub(r"//.*$", "", code_no_block, flags=re.MULTILINE)
        return code_clean

    @classmethod
    def count_assertions(cls, code: str) -> int:
        """Count legitimate expect(...) assertions in code."""
        clean = cls.strip_comments(code)
        matches = re.findall(r"\bexpect\s*\(", clean)
        return len(matches)

    @classmethod
    def verify_spec_content(
        cls,
        rel_path: str,
        proposed_content: str,
        existing_content: Optional[str] = None,
        allow_test_modification: bool = False,
    ) -> TypeScriptGuardResult:
        """Analyze proposed TypeScript/JavaScript test changes against security and anti-erosion rules."""
        reasons: List[str] = []
        warnings: List[str] = []

        clean_proposed = cls.strip_comments(proposed_content)

        # 1. Check prohibited test skip/fixme/only
        for pattern, msg in cls.PROHIBITED_TEST_PATTERNS:
            if re.search(pattern, clean_proposed):
                reasons.append(f"{rel_path}: {msg}")

        # 2. Check prohibited page.waitForTimeout(>0)
        for pattern, msg in cls.PROHIBITED_TIMEOUT_PATTERNS:
            if re.search(pattern, clean_proposed):
                reasons.append(f"{rel_path}: {msg}")

        # 3. Check tautological assertions
        for pattern, msg in cls.TAUTOLOGICAL_ASSERTIONS:
            if re.search(pattern, clean_proposed):
                reasons.append(f"{rel_path}: {msg}")

        # 4. Zero Assertion Erosion check
        existing_expects = cls.count_assertions(existing_content) if existing_content else 0
        proposed_expects = cls.count_assertions(proposed_content)
        delta = proposed_expects - existing_expects

        if existing_content and not allow_test_modification:
            if proposed_expects < existing_expects:
                reasons.append(
                    f"{rel_path}: Zero Assertion Erosion violated: expect count reduced from "
                    f"{existing_expects} to {proposed_expects} (delta: {delta})"
                )

        tampering_detected = len(reasons) > 0
        valid = not tampering_detected

        return TypeScriptGuardResult(
            valid=valid,
            tampering_detected=tampering_detected,
            reasons=reasons,
            existing_expect_count=existing_expects,
            proposed_expect_count=proposed_expects,
            expect_count_delta=delta,
            warnings=warnings,
        )


def analyze_ts_playwright_changes(
    workspace_root: Path,
    proposed_changes: Dict[str, str],
    allow_test_modification: bool = False,
) -> Dict[str, Any]:
    """Unified helper for analyzing TypeScript/JavaScript Playwright proposed changes."""
    reasons: List[str] = []
    tampering_detected = False
    details: Dict[str, Any] = {}

    for rel_path, proposed_content in proposed_changes.items():
        if not PlaywrightASTGuard.is_supported(rel_path):
            continue

        existing_content = None
        target_path = workspace_root / rel_path.replace("\\", "/").lstrip("/")
        if target_path.is_file():
            try:
                existing_content = target_path.read_text(encoding="utf-8")
            except Exception:
                existing_content = None

        res = PlaywrightASTGuard.verify_spec_content(
            rel_path=rel_path,
            proposed_content=proposed_content,
            existing_content=existing_content,
            allow_test_modification=allow_test_modification,
        )

        details[rel_path] = {
            "valid": res.valid,
            "existing_expect_count": res.existing_expect_count,
            "proposed_expect_count": res.proposed_expect_count,
            "expect_count_delta": res.expect_count_delta,
            "reasons": res.reasons,
        }

        if not res.valid:
            tampering_detected = True
            reasons.extend(res.reasons)

    return {
        "valid": not tampering_detected,
        "tampering_detected": tampering_detected,
        "reasons": reasons,
        "details": details,
    }
