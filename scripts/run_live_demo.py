"""
GAP-18: Live Self-Contained End-to-End Smoke Demo
Owner: AutomationTesterAgent (TIER_3)

Executes a complete self-healing workflow in an isolated temporary Git repository:
1. Creates temporary git repo with a buggy InMemoryLedger and failing pytest test.
2. Runs pytest to confirm failure (0% passing).
3. Executes full Hermes multi-agent pipeline:
   - RequirementsAgent: Ingests failure & extracts AC-1..N, EC-1..N.
   - ScrumMasterOrchestrator: Generates sprint plan & routes ticket.
   - DeveloperAgent: Synthesizes clean patch via HermesLLMAdapter / LocalHeuristicEngine.
   - QACriticAgent: Verifies Acceptance Criteria with line citations.
   - SecurityBlastRadiusAgent: Ensures no constant-time or injection vulnerabilities.
   - AutomationTesterAgent: Validates in isolated sandbox (repeat=3).
   - HumanWriteGate: Creates TimeMachine snapshot & atomically applies changes.
4. Verifies pytest turns green (100% passing).
5. Tests TimeMachine rollback to confirm workspace reverts cleanly to baseline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ast_patch_guard import ASTPatchGuard
from ci_failure_ingestor import CIFailureIngestor
from core.time_machine.engine import TimeMachineEngine
from hermes_workers import AutomationTesterAgent, DeveloperAgent, WorkerProposal
from llm_provider_adapter import AgentRole, HermesLLMAdapter
from qa_critic_reviewer import QACriticAgent
from sandbox_executor import SandboxExecutor
from scrum_master_orchestrator import ScrumMasterOrchestrator
from write_gate_controller import HumanWriteGateController


def run_demo() -> int:
    print("=" * 80)
    print("    HERMES MULTI-AGENT ORCHESTRATOR — LIVE END-TO-END SMOKE DEMO")
    print("=" * 80)

    demo_dir = Path(tempfile.mkdtemp(prefix="hermes_live_demo_")).resolve()
    print(f"\n[1/6] Initializing isolated test repository at: {demo_dir}")

    try:
        # Initialize Git repo
        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        # Create source and test directories
        src_dir = demo_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # 1. Buggy InMemoryLedger: does not validate negative deposits
        buggy_ledger = (
            "class InMemoryLedger:\n"
            "    def __init__(self, initial_balance: float = 0.0):\n"
            "        self._balance = initial_balance\n\n"
            "    @property\n"
            "    def balance(self) -> float:\n"
            "        return self._balance\n\n"
            "    def deposit(self, amount: float) -> float:\n"
            "        # BUG: Fails to reject negative or zero deposits\n"
            "        self._balance += amount\n"
            "        return self._balance\n"
        )
        (src_dir / "InMemoryLedger.py").write_text(buggy_ledger, encoding="utf-8")

        # 2. Strict unit test: expects ValueError on negative deposit
        test_content = (
            "import pytest\n"
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from InMemoryLedger import InMemoryLedger\n\n"
            "def test_deposit_valid():\n"
            "    ledger = InMemoryLedger(100.0)\n"
            "    assert ledger.deposit(50.0) == 150.0\n"
            "    assert ledger.balance == 150.0\n\n"
            "def test_deposit_rejects_negative():\n"
            "    ledger = InMemoryLedger(100.0)\n"
            "    with pytest.raises(ValueError):\n"
            "        ledger.deposit(-25.0)\n"
        )
        (tests_dir / "test_ledger.py").write_text(test_content, encoding="utf-8")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial buggy ledger"], cwd=str(demo_dir), capture_output=True, check=True)

        # [2/6] Execute pytest to confirm baseline failure
        print("\n[2/6] Executing pytest to confirm failure (expected: FAIL)...")
        res1 = subprocess.run([sys.executable, "-m", "pytest", "tests/test_ledger.py", "-v"], cwd=str(demo_dir), capture_output=True, text=True)
        print(f"      Exit Code: {res1.returncode} (Failure Confirmed)")
        assert res1.returncode != 0, "Initial test should have failed"

        # [3/6 - 5/6] Single Pipeline Execution: ScrumMasterOrchestrator.run_sprint
        print("\n[3-5/6] Executing unified pipeline ScrumMasterOrchestrator.run_sprint (auto_approve=True)...")
        orchestrator = ScrumMasterOrchestrator(demo_dir)
        sprint_res = orchestrator.run_sprint(
            mode="heal",
            failure_output=res1.stdout + "\n" + res1.stderr,
            pytest_cmd=[sys.executable, "-m", "pytest", "tests/test_ledger.py"],
            auto_approve=True,
        )

        assert sprint_res.get("success") or sprint_res.get("status") in ("APPLIED", "COMPLETED"), f"Sprint run failed: {sprint_res}"
        snapshot_id = sprint_res["snapshot_id"]
        print(f"      Sprint Status:            {sprint_res.get('status')}")
        print(f"      Pre-Apply Snapshot ID:    {snapshot_id}")
        print(f"      Atomically Written Files: {sprint_res.get('applied_files')}")

        # Confirm tests are now green on live workspace
        res2 = subprocess.run([sys.executable, "-m", "pytest", "tests/test_ledger.py", "-v"], cwd=str(demo_dir), capture_output=True, text=True)
        print(f"      Live Workspace pytest Exit Code: {res2.returncode} (100% PASSING)")
        assert res2.returncode == 0, "Live tests must pass after write-gate application"

        # [6/6] Verify TimeMachine Surgical Rollback
        print("\n[6/6] Testing TimeMachine rollback to restore baseline...")
        orchestrator.write_gate.rollback_snapshot(snapshot_id)
        current_ledger = (src_dir / "InMemoryLedger.py").read_text(encoding="utf-8")
        assert "BUG: Fails to reject" in current_ledger, "Rollback must restore original baseline"

        res3 = subprocess.run([sys.executable, "-m", "pytest", "tests/test_ledger.py"], cwd=str(demo_dir), capture_output=True, text=True)
        assert res3.returncode != 0, "Tests must fail again after rollback"
        print("      Rollback Verified: Workspace cleanly reverted to baseline.")

        print("\n" + "=" * 80)
        print("🎉 [DEMO COMPLETE] All 6 phases passed with exit code 0!")
        print("=" * 80)
        return 0

    finally:
        shutil.rmtree(demo_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_demo())

