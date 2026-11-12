"""
Hermes Option 2 — The Enterprise Wedge Tests
Owner: ScrumMasterOrchestrator, TIER_1

Tests:
1. Shadow Mode & Zero-Write Suggestion Engine (In-diff suggestion, out-of-diff fallback, anti-spam idempotency).
2. Executive ROI & MTTR Telemetry Engine (Hours saved, dollar ROI, MTTR compression, formula transparency).
3. Flake Quarantine PR Bot (Python/Pytest, Playwright, Jest retry injection, ZeroAssertionErosion compliance, Diagnostic Evidence table).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core.governance.assertion_erosion_guard import ZeroAssertionErosionGuard
from core.orchestrator.scrum_hierarchy import SubTaskTicket
from core.quarantine.flake_quarantine_agent import (
    FlakeDiagnosticEvidence,
    FlakeQuarantineAgent,
)
from core.shadow_mode.suggestion_engine import (
    DiffHunkParser,
    ExecutionMode,
    ShadowSuggestionClient,
    ShadowSuggestionFormatter,
)
from core.telemetry.roi_calculator import (
    ROIConfig,
    ROIMetrics,
    ROITelemetryEngine,
)


class TestShadowModeSuggestionEngine(unittest.TestCase):
    """Tests for SHADOW_SUGGEST zero-write mode, in-diff suggestions, and 422 fallback."""

    SAMPLE_UNIFIED_DIFF = (
        "diff --git a/src/service.py b/src/service.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/src/service.py\n"
        "+++ b/src/service.py\n"
        "@@ -10,6 +10,8 @@ def process_transaction(amount):\n"
        "     if amount is None:\n"
        "         return None\n"
        "+    if amount <= 0:\n"
        "+        raise ValueError('Invalid amount')\n"
        "     return amount * 1.1\n"
    )

    def test_diff_hunk_parser_and_span_detection(self):
        """Parser correctly extracts changed ranges and identifies whether a span is in-diff."""
        hunks = DiffHunkParser.parse_diff(self.SAMPLE_UNIFIED_DIFF)
        self.assertIn("src/service.py", hunks)
        self.assertEqual(len(hunks["src/service.py"]), 1)
        hunk = hunks["src/service.py"][0]
        self.assertEqual(hunk.new_start, 10)
        self.assertEqual(hunk.new_end, 17)

        # In-diff span
        in_diff = DiffHunkParser.is_span_in_diff(hunks, "src/service.py", start_line=12, end_line=14)
        self.assertTrue(in_diff)

        # Out-of-diff span in same file
        out_of_diff_line = DiffHunkParser.is_span_in_diff(hunks, "src/service.py", start_line=85, end_line=90)
        self.assertFalse(out_of_diff_line)

        # Out-of-diff separate file (e.g. untouched test file)
        out_of_diff_file = DiffHunkParser.is_span_in_diff(hunks, "tests/test_service.py", start_line=1, end_line=10)
        self.assertFalse(out_of_diff_file)

    def test_in_diff_suggestion_payload_formatting(self):
        """In-diff suggestion produces GitHub review comment payload with ```suggestion block."""
        sprint_id = "sprint_test_123"
        replacement = (
            "    if amount <= 0:\n"
            "        raise ValueError('Amount must be positive')\n"
        )
        payload = ShadowSuggestionFormatter.format_in_diff_payload(
            file_path="src/service.py",
            start_line=12,
            end_line=14,
            replacement_code=replacement,
            sprint_id=sprint_id,
            classification="PRODUCT_BUG",
            root_cause="Negative deposit allowed without defensive check",
        )

        self.assertEqual(payload["path"], "src/service.py")
        self.assertEqual(payload["line"], 14)
        self.assertEqual(payload["start_line"], 12)
        self.assertEqual(payload["side"], "RIGHT")
        self.assertEqual(payload["start_side"], "RIGHT")

        body = payload["body"]
        self.assertIn(f"<!-- hermes-shadow-heal:{sprint_id} -->", body)
        self.assertIn("```suggestion", body)
        self.assertIn("ZERO_ASSERTION_EROSION", body)
        self.assertIn("DELTA_SAST_PASSED", body)
        self.assertIn("SURGICAL_SPAN", body)
        self.assertIn("Commit suggestion", body)

    def test_out_of_diff_fallback_prevents_http_422(self):
        """Out-of-diff proposal emits collapsible issue summary comment to prevent GitHub 422."""
        sprint_id = "sprint_test_out_of_diff"
        body = ShadowSuggestionFormatter.format_out_of_diff_fallback(
            file_path="tests/test_checkout.py",
            start_line=25,
            end_line=30,
            unified_diff="--- a/tests/test_checkout.py\n+++ b/tests/test_checkout.py\n@@ -25,2 +25,2 @@\n-    assert res == 'OLD'\n+    assert res == 'NEW'\n",
            sprint_id=sprint_id,
            classification="TEST_BUG",
            governance_audit="Zero Assertion Erosion: PASS | Delta-SAST: PASS",
        )

        self.assertIn(f"<!-- hermes-shadow-heal:{sprint_id} -->", body)
        self.assertIn("<details open>", body)
        self.assertIn("View Proposed Unified Diff", body)
        self.assertIn("Governance & Security Audit Trail", body)
        self.assertIn("/hermes approve", body)
        self.assertIn("git apply", body)
        self.assertIn("HTTP 422", body)

    def test_shadow_client_simulated_mode_zero_write(self):
        """Shadow client executes in zero-write simulated trial mode without API token."""
        client = ShadowSuggestionClient(token=None)
        res = client.post_or_update_suggestion(
            owner="acme-corp",
            repo="fintech-core",
            pr_number=42,
            commit_sha="abcdef123456",
            file_path="src/service.py",
            start_line=10,
            end_line=15,
            replacement_code="return True",
            sprint_id="sprint_sim_001",
            is_in_diff=True,
        )

        self.assertEqual(res["status"], "simulated")
        self.assertEqual(res["mode"], "in_diff")
        self.assertEqual(res["payload"]["commit_id"], "abcdef123456")
        self.assertIn("<!-- hermes-shadow-heal:sprint_sim_001 -->", res["payload"]["body"])


