"""
Unified AST Patch Guard & Dispatcher
Owner: TestCaseWriterAgent & ScrumMasterOrchestrator

Dispatches proposed changes to:
- Python AST guard (core/time_machine/patch_guard.py) for .py files.
- TypeScript Playwright guard (ts_playwright_ast_guard.py) for .spec.ts, .test.ts, .spec.js, .test.js.
- Security Blast-Radius auditor (security_blast_radius.py) for high-risk calls and credentials.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.security.dlp_scrubber import DLPSessionVault
from core.security.prompt_sandbox import PromptSandbox
from core.time_machine.patch_guard import analyze_proposed_changes as analyze_python_ast
from core.verification.accessibility_locator_guard import AccessibilityLocatorGuard
from core.verification.semantic_assertion_guard import SemanticAssertionGuard
from hermes.guards.language_ast_guard import LanguageASTGuard
from hermes.guards.security_blast_radius import SecurityBlastRadiusAgent
from hermes.guards.ts_playwright_ast_guard import PlaywrightASTGuard, analyze_ts_playwright_changes


class ASTPatchGuard:
    """Unified dispatcher for AST inspection and security guardrails."""

    @classmethod
    def analyze(
        cls,
        workspace_root: Path,
        proposed_changes: Dict[str, str],
        allow_test_modification: bool = False,
        ticket: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Dispatch changes to language-specific AST guards and security auditor."""
        workspace = Path(workspace_root).resolve()
        py_changes: Dict[str, str] = {}
        ts_changes: Dict[str, str] = {}
        other_changes: Dict[str, str] = {}

        for rel_path, content in proposed_changes.items():
            if rel_path.endswith(".py"):
                py_changes[rel_path] = content
            elif PlaywrightASTGuard.is_supported(rel_path):
                ts_changes[rel_path] = content
            else:
                other_changes[rel_path] = content

        all_reasons: List[str] = []
        tampering_detected = False
        valid = True
        blast_radius: Dict[str, Any] = {}

        # 1. Python AST guard
        if py_changes:
            try:
                py_report = analyze_python_ast(
                    workspace_root=workspace,
                    proposed_changes=py_changes,
                    allow_test_modification=allow_test_modification,
                )
                if not py_report.get("valid", True):
                    valid = False
                    tampering_detected = True
                    all_reasons.extend(py_report.get("tampering_reasons", []))
                blast_radius.update(py_report.get("blast_radius", {}))
            except ValueError as e:
                valid = False
                all_reasons.append(str(e))

        # 2. TypeScript/Playwright AST guard
        if ts_changes:
            ts_report = analyze_ts_playwright_changes(
                workspace_root=workspace,
                proposed_changes=ts_changes,
                allow_test_modification=allow_test_modification,
            )
            if not ts_report.get("valid", True):
                valid = False
                tampering_detected = True
                all_reasons.extend(ts_report.get("reasons", []))

        # 2b. Multi-Language Assertion Erosion & Skip Injection Guard (Python, TS, Java, Go, C#)
        for rel_path, content in proposed_changes.items():
            lang = LanguageASTGuard.detect_language(rel_path)
            if lang != "unknown":
                orig_file = workspace / rel_path
                orig_content = orig_file.read_text(encoding="utf-8", errors="replace") if orig_file.exists() else ""
                erosion_res = LanguageASTGuard.check_assertion_erosion(orig_content, content, language=lang)
                if not erosion_res.get("passed", True):
                    valid = False
                    tampering_detected = True
                    all_reasons.extend(erosion_res.get("violations", []))

        # 3. Security Blast-Radius audit
        high_risk_flag = getattr(ticket, "high_risk", False) if ticket else False
        sec_report = SecurityBlastRadiusAgent.audit_proposal(proposed_changes, ticket=ticket)
        if not sec_report.passed or high_risk_flag:
            if not sec_report.passed:
                valid = False
                all_reasons.extend(sec_report.reasons)

        # 4. Semantic Assertion Weakening Guard (AST v2 - Option 4)
        semantic_report = SemanticAssertionGuard.evaluate_changes(
            proposed_changes=proposed_changes,
            workspace_root=workspace,
        )
        if not semantic_report.valid:
            valid = False
            tampering_detected = True
            all_reasons.extend(semantic_report.reasons)

        # 5. Accessibility-First Locator Guard (Playwright / Testing Library - Option 4)
        locator_report = AccessibilityLocatorGuard.audit_changes(
            proposed_changes=proposed_changes,
            workspace_root=workspace,
        )
        if not locator_report.valid:
            valid = False
            tampering_detected = True
            all_reasons.extend(locator_report.reasons)

        # 6. Exfiltration Diff Check (Option 5: Prompt-Injection Isolation)
        exfil_report = PromptSandbox.audit_patch_for_exfiltration(
            proposed_changes=proposed_changes,
        )
        if not exfil_report.valid:
            valid = False
            tampering_detected = True
            all_reasons.extend(exfil_report.reasons)

        # 7. Hallucinated Placeholder Check (Option 5: DLP Scrubber)
        for rel_f, content in proposed_changes.items():
            if DLPSessionVault.PLACEHOLDER_REGEX.search(content):
                valid = False
                tampering_detected = True
                all_reasons.append(
                    f"{rel_f}: Unhydrated or hallucinated Hermes DLP placeholder detected in patch. "
                    "Cannot commit raw placeholder token."
                )

        # 8. Delta-SAST Diff Security Scanner (Zero Assertion Erosion & SAST Guard)
        from core.audit.delta_sast import PatchGuard
        for rel_f, content in proposed_changes.items():
            orig_file = workspace / rel_f
            orig_content = orig_file.read_text(encoding="utf-8", errors="replace") if orig_file.exists() else ""
            fail_cat = getattr(ticket, "failure_category", "") if ticket else ""
            if not fail_cat and ticket and getattr(ticket, "status", None):
                fail_cat = getattr(ticket, "status", "")
            patch_verdict = PatchGuard.verify(
                original_code=orig_content,
                proposed_code=content,
                target_file=rel_f,
                failure_category=fail_cat,
            )
            if not patch_verdict.passed:
                valid = False
                tampering_detected = True
                for v in patch_verdict.violations:
                    all_reasons.append(f"{rel_f}: [Delta-SAST {v.rule_id}] {v.message}")

        return {
            "valid": valid and len(all_reasons) == 0,
            "tampering_detected": tampering_detected,
            "reasons": all_reasons,
            "blast_radius": blast_radius,
            "security": {
                "risk_score": sec_report.risk_score,
                "risk_level": sec_report.risk_level,
                "findings": [f.to_dict() for f in sec_report.findings],
            },
            "semantic_findings": [f.to_dict() for f in semantic_report.findings],
            "locator_findings": [f.to_dict() for f in locator_report.findings],
            "exfiltration_findings": exfil_report.findings,
        }
