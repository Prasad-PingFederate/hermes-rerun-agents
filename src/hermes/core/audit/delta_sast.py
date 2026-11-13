"""
Delta-SAST Security Sanitization & Zero Assertion Erosion Pre-Publication Gate
Owner: QACriticAgent & SecurityGateAgent
Phase: Phase 3 (Enterprise Patch Safety & Compliance)

Inspects every candidate code fix / unified diff / GitHub PR suggestion block
before publication. Two independent verification layers:

  A. Zero Assertion Erosion Guard:
     Blocks patches that delete/weaken assertions, inject skip directives,
     replace assertions with tautologies, swallow exceptions, or mask
     PRODUCT_BUG HTTP status codes in test assertions.

  B. Delta-SAST Security Sanitizer (diff-scoped static analysis):
     Blocks patches introducing code/command injection, TLS downgrades,
     SQL injection, secret leaks, or workflow tampering.

Structured PatchGuardVerdict determines whether a suggestion is APPROVED,
BLOCKED, or emitted as diagnostic-only (code patch stripped, prose preserved).

Zero external dependencies — Python 3.10 standard library only (ast, re, difflib).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────
#  Data Models
# ──────────────────────────────────────────────────────────────

@dataclass
class PatchViolation:
    """A single violation found during patch verification."""
    rule_id: str
    severity: str  # "ERROR", "WARNING"
    message: str
    line_excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "line_excerpt": self.line_excerpt,
        }


@dataclass
class PatchGuardVerdict:
    """Structured verdict from Delta-SAST & Assertion Erosion checks."""
    passed: bool
    status: str  # APPROVED, BLOCKED_ASSERTION_EROSION, BLOCKED_DELTA_SAST, BLOCKED_PRODUCT_BUG_MASKING
    violations: List[PatchViolation] = field(default_factory=list)
    sanitized_suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "violations": [v.to_dict() for v in self.violations],
            "sanitized_suggestion": self.sanitized_suggestion,
        }


# ──────────────────────────────────────────────────────────────
#  A. Zero Assertion Erosion Guard (Diff-Level)
# ──────────────────────────────────────────────────────────────

class AssertionErosionChecker:
    """Diff-level assertion erosion detection for Python & JS/TS test code."""

    # Multi-language assertion patterns
    ASSERTION_PATTERNS: List[re.Pattern[str]] = [
        # Python
        re.compile(r"\bassert\b\s+(?!False)"),
        re.compile(r"\bself\.assert\w+\s*\("),
        re.compile(r"\bpytest\.raises\s*\("),
        # JS/TS: expect(...).to*, assert.*
        re.compile(r"\bexpect\s*\(.*\)\s*\.to\w+"),
        re.compile(r"\bexpect\s*\(.*\)\s*\.not\s*\.to\w+"),
        re.compile(r"\bassert\w*\s*\("),  # JUnit: assertEquals, assertTrue, assertThat
    ]

    # Tautological assertion patterns
    TAUTOLOGY_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\bassert\s+True\b"),
        re.compile(r"\bassert\s+1\s*==\s*1\b"),
        re.compile(r"\bassert\s+0\s*==\s*0\b"),
        re.compile(r"\bexpect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)"),
        re.compile(r"\bexpect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)"),
        re.compile(r"\bassertTrue\s*\(\s*true\s*\)"),
        re.compile(r"\bassertTrue\s*\(\s*True\s*\)"),
        re.compile(r"\bassertEquals\s*\(\s*1\s*,\s*1\s*\)"),
    ]

    # Test suppression / skip / bypass directives
    SKIP_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"@pytest\.mark\.skip\b"),
        re.compile(r"@pytest\.mark\.skipif\b"),
        re.compile(r"@pytest\.mark\.xfail\b"),
        re.compile(r"\bpytest\.skip\s*\("),
        re.compile(r"\btest\.skip\s*\("),
        re.compile(r"\bit\.skip\s*\("),
        re.compile(r"\bdescribe\.skip\s*\("),
        re.compile(r"\.only\s*\("),
        re.compile(r"@Ignore\b"),
        re.compile(r"@Disabled\b"),
    ]

    # Exception swallowing patterns
    EXCEPTION_SWALLOW_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"except\s*:\s*pass\b"),
        re.compile(r"except\s+Exception\s*:\s*pass\b"),
        re.compile(r"except\s+BaseException\s*:\s*pass\b"),
        re.compile(r"except\s+Exception\s+as\s+\w+\s*:\s*pass\b"),
        re.compile(r"\.catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)"),
    ]

    @classmethod
    def count_assertions(cls, lines: List[str]) -> int:
        """Count assertion statements across multi-language lines."""
        count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            for pattern in cls.ASSERTION_PATTERNS:
                if pattern.search(stripped):
                    count += 1
                    break  # Count each line only once
        return count

    @classmethod
    def check_assertion_erosion(
        cls,
        original_lines: List[str],
        patched_lines: List[str],
    ) -> List[PatchViolation]:
        """Check for assertion deletion, tautologies, skips, and exception swallowing."""
        violations: List[PatchViolation] = []

        orig_count = cls.count_assertions(original_lines)
        patched_count = cls.count_assertions(patched_lines)

        # 1. No Net Assertion Deletion
        if patched_count < orig_count:
            violations.append(PatchViolation(
                rule_id="EROSION_ASSERTION_DELETED",
                severity="ERROR",
                message=f"Zero Assertion Erosion: assertion count dropped from {orig_count} to {patched_count}. "
                        f"Hermes never weakens tests to silence CI.",
                line_excerpt=f"original={orig_count} proposed={patched_count}",
            ))

        # 2. Check for tautological assertions in patched lines
        for line in patched_lines:
            stripped = line.strip()
            for pat in cls.TAUTOLOGY_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="EROSION_TAUTOLOGICAL_ASSERTION",
                        severity="ERROR",
                        message="Zero Assertion Erosion: tautological assertion detected (assert True / 1==1). "
                                "This neuters the test.",
                        line_excerpt=stripped[:120],
                    ))

        # 3. Check for skip/bypass directives added in patched lines
        orig_text = "\n".join(original_lines)
        for line in patched_lines:
            stripped = line.strip()
            for pat in cls.SKIP_PATTERNS:
                if pat.search(stripped) and not pat.search(orig_text):
                    violations.append(PatchViolation(
                        rule_id="EROSION_SKIP_INJECTED",
                        severity="ERROR",
                        message=f"Zero Assertion Erosion: prohibited skip/bypass directive injected: {stripped[:80]}",
                        line_excerpt=stripped[:120],
                    ))

        # 4. Check for exception swallowing in added lines
        for line in patched_lines:
            stripped = line.strip()
            for pat in cls.EXCEPTION_SWALLOW_PATTERNS:
                if pat.search(stripped) and not any(pat.search(ol.strip()) for ol in original_lines):
                    violations.append(PatchViolation(
                        rule_id="EROSION_EXCEPTION_SWALLOWED",
                        severity="ERROR",
                        message=f"Zero Assertion Erosion: blanket exception swallowing detected: {stripped[:80]}",
                        line_excerpt=stripped[:120],
                    ))

        return violations

    @classmethod
    def check_product_bug_masking(
        cls,
        original_lines: List[str],
        patched_lines: List[str],
        failure_category: str,
    ) -> List[PatchViolation]:
        """Block test patches that widen HTTP status expectations to tolerate server errors."""
        violations: List[PatchViolation] = []
        if failure_category.upper() not in ("PRODUCT_BUG", "INFRA_FLAKE"):
            return violations

        # Detect status-code widening patterns in patched lines
        STATUS_WIDENING = [
            re.compile(r"in\s*\(\s*200\s*,\s*500\s*\)"),
            re.compile(r"in\s*\[\s*200\s*,\s*500\s*\]"),
            re.compile(r">=\s*200\b"),
            re.compile(r"status_code\s*!=\s*0\b"),
            re.compile(r"\.ok\s*\|\|\s*.*status.*>=?\s*500"),
        ]

        for line in patched_lines:
            stripped = line.strip()
            for pat in STATUS_WIDENING:
                if pat.search(stripped) and not any(pat.search(ol.strip()) for ol in original_lines):
                    violations.append(PatchViolation(
                        rule_id="EROSION_PRODUCT_BUG_MASKED",
                        severity="ERROR",
                        message=f"PRODUCT_BUG Masking: test patch widens HTTP status tolerance to accept server "
                                f"errors. Backend crashes must not be masked by test modifications.",
                        line_excerpt=stripped[:120],
                    ))

        return violations


# ──────────────────────────────────────────────────────────────
#  B. Delta-SAST Security Sanitizer
# ──────────────────────────────────────────────────────────────

class DeltaSASTScanner:
    """Diff-scoped static analysis security scanner for added/modified lines."""

    # ── Rule 1: Code & Command Injection ──
    EXEC_INJECTION_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\beval\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"\bos\s*\.\s*system\s*\("),
        re.compile(r"\bos\s*\.\s*popen\s*\("),
        re.compile(r"subprocess\s*\.\s*\w+\s*\(.*shell\s*=\s*True"),
        re.compile(r"\bchild_process\s*\.\s*exec\s*\("),
        re.compile(r"\bFunction\s*\("),
        re.compile(r"\bpickle\s*\.\s*loads?\s*\("),
        re.compile(r"\bmarshal\s*\.\s*loads?\s*\("),
        re.compile(r"\byaml\s*\.\s*load\s*\([^)]*\)\s*(?!.*Loader\s*=\s*yaml\.SafeLoader)"),
    ]

    # ── Rule 2: TLS / Auth / Verification Downgrade ──
    TLS_BYPASS_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\bverify\s*=\s*False\b"),
        re.compile(r"\bssl\._create_unverified_context\b"),
        re.compile(r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]0['\"]"),
        re.compile(r"ignoreHTTPSErrors\s*:\s*true\b"),
    ]

    # ── Rule 3: SQL Injection & Path Traversal ──
    INJECTION_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r'f["\']SELECT\s', re.IGNORECASE),
        re.compile(r'f["\']INSERT\s', re.IGNORECASE),
        re.compile(r'f["\']UPDATE\s', re.IGNORECASE),
        re.compile(r'f["\']DELETE\s', re.IGNORECASE),
        re.compile(r'["\']SELECT\s.*["\']\s*\+', re.IGNORECASE),
        re.compile(r'\.\./\.\./'),
    ]

    # ── Rule 4: Secret / Token / Nonce Leakage ──
    SECRET_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----"),
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"),
        re.compile(r"\bHERMES_SANDBOX_NONCE=[A-Fa-f0-9]{16,}\b"),
    ]

    # ── Rule 5: CI / Workflow Tampering ──
    WORKFLOW_TAMPERING_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"curl\s+.*\|\s*(sh|bash)\b"),
        re.compile(r"wget\s+.*\|\s*(sh|bash)\b"),
        re.compile(r"\bchmod\s+777\b"),
    ]

    WORKFLOW_FILE_PATTERNS: List[re.Pattern[str]] = [
        re.compile(r"\.github/workflows/"),
        re.compile(r"\baction\.yml\b"),
    ]

    @classmethod
    def scan_added_lines(
        cls,
        added_lines: List[str],
        target_file: str = "",
    ) -> List[PatchViolation]:
        """Scan added/modified lines for security violations."""
        violations: List[PatchViolation] = []

        for line in added_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Rule 1: Code & Command Injection
            for pat in cls.EXEC_INJECTION_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="SAST_EXEC_INJECTION",
                        severity="ERROR",
                        message=f"Delta-SAST: code/command injection vector detected in proposed patch.",
                        line_excerpt=stripped[:120],
                    ))

            # Rule 2: TLS / Auth Bypass
            for pat in cls.TLS_BYPASS_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="SAST_TLS_BYPASS",
                        severity="ERROR",
                        message=f"Delta-SAST: TLS/auth verification downgrade detected in proposed patch.",
                        line_excerpt=stripped[:120],
                    ))

            # Rule 3: SQL Injection & Path Traversal
            for pat in cls.INJECTION_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="SAST_QUERY_OR_PATH_INJECTION",
                        severity="ERROR",
                        message=f"Delta-SAST: potential SQL injection or path traversal detected.",
                        line_excerpt=stripped[:120],
                    ))

            # Rule 4: Secret / Token Leakage
            for pat in cls.SECRET_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="SAST_SECRET_LEAK",
                        severity="ERROR",
                        message=f"Delta-SAST: hardcoded secret, token, or private key detected in patch.",
                        line_excerpt=re.sub(r"[A-Za-z0-9_\-]{8,}", "[REDACTED]", stripped[:120]),
                    ))

            # Rule 5: CI / Workflow Tampering
            for pat in cls.WORKFLOW_TAMPERING_PATTERNS:
                if pat.search(stripped):
                    violations.append(PatchViolation(
                        rule_id="SAST_WORKFLOW_TAMPERING",
                        severity="ERROR",
                        message=f"Delta-SAST: CI/workflow tampering pattern detected (pipe-to-shell or chmod 777).",
                        line_excerpt=stripped[:120],
                    ))

        # Rule 5 addendum: reject patches targeting workflow files
        norm_target = target_file.replace("\\", "/").lower()
        for pat in cls.WORKFLOW_FILE_PATTERNS:
            if pat.search(norm_target):
                violations.append(PatchViolation(
                    rule_id="SAST_WORKFLOW_TAMPERING",
                    severity="ERROR",
                    message=f"Delta-SAST: proposed patch targets protected CI/workflow file: {target_file}",
                    line_excerpt=target_file,
                ))

        return violations


# ──────────────────────────────────────────────────────────────
#  C. Unified PatchGuard Gate
# ──────────────────────────────────────────────────────────────

class PatchGuard:
    """Unified pre-publication verification gate combining Assertion Erosion + Delta-SAST."""

    @classmethod
    def _extract_lines_from_suggestion(cls, suggestion_block: str) -> List[str]:
        """Extract code lines from a ```suggestion block or raw code string."""
        lines = suggestion_block.splitlines()
        in_block = False
        extracted: List[str] = []
        for line in lines:
            if line.strip().startswith("```suggestion"):
                in_block = True
                continue
            if in_block and line.strip() == "```":
                in_block = False
                continue
            if in_block:
                extracted.append(line)
        # If no fenced block found, treat entire input as code
        return extracted if extracted else lines

    @classmethod
    def _build_sanitized_message(
        cls,
        original_suggestion: str,
        violations: List[PatchViolation],
    ) -> str:
        """Strip unsafe code but preserve diagnostic prose; append transparent audit notice."""
        violation_lines = []
        for v in violations:
            violation_lines.append(f"- **`{v.rule_id}`** ({v.severity}): {v.message}")

        return (
            f"⛔ **Hermes PatchGuard: Auto-Patch Withheld**\n\n"
            f"The proposed code fix was blocked by Hermes' pre-publication security gate. "
            f"The root-cause diagnosis is preserved below for developer review, but the "
            f"executable `suggestion` block has been stripped to prevent unsafe code from "
            f"being committed.\n\n"
            f"**Violations:**\n"
            + "\n".join(violation_lines)
            + "\n\n"
            f"*A human engineer must review and manually apply a safe fix for this failure.*\n\n"
            f"<!-- hermes-patchguard: blocked -->"
        )

    @classmethod
    def verify(
        cls,
        original_code: str,
        proposed_code: str,
        target_file: str = "",
        failure_category: str = "",
    ) -> PatchGuardVerdict:
        """Run full Delta-SAST + Assertion Erosion verification on a proposed patch.

        Args:
            original_code: The original source code being replaced.
            proposed_code: The proposed replacement (suggestion block or raw code).
            target_file: Relative file path being patched.
            failure_category: Root-cause classification (PRODUCT_BUG, TEST_BUG, etc.).

        Returns:
            PatchGuardVerdict with pass/block decision and structured violations.
        """
        all_violations: List[PatchViolation] = []

        original_lines = original_code.splitlines() if original_code else []
        proposed_lines = cls._extract_lines_from_suggestion(proposed_code)

        # ── Layer A: Assertion Erosion ──
        erosion_violations = AssertionErosionChecker.check_assertion_erosion(
            original_lines=original_lines,
            patched_lines=proposed_lines,
        )
        all_violations.extend(erosion_violations)

        # ── Layer A2: PRODUCT_BUG masking ──
        masking_violations = AssertionErosionChecker.check_product_bug_masking(
            original_lines=original_lines,
            patched_lines=proposed_lines,
            failure_category=failure_category,
        )
        all_violations.extend(masking_violations)

        # ── Layer B: Delta-SAST Security ──
        sast_violations = DeltaSASTScanner.scan_added_lines(
            added_lines=proposed_lines,
            target_file=target_file,
        )
        all_violations.extend(sast_violations)

        # ── Verdict ──
        if not all_violations:
            return PatchGuardVerdict(
                passed=True,
                status="APPROVED",
                violations=[],
                sanitized_suggestion=None,
            )

        # Determine most specific block reason
        rule_ids = {v.rule_id for v in all_violations}
        if any(r.startswith("EROSION_PRODUCT_BUG") for r in rule_ids):
            status = "BLOCKED_PRODUCT_BUG_MASKING"
        elif any(r.startswith("SAST_") for r in rule_ids):
            status = "BLOCKED_DELTA_SAST"
        else:
            status = "BLOCKED_ASSERTION_EROSION"

        sanitized = cls._build_sanitized_message(proposed_code, all_violations)

        return PatchGuardVerdict(
            passed=False,
            status=status,
            violations=all_violations,
            sanitized_suggestion=sanitized,
        )