class TestExecutiveROITelemetryEngine(unittest.TestCase):
    """Tests for transparent ROI calculation, MTTR compression, and formula breakdown."""

    def setUp(self):
        self.engine = ROITelemetryEngine(
            ROIConfig(
                hourly_rate_usd=125.0,
                manual_mttr_minutes=252.0,  # 4.2 hours
                product_bug_hours_saved=4.2,
                test_drift_hours_saved=2.0,
                flake_quarantine_hours_saved=1.5,
                security_blocked_hours_saved=3.0,
                avg_heal_time_seconds=78.0,
            )
        )

    def test_roi_calculation_with_auditable_breakdown(self):
        """Telemetry engine calculates hours saved, dollar ROI, and MTTR compression accurately."""
        sample_workspaces = [
            {"workspace_name": "InMemoryLedger", "classification": "PRODUCT_BUG", "status": "APPLIED"},
            {"workspace_name": "PlaywrightDrift", "classification": "TEST_BUG", "status": "APPLIED"},
            {"workspace_name": "PlaywrightFlake", "classification": "FLAKY_TEST", "status": "AWAITING_WRITE_GATE"},
            {"workspace_name": "HostilePatch", "classification": "PRODUCT_BUG", "status": "FAILED"},
        ]

        metrics = self.engine.calculate_from_workspaces(sample_workspaces)

        # Expected:
        # Product bugs: 1 * 4.2 = 4.2
        # Test drifts: 1 * 2.0 = 2.0
        # Flakes: 1 * 1.5 = 1.5
        # Hostiles: 1 * 3.0 = 3.0
        # Total hours = 10.7 hrs
        self.assertEqual(metrics.healed_product_bugs, 1)
        self.assertEqual(metrics.healed_test_drifts, 1)
        self.assertEqual(metrics.quarantined_flakes, 1)
        self.assertEqual(metrics.blocked_hostile_patches, 1)
        self.assertEqual(metrics.engineering_hours_saved, 10.7)

        # Dollar ROI: 10.7 * 125 = $1,337.50
        self.assertEqual(metrics.dollar_roi_usd, 1337.50)

        # MTTR: manual 4.2h (252m) -> 1.3m auto
        self.assertEqual(metrics.manual_mttr_hours, 4.2)
        self.assertEqual(metrics.autonomous_mttr_minutes, 1.3)
        self.assertGreater(metrics.mttr_reduction_percent, 99.0)

        # Mathematical transparency breakdown
        self.assertIn("formula", metrics.formula_breakdown)
        self.assertIn("components", metrics.formula_breakdown)
        self.assertEqual(metrics.formula_breakdown["components"]["product_bugs"]["subtotal_hours"], 4.2)

    def test_configurable_rates_update(self):
        """Updating hourly rates and MTTR baselines dynamically reflects in metrics."""
        self.engine.update_config(hourly_rate_usd=150.0, manual_mttr_minutes=300.0)
        self.assertEqual(self.engine.config.hourly_rate_usd, 150.0)
        self.assertEqual(self.engine.config.manual_mttr_minutes, 300.0)

        metrics = self.engine.calculate_from_workspaces([])
        # Seed metrics (10.7 hrs * $150 = $1605)
        self.assertEqual(metrics.dollar_roi_usd, 1605.0)


