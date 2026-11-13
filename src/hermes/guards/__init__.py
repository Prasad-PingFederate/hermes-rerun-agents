"""
Hermes Governance & Patch Guards Subsystem
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ASTPatchGuard",
    "LanguageASTGuard",
    "ASTAnalysisResult",
    "PlaywrightASTGuard",
    "TypeScriptGuardResult",
    "SecurityBlastRadiusAgent",
    "SecurityAuditReport",
    "SecurityFinding",
    "ASTSecurityScanner",
    "JSSecurityScanner",
    "HumanWriteGateController",
]


def __getattr__(name: str) -> Any:
    if name == "ASTPatchGuard":
        from hermes.guards.ast_patch_guard import ASTPatchGuard
        return ASTPatchGuard
    if name in ("LanguageASTGuard", "ASTAnalysisResult"):
        from hermes.guards.language_ast_guard import ASTAnalysisResult, LanguageASTGuard
        return ASTAnalysisResult if name == "ASTAnalysisResult" else LanguageASTGuard
    if name in ("PlaywrightASTGuard", "TypeScriptGuardResult"):
        from hermes.guards.ts_playwright_ast_guard import PlaywrightASTGuard, TypeScriptGuardResult
        return TypeScriptGuardResult if name == "TypeScriptGuardResult" else PlaywrightASTGuard
    if name in ("SecurityBlastRadiusAgent", "SecurityAuditReport", "SecurityFinding", "ASTSecurityScanner", "JSSecurityScanner"):
        import hermes.guards.security_blast_radius as sbr
        return getattr(sbr, name)
    if name == "HumanWriteGateController":
        from hermes.guards.write_gate_controller import HumanWriteGateController
        return HumanWriteGateController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
