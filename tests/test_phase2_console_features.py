"""
Hermes Phase 2 Feature Verification Test Suite
Tests:
1. hermes doctor workspace discovery exclusions and Python Playwright classification.
2. hermes console live SSE streaming and Stop/Cancel sprint endpoint.
3. Drag-and-drop artifact upload endpoint (JUnit XML, CTRF JSON, trace.zip, screenshots).
4. Switchable Tier 3 / Tier 2 / Tier 1 proposal comparison + steered instruction regeneration.
5. Mermaid SprintDAGScheduler dependency graph + 1-click DLP-scrubbed .zip audit bundle export.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from hermes.cli import cmd_doctor
from hermes.console.console_demo_manager import demo_manager, event_hub
from hermes.console.server import app


class TestPhase2ConsoleFeatures(unittest.TestCase):
    """Deep verification of all Phase 2 console upgrades and doctor improvements."""

    @classmethod
    def setUpClass(cls):
        os.environ["HERMES_API_TOKEN"] = "test-token"
        cls.client = TestClient(app)
        cls.headers = {"X-Hermes-Token": "test-token"}

    @classmethod
    def tearDownClass(cls):
        demo_manager.cleanup_all()

    def test_1_doctor_workspace_discovery_exclusions_and_playwright_classification(self):
        """Verifies doctor excludes _reference, node_modules, .venv and classifies Python Playwright."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            # 1. Ignored folders
            (ws / "_reference").mkdir(parents=True, exist_ok=True)
            (ws / "_reference" / "test_ignored.py").write_text("def test_x(): pass", encoding="utf-8")
            (ws / "node_modules").mkdir(parents=True, exist_ok=True)
            (ws / "node_modules" / "test_module.js").write_text("test()", encoding="utf-8")
            (ws / ".venv").mkdir(parents=True, exist_ok=True)
            (ws / ".venv" / "test_env.py").write_text("def test_y(): pass", encoding="utf-8")

            # 2. Valid test files
            tests_dir = ws / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)
            # Pytest test
            (tests_dir / "test_api.py").write_text("def test_api(): assert True\n", encoding="utf-8")
            # Python Playwright test (content contains playwright)
            (tests_dir / "test_login_flow.py").write_text("from playwright.sync_api import Page\ndef test_ui(page: Page):\n    page.goto('/')\n", encoding="utf-8")
            # Python Playwright test (filename contains playwright)
            (tests_dir / "Logout_Playwright.py").write_text("def test_logout(): pass\n", encoding="utf-8")
            # TS/JS Playwright test
            (tests_dir / "cart.spec.ts").write_text("test('cart', async () => {});\n", encoding="utf-8")

            # 3. Artifacts
            art_dir = ws / "test-results"
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "junit-report.xml").write_text("<testsuites></testsuites>", encoding="utf-8")
            (art_dir / "ctrf-report.json").write_text("{}", encoding="utf-8")
            (art_dir / "trace.zip").write_text("dummy-zip", encoding="utf-8")

            import argparse
            args = argparse.Namespace(workspace=str(ws), ping_llm=False)
            import io
            from contextlib import redirect_stdout
            f = io.StringIO()
            with redirect_stdout(f):
                rc = cmd_doctor(args)
            output = f.getvalue()

            self.assertEqual(rc, 0)
            self.assertIn("Target Workspace:", output)
            self.assertIn("1 Pytest", output)
            self.assertIn("2 Python Playwright", output)
            self.assertIn("1 Playwright/TS/JS", output)
            self.assertIn("1 JUnit XML", output)
            self.assertIn("1 CTRF JSON", output)
            self.assertIn("1 Playwright Traces", output)

    def test_2_console_drag_and_drop_upload_endpoint(self):
        """Uploads JUnit XML artifact and verifies DemoWorkspace creation."""
        xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="checkout_suite" tests="1" failures="1">
    <testcase classname="tests.test_checkout" name="test_payment_declined" file="tests/test_checkout.py">
      <failure message="CardDeclinedError">Traceback: Payment gateway returned code 402</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        response = self.client.post(
            "/api/demo/upload",
            headers=self.headers,
            files={"file": ("checkout_fail.xml", xml_content, "application/xml")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Upload: checkout_fail.xml", data["workspace_name"])
        self.assertEqual(data["classification"], "PRODUCT_BUG")

        # Verify workspace is persisted and accessible
        ws = demo_manager.get_workspace(data["workspace_id"])
        self.assertIsNotNone(ws)
        self.assertTrue((ws.workspace_path / "artifacts" / "checkout_fail.xml").exists())

    def test_3_console_sse_streaming_and_cancel_endpoint(self):
        """Verifies SSE connection and stop/cancel sprint capability."""
        ws = demo_manager.create_ledger_workspace()

        # Test cancel endpoint
        cancel_resp = self.client.post(f"/api/demo/{ws.workspace_id}/cancel", headers=self.headers)
        self.assertEqual(cancel_resp.status_code, 200)
        cancel_data = cancel_resp.json()
        self.assertEqual(cancel_data["status"], "cancelled")
        self.assertTrue(ws.cancelled)

        # Test SSE stream endpoint (read initial connected event)
        with self.client.stream("GET", f"/api/demo/{ws.workspace_id}/stream", headers=self.headers) as response:
            self.assertEqual(response.status_code, 200)
            lines = []
            for line in response.iter_lines():
                if line:
                    lines.append(line)
                if len(lines) >= 2:
                    break
            streamed_text = "\n".join(lines)
            self.assertIn("connected", streamed_text)

    def test_4_switchable_tier_proposals_and_regenerate(self):
        """Verifies switchable Tier 3 / Tier 2 / Tier 1 comparison and steered regeneration."""
        ws = demo_manager.create_ledger_workspace()
        # Trigger heal
        heal_resp = self.client.post(f"/api/demo/{ws.workspace_id}/heal", headers=self.headers)
        self.assertEqual(heal_resp.status_code, 200)

        # Retrieve proposals
        prop_resp = self.client.get(f"/api/demo/{ws.workspace_id}/proposals", headers=self.headers)
        self.assertEqual(prop_resp.status_code, 200)
        p_data = prop_resp.json()
        self.assertIn("TIER_3_JUNIOR_SWE", p_data["proposals"])
        self.assertIn("TIER_2_SENIOR_SWE", p_data["proposals"])
        self.assertIn("TIER_1_TECH_LEAD", p_data["proposals"])

        t3 = p_data["proposals"]["TIER_3_JUNIOR_SWE"]
        t2 = p_data["proposals"]["TIER_2_SENIOR_SWE"]
        t1 = p_data["proposals"]["TIER_1_TECH_LEAD"]

        self.assertIn("+", t3["diff"])
        self.assertIn("ValueError", t3["diff"])
        self.assertIn("isinstance", t2["diff"])
        self.assertIn("Invariant", t1["diff"])

        # Steered regeneration
        regen_resp = self.client.post(
            f"/api/demo/{ws.workspace_id}/regenerate",
            headers=self.headers,
            json={"tier": "TIER_2_SENIOR_SWE", "instruction": "Add structured logging to trace deposit attempts"},
        )
        self.assertEqual(regen_resp.status_code, 200)
        r_data = regen_resp.json()
        self.assertEqual(r_data["status"], "success")
        self.assertEqual(r_data["tier"], "TIER_2_SENIOR_SWE")
        self.assertIn("logging", r_data["diff"])

    def test_5_dag_and_zip_audit_bundle_export(self):
        """Verifies Mermaid SprintDAGScheduler graph and 1-click .zip audit bundle download."""
        ws = demo_manager.create_ledger_workspace()
        self.client.post(f"/api/demo/{ws.workspace_id}/heal", headers=self.headers)

        # 1. Mermaid DAG endpoint
        dag_resp = self.client.get(f"/api/demo/{ws.workspace_id}/dag", headers=self.headers)
        self.assertEqual(dag_resp.status_code, 200)
        dag_data = dag_resp.json()
        self.assertIn("graph LR", dag_data["mermaid"])
        self.assertIn("SprintDAGScheduler", dag_data["mermaid"])

        # 2. 1-Click .zip Audit Bundle Export
        zip_resp = self.client.get(f"/api/demo/{ws.workspace_id}/audit/export-zip", headers=self.headers)
        self.assertEqual(zip_resp.status_code, 200)
        self.assertEqual(zip_resp.headers["content-type"], "application/zip")
        self.assertIn("attachment; filename=", zip_resp.headers["content-disposition"])

        # Unpack zip and verify contents
        zf = zipfile.ZipFile(io.BytesIO(zip_resp.content))
        names = zf.namelist()
        self.assertIn("audit_trail.md", names)
        self.assertIn("report.sarif", names)
        self.assertIn("telemetry.json", names)
        self.assertIn("staged_patch.diff", names)
        self.assertIn("verification_verdicts.json", names)
        self.assertIn("sprint_manifest.json", names)

        # Inspect SARIF
        sarif = json.loads(zf.read("report.sarif").decode("utf-8"))
        self.assertEqual(sarif["version"], "2.1.0")

        # Inspect Telemetry
        telemetry = json.loads(zf.read("telemetry.json").decode("utf-8"))
        self.assertIn("pipeline_stages", telemetry)
        self.assertIn("roi", telemetry)


if __name__ == "__main__":
    unittest.main()
