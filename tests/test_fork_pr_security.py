"""
Untrusted Fork PR Security Guardrail Tests
Owner: SecurityGateAgent & WriteGateController
Phase: Phase 2 (v1.1.0) Deliverable 4
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hermes.execution.sandbox_executor import SandboxExecutor
from hermes.guards.write_gate_controller import HumanWriteGateController
from hermes.orchestration.hermes_workers import WorkerProposal


class TestForkPRSecurity(unittest.TestCase):
    """Verifies write blocking and privileged subprocess command suppression on fork PRs."""

    def test_fork_pr_blocks_write_gate_controller(self):
        """Fork PRs must never execute direct workspace writes, enforcing SHADOW_SUGGEST."""
        with tempfile.TemporaryDirectory() as td:
            gate = HumanWriteGateController(workspace_path=td, is_fork_pr=True)
            # Stage proposal
            proposal = WorkerProposal(
                ticket_id="ticket_fork_1",
                worker_agent="DeveloperAgent",
                model_tier="TIER_3_JUNIOR_SWE",
                proposed_changes={"src/app.py": "x = 42\n"},
            )
            sprint_id = "sprint_fork_test"
            gate.stage_proposal(sprint_id=sprint_id, ticket=MagicMock(ticket_id="ticket_fork_1"), proposal=proposal)

            # Attempt approve_and_apply
            res = gate.approve_and_apply(sprint_id=sprint_id, auto_approve=True)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FORK_PR_WRITE_BLOCKED")
            self.assertEqual(res["mode"], "SHADOW_SUGGEST")

    def test_fork_pr_env_var_blocks_write_gate(self):
        """Setting HERMES_IS_FORK_PR=true in environment triggers fork write blocking."""
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"HERMES_IS_FORK_PR": "true"}):
                gate = HumanWriteGateController(workspace_path=td)
                self.assertTrue(gate.is_fork_pr)

    def test_fork_pr_blocks_privileged_subprocess_execution(self):
        """Privileged runner (workflow_run) must block arbitrary command execution of untrusted fork code."""
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxExecutor(workspace_path=td, is_untrusted_fork=True)
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run"}):
                res = executor.execute_command("pytest tests/")
                self.assertEqual(res.fail_count, 1)
                self.assertEqual(res.runs[0].exit_code, 1)
                self.assertIn("FORK_PR_SUBPROCESS_BLOCKED", res.runs[0].stderr)

    def test_fork_pr_privileged_flag_blocks_execution(self):
        """HERMES_PRIVILEGED_RUNNER=true triggers execution blocking for untrusted fork."""
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxExecutor(workspace_path=td, is_untrusted_fork=True)
            with patch.dict(os.environ, {"HERMES_PRIVILEGED_RUNNER": "true"}):
                res = executor.execute_command(["python", "-c", "print('hello')"])
                self.assertEqual(res.fail_count, 1)
                self.assertIn("FORK_PR_SUBPROCESS_BLOCKED", res.runs[0].stderr)

    def test_trusted_non_fork_allows_execution(self):
        """Non-fork PR executes command normally."""
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxExecutor(workspace_path=td, is_untrusted_fork=False)
            res = executor.execute_command(["python", "-c", "print('trusted')"])
            self.assertEqual(res.pass_count, 1)
            self.assertIn("trusted", res.runs[0].stdout)

    def test_fork_pr_env_wired_in_action_and_workflow_yaml(self):
        """action.yml and hermes-decoupled.example.yml must wire HERMES_IS_FORK_PR."""
        repo_root = Path(__file__).resolve().parent.parent
        action_yml = repo_root / "action.yml"
        decoupled_yml = repo_root / ".github" / "workflows" / "hermes-decoupled.example.yml"

        self.assertTrue(action_yml.is_file())
        self.assertTrue(decoupled_yml.is_file())

        action_content = action_yml.read_text(encoding="utf-8")
        decoupled_content = decoupled_yml.read_text(encoding="utf-8")

        self.assertIn("HERMES_IS_FORK_PR", action_content)
        self.assertIn("github.event.pull_request.head.repo.full_name != github.repository", action_content)

        self.assertIn("HERMES_IS_FORK_PR", decoupled_content)
        self.assertIn("head_repository.full_name", decoupled_content)
