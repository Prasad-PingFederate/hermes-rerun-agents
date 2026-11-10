"""
Autonomous Test Failure Healer Agent with Time Machine Safety Guardrail
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from core.healer.gemini_flash import GeminiFlashHealer
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine


class TestHealerAgent:
    """Autonomous agent that investigates, heals, and verifies test failures with rollback safety."""

    def __init__(
        self,
        workspace_path: Optional[str | Path] = None,
        gemini_api_key: Optional[str] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = TimeMachineEngine(self.workspace_path)
        self.healer = GeminiFlashHealer(gemini_api_key)
        self.orchestrator = RerunOrchestrator(self.workspace_path / ".rerun_tasks")

    def run_and_heal(self, pytest_target: str, auto_rollback: bool = True) -> Dict[str, Any]:
        """Execute a test target; if it fails, diagnose and safely attempt remediation."""
        print(f"[AGENT] Taking baseline Time Machine snapshot before running: {pytest_target}")
        snapshot = self.tm.create_snapshot(
            label=f"pre_test_{Path(pytest_target).stem}",
            description=f"Baseline state before executing {pytest_target}",
        )

        task = self.orchestrator.create_task(
            title=f"Execute & Verify {pytest_target}",
            details={"target": pytest_target, "baseline_snapshot": snapshot.id},
        )

        # Execute test
        print(f"[AGENT] Running test: {pytest_target} ...")
        cmd = ["python", "-m", "pytest", pytest_target, "-v", "--tb=short"]
        proc = subprocess.run(cmd, cwd=str(self.workspace_path), capture_output=True, text=True)

        if proc.returncode == 0:
            print("[AGENT] ✅ Test passed cleanly on first attempt.")
            self.orchestrator.update_task_status(task.id, "COMPLETED")
            return {"status": "PASSED", "snapshot_id": snapshot.id, "task_id": task.id}

        print("[AGENT] ❌ Test failed. Initiating Gemini Flash Multimodal Diagnosis...")
        diagnosis = self.healer.diagnose_failure(
            test_name=pytest_target,
            error_message=proc.stdout[-500:],
            traceback_str=proc.stdout,
            code_snippet="",
            recent_diff="",
        )

        print("\n" + "=" * 60)
        print("🤖 [AI DIAGNOSIS RESULT]")
        print(f"Engine: {diagnosis.get('engine')}")
        if diagnosis.get("analysis"):
            print(diagnosis.get("analysis"))
        else:
            print(f"Category:    {diagnosis.get('category')}")
            print(f"Remediation: {diagnosis.get('remediation')}")
        print("=" * 60 + "\n")

        if auto_rollback:
            print(f"[AGENT] Safety Guardrail: Rolling back workspace to snapshot {snapshot.id}")
            self.tm.restore_snapshot(snapshot.id)
            print("[AGENT] ✅ Workspace restored to pristine state. Zero code damage.")
            self.orchestrator.update_task_status(task.id, "ROLLED_BACK")

        return {
            "status": "FAILED_DIAGNOSED",
            "snapshot_id": snapshot.id,
            "diagnosis": diagnosis,
            "task_id": task.id,
        }
