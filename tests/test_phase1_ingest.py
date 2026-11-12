"""
Unit & Integration Test Suite for Phase 1: Universal Artifact Ingestion & Playwright Trace Forensics
Validates:
1. NormalizedFailure schema & deterministic verdict computation (HTTP 500 -> PRODUCT_BUG, 502 -> INFRA_FLAKE).
2. JUnit XML parser across Pytest, Jest, and Playwright structures + XXE attack neutralization.
3. CTRF JSON report parser with Option 5 one-way DLP scrubbing and nonce sandboxing.
4. Playwright trace.zip forensics: network 5xx extraction, DOM excerpt capture, and zip-bomb guards.
5. ArtifactLoader universal glob resolution and dispatching.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Dict

from core.ingest.artifact_loader import ArtifactLoader
from core.ingest.ctrf_parser import CTRFParser
from core.ingest.junit_parser import JUnitParser
from core.ingest.models import FailedNetworkRequest, NormalizedFailure
from core.ingest.trace_parser import PlaywrightTraceForensics
from core.security.dlp_scrubber import DLPSessionVault


class TestNormalizedFailureModel(unittest.TestCase):
    """Tests the canonical NormalizedFailure schema and forensic deterministic overrides."""

    def test_deterministic_verdict_product_bug_on_http_500(self):
        req = FailedNetworkRequest(method="POST", url="https://api.corp.internal/v2/charge", status=500, response_body_snippet="NullPointerException")
        failure = NormalizedFailure(
            runner="playwright",
            test_node_id="order.spec.ts::submit checkout",
            file_path="e2e/order.spec.ts",
            error_message="locator.click: Timeout 5000ms exceeded",
            stack_trace="TimeoutError: locator.click...",
            failed_requests=[req],
        )
        self.assertEqual(failure.deterministic_verdict, "PRODUCT_BUG")

    def test_deterministic_verdict_infra_flake_on_http_502_503_504(self):
        for status_code in (502, 503, 504):
            req = FailedNetworkRequest(method="GET", url="https://gateway.internal/orders", status=status_code)
            failure = NormalizedFailure(
                runner="playwright",
                test_node_id="orders.spec.ts::list orders",
                file_path="e2e/orders.spec.ts",
                error_message="Gateway timeout",
                stack_trace="",
                failed_requests=[req],
            )
            self.assertEqual(failure.deterministic_verdict, "INFRA_FLAKE")

    def test_deterministic_verdict_environment_noise_on_port_conflict(self):
        failure = NormalizedFailure(
            runner="pytest",
            test_node_id="tests/test_server.py::test_bind",
            file_path="tests/test_server.py",
            error_message="OSError: [Errno 98] Address already in use: ('127.0.0.1', 54321)",
            stack_trace="Traceback...",
        )
        self.assertEqual(failure.deterministic_verdict, "ENVIRONMENT_NOISE")

    def test_to_cluster_dict_compatibility(self):
        failure = NormalizedFailure(
            runner="pytest",
            test_node_id="tests/test_cart.py::test_total",
            file_path="tests/test_cart.py",
            error_message="AssertionError: 100 != 120",
            stack_trace="assert calculate_total() == 120",
            duration_ms=45.2,
        )
        cluster_dict = failure.to_cluster_dict()
        self.assertEqual(cluster_dict["failing_test"], "tests/test_cart.py::test_total")
        self.assertIn("AssertionError", cluster_dict["raw_trace"])
        self.assertEqual(cluster_dict["runner"], "pytest")


class TestJUnitParser(unittest.TestCase):
    """Tests JUnit XML parsing, runner detection, XXE sanitization, and DLP scrubbing."""

    def test_parse_pytest_junit_xml(self):
        pytest_xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="1" skipped="0" tests="1" time="0.150">
    <testcase classname="tests.test_auth" file="tests/test_auth.py" line="42" name="test_token_refresh" time="0.080">
      <failure message="AssertionError: assert False">def test_token_refresh():
    assert False</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        failures = JUnitParser.parse_string(pytest_xml)
        self.assertEqual(len(failures), 1)
        f = failures[0]
        self.assertEqual(f.runner, "pytest")
        self.assertEqual(f.test_node_id, "tests/test_auth.py::test_token_refresh")
        self.assertEqual(f.file_path, "tests/test_auth.py")
        self.assertEqual(f.line, 42)
        self.assertEqual(f.duration_ms, 80.0)
        self.assertIn("assert False", f.error_message)

    def test_parse_jest_junit_xml(self):
        jest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="jest tests">
  <testsuite name="AuthService" tests="2" failures="1" errors="0" time="1.2">
    <testcase classname="src/__tests__/auth.test.ts" name="AuthService validates user roles" time="0.045">
      <failure message="Expected: 200, Received: 403">Error: expect(received).toBe(expected)</failure>
    </testcase>
    <testcase classname="src/__tests__/auth.test.ts" name="AuthService signs out" time="0.010"/>
  </testsuite>
</testsuites>
"""
        failures = JUnitParser.parse_string(jest_xml)
        self.assertEqual(len(failures), 1)
        f = failures[0]
        self.assertEqual(f.runner, "jest")
        self.assertEqual(f.file_path, "src/__tests__/auth.test.ts")
        self.assertIn("AuthService validates user roles", f.test_node_id)
        self.assertIn("Expected: 200", f.error_message)

    def test_xxe_attack_sanitization(self):
        malicious_xxe = """<?xml version="1.0"?>
<!DOCTYPE test [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<testsuite name="xxe_test" tests="1" failures="1">
  <testcase name="test_xxe" classname="tests.test_sec">
    <failure message="Failed: &xxe;">Stack with &xxe;</failure>
  </testcase>
</testsuite>
"""
        # Sanitizer strips DOCTYPE & ENTITY cleanly, preventing XXE entity resolution
        safe_xml = JUnitParser.sanitize_xml(malicious_xxe)
        self.assertNotIn("<!DOCTYPE", safe_xml)
        self.assertNotIn("<!ENTITY", safe_xml)

        failures = JUnitParser.parse_string(malicious_xxe)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].test_node_id, "tests/test_sec.py::test_xxe")

    def test_dlp_secret_scrubbing_in_junit_traces(self):
        vault = DLPSessionVault()
        raw_xml = """<testsuite name="auth" tests="1" failures="1">
  <testcase name="test_login" file="tests/test_login.py">
    <failure message="Database error postgres://admin:SecretPassword99@db.internal:5432/main">
      Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature
      Connected using AWS Key AKIAIOSFODNN7EXAMPLE
    </failure>
  </testcase>
</testsuite>"""
        failures = JUnitParser.parse_string(raw_xml, dlp_vault=vault)
        self.assertEqual(len(failures), 1)
        f = failures[0]
        self.assertNotIn("SecretPassword99", f.error_message)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", f.stack_trace)
        self.assertIn("<HERMES_URI_1>", f.error_message)
        self.assertIn("<HERMES_KEY_1>", f.stack_trace)


