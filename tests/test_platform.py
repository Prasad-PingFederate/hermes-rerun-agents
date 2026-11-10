"""
Unit Tests for Hermes + Rerun Autonomous AI Agent Platform
"""

import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].id, snap1.id)

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
        # Without API key, healer uses heuristic fallback cleanly
        healer = GeminiFlashHealer(api_key=None)
        res = healer.diagnose_failure(
            test_name="test_login",
            error_message="PlaywrightTimeoutError: waiting for locator('button#submit')",
            traceback_str="Traceback ...",
            code_snippet="page.click('button#submit')",
        )
        self.assertFalse(res["ai_powered"])
        self.assertIn("Timeout", res["category"])


if __name__ == "__main__":
    unittest.main()
