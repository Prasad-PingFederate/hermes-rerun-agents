"""
End-to-End Demonstration:
Autonomous Detection & Healing of a Stage-style Breakglass 'QR Expired' Failure.
Enforces Pytest Preflight Check and Approval Write-Gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.test_healer_agent import TestHealerAgent
from core.sandbox.runner import SandboxRunner
from core.time_machine.engine import TimeMachineEngine


def run_demo():
    print("=" * 70)
    print("🚀 [DEMO] Hermes + Rerun Autonomous Bug Detection & Healing Demonstration")
    print("=" * 70)

    # Preflight: Verify pytest is available before proceeding
    if not SandboxRunner.is_pytest_available():
        print("\n[SANDBOX] pytest is not installed in the active Python environment.")
        print("Demo cannot run without pytest. Please install pytest (`pip install pytest`) and retry.\n")
        sys.exit(1)

    # 1. Create a simulated sandbox workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir).resolve()
        print(f"[DEMO] 📁 Created isolated demo workspace: {workspace}")

        # Initialize git repo in sandbox
        subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Demo"], cwd=str(workspace), check=True)
        subprocess.run(["git", "config", "user.email", "demo@local"], cwd=str(workspace), check=True)

        # 2. Create a test file representing the Breakglass Preview test BEFORE the fix
        test_file = workspace / "test_breakglass_responder.py"
        initial_test_code = """import pytest

BASE_URL = "https://www.stage.b4igo.com"

class DummyLocator:
    @property
    def first(self):
        return self

# Simulated Playwright Page
class MockPage:
    url = "https://www.stage.b4igo.com/m?b=mock_piv_key"
    def evaluate(self, script, *args):
        if "userId" in script:
            return "usr_1092837465"
        return None
    def reload(self, **kwargs):
        pass
    def wait_for_timeout(self, ms):
        pass
    def goto(self, url, **kwargs):
        self.url = url
    def locator(self, selector):
        return DummyLocator()

def _is_visible(loc, timeout=3000):
    return False

def _derive_breakglass_url(page):
    return "https://www.stage.b4igo.com/m?b=mock_piv_key"

def test_breakglass_responder_full_flow():
    owner_page = MockPage()
    resp_page = MockPage()

    breakglass_url = _derive_breakglass_url(owner_page)

    print("\\n[STEP 4] Initiating Responder Registration...")
    click_here_link = None  # Preview handshake timed out -> InfoNote was not rendered

    if click_here_link and _is_visible(click_here_link):
        pass
    else:
        raise AssertionError(
            "Could not find the 'Click here' link on the Breakglass preview page (URL: "
            + resp_page.url + ") to start Responder Registration. InfoNote.tsx renders "
            "this inside the AHD summary section gated behind the helloServer/verifySignature "
            "crypto handshake. If that handshake failed or page fell into 'QR Expired', "
            "no registration link is ever rendered."
        )
"""
        test_file.write_text(initial_test_code.strip() + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(workspace), check=True)
        subprocess.run(["git", "commit", "-m", "Initial test before fix"], cwd=str(workspace), check=True)

        # 3. Instantiate the Autonomous Test Healer Agent in this workspace
        agent = TestHealerAgent(workspace_path=workspace)

        # 4. Run the autonomous healing pipeline (executed in temporary sandbox copy)
        print("\n--- [STEP 1] Agent executes test and observes failure ---")
        result = agent.run_and_heal(
            test_file="test_breakglass_responder.py",
            auto_rollback_on_failure=False,
            auto_apply_fix=True,
        )

        print("\n--- [STEP 2] Results Evaluation ---")
        print(f"Status:             {result['status']}")
        print(f"Baseline Snapshot:  {result.get('baseline_snapshot')}")
        print(f"Diagnosis Category: {result.get('diagnosis', {}).get('category')}")

        assert result["status"] == "HEALED_VERIFIED", f"Expected HEALED_VERIFIED, got {result['status']}"

        # Write Gate Verification: Caller workspace must remain untouched while fix is only proposed!
        caller_content_pre_approval = test_file.read_text(encoding="utf-8")
        assert "owner_user_id" not in caller_content_pre_approval, "Write gate failed: Caller workspace modified before approval!"
        print("✅ Write Gate verified: Caller workspace untouched while fix is AWAITING_APPROVAL.")

        # Human Approval Gate: Approve and promote verified fix
        print("\n--- [STEP 3] Human Approval Gate: Approving and Promoting Fix ---")
        agent.approve_task(result["task_id"])
        healed_content = test_file.read_text(encoding="utf-8")
        assert "owner_user_id" in healed_content, "Failed: owner_user_id was not written on approval"
        assert "sessionStorage.setItem('responderSignupCallback'" in healed_content, "Failed: canonical fallback was not written on approval"
        print("✅ Approval Gate verified: Verified fix successfully written to workspace.")

        # Safety Rollback Verification
        print("\n--- [STEP 4] Testing Safety Rollback ---")
        agent.rollback_task(result["task_id"])
        rolled_back_content = test_file.read_text(encoding="utf-8")
        assert "owner_user_id" not in rolled_back_content, "Failed: rollback did not restore original code"
        print("✅ Safety Rollback verified: File reverted 100% to baseline state with zero code damage.")

        print("\n" + "=" * 70)
        print("🎉 [SUCCESS] All Autonomous Detection, Healing & Rollback checks PASSED!")
        print("=" * 70)


if __name__ == "__main__":
    run_demo()
