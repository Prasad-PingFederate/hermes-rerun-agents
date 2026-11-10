"""
Autonomous Test Failure Healer Agent with Time Machine Safety Guardrail
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agents.breakglass_responder_healer import BreakglassResponderHealerSkill
from core.healer.gemini_flash import GeminiFlashHealer
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.sandbox.runner import SandboxRunner
from core.time_machine.engine import TimeMachineEngine


class TestHealerAgent:
    """Autonomous agent that investigates, heals, and verifies test failures with rollback safety."""

    def __init__(
        self,
        workspace_path: Optional[str | Path] = None,
        gemini_api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = TimeMachineEngine(self.workspace_path)
        self.healer = GeminiFlashHealer(api_key=gemini_api_key, ollama_base_url=ollama_base_url)
        self.sandbox = SandboxRunner(self.workspace_path)
        self.orchestrator = RerunOrchestrator(self.workspace_path / ".rerun_tasks")

    def run_and_heal(
        self,
        test_file: str,
        auto_rollback_on_failure: bool = True,
        auto_apply_fix: bool = True,
    ) -> Dict[str, Any]:
        """Execute a test; if it fails, diagnose and safely attempt remediation with rollback protection."""
        print(f"[AGENT] 📸 Taking baseline Time Machine snapshot before running: {test_file}")
        baseline_snap = self.tm.create_snapshot(
            label=f"pre_test_{Path(test_file).stem}",
            description=f"Baseline state before executing {test_file}",
        )

        task = self.orchestrator.create_task(
            title=f"Test & Heal: {test_file}",
            details={"test_file": test_file, "baseline_snapshot": baseline_snap.id},
        )

        # 1. Execute test in sandbox
        print(f"[AGENT] 🧪 Executing test in sandbox harness: {test_file} ...")
        res1 = self.sandbox.execute_test(test_file)

        if res1.passed:
            print("[AGENT] ✅ Test passed cleanly on first attempt.")
            self.orchestrator.update_task_status(task.id, "COMPLETED")
            return {
                "status": "PASSED",
                "snapshot_id": baseline_snap.id,
                "task_id": task.id,
                "duration": res1.duration_seconds,
            }

        # 2. Test failed - extract context & diagnose
        print(f"[AGENT] ❌ Test failed (code {res1.returncode}). Initiating Failure Diagnosis...")
        target_path = self.workspace_path / test_file
        code_snippet = ""
        if target_path.is_file():
            try:
                code_snippet = target_path.read_text(encoding="utf-8", errors="replace")[:1500]
            except Exception:
                pass

        # Check domain-specific skill first (e.g. Breakglass QR Expired preview bug)
        applied_skill = False
        if BreakglassResponderHealerSkill.is_matching_failure(test_file, res1.stderr or res1.stdout, res1.stdout):
            print("[AGENT] 💡 Breakglass Preview Handshake / QR Expired pattern detected! Applying specialized skill...")
            ok, msg = BreakglassResponderHealerSkill.apply_recovery_patch(target_path)
            applied_skill = ok
            diagnosis = {
                "engine": "Breakglass Skill",
                "category": "Stage Preview Crypto Handshake Timeout",
                "root_cause": msg,
            }
        else:
            diagnosis = self.healer.diagnose_failure(
                test_name=test_file,
                error_message=res1.stderr or res1.stdout[-400:],
                traceback_str=res1.stdout,
                code_snippet=code_snippet,
                screenshot_path=res1.screenshot_path,
            )

        print("\n" + "=" * 60)
        print("🤖 [AI DIAGNOSIS RESULT]")
        print(f"Engine:   {diagnosis.get('engine')}")
        print(f"Category: {diagnosis.get('category')}")
        if diagnosis.get("analysis"):
            print(f"Analysis: {diagnosis.get('analysis')[:300]}...")
        elif diagnosis.get("root_cause"):
            print(f"Root Cause: {diagnosis.get('root_cause')}")
        print("=" * 60 + "\n")

        # 3. If a patch was applied, re-verify in sandbox
        if applied_skill:
            print("[AGENT] 🔄 Re-executing test in sandbox to verify patch...")
            res2 = self.sandbox.execute_test(test_file)
            if res2.passed:
                print("[AGENT] 🏆 Patch verified! Test is now PASSING 100%.")
                verified_snap = self.tm.create_snapshot(
                    label=f"verified_{Path(test_file).stem}",
                    description=f"Verified working fix for {test_file}",
                )
                self.orchestrator.update_task_status(
                    task.id,
                    "AWAITING_APPROVAL",
                    proposed_patch=self.tm.get_diff(baseline_snap.id),
                )
                return {
                    "status": "HEALED_VERIFIED",
                    "baseline_snapshot": baseline_snap.id,
                    "verified_snapshot": verified_snap.id,
                    "task_id": task.id,
                    "diagnosis": diagnosis,
                }
            else:
                print(f"[AGENT] ⚠️ Patch did not resolve the failure. Return code {res2.returncode}.\nOutput:\n{res2.stdout}\n{res2.stderr}")

        # 4. Safe rollback if still failing
        if auto_rollback_on_failure:
            print(f"[AGENT] 🛡️ Safety Guardrail Triggered: Rolling back workspace to {baseline_snap.id}...")
            self.tm.restore_snapshot(baseline_snap.id)
            print("[AGENT] ✅ Workspace restored cleanly. Zero code damage.")
            self.orchestrator.update_task_status(task.id, "ROLLED_BACK")

        return {
            "status": "FAILED_DIAGNOSED",
            "snapshot_id": baseline_snap.id,
            "task_id": task.id,
            "diagnosis": diagnosis,
        }
