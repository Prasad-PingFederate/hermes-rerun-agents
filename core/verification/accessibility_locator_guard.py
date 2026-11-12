"""
Accessibility-First Locator Upgrading & Integrity Guard (Playwright / Testing Library)
Owner: TestCaseWriterAgent & TestHealerAgent
Phase: Option 4 (Zero False-Green Verification)

Rejects brittle CSS/XPath locator substitutions and enforces resilient, accessible locators:
- Rejects:
  * Structural pseudo-classes: :nth-child(n), :nth-of-type(n), :first-child, :last-child
  * Deep DOM tag chains: div.card > form > div:nth-child(2) > button
  * Brittle XPath: /html/body/..., //div[2]/button
  * Auto-generated CSS hashes: .css-1a2b3c, .jsx-12345, [class*="_Styled"]
- Enforces & Recommends Accessible Alternatives:
  * page.getByRole('button', { name: 'Submit' }) / page.get_by_role("button", name="Submit")
  * page.getByLabel('Username') / page.get_by_label("Username")
  * page.getByPlaceholder('Email') / page.get_by_placeholder("Email")
  * page.getByText('Save') / page.get_by_text("Save")
  * page.getByTestId('checkout-btn') / page.get_by_test_id("checkout-btn")

Zero external dependencies (uses standard library: re, pathlib, typing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BrittleLocatorFinding:
    """Details of a brittle selector detected in a test proposal."""
    file_path: str
    pattern_type: str  # "NTH_CHILD_OR_POSITIONAL", "DEEP_TAG_HIERARCHY", "BRITTLE_XPATH", "HASHED_CLASS_NAME"
    selector: str
    line_number: Optional[int] = None
    suggested_upgrade: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "pattern_type": self.pattern_type,
            "selector": self.selector,
            "line_number": self.line_number,
            "suggested_upgrade": self.suggested_upgrade,
            "message": self.message,
        }


@dataclass
class LocatorAuditResult:
    """Outcome of accessibility locator auditing."""
    valid: bool
    brittle_detected: bool
    findings: List[BrittleLocatorFinding] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    suggested_replacements: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "brittle_detected": self.brittle_detected,
            "findings": [f.to_dict() for f in self.findings],
            "reasons": self.reasons,
            "suggested_replacements": self.suggested_replacements,
        }


class AccessibilityLocatorGuard:
    """Deterministic scanner auditing UI test locators for accessibility-first resilience."""

    # Patterns matching locator calls in JS/TS and Python Playwright
    # Examples: page.locator('...'), page.click('...'), page.fill('...'), $( '...' )
    LOCATOR_CALL_REGEX = re.compile(
        r"""(?:page|frame)\s*\.\s*(?:locator|click|fill|hover|press|check|uncheck|dblclick|tap|wait_for_selector|waitForSelector)\s*\(\s*(['"`])(?P<sel>[^'"`\r\n]+)\1""",
        re.IGNORECASE,
    )

    # Brittle selector patterns
    BRITTLE_PATTERNS = [
        (
            "NTH_CHILD_OR_POSITIONAL",
            re.compile(r":(?:nth-child|nth-of-type|first-child|last-child)\s*\(\s*\d+\s*\)|:(?:first-child|last-child)", re.IGNORECASE),
            "Positional selector ':nth-child/:first-child' breaks when adjacent DOM nodes change.",
        ),
        (
            "DEEP_TAG_HIERARCHY",
            re.compile(r"(?:[a-z0-9_-]+\s*>\s*){2,}[a-z0-9_-]+", re.IGNORECASE),
            "Deep tag hierarchy (> 2 nested combinators) tightly couples test to layout markup.",
        ),
        (
            "BRITTLE_XPATH",
            re.compile(r"^(?:xpath=)?\s*(?:\/html\/|\/\/[a-z0-9_-]+\[\d+\])", re.IGNORECASE),
            "Absolute or positional XPath is extremely fragile to template structure changes.",
        ),
        (
            "HASHED_CLASS_NAME",
            re.compile(r"\.(?:css|jsx|style)-[0-9a-zA-Z]{5,}|\[class\*=['\"][a-zA-Z0-9_-]*__[a-zA-Z0-9_-]{5,}['\"]", re.IGNORECASE),
            "Generated CSS-in-JS or build-hash class name changes across production builds.",
        ),
    ]

    # Semantic, accessible locator indicators
    SEMANTIC_LOCATOR_INDICATORS = [
        "getByRole", "get_by_role",
        "getByLabel", "get_by_label",
        "getByPlaceholder", "get_by_placeholder",
        "getByText", "get_by_text",
        "getByTestId", "get_by_test_id",
        "getByTitle", "get_by_title",
        "getByAltText", "get_by_alt_text",
        "[data-testid=", "[data-test=",
    ]

    @classmethod
    def is_ui_test(cls, file_path: str) -> bool:
        """Determine if file represents an E2E or Playwright UI test file."""
        lower = file_path.lower().replace("\\", "/")
        return (
            "playwright" in lower
            or "e2e" in lower
            or "spec" in lower
            or lower.endswith((".spec.ts", ".spec.js", ".spec.tsx", ".spec.jsx"))
            or ("test_" in lower and ("ui" in lower or "web" in lower or "page" in lower or "browser" in lower))
        )

    @classmethod
    def audit_changes(
        cls,
        proposed_changes: Dict[str, str],
        existing_files: Optional[Dict[str, str]] = None,
        workspace_root: Optional[Path | str] = None,
    ) -> LocatorAuditResult:
        """Audit all proposed test changes for newly introduced brittle locators."""
        findings: List[BrittleLocatorFinding] = []
        suggested_replacements: Dict[str, str] = {}
        root = Path(workspace_root).resolve() if workspace_root else None

        for rel_path, proposed_content in proposed_changes.items():
            norm_path = rel_path.replace("\\", "/").lstrip("/")
            if not cls.is_ui_test(norm_path):
                continue

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

            file_findings = cls.audit_file_content(norm_path, proposed_content, existing_content)
            findings.extend(file_findings)

            for f in file_findings:
                if f.suggested_upgrade:
                    suggested_replacements[f.selector] = f.suggested_upgrade

        brittle_detected = len(findings) > 0
        reasons = [
            f"{f.file_path} [{f.pattern_type}]: Brittle locator '{f.selector}' rejected. {f.message} Suggestion: {f.suggested_upgrade}"
            for f in findings
        ]

        return LocatorAuditResult(
            valid=not brittle_detected,
            brittle_detected=brittle_detected,
            findings=findings,
            reasons=reasons,
            suggested_replacements=suggested_replacements,
        )

    @classmethod
    def audit_file_content(
        cls,
        file_path: str,
        proposed_content: str,
        existing_content: str = "",
    ) -> List[BrittleLocatorFinding]:
        """Audit single file content for brittle locators introduced in proposed patch."""
        findings: List[BrittleLocatorFinding] = []

        existing_selectors = set()
        if existing_content:
            for match in cls.LOCATOR_CALL_REGEX.finditer(existing_content):
                existing_selectors.add(match.group("sel").strip())

        lines = proposed_content.splitlines()
        for line_no, line in enumerate(lines, 1):
            for match in cls.LOCATOR_CALL_REGEX.finditer(line):
                selector = match.group("sel").strip()

                # If this selector was already in the file before, don't penalize legacy unchanged code
                if selector in existing_selectors:
                    continue

                # Test selector against brittle patterns
                for p_type, regex, desc in cls.BRITTLE_PATTERNS:
                    if regex.search(selector):
                        upgrade = cls.generate_upgrade_suggestion(selector, p_type, is_python=file_path.endswith(".py"))
                        findings.append(
                            BrittleLocatorFinding(
                                file_path=file_path,
                                pattern_type=p_type,
                                selector=selector,
                                line_number=line_no,
                                suggested_upgrade=upgrade,
                                message=desc,
                            )
                        )
                        break

        return findings

    @classmethod
    def generate_upgrade_suggestion(
        cls,
        selector: str,
        pattern_type: str,
        is_python: bool = False,
    ) -> str:
        """Synthesize an accessible semantic locator replacement based on selector hints."""
        clean = selector.strip()
        lower = clean.lower()

        # If button
        if "button" in lower or "btn" in lower:
            # Check if has text hint
            text_match = re.search(r"text\s*=\s*['\"]([^'\"]+)['\"]", clean, re.IGNORECASE)
            name_val = text_match.group(1) if text_match else "Submit"
            if is_python:
                return f'page.get_by_role("button", name="{name_val}")'
            return f"page.getByRole('button', {{ name: '{name_val}' }})"

        # If input
        if "input" in lower or "search" in lower or "email" in lower or "password" in lower:
            if "search" in lower:
                return 'page.get_by_role("searchbox")' if is_python else "page.getByRole('searchbox')"
            if "password" in lower:
                return 'page.get_by_label("Password")' if is_python else "page.getByLabel('Password')"
            if "email" in lower:
                return 'page.get_by_label("Email")' if is_python else "page.getByLabel('Email')"
            return 'page.get_by_role("textbox")' if is_python else "page.getByRole('textbox')"

        # If link / navigation
        if "a" in lower.split() or "nav" in lower or "link" in lower:
            return 'page.get_by_role("link")' if is_python else "page.getByRole('link')"

        # General test id fallback
        clean_tag = re.sub(r"[^a-zA-Z0-9_-]", "-", clean).strip("-")[:20]
        test_id = clean_tag or "target-element"
        if is_python:
            return f'page.get_by_test_id("{test_id}")'
        return f"page.getByTestId('{test_id}')"

