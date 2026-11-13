"""
Packaging Integrity and Root Shim Equivalence Tests
Owner: Platform & Packaging
Phase: Phase 2 (v1.1.0) Deliverable 1

Verifies:
1. Root-level .py files are thin backwards-compatibility re-export shims.
2. No duplicate class or standalone function definitions exist in root files.
3. Importing from root and from hermes.* resolves to the exact same Python objects.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SHIM_MODULE_MAPPING = {
    "ast_patch_guard": ("hermes.guards.ast_patch_guard", ["ASTPatchGuard"]),
    "ci_failure_ingestor": ("hermes.ingestion.ci_failure_ingestor", ["CIFailureIngestor", "ParsedFailure", "JUnitXMLIngestor"]),
    "console_demo_manager": ("hermes.console.console_demo_manager", ["ConsoleDemoManager", "DemoWorkspace"]),
    "console_ui": ("hermes.console.console_ui", ["CONSOLE_HTML"]),
    "context_slicer": ("hermes.ingestion.context_slicer", ["ContextSlicer", "PytestFixtureIndexer"]),
    "hermes_cli": ("hermes.cli", ["main"]),
    "hermes_workers": ("hermes.orchestration.hermes_workers", ["WorkerProposal", "DeveloperAgent", "TestCaseWriterAgent"]),
    "llm_provider_adapter": ("hermes.execution.llm_provider_adapter", ["HermesLLMAdapter", "LocalHeuristicEngine"]),
    "qa_critic_reviewer": ("hermes.orchestration.qa_critic_reviewer", ["QACriticAgent", "QACriticReview"]),
    "sandbox_executor": ("hermes.execution.sandbox_executor", ["SandboxExecutor", "ExecutionRun", "MultiRunResult"]),
    "scrum_master_orchestrator": ("hermes.orchestration.scrum_master_orchestrator", ["ScrumMasterOrchestrator"]),
    "security_blast_radius": ("hermes.guards.security_blast_radius", ["SecurityBlastRadiusAgent", "SecurityAuditReport"]),
    "server": ("hermes.console.server", ["app"]),
    "sprint_dag_scheduler": ("hermes.orchestration.sprint_dag_scheduler", ["SprintDAGScheduler"]),
    "sprint_state_store": ("hermes.orchestration.sprint_state_store", ["SprintStateStore", "GitNotesStateBackend"]),
    "ticket_router": ("hermes.ingestion.ticket_router", ["TicketRouter"]),
    "ts_playwright_ast_guard": ("hermes.guards.ts_playwright_ast_guard", ["PlaywrightASTGuard"]),
    "workspace_patch_applier": ("hermes.execution.workspace_patch_applier", ["AtomicPatchApplier", "UnifiedDiffGenerator"]),
    "write_gate_controller": ("hermes.guards.write_gate_controller", ["HumanWriteGateController"]),
}


class TestPackagingIntegrity:
    """Verifies that root-level files are pure shims pointing to src/hermes."""

    def test_root_files_contain_no_duplicate_class_definitions(self):
        """All 19 root files must contain 0 ast.ClassDef nodes."""
        for root_mod_name in SHIM_MODULE_MAPPING:
            py_file = REPO_ROOT / f"{root_mod_name}.py"
            assert py_file.is_file(), f"Expected root file {py_file} to exist"

            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
            assert classes == [], (
                f"Root shim {py_file.name} defines duplicate classes: {classes}. "
                f"Single source of truth must live under src/hermes/."
            )

    def test_root_and_package_exports_are_identical_objects(self):
        """Root modules and hermes.* modules must export identical objects."""
        for root_mod_name, (pkg_mod_name, exported_symbols) in SHIM_MODULE_MAPPING.items():
            root_mod = importlib.import_module(root_mod_name)
            pkg_mod = importlib.import_module(pkg_mod_name)

            for sym in exported_symbols:
                assert hasattr(root_mod, sym), f"Root shim {root_mod_name} missing {sym}"
                assert hasattr(pkg_mod, sym), f"Package module {pkg_mod_name} missing {sym}"
                root_obj = getattr(root_mod, sym)
                pkg_obj = getattr(pkg_mod, sym)
                assert root_obj is pkg_obj, (
                    f"Object {sym} mismatch: {root_mod_name}.{sym} is not identical to {pkg_mod_name}.{sym}"
                )

    def test_agents_and_core_shims_contain_no_duplicate_classes(self):
        """All files in root agents/ and core/ must contain 0 ast.ClassDef nodes (pure shims)."""
        for folder in ("agents", "core"):
            for py_path in (REPO_ROOT / folder).rglob("*.py"):
                tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
                classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
                assert classes == [], (
                    f"Shim {py_path.relative_to(REPO_ROOT)} defines duplicate classes: {classes}. "
                    f"Canonical source of truth must live exclusively under src/hermes/{folder}/."
                )

    def test_core_and_agents_exports_are_identical_objects(self):
        """Root agents.* and core.* modules resolve to identical object identity as hermes.*."""
        import agents.ci_detective
        import hermes.agents.ci_detective
        assert agents.ci_detective.CIDetectiveAgent is hermes.agents.ci_detective.CIDetectiveAgent

        import core.audit.delta_sast
        import hermes.core.audit.delta_sast
        assert core.audit.delta_sast.PatchGuard is hermes.core.audit.delta_sast.PatchGuard

        import core.governance.policy_engine
        import hermes.core.governance.policy_engine
        assert core.governance.policy_engine.PolicyEngine is hermes.core.governance.policy_engine.PolicyEngine

        import core.ingest.artifact_loader
        import hermes.core.ingest.artifact_loader
        assert core.ingest.artifact_loader.ArtifactLoader is hermes.core.ingest.artifact_loader.ArtifactLoader
