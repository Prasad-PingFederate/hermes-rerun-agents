"""
Generate backwards-compatibility shims for root .py files.
"""
from __future__ import annotations

from pathlib import Path

mapping = {
    'ast_patch_guard.py': 'hermes.guards.ast_patch_guard',
    'ci_failure_ingestor.py': 'hermes.ingestion.ci_failure_ingestor',
    'console_demo_manager.py': 'hermes.console.console_demo_manager',
    'console_ui.py': 'hermes.console.console_ui',
    'context_slicer.py': 'hermes.ingestion.context_slicer',
    'hermes_cli.py': 'hermes.cli',
    'hermes_workers.py': 'hermes.orchestration.hermes_workers',
    'llm_provider_adapter.py': 'hermes.execution.llm_provider_adapter',
    'qa_critic_reviewer.py': 'hermes.orchestration.qa_critic_reviewer',
    'sandbox_executor.py': 'hermes.execution.sandbox_executor',
    'scrum_master_orchestrator.py': 'hermes.orchestration.scrum_master_orchestrator',
    'security_blast_radius.py': 'hermes.guards.security_blast_radius',
    'server.py': 'hermes.console.server',
    'sprint_dag_scheduler.py': 'hermes.orchestration.sprint_dag_scheduler',
    'sprint_state_store.py': 'hermes.orchestration.sprint_state_store',
    'ticket_router.py': 'hermes.ingestion.ticket_router',
    'ts_playwright_ast_guard.py': 'hermes.guards.ts_playwright_ast_guard',
    'workspace_patch_applier.py': 'hermes.execution.workspace_patch_applier',
    'write_gate_controller.py': 'hermes.guards.write_gate_controller',
}

repo_root = Path(__file__).resolve().parent.parent

for root_f, target_mod in mapping.items():
    extra = ""
    if root_f == "hermes_cli.py":
        extra = """
if __name__ == "__main__":
    import sys
    sys.exit(main())
"""
    elif root_f == "server.py":
        extra = """
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("RERUN_SERVER_PORT", 8000))
    host = os.environ.get("RERUN_SERVER_HOST", "127.0.0.1")
    print(f"🚀 Starting Hermes + Rerun Webhook Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
"""
    content = f'''"""
Backwards-compatibility shim for {target_mod}
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import {target_mod} as _target_module
sys.modules[__name__] = _target_module
from {target_mod} import *
{extra}'''
    target_path = repo_root / root_f
    target_path.write_text(content.strip() + "\n", encoding="utf-8")

print(f"Successfully generated {len(mapping)} backwards-compatibility shims.")