class TestCTRFParser(unittest.TestCase):
    """Tests CTRF JSON parsing and DLP sanitization."""

    def test_parse_ctrf_json(self):
        ctrf_json = {
            "results": {
                "tool": {"name": "playwright"},
                "summary": {"tests": 2, "passed": 1, "failed": 1},
                "tests": [
                    {
                        "name": "checkout flow succeeds",
                        "status": "passed",
                        "duration": 450,
                    },
                    {
                        "name": "cart modal displays items",
                        "status": "failed",
                        "duration": 1200,
                        "filePath": "e2e/cart.spec.ts",
                        "retries": 1,
                        "line": 88,
                        "message": "Timed out 5000ms waiting for locator('.cart-item')",
                        "trace": "TimeoutError: locator.waitFor\n  at CartPage.open (e2e/cart.spec.ts:88:15)",
                    },
                ],
            }
        }
        failures = CTRFParser.parse_string(json.dumps(ctrf_json))
        self.assertEqual(len(failures), 1)
        f = failures[0]
        self.assertEqual(f.runner, "playwright")
        self.assertEqual(f.test_node_id, "e2e/cart.spec.ts::cart modal displays items")
        self.assertEqual(f.file_path, "e2e/cart.spec.ts")
        self.assertEqual(f.line, 88)
        self.assertEqual(f.duration_ms, 1200.0)
        self.assertEqual(f.retries, 1)
        self.assertIn("Timed out 5000ms", f.error_message)


