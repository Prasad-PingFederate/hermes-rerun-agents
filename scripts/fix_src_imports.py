"""
Fix internal flat imports inside src/hermes/ to use fully-qualified hermes package paths.
"""
from __future__ import annotations

import re
from pathlib import Path

MODULE_TO_PKG = {
    'ast_patch_guard': 'hermes.guards.ast_patch_guard',
    'ci_failure_ingestor': 'hermes.ingestion.ci_failure_ingestor',
    'console_demo_manager': 'hermes.console.console_demo_manager',
    'console_ui': 'hermes.console.console_ui',
    'context_slicer': 'hermes.ingestion.context_slicer',
    'hermes_cli': 'hermes.cli',
    'hermes_workers': 'hermes.orchestration.hermes_workers',
    'llm_provider_adapter': 'hermes.execution.llm_provider_adapter',
    'qa_critic_reviewer': 'hermes.orchestration.qa_critic_reviewer',
    'sandbox_executor': 'hermes.execution.sandbox_executor',
    'scrum_master_orchestrator': 'hermes.orchestration.scrum_master_orchestrator',
    'security_blast_radius': 'hermes.guards.security_blast_radius',
    'server': 'hermes.console.server',
    'sprint_dag_scheduler': 'hermes.orchestration.sprint_dag_scheduler',
    'sprint_state_store': 'hermes.orchestration.sprint_state_store',
    'ticket_router': 'hermes.ingestion.ticket_router',
    'ts_playwright_ast_guard': 'hermes.guards.ts_playwright_ast_guard',
    'workspace_patch_applier': 'hermes.execution.workspace_patch_applier',
    'write_gate_controller': 'hermes.guards.write_gate_controller',
}

src_dir = Path(__file__).resolve().parent.parent / "src" / "hermes"
core_dir = Path(__file__).resolve().parent.parent / "core"

for d in [src_dir, core_dir]:
    for py_file in d.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        original = content
        for mod, full_pkg in MODULE_TO_PKG.items():
            content = re.sub(rf"(?<!hermes\.)(?<![a-zA-Z0-9_.])from\s+{mod}\s+import", f"from {full_pkg} import", content)
            content = re.sub(rf"(?<!hermes\.)(?<![a-zA-Z0-9_.])import\s+{mod}\b", f"import {full_pkg} as {mod}", content)

        if content != original:
            py_file.write_text(content, encoding="utf-8")
            print(f"Updated imports in {py_file.name}")

print("Import migration in src/hermes/ completed.")
