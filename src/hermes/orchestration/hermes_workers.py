"""
Hermes Specialized Worker Agents: Thin Worker Contract & Architectural Invariants
Owner: ScrumMasterOrchestrator

Implements thin worker agents:
- WorkerProposal: Standardized data container returned by workers (never modifying workspace directly).
- Zero Assertion Erosion: TestCaseWriterAgent and TestHealerAgent must never reduce assertions or skip tests.
- Clean Failure Classification: AutomationTesterAgent classifies ENVIRONMENT_NOISE vs TEST_BUG vs PRODUCT_BUG vs FLAKY_TEST.
- Context-Enriched Workers: DeveloperAgent receives read-only context slice from ContextSlicer.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from hermes.ingestion.context_slicer import ContextSlicer, PytestFixtureIndexer
from hermes.core.governance.assertion_erosion_guard import ZeroAssertionErosionGuard
from hermes.core.orchestrator.scrum_hierarchy import ModelTier, SubTaskTicket
from hermes.execution.sandbox_executor import ExecutionRun, MultiRunResult, SandboxExecutor
from hermes.orchestration.sprint_state_store import AttemptRecord


@dataclass
class WorkerProposal:
    """Thin worker proposal container. Workers return this instead of modifying files directly."""
    ticket_id: str
    worker_agent: str
    model_tier: str
    proposed_changes: Dict[str, str]  # rel_path -> file content
    explanation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutomationTesterAgent:
    """TIER_3 / Worker: Executes tests in isolated ephemeral worktree and classifies failures."""

    NAME = "AutomationTesterAgent"
    DEFAULT_TIER = ModelTier.TIER_3_JUNIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None, artifacts_dir: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.executor = SandboxExecutor(workspace_path=self.workspace_path, artifacts_dir=artifacts_dir)

    def execute_and_triage(
        self,
        command: List[str],
        repeat: int = 3,
        proposed_changes: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> MultiRunResult:
        """Run multi-pass test execution and classify outcome with zero risk to workspace."""
        return self.executor.run_tests(
            command=command,
            repeat=repeat,
            timeout_seconds=timeout_seconds,
            proposed_changes=proposed_changes,
        )


class TestCaseWriterAgent:
    """TIER_2 Worker: Generates new test cases while enforcing Zero Assertion Erosion."""

    __test__ = False
    NAME = "TestCaseWriterAgent"
    DEFAULT_TIER = ModelTier.TIER_2_SENIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    def generate_tests(
        self,
        ticket: SubTaskTicket,
        test_file_path: str,
        test_code: str,
        explanation: str = "Authored new test suite",
    ) -> WorkerProposal:
        """Generate test cases, verifying that assertions are present and not eroded."""
        clean_path = test_file_path.replace("\\", "/").lstrip("/")
        if not (clean_path.startswith("tests/") or Path(clean_path).name.startswith("test_") or clean_path.endswith("_test.py") or clean_path.endswith(".ts")):
            raise ValueError(f"Scope Gate: TestCaseWriterAgent is strictly forbidden from modifying implementation files: {test_file_path}")

        # Enforce that proposed test code contains legitimate assertions
        has_python_assert = bool(re.search(r"\bassert\b", test_code))
        has_js_expect = bool(re.search(r"\bexpect\s*\(", test_code))

        if not (has_python_assert or has_js_expect):
            raise ValueError(f"Zero Assertion Erosion: Proposed test file '{test_file_path}' contains zero assertions.")

        # Check for banned test skipping
        for p in ("@pytest.mark.skip", "pytest.xfail", "test.skip", "test.fixme", "test.only"):
            if p in test_code:
                raise ValueError(f"Zero Assertion Erosion: Prohibited {p} detected.")

        if re.search(r"\bassert\s+(?:True|1|1\s*==\s*1|True\s+is\s+not\s+False)\b", test_code):
            raise ValueError("Zero Assertion Erosion: Trivial assertion (assert True / assert 1 == 1) detected.")

        return WorkerProposal(
            ticket_id=ticket.ticket_id,
            worker_agent=self.NAME,
            model_tier=ticket.assigned_tier or self.DEFAULT_TIER,
            proposed_changes={test_file_path: test_code},
            explanation=explanation,
        )


class TestHealerAgent:
    """TIER_2 Worker: Repairs failing tests while strictly forbidding assertion removal."""

    __test__ = False
    NAME = "TestHealerAgent"
    DEFAULT_TIER = ModelTier.TIER_2_SENIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    def heal_test(
        self,
        ticket: SubTaskTicket,
        test_file_path: str,
        healed_content: str,
        original_content: Optional[str] = None,
        explanation: str = "Healed failing test",
    ) -> WorkerProposal:
        """Repair test content and verify assertion count is preserved."""
        clean_path = test_file_path.replace("\\", "/").lstrip("/")
        if not (clean_path.startswith("tests/") or Path(clean_path).name.startswith("test_") or clean_path.endswith("_test.py") or clean_path.endswith(".ts")):
            raise ValueError(f"Scope Gate: TestHealerAgent is strictly forbidden from modifying implementation files: {test_file_path}")

        if original_content:
            report = ZeroAssertionErosionGuard.verify(
                rel_path=test_file_path,
                proposed_content=healed_content,
                existing_content=original_content,
                allow_test_modification=True,
            )
            if not report.valid:
                raise ValueError(f"Zero Assertion Erosion: {'; '.join(report.reasons)}")

            orig_asserts = len(re.findall(r"\bassert\b", original_content))
            new_asserts = len(re.findall(r"\bassert\b", healed_content))
            if new_asserts < orig_asserts:
                raise ValueError(
                    f"Zero Assertion Erosion: Healer cannot reduce assertions from {orig_asserts} to {new_asserts}."
                )

        for p in ("@pytest.mark.skip", "pytest.xfail", "test.skip", "test.fixme", "test.only"):
            if p in healed_content:
                raise ValueError(f"Zero Assertion Erosion: Healer cannot inject skip/xfail decorators: {p}")

        if re.search(r"\bassert\s+(?:True|1|1\s*==\s*1|True\s+is\s+not\s+False)\b", healed_content):
            raise ValueError("Zero Assertion Erosion: Trivial assertion (assert True) detected.")

        return WorkerProposal(
            ticket_id=ticket.ticket_id,
            worker_agent=self.NAME,
            model_tier=ticket.assigned_tier or self.DEFAULT_TIER,
            proposed_changes={test_file_path: healed_content},
            explanation=explanation,
        )


class DeveloperAgent:
    """TIER_2 / TIER_3 Worker: Implements application/feature code using read-only context stubs."""

    NAME = "DeveloperAgent"
    DEFAULT_TIER = ModelTier.TIER_2_SENIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    def implement_solution(
        self,
        ticket: SubTaskTicket,
        proposed_changes: Dict[str, str],
        explanation: str = "Implemented ticket requirements",
    ) -> WorkerProposal:
        """Submit proposed changes without modifying workspace files."""
        # Enforce scope boundary
        allowed_set = {f.replace("\\", "/").lstrip("/") for f in ticket.allowed_files}
        for f in proposed_changes.keys():
            clean_f = f.replace("\\", "/").lstrip("/")
            if clean_f not in allowed_set:
                raise ValueError(f"Scope Gate: DeveloperAgent modified unauthorized file: {clean_f}. Allowed: {allowed_set}")
            if clean_f.startswith("tests/") or Path(clean_f).name.startswith("test_") or clean_f.endswith("_test.py"):
                raise ValueError(f"Scope Gate: DeveloperAgent is strictly forbidden from modifying test files: {clean_f}")

        return WorkerProposal(
            ticket_id=ticket.ticket_id,
            worker_agent=self.NAME,
            model_tier=ticket.assigned_tier or self.DEFAULT_TIER,
            proposed_changes=proposed_changes,
            explanation=explanation,
        )


class RequirementsAgent:
    """TIER_2 Worker: Generates context slices and indexes test fixtures for workers."""

    NAME = "RequirementsAgent"
    DEFAULT_TIER = ModelTier.TIER_2_SENIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    def prepare_ticket_context(self, ticket: SubTaskTicket, max_tokens: int = 2000) -> Dict[str, Any]:
        """Produce read-only interface slice and fixture catalogue without expanding ticket write scope."""
        return ContextSlicer.build_sliced_context(
            workspace_root=self.workspace_path,
            target_files=ticket.allowed_files,
            max_context_tokens=max_tokens,
        )


# Export FlakeQuarantineAgent for worker hierarchy
from hermes.core.quarantine.flake_quarantine_agent import FlakeQuarantineAgent