class TestFlakeQuarantinePRBot(unittest.TestCase):
    """Tests for FlakeQuarantineAgent, non-erosive retry injection, and ZeroAssertionErosion compliance."""

    def setUp(self):
        self.agent = FlakeQuarantineAgent()

    def test_python_pytest_flake_quarantine(self):
        """Injects @pytest.mark.flaky(reruns=2, reruns_delay=1) and auto-imports pytest."""
        code = (
            "def test_intermittent_payment():\n"
            "    res = call_payment_gateway()\n"
            "    assert res.status == 'SUCCESS'\n"
        )
        quarantined = self.agent.quarantine_code("tests/test_payment.py", code, test_name="test_intermittent_payment")

        self.assertIn("import pytest", quarantined)
        self.assertIn("@pytest.mark.flaky(reruns=2, reruns_delay=1)", quarantined)
        self.assertIn("assert res.status == 'SUCCESS'", quarantined)

        # Verify Zero Assertion Erosion passes
        report = ZeroAssertionErosionGuard.verify("tests/test_payment.py", quarantined, code)
        self.assertTrue(report.valid)
        self.assertEqual(report.existing_assertions, 1)
        self.assertEqual(report.proposed_assertions, 1)

    def test_playwright_spec_quarantine(self):
        """Injects test.describe.configure({ retries: 2 }); into Playwright TypeScript spec."""
        code = (
            "import { test, expect } from '@playwright/test';\n\n"
            "test('checkout navigation', async ({ page }) => {\n"
            "    await page.goto('/checkout');\n"
            "    await expect(page.locator('#order-btn')).toBeVisible();\n"
            "});\n"
        )
        quarantined = self.agent.quarantine_code("tests/checkout.spec.ts", code)

        self.assertIn("test.describe.configure({ retries: 2 });", quarantined)
        self.assertIn("Auto-Quarantined by Hermes FlakeQuarantineAgent", quarantined)

        # Verify Zero Assertion Erosion passes
        report = ZeroAssertionErosionGuard.verify("tests/checkout.spec.ts", quarantined, code)
        self.assertTrue(report.valid)
        self.assertEqual(report.existing_assertions, 1)
        self.assertEqual(report.proposed_assertions, 1)

    def test_jest_test_quarantine(self):
        """Injects jest.retryTimes(2); into Jest test file."""
        code = (
            "describe('user service', () => {\n"
            "    it('fetches profile', async () => {\n"
            "        const res = await getUser(1);\n"
            "        expect(res.name).toBe('Alice');\n"
            "    });\n"
            "});\n"
        )
        quarantined = self.agent.quarantine_code("tests/user.test.js", code)

        self.assertIn("jest.retryTimes(2);", quarantined)
        self.assertIn("expect(res.name).toBe('Alice');", quarantined)

        report = ZeroAssertionErosionGuard.verify("tests/user.test.js", quarantined, code)
        self.assertTrue(report.valid)
        self.assertEqual(report.existing_assertions, 1)
        self.assertEqual(report.proposed_assertions, 1)

    def test_flake_diagnostic_evidence_table_and_draft_pr_body(self):
        """Generates structured diagnostic evidence and formatted Draft PR body."""
        error_output = "TimeoutError: Page.wait_for_selector: Timeout 30000ms exceeded waiting for locator('#checkout')"
        evidence = FlakeQuarantineAgent.diagnose_flake(error_output, "tests/checkout.spec.ts")

        self.assertIn("TimeoutError", evidence.failure_signature)
        self.assertIn("locator", evidence.recommended_fix)

        pr_body = FlakeQuarantineAgent.format_quarantine_pr_body(
            sprint_id="sprint_flake_789",
            test_file="tests/checkout.spec.ts",
            evidence=evidence,
            pr_branch="hermes/quarantine-789",
        )

        self.assertIn("Flake Diagnostic Evidence Table", pr_body)
        self.assertIn("TimeoutError", pr_body)
        self.assertIn("reruns=2", pr_body)
        self.assertIn("Zero Assertion Erosion", pr_body)
        self.assertIn("BYTE-FOR-BYTE UNTOUCHED", pr_body)
        self.assertIn("/hermes approve", pr_body)


