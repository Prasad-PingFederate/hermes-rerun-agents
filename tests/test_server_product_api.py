"""Integration tests for Hermes Product APIs (Phase 1, 2, 3 endpoints).

Tests:
- /api/repos/connect
- CI task webhook ingestion into /api/demo/inbox
- /api/demo/{workspace_id}/pr branch creation
- /api/demo/flake and /api/demo/noise
- /api/demo/{workspace_id}/story
- /api/demo/{workspace_id}/audit/export
- /api/providers/config and /api/providers/test
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import server
from console_demo_manager import REGISTRY_DB_PATH


class TestServerProductAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HERMES_API_TOKEN"] = "test-token"
        os.environ["WEBHOOK_SECRET"] = "secret-123"
        cls.client = TestClient(server.app)
        cls.headers = {"X-Hermes-Token": "test-token"}

    @classmethod
    def tearDownClass(cls):
        server.demo_manager.cleanup_all()

    def test_connect_repo_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            repo_dir = Path(td)
            tests_dir = repo_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")

            res = self.client.post(
                "/api/repos/connect",
                headers=self.headers,
                json={"repo_path": str(repo_dir), "name": "TestSampleRepo"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["workspace_name"], "TestSampleRepo")
            self.assertEqual(data["classification"], "PRODUCT_BUG")
            self.assertIn("tests/test_sample.py", data["scope"])
            server.demo_manager.delete_workspace(data["workspace_id"])

    def test_webhook_ci_task_in_inbox(self):
        payload = {
            "action": "completed",
            "workflow_run": {
                "id": 998877,
                "head_branch": "feature/checkout",
                "conclusion": "failure",
            },
            "repository": {"full_name": "acme/checkout-service"},
            "check_run": {
                "name": "Unit Tests",
                "output": {
                    "title": "pytest failure",
                    "summary": "FAILED tests/test_payment.py::test_stripe_charge - CardError",
                },
            },
        }
        body = json.dumps(payload).encode("utf-8")
        sig = "sha256=" + hmac.new(b"secret-123", body, hashlib.sha256).hexdigest()

        # Post to webhook
        res_hook = self.client.post(
            "/api/webhook/github-actions",
            content=body,
            headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
        self.assertEqual(res_hook.status_code, 200)
        self.assertTrue(res_hook.json().get("triaged"))

        # Check demo inbox
        res_inbox = self.client.get("/api/demo/inbox", headers=self.headers)
        self.assertEqual(res_inbox.status_code, 200)
        inbox_data = res_inbox.json()
        workspaces = inbox_data.get("workspaces", [])
        ci_ws = next((w for w in workspaces if "test_payment.py" in w.get("failing_test", "")), None)
        self.assertIsNotNone(ci_ws)

    def test_create_flake_and_noise_endpoints(self):
        res_flake = self.client.post("/api/demo/flake", headers=self.headers)
        self.assertEqual(res_flake.status_code, 200)
        self.assertEqual(res_flake.json()["classification"], "FLAKY_TEST")

        res_noise = self.client.post("/api/demo/noise", headers=self.headers)
        self.assertEqual(res_noise.status_code, 200)
        self.assertEqual(res_noise.json()["classification"], "ENVIRONMENT_NOISE")

    def test_pr_branch_creation(self):
        # Create a ledger workspace first
        res_led = self.client.post("/api/demo/ledger", headers=self.headers)
        ws_id = res_led.json()["workspace_id"]

        # Call PR creation
        res_pr = self.client.post(
            f"/api/demo/{ws_id}/pr",
            headers=self.headers,
            json={"branch_name": "hermes/heal-test-01", "approver": "QALead"},
        )
        self.assertEqual(res_pr.status_code, 200)
        pr_data = res_pr.json()
        self.assertEqual(pr_data["status"], "success")
        self.assertEqual(pr_data["branch"], "hermes/heal-test-01")
        self.assertIn("git push origin hermes/heal-test-01", pr_data["push_cmd"])

    def test_audit_export_formats(self):
        res_led = self.client.post("/api/demo/ledger", headers=self.headers)
        ws_id = res_led.json()["workspace_id"]

        # Markdown
        res_md = self.client.get(f"/api/demo/{ws_id}/audit/export?format=markdown", headers=self.headers)
        self.assertEqual(res_md.status_code, 200)
        self.assertIn("HERMES SPRINT AUDIT REPORT", res_md.json()["markdown"])

        # JSON
        res_json = self.client.get(f"/api/demo/{ws_id}/audit/export?format=json", headers=self.headers)
        self.assertEqual(res_json.status_code, 200)
        self.assertEqual(res_json.json()["workspace_id"], ws_id)

        # HTML
        res_html = self.client.get(f"/api/demo/{ws_id}/audit/export?format=html", headers=self.headers)
        self.assertEqual(res_html.status_code, 200)
        self.assertIn("<!DOCTYPE html>", res_html.text)
        self.assertIn("HERMES SPRINT AUDIT REPORT", res_html.text)

    def test_provider_config_and_test_endpoints(self):
        res_cfg = self.client.get("/api/providers/config", headers=self.headers)
        self.assertEqual(res_cfg.status_code, 200)
        cfg_data = res_cfg.json()
        self.assertIn("providers", cfg_data)
        self.assertGreaterEqual(len(cfg_data["providers"]), 18)

        # Set provider config
        res_set = self.client.post(
            "/api/providers/config",
            headers=self.headers,
            json={"active_provider": "ollama", "base_url": "http://localhost:11434"},
        )
        self.assertEqual(res_set.status_code, 200)

        # Test provider connection
        res_test = self.client.post(
            "/api/providers/test",
            headers=self.headers,
            json={"provider_name": "openai"},
        )
        self.assertEqual(res_test.status_code, 200)
        self.assertEqual(res_test.json()["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
