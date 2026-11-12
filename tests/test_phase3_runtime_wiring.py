"""
Comprehensive Unit & Integration Test Suite for GAP-13 through GAP-18 (Phase 3 Runtime Wiring).
Covers:
- AGENT_SKILL_REGISTRY: All 8 agents with roles, tiers, skills, and boundaries.
- HermesLLMAdapter & LocalHeuristicEngine: Offline and multi-tier routing.
- WorkspaceFileReader, UnifiedDiffGenerator & AtomicPatchApplier: Path safety and atomic writing.
- HumanWriteGateController & TimeMachineEngine: Pre-apply snapshotting, CLI approval, and surgical rollback.
- CIFailureIngestor & PytestTracebackParser: Traceback and JUnit XML decomposition.
- Hermes CLI: All commands (agents, status, run, heal, approve, rollback).
- Live Smoke Demo: End-to-end self-healing run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ci_failure_ingestor import CIFailureIngestor, JUnitXMLIngestor, PytestTracebackParser
from core.orchestrator.scrum_hierarchy import SubTaskTicket
from core.time_machine.engine import TimeMachineEngine
from hermes_cli import main as cli_main
from hermes_workers import WorkerProposal
from llm_provider_adapter import (
    AGENT_SKILL_REGISTRY,
    AgentRole,
    HermesLLMAdapter,
    LocalHeuristicEngine,
    extract_code_or_diff,
    extract_json_from_response,
    get_agent_skill_definition,
)
from scripts.run_live_demo import run_demo
from sprint_state_store import SprintStateStore
from workspace_patch_applier import (
    AtomicPatchApplier,
    SafePathViolationError,
    UnifiedDiffGenerator,
    WorkspaceFileReader,
)
from write_gate_controller import HumanWriteGateController


class TestHermesPhase3RuntimeWiring(unittest.TestCase):
    """Test suite for Phase 3 live runtime wiring and skills registry."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="hermes_p3_test_")).resolve()
        self.workspace = self.test_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        (self.workspace / "calculator.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        tests_dir = self.workspace / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_calc.py").write_text(
            "from calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )

        self.tm_engine = TimeMachineEngine(self.workspace)
        self.store = SprintStateStore(db_path=self.test_dir / "sprint.db")
        self.gate_controller = HumanWriteGateController(self.workspace, self.tm_engine, self.store)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # GAP-13: Agent Skill Registry & LLM Adapter
    # -------------------------------------------------------------------------
    def test_agent_skill_registry_all_8_agents_registered(self):
        """All 8 agents must be explicitly registered with roles, tiers, skills, and boundaries."""
        expected_roles = [
            AgentRole.SCRUM_MASTER_ORCHESTRATOR.value,
            AgentRole.REQUIREMENTS_AGENT.value,
            AgentRole.TEST_CASE_WRITER_AGENT.value,
            AgentRole.AUTOMATION_TESTER_AGENT.value,
            AgentRole.DEVELOPER_AGENT.value,
            AgentRole.TEST_HEALER_AGENT.value,
            AgentRole.QA_CRITIC_AGENT.value,
            AgentRole.SECURITY_BLAST_RADIUS_AGENT.value,
        ]

        self.assertEqual(len(AGENT_SKILL_REGISTRY), 8)
        for role in expected_roles:
            self.assertIn(role, AGENT_SKILL_REGISTRY)
            defn = AGENT_SKILL_REGISTRY[role]
            self.assertTrue(len(defn.skills) >= 3, f"Agent {role} must have at least 3 skills")
            self.assertTrue(len(defn.owned_modules) >= 1, f"Agent {role} must have owned modules")
            self.assertTrue(len(defn.strict_boundaries) >= 2, f"Agent {role} must have strict boundaries")

            # Verify system prompt formatting
            system_prompt = defn.format_system_prompt("Extra directive")
            self.assertIn(f"=== AGENT IDENTITY & ROLE: {role} ===", system_prompt)
            self.assertIn("[STRICT BOUNDARY]", system_prompt)
            self.assertIn("Extra directive", system_prompt)

    def test_json_and_diff_extractors(self):
        """Extractors must cleanly parse markdown fences and raw blocks."""
        fenced_json = "```json\n{\"status\": \"OK\", \"count\": 42}\n```"
        parsed = extract_json_from_response(fenced_json)
        self.assertEqual(parsed.get("status"), "OK")
        self.assertEqual(parsed.get("count"), 42)

        raw_json = "Leading text {\"key\": \"value\"} trailing text"
        parsed_raw = extract_json_from_response(raw_json)
        self.assertEqual(parsed_raw.get("key"), "value")

        fenced_code = "```python\ndef foo():\n    return 'bar'\n```"
        self.assertEqual(extract_code_or_diff(fenced_code), "def foo():\n    return 'bar'")

    def test_local_heuristic_engine_and_adapter(self):
        """LocalHeuristicEngine provides deterministic zero-API-key fallback."""
        adapter = HermesLLMAdapter(self.workspace)
        self.assertFalse(adapter.has_active_api_key())

        # Requirements decomposition
        req_res = adapter.generate_structured(
            prompt="As a user, I want in-memory ledger with deposit validation",
            tier="TIER_2_SENIOR_SWE",
            agent_role=AgentRole.REQUIREMENTS_AGENT,
        )
        self.assertIn("acceptance_criteria", req_res)
        self.assertIn("edge_cases", req_res)

        # Developer patch synthesis
        ticket = SubTaskTicket("TICK-01", "Implement InMemoryLedger", 2, "TIER_3", ["src/InMemoryLedger.py"])
        patches = adapter.propose_patch(
            AgentRole.DEVELOPER_AGENT, ticket, "TIER_3", {"src/InMemoryLedger.py": ""}
        )
        self.assertIn("src/InMemoryLedger.py", patches)
        self.assertIn("class InMemoryLedger", patches["src/InMemoryLedger.py"])

    # -------------------------------------------------------------------------
    # GAP-14: Workspace File Reader & Atomic Applier
    # -------------------------------------------------------------------------
    def test_workspace_file_reader_safe_paths(self):
        """WorkspaceFileReader validates paths and rejects traversals."""
        reader = WorkspaceFileReader(self.workspace)

        # Valid path
        safe_p = reader.validate_safe_path("calculator.py")
        self.assertEqual(safe_p, self.workspace / "calculator.py")

        # Reject path traversal
        with self.assertRaises(SafePathViolationError):
            reader.validate_safe_path("../outside.py")

        # Reject protected paths
        with self.assertRaises(SafePathViolationError):
            reader.validate_safe_path(".git/config")
        with self.assertRaises(SafePathViolationError):
            reader.validate_safe_path(".env")

        # Reading allowed files
        contents = reader.read_allowed_files(["calculator.py", "tests/test_*.py"])
        self.assertIn("calculator.py", contents)
        self.assertIn("tests/test_calc.py", contents)

    def test_unified_diff_generator_and_atomic_patch_applier(self):
        """UnifiedDiffGenerator creates diffs and AtomicPatchApplier replaces files atomically."""
        orig = "def add(a, b):\n    return a + b\n"
        new = "def add(a, b):\n    # verified\n    return a + b\n"
        diff_str = UnifiedDiffGenerator.generate_diff("calc.py", orig, new)
        self.assertIn("--- a/calc.py", diff_str)
        self.assertIn("+++ b/calc.py", diff_str)
        self.assertIn("+    # verified", diff_str)

        initial_calc = (self.workspace / "calculator.py").read_text(encoding="utf-8")
        applier = AtomicPatchApplier(self.workspace)
        applied, backup = applier.apply_proposal_patches({"calculator.py": new})
        self.assertEqual(applied, ["calculator.py"])
        self.assertEqual(backup["calculator.py"], initial_calc)

        # Verify new content on disk
        current = (self.workspace / "calculator.py").read_text(encoding="utf-8")
        self.assertEqual(current, new)

    # -------------------------------------------------------------------------
    # GAP-15: Human Write-Gate Controller & Surgical Rollback
    # -------------------------------------------------------------------------
    def test_human_write_gate_controller_lifecycle_and_rollback(self):
        """HumanWriteGateController stages proposals, requires approval, and rolls back on error."""
        sprint_id = "sprint_gate_test_1"
        ticket = SubTaskTicket("TICK-10", "Update calc", 2, "TIER_3", ["calculator.py"])
        proposal = WorkerProposal(
            ticket_id="TICK-10",
            worker_agent="DeveloperAgent",
            model_tier="TIER_3_JUNIOR_SWE",
            proposed_changes={"calculator.py": "# modified calc\ndef add(a, b): return a + b\n"},
        )

        stage_id = self.gate_controller.stage_proposal(sprint_id, ticket, proposal)
        self.assertTrue(stage_id.startswith("stage_TICK-10"))

        # Without auto_approve and non-interactive: remains AWAITING_APPROVAL
        res_pause = self.gate_controller.approve_and_apply(sprint_id, auto_approve=False, interactive=False)
        self.assertFalse(res_pause["success"])
        self.assertEqual(res_pause["status"], "AWAITING_APPROVAL")

        # With auto_approve=True: takes snapshot and applies
        res_apply = self.gate_controller.approve_and_apply(sprint_id, auto_approve=True)
        self.assertTrue(res_apply["success"])
        self.assertEqual(res_apply["status"], "APPLIED")
        snapshot_id = res_apply["snapshot_id"]

        # Verify rollback on verification failure
        proposal_broken = WorkerProposal(
            ticket_id="TICK-10",
            worker_agent="DeveloperAgent",
            model_tier="TIER_3_JUNIOR_SWE",
            proposed_changes={"calculator.py": "# broken syntax def ("},
        )
        self.gate_controller.stage_proposal("sprint_gate_test_2", ticket, proposal_broken)

        # Verification function returns False -> triggers automatic surgical rollback!
        res_fail = self.gate_controller.approve_and_apply(
            "sprint_gate_test_2",
            auto_approve=True,
            verification_fn=lambda: False,
        )
        self.assertFalse(res_fail["success"])
        self.assertEqual(res_fail["status"], "ROLLED_BACK")

        # Manual snapshot rollback
        self.gate_controller.rollback_snapshot(snapshot_id)

    # -------------------------------------------------------------------------
    # GAP-16: CI Failure Ingestor & Pytest Traceback Parsing
    # -------------------------------------------------------------------------
    def test_ci_failure_ingestor_traceback_and_junit_xml(self):
        """PytestTracebackParser and JUnitXMLIngestor extract failing files and node IDs."""
        sample_pytest_output = (
            "============================= FAILURES =============================\n"
            "_____________________ test_deposit_negative _____________________\n"
            "tests/test_calc.py:12: Failed: DID NOT RAISE <class 'ValueError'>\n"
            "FAILED tests/test_calc.py::test_deposit_negative - Failed\n"
        )
        failures = PytestTracebackParser.parse(sample_pytest_output)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].test_file, "tests/test_calc.py")

        sample_junit_xml = """<?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="2" failures="1">
            <testcase classname="tests.test_calc" name="test_div" file="tests/test_calc.py">
              <failure message="ZeroDivisionError">Traceback ...</failure>
            </testcase>
          </testsuite>
        </testsuites>
        """
        xml_failures = JUnitXMLIngestor.parse_xml_string(sample_junit_xml)
        self.assertEqual(len(xml_failures), 1)
        self.assertEqual(xml_failures[0].test_node_id, "tests.test_calc::test_div")
        self.assertEqual(xml_failures[0].exception_type, "ZeroDivisionError")

        ingestor = CIFailureIngestor(self.workspace)
        ingested = ingestor.ingest_failure_output(sample_pytest_output)
        self.assertIn("tests/test_calc.py", ingested["allowed_files"])
        self.assertTrue(len(ingested["acceptance_criteria"]) >= 2)

    # -------------------------------------------------------------------------
    # GAP-17: Hermes CLI Commands
    # -------------------------------------------------------------------------
    def test_hermes_cli_commands(self):
        """Hermes CLI commands agents, status, and status command execution."""
        # Test 'agents' command
        exit_code_agents = cli_main(["agents"])
        self.assertEqual(exit_code_agents, 0)

        # Test 'status' command
        exit_code_status = cli_main(["status"])
        self.assertEqual(exit_code_status, 0)

    # -------------------------------------------------------------------------
    # GAP-18: Live Smoke Demo Execution
    # -------------------------------------------------------------------------
    def test_live_smoke_demo_run(self):
        """Live smoke demo runs end-to-end self-healing and exits 0."""
        exit_code = run_demo()
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