class TestOption2ServerEndpoints(unittest.TestCase):
    """Integration tests for Option 2 server APIs (ROI telemetry and Shadow Suggestion PRs)."""

    @classmethod
    def setUpClass(cls):
        import os
        from fastapi.testclient import TestClient
        import server
        os.environ["HERMES_API_TOKEN"] = "opt2-test-token"
        cls.client = TestClient(server.app)
        cls.headers = {"X-Hermes-Token": "opt2-test-token"}
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        cls.server.demo_manager.cleanup_all()

    def test_get_roi_telemetry_endpoint(self):
        """GET /api/telemetry/roi returns 200 with structured ROI metrics and formula."""
        res = self.client.get("/api/telemetry/roi", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("engineering_hours_saved", data)
        self.assertIn("dollar_roi_usd", data)
        self.assertIn("mttr_reduction_percent", data)
        self.assertIn("formula_breakdown", data)
        self.assertGreater(data["engineering_hours_saved"], 0)
        self.assertGreater(data["dollar_roi_usd"], 0)

    def test_set_roi_config_endpoint(self):
        """POST /api/telemetry/roi/config updates hourly rate and manual MTTR baseline."""
        res = self.client.post(
            "/api/telemetry/roi/config",
            headers=self.headers,
            json={"hourly_rate_usd": 165.0, "manual_mttr_minutes": 270.0},
        )
        self.assertEqual(res.status_code, 200)
        config = res.json().get("config", {})
        self.assertEqual(config.get("hourly_rate_usd"), 165.0)
        self.assertEqual(config.get("manual_mttr_minutes"), 270.0)

        # Verify reflected in subsequent GET
        get_res = self.client.get("/api/telemetry/roi", headers=self.headers)
        self.assertEqual(get_res.json()["hourly_rate_usd"], 165.0)

    def test_shadow_suggest_pr_endpoint(self):
        """POST /api/demo/{workspace_id}/pr with SHADOW_SUGGEST returns zero-write suggestion."""
        # Create ledger demo workspace
        ws_res = self.client.post("/api/demo/ledger", headers=self.headers)
        self.assertEqual(ws_res.status_code, 200)
        ws_id = ws_res.json()["workspace_id"]

        pr_res = self.client.post(
            f"/api/demo/{ws_id}/pr",
            headers=self.headers,
            json={"execution_mode": "SHADOW_SUGGEST", "pr_number": 99},
        )
        self.assertEqual(pr_res.status_code, 200)
        pr_data = pr_res.json()
        self.assertEqual(pr_data["status"], "success")
        self.assertEqual(pr_data["execution_mode"], "SHADOW_SUGGEST")
        self.assertIsNone(pr_data["branch"])
        self.assertIn("suggestion", pr_data)
        self.assertIn("Zero-Write Shadow Suggestion", pr_data["instructions"])

    def test_hermes_action_runner_passing_test(self):
        """Action runner exits 0 when tests pass cleanly without triggering heal DAG."""
        import os
        from unittest.mock import patch
        import scripts.hermes_action_runner as runner

        with patch.dict(os.environ, {
            "INPUT_MODE": "shadow",
            "INPUT_TEST_COMMAND": "python -c \"print('All passed')\"",
            "INPUT_HOURLY_RATE_USD": "125.0",
        }):
            code = runner.main()
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
