"""
Comprehensive Unit & Integration Test Suite for Hermes Multi-Agent Orchestrator (GAP-06 through GAP-12).
Tests all 7 production modules, architectural invariants, and end-to-end pipeline execution.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from ast_patch_guard import ASTPatchGuard
from context_slicer import ContextSlicer, PytestFixtureIndexer
from core.orchestrator.scrum_hierarchy import ModelTier, SubTaskTicket
from core.time_machine.engine import TimeMachineEngine
from hermes_workers import (
    AutomationTesterAgent,
    DeveloperAgent,
    TestCaseWriterAgent,
    TestHealerAgent,
    WorkerProposal,
)
from qa_critic_reviewer import CriterionVerdict, EscalationPromptBuilder, QACriticAgent, QACriticReview
from sandbox_executor import ExecutionRun, MultiRunResult, SandboxExecutor
from scrum_master_orchestrator import HumanWriteGate, ScrumMasterOrchestrator
from security_blast_radius import SecurityAuditReport, SecurityBlastRadiusAgent, SecurityFinding
from sprint_dag_scheduler import (
    DependencyCycleError,
    PatchConflictError,
    SprintDAGScheduler,
    StagedPatchComposer,
)
from sprint_state_store import AttemptRecord, SprintStateStore
from ticket_router import TicketRouter
from ts_playwright_ast_guard import PlaywrightASTGuard, analyze_ts_playwright_changes


class TestHermesFullPipeline(unittest.TestCase):
    """Test suite verifying all Hermes multi-agent orchestrator modules and invariants."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="hermes_full_test_")).resolve()
        self.workspace = self.test_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Baseline workspace files
        (self.workspace / "calculator.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n\n"
            "def divide(a: int, b: int) -> float:\n    if b == 0:\n        raise ZeroDivisionError('Division by zero')\n    return a / b\n",
            encoding="utf-8",
        )
        (self.workspace / "auth.py").write_text(
            "import hmac\n\ndef check_token(provided: str, expected: str) -> bool:\n    return hmac.compare_digest(provided, expected)\n",
            encoding="utf-8",
        )

        tests_dir = self.workspace / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "conftest.py").write_text(
            "import pytest\n\n@pytest.fixture(scope='function')\ndef sample_numbers() -> tuple[int, int]:\n    '''Provides test numbers.'''\n    return (10, 5)\n",
            encoding="utf-8",
        )
        (tests_dir / "test_calc.py").write_text(
            "from calculator import add, divide\nimport pytest\n\ndef test_add(sample_numbers):\n    a, b = sample_numbers\n    assert add(a, b) == 15\n\ndef test_divide():\n    assert divide(10, 2) == 5.0\n    with pytest.raises(ZeroDivisionError):\n        divide(10, 0)\n",
            encoding="utf-8",
        )

        self.tm_engine = TimeMachineEngine(self.workspace)
        self.store_db = self.test_dir / "test_sprint.db"
        self.store = SprintStateStore(db_path=self.store_db)
        self.orchestrator = ScrumMasterOrchestrator(
            workspace_path=self.workspace,
            tm_engine=self.tm_engine,
            store=self.store,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Invariant 1: Thin Worker Contract
    # -------------------------------------------------------------------------
    def test_thin_worker_contract_never_mutates_workspace_directly(self):
        """Workers must return a WorkerProposal and never modify workspace files during execution."""
        original_calc = (self.workspace / "calculator.py").read_text(encoding="utf-8")

        ticket = SubTaskTicket(
            ticket_id="HERMES-001",
            title="Refactor add",
            complexity=2,
            assigned_tier=ModelTier.TIER_3_JUNIOR_SWE.value,
            allowed_files=["calculator.py"],
        )

        dev_agent = DeveloperAgent(self.workspace)
        proposal = dev_agent.implement_solution(
            ticket=ticket,
            proposed_changes={"calculator.py": "# modified code\ndef add(a, b): return a + b + 1"},
        )

        self.assertIsInstance(proposal, WorkerProposal)
        self.assertEqual(proposal.ticket_id, "HERMES-001")
        self.assertIn("calculator.py", proposal.proposed_changes)

        # Invariant check: Workspace file must be completely untouched!
        current_calc = (self.workspace / "calculator.py").read_text(encoding="utf-8")
        self.assertEqual(current_calc, original_calc)

    # -------------------------------------------------------------------------
    # Invariant 2: Zero Assertion Erosion
    # -------------------------------------------------------------------------
    def test_zero_assertion_erosion_rejects_net_reduction_and_skips(self):
        """TestCaseWriterAgent & TestHealerAgent must reject removing asserts or adding skips."""
        writer = TestCaseWriterAgent(self.workspace)
        ticket = SubTaskTicket(
            ticket_id="HERMES-002",
            title="Write tests",
            complexity=2,
            assigned_tier=ModelTier.TIER_2_SENIOR_SWE.value,
            allowed_files=["tests/test_new.py"],
        )

        # 1. Rejecting test without assertions
        with self.assertRaises(ValueError) as ctx:
            writer.generate_tests(ticket, "tests/test_new.py", "def test_empty(): pass")
        self.assertIn("Zero Assertion Erosion", str(ctx.exception))

        # 2. Rejecting test with skip decorator
        with self.assertRaises(ValueError) as ctx:
            writer.generate_tests(
                ticket,
                "tests/test_new.py",
                "@pytest.mark.skip(reason='broken')\ndef test_skipped(): assert True",
            )
        self.assertIn("Zero Assertion Erosion", str(ctx.exception))

        # 3. TestHealerAgent rejects reducing assertions
        healer = TestHealerAgent(self.workspace)
        orig_code = "def test_two():\n    assert 1 == 1\n    assert 2 == 2\n"
        reduced_code = "def test_two():\n    assert 1 == 1\n"
        with self.assertRaises(ValueError) as ctx:
            healer.heal_test(ticket, "tests/test_calc.py", reduced_code, original_content=orig_code)
        self.assertIn("cannot reduce assertions", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Invariant 3: Clean Failure Classification (GAP-06)
    # -------------------------------------------------------------------------
    def test_clean_failure_classification_categories(self):
        """AutomationTesterAgent must distinguish FLAKY_TEST, ENVIRONMENT_NOISE, TEST_BUG, and PRODUCT_BUG."""
        executor = SandboxExecutor(self.workspace)

        # 1. All passed
        runs_pass = [
            ExecutionRun(1, ["pytest"], 0, True, "passed", "", 0.1),
            ExecutionRun(2, ["pytest"], 0, True, "passed", "", 0.1),
            ExecutionRun(3, ["pytest"], 0, True, "passed", "", 0.1),
        ]
        self.assertEqual(executor.classify_failure(runs_pass), "PASSED")

        # 2. Intermittent (Flaky)
        runs_flaky = [
            ExecutionRun(1, ["pytest"], 0, True, "passed", "", 0.1),
            ExecutionRun(2, ["pytest"], 1, False, "AssertionError", "failed", 0.1),
            ExecutionRun(3, ["pytest"], 0, True, "passed", "", 0.1),
        ]
        self.assertEqual(executor.classify_failure(runs_flaky), "FLAKY_TEST")

        # 3. Environment Noise
        runs_env = [
            ExecutionRun(1, ["pytest"], 1, False, "", "ConnectionRefusedError: [Errno 111] Connection refused", 0.1),
            ExecutionRun(2, ["pytest"], 1, False, "", "ConnectionRefusedError: [Errno 111] Connection refused", 0.1),
            ExecutionRun(3, ["pytest"], 1, False, "", "ConnectionRefusedError: [Errno 111] Connection refused", 0.1),
        ]
        self.assertEqual(executor.classify_failure(runs_env), "ENVIRONMENT_NOISE")

        # 4. Test Bug (AssertionError)
        runs_test_bug = [
            ExecutionRun(1, ["pytest"], 1, False, "test_calc.py:10: AssertionError: assert 5 == 6", "", 0.1),
            ExecutionRun(2, ["pytest"], 1, False, "test_calc.py:10: AssertionError: assert 5 == 6", "", 0.1),
            ExecutionRun(3, ["pytest"], 1, False, "test_calc.py:10: AssertionError: assert 5 == 6", "", 0.1),
        ]
        self.assertEqual(executor.classify_failure(runs_test_bug), "TEST_BUG")

        # 5. Product Bug (unhandled exception in core/)
        runs_prod_bug = [
            ExecutionRun(1, ["pytest"], 1, False, "", "File \"core/calc.py\", line 4: ZeroDivisionError", 0.1),
            ExecutionRun(2, ["pytest"], 1, False, "", "File \"core/calc.py\", line 4: ZeroDivisionError", 0.1),
            ExecutionRun(3, ["pytest"], 1, False, "", "File \"core/calc.py\", line 4: ZeroDivisionError", 0.1),
        ]
        self.assertEqual(executor.classify_failure(runs_prod_bug), "PRODUCT_BUG")

    # -------------------------------------------------------------------------
    # GAP-06: SandboxExecutor Ephemeral Isolation & Timeouts
    # -------------------------------------------------------------------------
    def test_sandbox_executor_isolation_and_timeout(self):
        """SandboxExecutor runs patches in isolation and cleanly terminates timeouts."""
        executor = SandboxExecutor(self.workspace, default_timeout_seconds=2)

        # Unapproved patch applied only inside sandbox
        unapproved_patch = {"calculator.py": "# unapproved patch\ndef add(a, b): return 999\n"}
        with executor.ephemeral_sandbox(proposed_changes=unapproved_patch) as sandbox_dir:
            self.assertTrue(sandbox_dir.exists())
            content = (sandbox_dir / "calculator.py").read_text(encoding="utf-8")
            self.assertIn("999", content)
            # Live workspace must remain unaffected (AC-1)
            live_content = (self.workspace / "calculator.py").read_text(encoding="utf-8")
            self.assertNotIn("999", live_content)

        # Sandbox is cleaned up automatically (AC-3)
        self.assertFalse(sandbox_dir.exists())

        # Test timeout handling (AC-2)
        hang_cmd = ["python", "-c", "import time; time.sleep(10)"]
        run_res = executor.run_single_test(hang_cmd, cwd=self.workspace, timeout_seconds=1)
        self.assertTrue(run_res.timed_out)
        self.assertEqual(run_res.exit_code, 124)
        self.assertIn("timed out", run_res.stderr)

    # -------------------------------------------------------------------------
    # GAP-07: TypeScript / Playwright AST Guard
    # -------------------------------------------------------------------------
    def test_ts_playwright_ast_guard_blocks_tampering_and_erosion(self):
        """PlaywrightASTGuard must reject test.skip, waitForTimeout, and expect reductions."""
        existing_ts = """
        import { test, expect } from '@playwright/test';
        test('user login', async ({ page }) => {
            await page.goto('/login');
            await expect(page.locator('#submit')).toBeVisible();
            await expect(page.locator('.welcome')).toHaveText('Welcome');
        });
        """

        # 1. AC-1: Reject test.skip
        skip_ts = existing_ts.replace("test('user login'", "test.skip('user login'")
        res = PlaywrightASTGuard.verify_spec_content("tests/login.spec.ts", skip_ts, existing_content=existing_ts)
        self.assertFalse(res.valid)
        self.assertTrue(res.tampering_detected)
        self.assertTrue(any("test.skip" in r for r in res.reasons))

        # 2. AC-1: Reject tautological expect(true).toBe(true)
        tauto_ts = existing_ts + "\nawait expect(true).toBe(true);"
        res_tauto = PlaywrightASTGuard.verify_spec_content("tests/login.spec.ts", tauto_ts, existing_content=existing_ts)
        self.assertFalse(res_tauto.valid)
        self.assertTrue(any("Tautological" in r for r in res_tauto.reasons))

        # 3. AC-2: Reject hardcoded page.waitForTimeout(>0)
        timeout_ts = existing_ts + "\nawait page.waitForTimeout(3000);"
        res_timeout = PlaywrightASTGuard.verify_spec_content("tests/login.spec.ts", timeout_ts, existing_content=existing_ts)
        self.assertFalse(res_timeout.valid)
        self.assertTrue(any("waitForTimeout" in r for r in res_timeout.reasons))

        # 4. AC-3: Assertion erosion (reducing expect count from 2 to 1)
        eroded_ts = """
        import { test, expect } from '@playwright/test';
        test('user login', async ({ page }) => {
            await page.goto('/login');
            await expect(page.locator('#submit')).toBeVisible();
        });
        """
        res_erode = PlaywrightASTGuard.verify_spec_content("tests/login.spec.ts", eroded_ts, existing_content=existing_ts)
        self.assertFalse(res_erode.valid)
        self.assertTrue(any("Zero Assertion Erosion" in r for r in res_erode.reasons))

    # -------------------------------------------------------------------------
    # GAP-08: Cross-Ticket Dependency DAG & Staged Patch Composer
    # -------------------------------------------------------------------------
    def test_sprint_dag_scheduler_and_staged_composer(self):
        """Topological ordering, cycle detection, and multi-ticket patch composition."""
        t1 = SubTaskTicket("HERMES-101", "Write Test", 2, "TIER_3_JUNIOR_SWE", ["tests/test_feature.py"])
        t2 = SubTaskTicket("HERMES-102", "Implement Feature", 3, "TIER_2_SENIOR_SWE", ["src/feature.py"])
        t3 = SubTaskTicket("HERMES-103", "Integration", 4, "TIER_2_SENIOR_SWE", ["src/feature.py", "tests/test_feature.py"])

        setattr(t2, "depends_on", ["HERMES-101"])
        setattr(t3, "depends_on", ["HERMES-102"])

        # AC-1: Topological sort
        ordered = SprintDAGScheduler.topological_sort([t3, t1, t2])
        self.assertEqual([t.ticket_id for t in ordered], ["HERMES-101", "HERMES-102", "HERMES-103"])

        # AC-2: Cyclic dependency rejection
        setattr(t1, "depends_on", ["HERMES-103"])
        with self.assertRaises(DependencyCycleError):
            SprintDAGScheduler.topological_sort([t1, t2, t3])

        # AC-3: Failed upstream halts downstream
        setattr(t1, "depends_on", [])
        blocked, reason = SprintDAGScheduler.is_ticket_blocked(t2, completed_ids=set(), failed_ids={"HERMES-101"})
        self.assertTrue(blocked)
        self.assertIn("Blocked by failed upstream", reason)

        # StagedPatchComposer combining HERMES-101 and HERMES-102
        t1.proposed_changes = {"tests/test_feature.py": "def test_feat(): assert True"}
        t2.proposed_changes = {"src/feature.py": "def feat(): return 1"}
        composed = StagedPatchComposer.compose_patches([t1, t2])
        self.assertIn("tests/test_feature.py", composed)
        self.assertIn("src/feature.py", composed)

        # Conflict detection
        t2_conflict = SubTaskTicket("HERMES-102C", "Conflict", 3, "TIER_2", ["tests/test_feature.py"])
        t2_conflict.proposed_changes = {"tests/test_feature.py": "def test_other(): pass"}
        conflicts = StagedPatchComposer.detect_conflicts(t1, t2_conflict)
        self.assertTrue(len(conflicts) > 0)

    # -------------------------------------------------------------------------
    # GAP-09: QACriticAgent Rubric & Escalation Memory
    # -------------------------------------------------------------------------
    def test_qa_critic_rubric_and_escalation_prompt_builder(self):
        """QACriticAgent scores ACs individually and EscalationPromptBuilder injects feedback."""
        ticket = SubTaskTicket(
            ticket_id="HERMES-201",
            title="Add divide with ZeroDivisionError",
            complexity=2,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["calculator.py", "tests/test_calc.py"],
            acceptance_criteria=[
                "Implement divide function in calculator.py",
                "Ensure ZeroDivisionError raised on zero divisor",
            ],
        )

        # 1. AC-1 & AC-3: Proposal addressing only part of the AC
        partial_proposal = {
            "calculator.py": "def divide(a, b):\n    return a / b\n"
        }
        review: QACriticReview = QACriticAgent.review_worker_output(ticket, partial_proposal)
        self.assertFalse(review.approved)
        # Check individual verdicts
        self.assertTrue(len(review.verdicts) >= 2)
        fail_verdicts = [v for v in review.verdicts if v.status == "FAIL"]
        self.assertTrue(len(fail_verdicts) > 0)

        # 2. Complete proposal addressing all ACs with test assertion
        full_proposal = {
            "calculator.py": "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('zero divisor')\n    return a / b\n",
            "tests/test_calc.py": "import pytest\nfrom calculator import divide\ndef test_div():\n    assert divide(10, 2) == 5\n    with pytest.raises(ZeroDivisionError):\n        divide(10, 0)\n",
        }
        good_review = QACriticAgent.review_worker_output(ticket, full_proposal)
        self.assertTrue(good_review.approved)

        # 3. AC-2: EscalationPromptBuilder carries rejection memory to higher tier
        att = AttemptRecord(
            tier="TIER_3_JUNIOR_SWE",
            agent_name="JuniorWorker",
            model_name="gemini-flash",
            status="REJECTED",
            rejection_reason="Unaddressed acceptance criterion: 'Ensure ZeroDivisionError raised'",
        )
        ticket.attempt_history.append(att.to_dict())

        prompt = EscalationPromptBuilder.build_escalation_prompt(ticket, target_tier="TIER_2_SENIOR_SWE", qa_review=review)
        self.assertIn("ESCALATED TASK BRIEF FOR TIER_2_SENIOR_SWE", prompt)
        self.assertIn("Prior Failed Attempts", prompt)
        self.assertIn("Ensure ZeroDivisionError raised", prompt)

    # -------------------------------------------------------------------------
    # GAP-10: Security Blast Radius Auditor
    # -------------------------------------------------------------------------
    def test_security_blast_radius_audits_timing_attacks_and_sqli(self):
        """SecurityBlastRadiusAgent detects timing attacks, SQL injection, and shell=True."""
        # 1. AC-1: Timing attack comparison
        insecure_timing_code = {
            "auth.py": "def verify(user_token, secret_token):\n    return user_token == secret_token\n"
        }
        report_timing = SecurityBlastRadiusAgent.audit_proposal(insecure_timing_code)
        self.assertFalse(report_timing.passed)
        self.assertTrue(any(f.rule_id == "SEC-TIMING-001" for f in report_timing.findings))

        # 2. AC-1: SQL injection f-string
        sqli_code = {
            "db.py": "def get_user(cursor, user_id):\n    cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')\n"
        }
        report_sql = SecurityBlastRadiusAgent.audit_proposal(sqli_code)
        self.assertFalse(report_sql.passed)
        self.assertTrue(any(f.rule_id == "SEC-SQLI-001" for f in report_sql.findings))

        # 3. AC-1: subprocess shell=True
        shell_code = {
            "cmd.py": "import subprocess\ndef run_cmd(user_cmd):\n    subprocess.run(user_cmd, shell=True)\n"
        }
        report_shell = SecurityBlastRadiusAgent.audit_proposal(shell_code)
        self.assertFalse(report_shell.passed)
        self.assertTrue(any(f.rule_id == "SEC-SUBPROCESS-001" for f in report_shell.findings))

        # 4. AC-3: Security findings appended directly to ticket.attempt_history
        ticket = SubTaskTicket("HERMES-SEC", "Insecure Feature", 3, "TIER_2", ["cmd.py"])
        SecurityBlastRadiusAgent.audit_proposal(shell_code, ticket=ticket)
        self.assertEqual(len(ticket.attempt_history), 1)
        self.assertEqual(ticket.attempt_history[0]["status"], "REJECTED")

    # -------------------------------------------------------------------------
    # GAP-11: Context Slicer & Pytest Fixture Indexer
    # -------------------------------------------------------------------------
    def test_context_slicer_and_fixture_indexer(self):
        """PytestFixtureIndexer discovers conftest fixtures and ContextSlicer extracts public stubs."""
        # 1. AC-1: Fixture Indexer
        fixtures = PytestFixtureIndexer.scan_fixtures(self.workspace)
        self.assertTrue(len(fixtures) >= 1)
        fix_names = [f.name for f in fixtures]
        self.assertIn("sample_numbers", fix_names)
        self.assertEqual(fixtures[0].scope, "function")

        # 2. AC-2 & AC-3: ContextSlicer produces public skeleton under budget
        slice_res = ContextSlicer.build_sliced_context(
            workspace_root=self.workspace,
            target_files=["tests/test_calc.py"],
            max_context_tokens=1000,
        )
        context_str = slice_res["context_str"]
        self.assertIn("@pytest.fixture", context_str)
        self.assertIn("def add", context_str)
        # Verify function body is omitted in read-only slice
        self.assertNotIn("return a + b", context_str)
        self.assertLessEqual(slice_res["estimated_tokens"], 1000)

    # -------------------------------------------------------------------------
    # GAP-12: Persistent Sprint Store & Resumable Human Write-Gate
    # -------------------------------------------------------------------------
    def test_sprint_state_store_and_write_gate(self):
        """SprintStateStore persists attempts and HumanWriteGate manages pre-apply snapshots."""
        sprint_id = "sprint_test_123"
        t1 = SubTaskTicket(
            ticket_id="TICK-101",
            title="Fix calc",
            complexity=2,
            assigned_tier="TIER_3_JUNIOR_SWE",
            allowed_files=["calculator.py"],
            status="AWAITING_WRITE_GATE",
        )

        # 1. AC-1: Durable flush of attempt record before escalation
        att = AttemptRecord("TIER_3_JUNIOR_SWE", "JuniorWorker", "model-a", "REJECTED", "SyntaxError")
        self.store.record_attempt("TICK-101", sprint_id, att)
        self.store.save_sprint(sprint_id, "AWAITING_WRITE_GATE", {}, [t1])

        # 2. AC-2: Resuming paused sprint from disk
        paused = self.store.list_paused_sprints("AWAITING_WRITE_GATE")
        self.assertEqual(len(paused), 1)
        loaded = self.store.resume_sprint(sprint_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["tickets"][0]["attempt_history"][0]["rejection_reason"], "SyntaxError")

        # 3. Invariant 5: HumanWriteGate takes safety snapshot and applies verified files
        gate = HumanWriteGate(self.workspace, self.tm_engine, self.store)
        proposal = WorkerProposal(
            ticket_id="TICK-101",
            worker_agent="SeniorWorker",
            model_tier="TIER_2_SENIOR_SWE",
            proposed_changes={"calculator.py": "# newly verified content\ndef add(a, b): return a + b\n"},
        )
        stage_id = gate.stage_proposal(sprint_id, t1, proposal)
        apply_res = gate.approve_and_apply(stage_id)

        self.assertTrue(apply_res["success"])
        self.assertIn("snapshot_id", apply_res)
        self.assertEqual(apply_res["status"], "APPLIED")

        # Verify file written to live workspace
        applied_content = (self.workspace / "calculator.py").read_text(encoding="utf-8")
        self.assertIn("# newly verified content", applied_content)

    # -------------------------------------------------------------------------
    # End-to-End Multi-Tier Escalation Pipeline Test
    # -------------------------------------------------------------------------
    def test_end_to_end_scrum_pipeline_with_auto_escalation(self):
        """End-to-end integration: TIER_3 worker scope violation escalates to TIER_2 which succeeds."""
        ticket = SubTaskTicket(
            ticket_id="E2E-001",
            title="Add multiply to calculator",
            complexity=2,
            assigned_tier=ModelTier.TIER_3_JUNIOR_SWE.value,
            allowed_files=["calculator.py", "tests/test_calc.py"],
            acceptance_criteria=["Implement multiply(a, b) -> int", "Add test_multiply assertion"],
        )

        def mock_worker(t: SubTaskTicket, tier: str, escalation_prompt: str | None) -> WorkerProposal:
            if tier == ModelTier.TIER_3_JUNIOR_SWE.value:
                # Junior worker causes scope violation (touches unallowed file)
                return WorkerProposal(
                    ticket_id=t.ticket_id,
                    worker_agent="JuniorWorker",
                    model_tier=tier,
                    proposed_changes={"unauthorized.py": "x = 1"},
                )
            else:
                # Senior worker fixes the issue cleanly within allowed_files
                return WorkerProposal(
                    ticket_id=t.ticket_id,
                    worker_agent="SeniorWorker",
                    model_tier=tier,
                    proposed_changes={
                        "calculator.py": "def multiply(a: int, b: int) -> int:\n    return a * b\n",
                        "tests/test_calc.py": "from calculator import multiply\ndef test_multiply():\n    assert multiply(3, 4) == 12\n",
                    },
                )

        final_ticket, approved_proposal = self.orchestrator.execute_ticket_with_escalation(
            sprint_id="sprint_e2e_test",
            ticket=ticket,
            worker_fn=mock_worker,
            allow_test_modification=True,
        )

        self.assertEqual(final_ticket.status, "DONE")
        self.assertIsNotNone(approved_proposal)
        # Verify escalation occurred: TIER_3 was rejected, escalated to TIER_2
        self.assertEqual(len(final_ticket.attempt_history), 2)
        self.assertEqual(final_ticket.attempt_history[0]["status"], "REJECTED")
        self.assertIn("Scope violation", final_ticket.attempt_history[0]["rejection_reason"])
        self.assertEqual(final_ticket.attempt_history[1]["status"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
