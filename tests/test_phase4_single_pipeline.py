"""
Comprehensive Test Suite for Phase 4 Single Pipeline (GAP-19 to GAP-23).
Tests:
1. test_provider_resolution: Ollama default, env var overrides, provider prefix stripped, bad model raises RuntimeError.
2. test_cloud_error_does_not_fall_back_to_heuristic: Mock 500 from provider; complete must raise, not return fallback text.
3. test_scope_separation_product_vs_test: Synthetic sprint with PRODUCT_BUG routes to DeveloperAgent; failure containing only test files routes to TestHealerAgent. Neither agent can write outside its partition.
4. test_assertion_erosion_rejected: Synthetic proposal with assert True, fewer assertions, or skip is rejected at tier 4 and escalates or fails.
5. test_single_pipeline_story_mode: End-to-end through run_sprint(mode='story', story=...) with LocalHeuristicEngine, auto_approve=True, verify_cmd asserts file written and passes.
6. test_single_pipeline_heal_mode: End-to-end through run_sprint(mode='heal', failure_output=...) repairing a failing test.
7. test_single_pipeline_rollback_on_failed_verification: Proposal applied, verify_fn returns False, workspace rolled back, sprint status rolled back.
8. test_staged_proposal_persists_across_restart: Stage proposal, drop in-memory controller, construct a new HumanWriteGateController against the same SQLite path, approve it; changes write correctly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from ast_patch_guard import ASTPatchGuard
from core.orchestrator.scrum_hierarchy import ModelTier, SubTaskTicket
from core.time_machine.engine import TimeMachineEngine
from hermes_workers import DeveloperAgent, TestHealerAgent, WorkerProposal
from llm_provider_adapter import (
    AgentRole,
    HermesLLMAdapter,
    resolve_model_for_call,
    resolve_provider,
)
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore
from write_gate_controller import HumanWriteGateController


class ErrorServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Internal Server Error from upstream LLM"}).encode("utf-8"))


class TestPhase4SinglePipeline(unittest.TestCase):
    """Verifies all Phase 4 specifications and invariants."""

    @classmethod
    def setUpClass(cls):
        cls.err_server = HTTPServer(("127.0.0.1", 0), ErrorServerHandler)
        cls.err_port = cls.err_server.server_address[1]
        cls.err_thread = threading.Thread(target=cls.err_server.serve_forever, daemon=True)
        cls.err_thread.start()
        cls.err_url = f"http://127.0.0.1:{cls.err_port}"

    @classmethod
    def tearDownClass(cls):
        cls.err_server.shutdown()
        cls.err_server.server_close()

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="hermes_phase4_test_")).resolve()
        self.workspace = self.test_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.store_db = self.test_dir / "sprint_state.db"
        self.store = SprintStateStore(db_path=self.store_db)
        self.tm_engine = TimeMachineEngine(self.workspace)
        self.orchestrator = ScrumMasterOrchestrator(
            workspace_path=self.workspace,
            tm_engine=self.tm_engine,
            store=self.store,
        )

        preserved = {
            k: v for k, v in os.environ.items()
            if k.upper() in (
                "SYSTEMROOT", "WINDIR", "PATH", "TMP", "TEMP", "SYSTEMDRIVE",
                "PYTHONPATH", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEPATH", "HOMEDRIVE"
            )
        }
        self.env_patcher = mock.patch.dict(os.environ, preserved, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Provider Resolution & Model Routing
    # -------------------------------------------------------------------------
    def test_provider_resolution(self):
        """Ollama default, env var overrides, provider prefix stripped, bad model raises RuntimeError."""
        # A. Ollama is default when OLLAMA_BASE_URL is set
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        self.assertEqual(resolve_provider(), "ollama")

        # B. Env var override HERMES_LLM_PROVIDER takes highest priority
        os.environ["HERMES_LLM_PROVIDER"] = "groq"
        self.assertEqual(resolve_provider(), "groq")

        # C. Provider prefix stripped and parsed for specific agent
        os.environ["HERMES_AGENT_DEVELOPER_AGENT_MODEL"] = "groq:llama-3.3-70b-versatile"
        self.assertEqual(resolve_provider(AgentRole.DEVELOPER_AGENT), "groq")
        prov, model = resolve_model_for_call(AgentRole.DEVELOPER_AGENT, "TIER_3_JUNIOR_SWE", "groq")
        self.assertEqual(prov, "groq")
        self.assertEqual(model, "llama-3.3-70b-versatile")

        # D. Bad/placeholder model with no provider fallback raises RuntimeError
        os.environ["HERMES_LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "sk-dummy"
        os.environ.pop("OPENAI_MODEL", None)
        os.environ.pop("HERMES_AGENT_DEVELOPER_AGENT_MODEL", None)
        with self.assertRaises(RuntimeError) as ctx:
            resolve_model_for_call(AgentRole.DEVELOPER_AGENT, "TIER_3_JUNIOR_SWE", "openai")
        self.assertIn("missing model configuration", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. Cloud Error Does Not Fall Back to Heuristic
    # -------------------------------------------------------------------------
    def test_cloud_error_does_not_fall_back_to_heuristic(self):
        """Mock 500 from provider; complete must raise, not return fallback text."""
        os.environ["HERMES_LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "sk-dummy"
        os.environ["OPENAI_BASE_URL"] = self.err_url
        os.environ["OPENAI_MODEL"] = "gpt-4o"

        adapter = HermesLLMAdapter(self.workspace)
        with self.assertRaises((RuntimeError, urllib.error.HTTPError)):
            adapter.complete(
                role=AgentRole.DEVELOPER_AGENT,
                tier="TIER_3_JUNIOR_SWE",
                system_prompt="You are DeveloperAgent.",
                user_prompt="Fix bug",
            )

    # -------------------------------------------------------------------------
    # 3. Scope Separation: Product vs Test
    # -------------------------------------------------------------------------
    def test_scope_separation_product_vs_test(self):
        """Synthetic sprint with PRODUCT_BUG routes to DeveloperAgent; failure containing only test files routes to TestHealerAgent. Neither agent can write outside its partition."""
        src_file = self.workspace / "calculator.py"
        src_file.write_text("def add(a, b): return a - b\n", encoding="utf-8")
        test_file = self.workspace / "test_calculator.py"
        test_file.write_text("from calculator import add\ndef test_add(): assert add(1, 2) == 3\n", encoding="utf-8")

        # Case A: PRODUCT_BUG failure output
        prod_failure_output = (
            "FAILED test_calculator.py::test_add - assert -1 == 3\n"
            "    def test_add():\n"
            ">       assert add(1, 2) == 3\n"
            "calculator.py:1: in add\n"
            "    return a - b\n"
            "E   AssertionError: assert -1 == 3"
        )
        classification = self.orchestrator.sandbox.classify_failure(prod_failure_output)
        self.assertEqual(classification, "PRODUCT_BUG")

        # Scope enforcement: DeveloperAgent cannot write to test file
        dev_ticket = SubTaskTicket(
            ticket_id="TICK-DEV-001",
            title="Fix calc",
            complexity=2,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["calculator.py"],
        )
        scope_ok, scope_reasons = self.orchestrator.router.validate_worker_scope(
            dev_ticket,
            {"test_calculator.py": "def test_add(): pass\n"}
        )
        self.assertFalse(scope_ok)
        self.assertIn("Scope violation", "; ".join(scope_reasons))

        # Case B: TEST_BUG failure output (only test file referenced)
        test_failure_output = (
            "tests/test_calc.py:3: in <module>\n"
            "    import nonexistent_module\n"
            "E   ModuleNotFoundError: No module named 'nonexistent_module'"
        )
        test_classification = self.orchestrator.sandbox.classify_failure(test_failure_output)
        self.assertEqual(test_classification, "TEST_BUG")

        # Scope enforcement: TestHealerAgent cannot write to implementation file
        healer_ticket = SubTaskTicket(
            ticket_id="TICK-HEAL-001",
            title="Fix test",
            complexity=2,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["tests/test_calc.py"],
        )
        scope_ok_healer, healer_reasons = self.orchestrator.router.validate_worker_scope(
            healer_ticket,
            {"src/calculator.py": "def add(a, b): return a + b\n"}
        )
        self.assertFalse(scope_ok_healer)
        self.assertIn("Scope violation", "; ".join(healer_reasons))

    # -------------------------------------------------------------------------
    # 4. Zero Assertion Erosion Rejected
    # -------------------------------------------------------------------------
    def test_assertion_erosion_rejected(self):
        """Synthetic proposal with assert True, fewer assertions, or skip is rejected at tier 4 and escalates or fails."""
        test_f = self.workspace / "tests" / "test_example.py"
        test_f.parent.mkdir(parents=True, exist_ok=True)
        test_f.write_text(
            "def test_one():\n    assert 10 > 5\n\ndef test_two():\n    assert 20 > 10\n",
            encoding="utf-8",
        )

        ticket = SubTaskTicket(
            ticket_id="TICK-EROSION-001",
            title="Clean tests",
            complexity=1,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["tests/test_example.py"],
        )

        # 1. Proposal injecting assert True
        res_trivial = ASTPatchGuard.analyze(
            workspace_root=self.workspace,
            proposed_changes={"tests/test_example.py": "def test_one():\n    assert True\n"},
            allow_test_modification=True,
            ticket=ticket,
        )
        self.assertFalse(res_trivial["valid"])
        self.assertTrue(any("trivial assert True" in r or "Deleted test" in r for r in res_trivial.get("reasons", [])))

        # 2. Proposal with decreased assertion count
        res_decreased = ASTPatchGuard.analyze(
            workspace_root=self.workspace,
            proposed_changes={"tests/test_example.py": "def test_one():\n    assert 10 > 5\n\ndef test_two():\n    pass\n"},
            allow_test_modification=True,
            ticket=ticket,
        )
        self.assertFalse(res_decreased["valid"])
        self.assertTrue(any("assert count decreased" in r for r in res_decreased.get("reasons", [])))

        # 3. Proposal with skip decorator
        res_skip = ASTPatchGuard.analyze(
            workspace_root=self.workspace,
            proposed_changes={"tests/test_example.py": "import pytest\n@pytest.mark.skip\ndef test_one():\n    assert 10 > 5\n\ndef test_two():\n    assert 20 > 10\n"},
            allow_test_modification=True,
            ticket=ticket,
        )
        self.assertFalse(res_skip["valid"])
        self.assertTrue(any("skip decorator" in r for r in res_skip.get("reasons", [])))

    # -------------------------------------------------------------------------
    # 5. Single Pipeline Story Mode
    # -------------------------------------------------------------------------
    def test_single_pipeline_story_mode(self):
        """End-to-end through run_sprint(mode='story', story=...) with LocalHeuristicEngine, auto_approve=True, verify_cmd asserts file written and passes."""
        story = "Implement add function in math_ops.py and test_add in test_math_ops.py"
        res = self.orchestrator.run_sprint(
            mode="story",
            story=story,
            scope=["math_ops.py", "test_math_ops.py"],
            pytest_cmd=[sys.executable, "-c", "import sys; sys.exit(0)"],
            auto_approve=True,
        )

        self.assertIn(res.get("status"), ("APPLIED", "COMPLETED"))
        self.assertTrue((self.workspace / "math_ops.py").is_file() or (self.workspace / "test_math_ops.py").is_file())
        self.assertIn("snapshot_id", res)

    # -------------------------------------------------------------------------
    # 6. Single Pipeline Heal Mode
    # -------------------------------------------------------------------------
    def test_single_pipeline_heal_mode(self):
        """End-to-end through run_sprint(mode='heal', failure_output=...) repairing a failing test."""
        src_file = self.workspace / "src" / "calc.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("def multiply(a: int, b: int) -> int:\n    raise ValueError('multiplication error')\n", encoding="utf-8")

        test_file = self.workspace / "tests" / "test_calc.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from calc import multiply\n"
            "def test_multiply():\n    assert multiply(3, 4) == 12\n",
            encoding="utf-8",
        )

        # Run pytest to get initial failure
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_calc.py"],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

        # Run single pipeline heal
        res = self.orchestrator.run_sprint(
            mode="heal",
            failure_output=proc.stdout + "\n" + proc.stderr,
            pytest_cmd=[sys.executable, "-m", "pytest", "tests/test_calc.py"],
            auto_approve=True,
        )

        self.assertIn(res.get("status"), ("APPLIED", "COMPLETED"))
        # Verify workspace now passes tests
        proc_after = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_calc.py"],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc_after.returncode, 0)

    # -------------------------------------------------------------------------
    # 7. Single Pipeline Rollback on Failed Verification
    # -------------------------------------------------------------------------
    def test_single_pipeline_rollback_on_failed_verification(self):
        """Proposal applied, verify_fn returns False, workspace rolled back, sprint status rolled back."""
        app_file = self.workspace / "app.py"
        app_file.write_text("original_app_code = True\n", encoding="utf-8")

        ticket = SubTaskTicket(
            ticket_id="TICK-ROLLBACK-001",
            title="Modify app",
            complexity=1,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["app.py"],
        )
        proposal = WorkerProposal(
            ticket_id="TICK-ROLLBACK-001",
            worker_agent="DeveloperAgent",
            model_tier="TIER_3_JUNIOR_SWE",
            proposed_changes={"app.py": "mutated_code = True\n"},
        )

        sprint_id = "sprint_rollback_test"
        self.orchestrator.write_gate.stage_proposal(sprint_id, ticket, proposal)

        # Verification fails: returns False
        res = self.orchestrator.write_gate.approve_proposal(
            sprint_id=sprint_id,
            verification_fn=lambda: False,
        )

        self.assertEqual(res["status"], "ROLLED_BACK")
        self.assertFalse(res["success"])
        # File should have been rolled back to original content
        self.assertEqual(app_file.read_text(encoding="utf-8"), "original_app_code = True\n")

    # -------------------------------------------------------------------------
    # 8. Staged Proposal Persists Across Process Restart
    # -------------------------------------------------------------------------
    def test_staged_proposal_persists_across_restart(self):
        """Stage proposal, drop in-memory controller, construct a new HumanWriteGateController against the same SQLite path, approve it; changes write correctly."""
        file_to_change = self.workspace / "persistent_target.py"
        file_to_change.write_text("initial_state = 1\n", encoding="utf-8")

        sprint_id = "sprint_restart_persists_001"
        ticket = SubTaskTicket(
            ticket_id="TICK-RESTART-001",
            title="Persistent change",
            complexity=2,
            assigned_tier="TIER_2_SENIOR_SWE",
            allowed_files=["persistent_target.py"],
        )
        proposal = WorkerProposal(
            ticket_id="TICK-RESTART-001",
            worker_agent="SeniorWorker",
            model_tier="TIER_2_SENIOR_SWE",
            proposed_changes={"persistent_target.py": "persisted_state = 2\n"},
        )

        # 1. Stage in initial gate controller
        gate1 = HumanWriteGateController(
            workspace_path=self.workspace,
            tm_engine=self.tm_engine,
            store=self.store,
        )
        gate1.stage_proposal(sprint_id, ticket, proposal)

        # 2. Drop in-memory controller
        del gate1

        # 3. Reconstruct new gate controller against same SQLite DB
        reloaded_store = SprintStateStore(db_path=self.store_db)
        gate2 = HumanWriteGateController(
            workspace_path=self.workspace,
            tm_engine=self.tm_engine,
            store=reloaded_store,
        )

        # 4. Approve staged proposal across process boundary
        res = gate2.approve_proposal(sprint_id)
        self.assertEqual(res["status"], "APPLIED")
        self.assertTrue(res["success"])

        # 5. Verify live workspace content
        self.assertEqual(file_to_change.read_text(encoding="utf-8"), "persisted_state = 2\n")


if __name__ == "__main__":
    unittest.main()
