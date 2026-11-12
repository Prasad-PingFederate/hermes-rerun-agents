"""
Core Verification & Anti-Erosion Module (Option 4: Zero False-Green Verification)
Provides:
- SemanticAssertionGuard (AST v2): Detects value dilution, exception broadening, and timeout masking.
- AccessibilityLocatorGuard: Enforces semantic Playwright / Testing Library locators over brittle CSS/XPath.
- CounterfactualVerifier: Differential sandbox execution proving tests fail against broken base code.
"""

from __future__ import annotations

from core.verification.accessibility_locator_guard import (
    AccessibilityLocatorGuard,
    LocatorAuditResult,
)
from core.verification.counterfactual_verifier import (
    CounterfactualResult,
    CounterfactualVerifier,
)
from core.verification.semantic_assertion_guard import (
    DowngradeFinding,
    SemanticAssertionGuard,
    SemanticGuardResult,
)

__all__ = [
    "SemanticAssertionGuard",
    "SemanticGuardResult",
    "DowngradeFinding",
    "AccessibilityLocatorGuard",
    "LocatorAuditResult",
    "CounterfactualVerifier",
    "CounterfactualResult",
]

