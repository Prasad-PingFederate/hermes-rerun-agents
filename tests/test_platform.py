"""
Comprehensive Unit & Integration Test Suite for Hermes + Rerun Autonomous AI Agent Platform
Verifies safe restore, sandbox isolation, write gates, signature auth, CI routing, and syntax guards.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.breakglass_responder_healer import BreakglassResponderHealerSkill
from agents.ci_detective import CIDetectiveAgent
from agents.test_healer_agent import TestHealerAgent
from core.healer.gemini_flash import GeminiFlashHealer
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine
from scripts.syntax_guard import check_py310_compatibility
from server import github_actions_webhook, verify_hermes_token


class MockRequest:
    def __init__(self, body_bytes: bytes, headers: dict):
        self._body = body_bytes
        self.headers = headers

    async def body(self) -> bytes:
        return self._body


class TestHermesRerunPlatform(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        # Initialize git repo in workspace for snapshot engine testing
        subprocess.run(["git", "init"], cwd=str(self.workspace), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.local"], cwd=str(self.workspace), check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --------------------------------------------------------------------------
    # 1. Existing Foundation Tests (Preserved)
    # --------------------------------------------------------------------------

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

    # --------------------------------------------------------------------------
    # 2. Hardening Pass Required Tests (Step 8)
    # --------------------------------------------------------------------------

    def test_untracked_files_survive_restore(self):
        """Verify restore copies snapshot files back while leaving new unrelated untracked files intact."""
        tracked_file = self.workspace / "tracked.py"
        tracked_file.write_text("x = 100\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "commit", "-m", "add tracked.py"], cwd=str(self.workspace), check=True)

        tm = TimeMachineEngine(self.workspace)
        snap = tm.create_snapshot("clean_baseline")

        # Mutate tracked file and create a new unrelated untracked file
        tracked_file.write_text("x = 999\n", encoding="utf-8")
        untracked_file = self.workspace / "unrelated_untracked.txt"
        untracked_bytes = b"important user data created after snapshot"
        untracked_file.write_bytes(untracked_bytes)

        # Restore snapshot
        res = tm.restore_snapshot(snap.id, create_safety_snapshot=True)
        self.assertTrue(res["success"])

        # Tracked file must be restored to snapshot state
        self.assertEqual(tracked_file.read_text(encoding="utf-8"), "x = 100\n")

        # Untracked file MUST survive intact with identical bytes
        self.assertTrue(untracked_file.is_file(), "Unrelated untracked file was deleted by restore!")
        self.assertEqual(untracked_file.read_bytes(), untracked_bytes)

    def test_failed_patch_leaves_workspace_untouched(self):
        """Verify that a failing patch inside sandbox copy never touches the caller workspace."""
        failing_test = self.workspace / "test_unfixable.py"
        initial_content = "import pytest\n\ndef test_cannot_pass():\n    assert 1 == 2\n"
        failing_test.write_text(initial_content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "commit", "-m", "unfixable test"], cwd=str(self.workspace), check=True)

        agent = TestHealerAgent(workspace_path=self.workspace)
        res = agent.run_and_heal("test_unfixable.py", auto_rollback_on_failure=True)

        self.assertEqual(res["status"], "FAILED_DIAGNOSED")
        # Workspace file must remain 100% identical
        self.assertEqual(failing_test.read_text(encoding="utf-8"), initial_content)

    def test_approve_writes_and_rollback_leaves_tree_at_baseline(self):
        """Verify write gate: Caller workspace is untouched until approval, and rollback restores baseline."""
        test_file = self.workspace / "test_breakglass_gate.py"
        initial_content = (
            "import pytest\n"
            "BASE_URL = 'https://www.stage.b4igo.com'\n"
            "class MockLoc:\n"
            "    @property\n"
            "    def first(self):\n"
            "        return self\n"
            "class MockPage:\n"
            "    url = 'https://www.stage.b4igo.com/m?b=key'\n"
            "    def evaluate(self, s, *a):\n"
            "        return 'usr_test' if 'userId' in s else None\n"
            "    def reload(self, **kw):\n"
            "        pass\n"
            "    def wait_for_timeout(self, ms):\n"
            "        pass\n"
            "    def goto(self, u, **kw):\n"
            "        self.url = u\n"
            "    def locator(self, s):\n"
            "        return MockLoc()\n"
            "def _is_visible(l, timeout=3000):\n"
            "    return False\n"
            "def _derive_breakglass_url(p):\n"
            "    return 'https://www.stage.b4igo.com/m?b=key'\n"
            "def test_flow():\n"
            "    owner_page = MockPage()\n"
            "    resp_page = MockPage()\n"
            "    breakglass_url = _derive_breakglass_url(owner_page)\n"
            "    print('\\n[STEP 4] Initiating Responder Registration...')\n"
            "    click_here = None\n"
            "    if click_here and _is_visible(click_here):\n"
            "        pass\n"
            "    else:\n"
            "        raise AssertionError('Could not find Click here link on preview page')\n"
        )
        test_file.write_text(initial_content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "commit", "-m", "breakglass test"], cwd=str(self.workspace), check=True)

        agent = TestHealerAgent(workspace_path=self.workspace)
        result = agent.run_and_heal("test_breakglass_gate.py", auto_rollback_on_failure=False, auto_apply_fix=True)

        self.assertEqual(result["status"], "HEALED_VERIFIED")

        # Write Gate Check: caller workspace must NOT have the fix yet
        self.assertEqual(test_file.read_text(encoding="utf-8"), initial_content)

        # Human Approval: promotes verified fix to caller workspace
        app_res = agent.approve_task(result["task_id"])
        self.assertEqual(app_res["status"], "COMPLETED")
        self.assertIn("owner_user_id", test_file.read_text(encoding="utf-8"))

        # Rejection / Rollback: restores workspace to baseline
        rb_res = agent.rollback_task(result["task_id"])
        self.assertEqual(rb_res["status"], "ROLLED_BACK")
        self.assertEqual(test_file.read_text(encoding="utf-8"), initial_content)

    def test_webhook_bad_signature_401_and_fixture_resolution(self):
        """Verify webhook 401 on bad signature, and fixture resolution to rolebased-subscribers with continue_on_error."""
        from fastapi import BackgroundTasks, HTTPException

        os.environ["WEBHOOK_SECRET"] = "test_webhook_secret_key"

        # 1. Bad signature -> 401
        bad_req = MockRequest(b'{"action":"completed"}', {"X-Hub-Signature-256": "sha256=badbadbad"})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(github_actions_webhook(bad_req, BackgroundTasks()))
        self.assertEqual(ctx.exception.status_code, 401)

        # 2. Missing signature -> 401
        missing_req = MockRequest(b'{"action":"completed"}', {})
        with self.assertRaises(HTTPException) as ctx2:
            asyncio.run(github_actions_webhook(missing_req, BackgroundTasks()))
        self.assertEqual(ctx2.exception.status_code, 401)

        # 3. Valid signature with tests/fixtures/gha_workflow_job_failure.json
        fixture_path = REPO_ROOT / "tests" / "fixtures" / "gha_workflow_job_failure.json"
        raw_body = fixture_path.read_bytes()
        valid_sig = "sha256=" + hmac.new(b"test_webhook_secret_key", raw_body, hashlib.sha256).hexdigest()
        valid_req = MockRequest(raw_body, {"X-Hub-Signature-256": valid_sig})

        res = asyncio.run(github_actions_webhook(valid_req, BackgroundTasks()))
        self.assertEqual(res["status"], "triaged")
        self.assertTrue(res["triaged"])
        self.assertEqual(res["event"]["recommended_job"], "rolebased-subscribers")
        self.assertTrue(res["event"]["continue_on_error"])
        self.assertIn("Breakglass_Responder_Signup_Stage_Playwright.py", res["event"]["failing_test"])

        # 4. Unknown test name returns triaged=false
        unknown_body = json.dumps({"workflow_job": {"conclusion": "failure", "name": "Some Generic Job"}}).encode()
        unk_sig = "sha256=" + hmac.new(b"test_webhook_secret_key", unknown_body, hashlib.sha256).hexdigest()
        unk_req = MockRequest(unknown_body, {"X-Hub-Signature-256": unk_sig})

        unk_res = asyncio.run(github_actions_webhook(unk_req, BackgroundTasks()))
        self.assertEqual(unk_res["status"], "triaged")
        self.assertFalse(unk_res["triaged"])

    def test_ci_detective_a_star_registration_routing_strict(self):
        """Verify A_* tests strictly route to registration with continue_on_error: False."""
        routing = CIDetectiveAgent.get_recommended_ci_routing("A_Role_Accounts_Registration_Playwright.py")
        self.assertEqual(routing["target_job"], "registration")
        self.assertFalse(routing["continue_on_error"])
        self.assertTrue(routing["is_critical_prerequisite"])

        routing2 = CIDetectiveAgent.get_recommended_ci_routing("A_Create_Vault_Keys.py")
        self.assertEqual(routing2["target_job"], "registration")
        self.assertFalse(routing2["continue_on_error"])

    def test_breakglass_patch_returns_false_on_zero_anchors(self):
        """Verify apply_recovery_patch returns (False, reason) when zero anchors match."""
        generic_file = self.workspace / "generic_math.py"
        generic_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

        ok, reason = BreakglassResponderHealerSkill.apply_recovery_patch(generic_file)
        self.assertFalse(ok)
        self.assertIn("zero", reason.lower())

    def test_syntax_guard_catches_bad_py310_fstring(self):
        """Verify syntax guard detects backslash inside f-string expression in fixture without tokenize.FSTRING_*."""
        bad_fixture = REPO_ROOT / "tests" / "fixtures" / "bad_py310_fstring.py.txt"
        self.assertTrue(bad_fixture.is_file(), "Fixture bad_py310_fstring.py.txt is missing!")

        errors = check_py310_compatibility(bad_fixture)
        self.assertGreaterEqual(len(errors), 1)
        line, msg = errors[0]
        self.assertEqual(line, 5)
        self.assertTrue("backslash" in msg.lower() or "syntaxerror" in msg.lower())

    def test_auth_token_gate_on_api_endpoints(self):
        """Verify X-Hermes-Token requirement for /api/* endpoints."""
        from fastapi import HTTPException
        os.environ["HERMES_API_TOKEN"] = "secure_token_abc"

        # Missing token -> 401
        req_unauth = MockRequest(b"", {})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_hermes_token(req_unauth))
        self.assertEqual(ctx.exception.status_code, 401)

        # Wrong token -> 401
        req_bad_auth = MockRequest(b"", {"X-Hermes-Token": "wrong_token"})
        with self.assertRaises(HTTPException) as ctx2:
            asyncio.run(verify_hermes_token(req_bad_auth))
        self.assertEqual(ctx2.exception.status_code, 401)

        # Valid token -> succeeds
        req_good = MockRequest(b"", {"X-Hermes-Token": "secure_token_abc"})
        asyncio.run(verify_hermes_token(req_good))


if __name__ == "__main__":
    unittest.main()
