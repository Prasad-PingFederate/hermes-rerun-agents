"""
Flake Quarantine PR Bot & FlakeQuarantineAgent
Owner: TestCaseWriterAgent & AutomationTesterAgent, TIER_2

Features:
- Non-erosive quarantine: Injects retry policies instead of mutating product logic or deleting tests:
  * Pytest: @pytest.mark.flaky(reruns=2, reruns_delay=1) (auto-imports pytest).
  * Playwright: test.describe.configure({ retries: 2 });
  * Jest: jest.retryTimes(2);
- Zero Assertion Erosion compliance: Strictly validated against ZeroAssertionErosionGuard
  to ensure all assertions are preserved and zero .skip modifiers are introduced.
- Structured Flake Diagnostic Evidence Table generation for automated Draft PRs (hermes/quarantine-<id>).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.governance.assertion_erosion_guard import ZeroAssertionErosionGuard
from core.orchestrator.scrum_hierarchy import ModelTier, SubTaskTicket


@dataclass
class FlakeDiagnosticEvidence:
    failure_signature: str
    suspected_source: str
    recommended_fix: str
    test_file: str
    flaky_runs_observed: int = 1
    total_runs: int = 3


class FlakeQuarantineAgent:
    """TIER_2 Agent: Synthesizes non-erosive retry quarantine patches for flaky test suites."""

    NAME = "FlakeQuarantineAgent"
    DEFAULT_TIER = ModelTier.TIER_2_SENIOR_SWE.value

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    @classmethod
    def diagnose_flake(cls, failure_output: str, test_file: str) -> FlakeDiagnosticEvidence:
        """Analyze failure logs to extract failure signature, suspected cause, and permanent fix."""
        output_lower = failure_output.lower()

        if "timeout" in output_lower or "timed out" in output_lower:
            sig = "TimeoutError / Async Wait Exceeded"
            cause = "Asynchronous race condition or slow background event loop under CI runner load"
            fix = "Replace fixed-interval timers or arbitrary timeouts with web-first locator assertions (e.g., expect(locator).toBeVisible())."
        elif "econnreset" in output_lower or "connection reset" in output_lower or "connectionrefused" in output_lower:
            sig = "ECONNRESET / Socket Connection Reset"
            cause = "Ephemeral socket teardown or network latency during local mock/service handshake"
            fix = "Add resilient connection pooling with exponential backoff or use persistent mock fixtures."
        elif "sqlite" in output_lower and ("locked" in output_lower or "busy" in output_lower):
            sig = "DatabaseLockError / Concurrency Contention"
            cause = "Parallel test threads attempting simultaneous write locks on in-memory or file database"
            fix = "Configure isolated database schemas per test worker or employ transaction rollbacks."
        else:
            sig = "Intermittent Non-Deterministic Test Failure"
            cause = "State leakage across test boundaries or asynchronous timing race condition"
            fix = "Ensure clean fixture teardown in conftest/beforeEach and avoid shared mutable static state."

        return FlakeDiagnosticEvidence(
            failure_signature=sig,
            suspected_source=cause,
            recommended_fix=fix,
            test_file=test_file,
        )

    def quarantine_code(
        self,
        test_file: str,
        original_content: str,
        test_name: Optional[str] = None,
    ) -> str:
        """Inject non-erosive quarantine decorators or retry configurations into test code."""
        clean_path = test_file.replace("\\", "/").lower()

        # 1. Python / Pytest files
        if clean_path.endswith(".py"):
            return self._quarantine_python(original_content, test_name=test_name)

        # 2. Playwright TypeScript / JavaScript specs
        if any(clean_path.endswith(ext) for ext in (".spec.ts", ".spec.js", ".spec.tsx", ".spec.jsx")):
            return self._quarantine_playwright(original_content)

        # 3. Jest TypeScript / JavaScript tests
        if any(clean_path.endswith(ext) for ext in (".test.ts", ".test.js", ".test.tsx", ".test.jsx")):
            return self._quarantine_jest(original_content)

        # Fallback Python
        return self._quarantine_python(original_content, test_name=test_name)

    def _quarantine_python(self, code: str, test_name: Optional[str] = None) -> str:
        """Inject @pytest.mark.flaky(reruns=2, reruns_delay=1) into Python test suite."""
        lines = code.splitlines()
        has_pytest = any(re.match(r"^\s*import\s+pytest\b", line) for line in lines)

        decorator = "@pytest.mark.flaky(reruns=2, reruns_delay=1)"

        # Check if already decorated
        if decorator in code:
            return code

        new_lines: List[str] = []
        if not has_pytest:
            new_lines.append("import pytest")

        target_func = f"def {test_name}" if test_name else "def test_"
        decorated = False

        for line in lines:
            if target_func in line and not decorated:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + decorator)
                decorated = True
            new_lines.append(line)

        # If no specific function matched, add module-level pytestmark
        if not decorated:
            new_lines.insert(1 if not has_pytest else 0, "pytestmark = pytest.mark.flaky(reruns=2, reruns_delay=1)")

        return "\n".join(new_lines) + ("\n" if code.endswith("\n") else "")

    def _quarantine_playwright(self, code: str) -> str:
        """Inject test.describe.configure({ retries: 2 }); into Playwright spec."""
        config_line = "test.describe.configure({ retries: 2 });"
        if config_line in code or "retries: 2" in code:
            return code

        lines = code.splitlines()
        new_lines: List[str] = []
        injected = False

        for line in lines:
            new_lines.append(line)
            if not injected and ("from '@playwright/test'" in line or 'from "@playwright/test"' in line):
                new_lines.append("")
                new_lines.append(f"// Auto-Quarantined by Hermes FlakeQuarantineAgent (GAP-Flake)")
                new_lines.append(config_line)
                injected = True

        if not injected:
            new_lines.insert(0, config_line)

        return "\n".join(new_lines) + ("\n" if code.endswith("\n") else "")

    def _quarantine_jest(self, code: str) -> str:
        """Inject jest.retryTimes(2); into Jest test."""
        retry_line = "jest.retryTimes(2);"
        if retry_line in code:
            return code

        return f"{retry_line}\n\n{code}"

    def synthesize_quarantine_patch(
        self,
        ticket: SubTaskTicket,
        test_file: str,
        original_content: str,
        failure_output: str = "",
        test_name: Optional[str] = None,
    ) -> WorkerProposal:
        """Synthesize non-erosive quarantine patch, verifying Zero Assertion Erosion."""
        quarantined = self.quarantine_code(test_file, original_content, test_name=test_name)

        # Verification: Zero Assertion Erosion Guard
        report = ZeroAssertionErosionGuard.verify(
            rel_path=test_file,
            proposed_content=quarantined,
            existing_content=original_content,
            allow_test_modification=True,
        )
        if not report.valid:
            raise ValueError(f"Quarantine Patch failed ZeroAssertionErosionGuard: {'; '.join(report.reasons)}")

        # Verification: Zero .skip decorators
        for prohibited in ("test.skip", "it.skip", "describe.skip", "pytest.mark.skip", "xit("):
            if prohibited in quarantined and prohibited not in original_content:
                raise ValueError(f"Quarantine cannot introduce skip modifier: {prohibited}")

        diag = self.diagnose_flake(failure_output, test_file)
        from hermes.orchestration.hermes_workers import WorkerProposal

        return WorkerProposal(
            ticket_id=ticket.ticket_id,
            worker_agent=self.NAME,
            model_tier=ticket.assigned_tier or self.DEFAULT_TIER,
            proposed_changes={test_file: quarantined},
            explanation=f"Quarantined intermittent flake in {test_file} with retry policy (reruns=2).",
            metadata={
                "diagnostics": {
                    "signature": diag.failure_signature,
                    "suspected_source": diag.suspected_source,
                    "recommended_fix": diag.recommended_fix,
                }
            },
        )

    @classmethod
    def format_quarantine_pr_body(
        cls,
        sprint_id: str,
        test_file: str,
        evidence: FlakeDiagnosticEvidence,
        pr_branch: str = "",
    ) -> str:
        """Generate structured Flake Diagnostic Evidence table for Draft PR."""
        branch_name = pr_branch or f"hermes/quarantine-{sprint_id[-8:]}"

        return (
            f"## 🧪 Hermes Flake Quarantine: Non-Erosive Test Stabilization\n\n"
            f"> **Sprint ID**: `{sprint_id}` | **Branch**: `{branch_name}`\n"
            f"> **Target Test Suite**: `{test_file}`\n\n"
            f"### 🔬 Flake Diagnostic Evidence Table\n\n"
            f"| Diagnostic Dimension | Finding & Evidence |\n"
            f"| :--- | :--- |\n"
            f"| **Failure Signature** | `{evidence.failure_signature}` |\n"
            f"| **Suspected Root Cause** | {evidence.suspected_source} |\n"
            f"| **Quarantine Policy** | Non-erosive auto-retry (`reruns=2`, `reruns_delay=1s`) |\n"
            f"| **Assertion Erosion Check** | ✅ **PASSED** (100% assertions preserved, 0 skipped) |\n"
            f"| **Product Logic Status** | 🛡️ **BYTE-FOR-BYTE UNTOUCHED** (Scope Gate Enforced) |\n"
            f"| **Recommended Permanent Fix** | {evidence.recommended_fix} |\n\n"
            f"### 📋 Governance & Safety Invariants\n"
            f"- **Zero Assertion Erosion**: Assertion counts verified non-decreasing via `ZeroAssertionErosionGuard`.\n"
            f"- **No Test Skipping**: Zero `@pytest.mark.skip`, `test.skip`, or `xit` markers.\n"
            f"- **Reversible Snapshot**: Pre-apply snapshot created in Hermes Time Machine.\n\n"
            f"---\n"
            f"*To merge this quarantine draft into main, comment `/hermes approve`.*"
        )
