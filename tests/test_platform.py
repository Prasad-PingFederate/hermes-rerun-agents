"""
Comprehensive Unit & Integration Test Suite for Hermes + Rerun Autonomous AI Agent Platform
"""

import tempfile
import unittest
from pathlib import Path

from agents.breakglass_responder_healer import BreakglassResponderHealerSkill
from agents.ci_detective import CIDetectiveAgent
from core.healer.gemini_flash import GeminiFlashHealer
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine


class TestHermesRerunPlatform(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_time_machine_snapshot_and_listing(self):
        tm = TimeMachineEngine(self.workspace)
        snap1 = tm.create_snapshot("initial_baseline", "Clean state")
        self.assertTrue(snap1.id.startswith("snap_"))
        self.assertEqual(snap1.label, "initial_baseline")

        snapshots = tm.list_snapshots()
        self.assertGreaterEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].id, snap1.id)

    def test_time_machine_safety_snapshot_before_rollback(self):
        tm = TimeMachineEngine(self.workspace)
        snap1 = tm.create_snapshot("step_1", "Step 1 state")
        snap2 = tm.create_snapshot("step_2", "Step 2 state")

        # Rollback to snap1 with safety snapshot enabled
        tm.restore_snapshot(snap1.id, create_safety_snapshot=True)

        snapshots = tm.list_snapshots()
        safety_snaps = [s for s in snapshots if "pre_rollback" in s.label]
        self.assertGreaterEqual(len(safety_snaps), 1)
        self.assertEqual(safety_snaps[0].metadata.get("target_restored"), snap1.id)

    def test_rerun_orchestrator_task_lifecycle(self):
        orch = RerunOrchestrator(self.workspace / ".rerun_tasks")
        task = orch.create_task("Fix TC041", {"issue": "locator drift"})
        self.assertEqual(task.status, "PENDING")

        orch.update_task_status(task.id, "AWAITING_APPROVAL", proposed_patch="diff --git ...")
        pending = orch.list_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, task.id)
        self.assertEqual(pending[0].proposed_patch, "diff --git ...")

    def test_gemini_flash_healer_fallback(self):
        healer = GeminiFlashHealer(api_key=None)
        res = healer.diagnose_failure(
            test_name="test_login",
            error_message="PlaywrightTimeoutError: waiting for locator('button#submit')",
            traceback_str="Traceback ...",
            code_snippet="page.click('button#submit')",
        )
        self.assertFalse(res["ai_powered"])
        self.assertIn("Locator Drift", res["category"])

    def test_breakglass_responder_skill_detection(self):
        is_match = BreakglassResponderHealerSkill.is_matching_failure(
            test_name="test_breakglass_responder_full_flow",
            error_message="AssertionError: Could not find the 'Click here' link on the Breakglass preview page",
            stdout="[RESP_BROWSER] QR Expired – Emergency Profile",
        )
        self.assertTrue(is_match)

    def test_breakglass_responder_skill_patch_application(self):
        test_file = self.workspace / "test_breakglass.py"
        test_file.write_text(
            "def test_foo():\n"
            "    breakglass_url = _derive_breakglass_url(owner_page)\n"
            "    print('\\n[STEP 4] Initiating Responder Registration...')\n"
            "    if click_here:\n"
            "        pass\n"
            "    else:\n"
            "        raise AssertionError('Could not find Click here')\n",
            encoding="utf-8",
        )
        ok, msg = BreakglassResponderHealerSkill.apply_recovery_patch(test_file)
        self.assertTrue(ok)
        patched = test_file.read_text(encoding="utf-8")
        self.assertIn("owner_user_id = \"\"", patched)
        self.assertIn("qr_expired", patched)
        self.assertIn("responderSignupCallback", patched)

    def test_ci_detective_routing_isolation(self):
        reg_routing = CIDetectiveAgent.get_recommended_ci_routing("A_Role_Accounts_Registration_Playwright.py")
        self.assertEqual(reg_routing["target_job"], "registration")
        self.assertTrue(reg_routing["is_critical_prerequisite"])
        self.assertFalse(reg_routing["continue_on_error"])

        resp_routing = CIDetectiveAgent.get_recommended_ci_routing("Breakglass_Responder_Signup_Stage_Playwright.py")
        self.assertEqual(resp_routing["target_job"], "rolebased-subscribers")
        self.assertFalse(resp_routing["is_critical_prerequisite"])
        self.assertTrue(resp_routing["continue_on_error"])


if __name__ == "__main__":
    unittest.main()