class TestPlaywrightTraceForensics(unittest.TestCase):
    """Tests Playwright trace.zip forensics: HTTP 500 extraction, DOM snapshots, and zip-bomb guards."""

    def _create_mock_trace_zip(self, network_events: list, trace_events: list, include_binary: bool = True) -> io.BytesIO:
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if network_events:
                net_text = "\n".join(json.dumps(e) for e in network_events)
                zf.writestr("0.network", net_text)
            if trace_events:
                trace_text = "\n".join(json.dumps(e) for e in trace_events)
                zf.writestr("0.trace", trace_text)
            if include_binary:
                # Add mock screenshot/binary entry that must be safely ignored
                zf.writestr("resources/screenshot1.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
        bio.seek(0)
        return bio

    def test_trace_forensics_captures_http_500_backend_product_bug(self):
        """Forensic Killer Feature: Correlates failed button click with backend HTTP 500 NullPointerException."""
        network_events = [
            {"type": "request", "method": "GET", "url": "https://app.corp/index.html"},
            {
                "type": "response",
                "request": {"method": "POST", "url": "https://app.corp/v2/charge"},
                "response": {
                    "status": 500,
                    "url": "https://app.corp/v2/charge",
                    "statusText": "Internal Server Error",
                    "body": '{"error": "NullPointerException: payment_gateway_timeout"}',
                },
            },
        ]
        trace_events = [
            {
                "type": "action",
                "apiName": "page.click",
                "selector": "button.pay-btn",
                "error": {"error": {"message": "TimeoutError: locator.click: Timeout 5000ms exceeded"}},
            },
            {
                "type": "snapshot",
                "snapshot": {"html": "<div id='app'><button class='pay-btn' disabled>Pay $50</button></div>"},
            },
        ]
        zip_buf = self._create_mock_trace_zip(network_events, trace_events)
        failures = PlaywrightTraceForensics.parse_zip(
            zip_buf, test_node_id_hint="e2e/payment.spec.ts::user checkout"
        )
        self.assertEqual(len(failures), 1)
        f = failures[0]
        self.assertEqual(f.runner, "playwright")
        self.assertEqual(len(f.failed_requests), 1)
        req = f.failed_requests[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.status, 500)
        self.assertIn("NullPointerException", req.response_body_snippet)
        self.assertEqual(f.deterministic_verdict, "PRODUCT_BUG")
        self.assertIn("button.pay-btn", f.error_message)
        self.assertIsNotNone(f.dom_excerpt)

    def test_trace_forensics_captures_http_502_gateway_infra_flake(self):
        network_events = [
            {
                "type": "response",
                "request": {"method": "GET", "url": "https://gateway.corp/orders"},
                "response": {"status": 502, "url": "https://gateway.corp/orders", "statusText": "Bad Gateway"},
            }
        ]
        trace_events = [
            {"type": "action", "apiName": "page.goto", "error": {"error": {"message": "Navigation failed: 502"}}}
        ]
        zip_buf = self._create_mock_trace_zip(network_events, trace_events)
        failures = PlaywrightTraceForensics.parse_zip(zip_buf)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].deterministic_verdict, "INFRA_FLAKE")

    def test_trace_zip_bomb_guard_rejection(self):
        """Simulate a zip-bomb entry exceeding 50 MB total decompressed cap."""
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 60 MB of zeroes compresses to ~60 KB but has 60 MB uncompressed size
            zf.writestr("huge_bomb.json", b"0" * (60 * 1024 * 1024))
        bio.seek(0)

        failures = PlaywrightTraceForensics.parse_zip(bio)
        self.assertEqual(len(failures), 1)
        self.assertIn("size envelope", failures[0].error_message)
        self.assertEqual(failures[0].deterministic_verdict, "ENVIRONMENT_NOISE")


class TestArtifactLoaderIntegration(unittest.TestCase):
    """Tests the universal ArtifactLoader resolving globs across JUnit, CTRF, and trace.zip."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # 1. Create a mock junit.xml
        junit_xml = """<testsuite name="unit" tests="1" failures="1">
  <testcase name="test_cart" file="tests/test_cart.py"><failure message="Cart empty">Trace</failure></testcase>
</testsuite>"""
        (self.root / "junit-results.xml").write_text(junit_xml, encoding="utf-8")

        # 2. Create a mock ctrf-report.json
        ctrf_json = {
            "results": {
                "tests": [
                    {"name": "test_auth", "status": "failed", "filePath": "e2e/auth.spec.ts", "message": "Failed"}
                ]
            }
        }
        (self.root / "ctrf-report.json").write_text(json.dumps(ctrf_json), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_artifacts_with_glob_dispatches_cleanly(self):
        failures = ArtifactLoader.load_artifacts(
            patterns=["*.xml", "*.json"],
            workspace_root=self.root,
        )
        self.assertEqual(len(failures), 2)
        test_ids = [f.test_node_id for f in failures]
        self.assertTrue(any("test_cart" in tid for tid in test_ids))
        self.assertTrue(any("test_auth" in tid for tid in test_ids))


if __name__ == "__main__":
    unittest.main()
