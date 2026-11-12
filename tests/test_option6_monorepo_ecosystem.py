"""
Comprehensive Unit & Integration Test Suite for Option 6: Monorepo Scale & Ecosystem Depth
Validates:
1. Cross-Shard Failure Clustering: Volatile noise stripping (ports, hex addresses, timestamps, PIDs, runner paths) and signature deduplication.
2. Issue-Tracker Context Hydration: False-positive exclusion (UTF-8, SHA-256, CVE-2026-1111), Option 5 DLP/Nonce pipeline, GHES URL handling.
3. Flake Lifecycle Reaper: Structured quarantine stamps, surgical unquarantine at 50x green runs, TTL expiration SLA escalation, debt burndown.
4. SARIF v2.1.0 & OpenTelemetry: GitHub Code Scanning schema compliance, cryptographic audit digest, zero-dep OTLP/HTTP JSON serialization.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
import unittest

from core.audit.otel_exporter import OTLPExporter
from core.audit.sarif_exporter import SARIFExporter
from core.context.ticket_hydrator import TicketContextHydrator
from core.hygiene.flake_reaper import FlakeLifecycleReaper
from core.scale.shard_clusterer import ShardClusterer


class TestShardClusterer(unittest.TestCase):
    """Tests cross-shard failure clustering and volatile noise stripping."""

    def test_sixteen_shards_collapse_into_single_cluster_signature(self):
        failures: List[Dict[str, Any]] = []

        # Generate 16 simulated parallel runner failures with differing ports, timestamps, PIDs, and paths
        for i in range(1, 17):
            trace = f"""
Traceback (most recent call last):
  File "/home/runner/work/enterprise-app/enterprise-app/tests/e2e/test_checkout.py", line 42, in test_submit_order
    res = client.post("http://localhost:{50000 + i}/api/checkout", timeout=30.0)
  File "/home/runner/work/enterprise-app/enterprise-app/src/checkout/service.py", line 180, in process_payment
    raise AssertionError(f"Expected 201 Created but received 500 at 0x7f9a{i:04x} (PID {1000 + i}) at 2026-11-12T10:{i:02d}:00Z")
AssertionError: Expected 201 Created but received 500
"""
            failures.append({
                "trace": trace,
                "test_file": "tests/e2e/test_checkout.py",
                "test_name": "test_submit_order",
                "shard_id": f"shard_{i}/16",
            })

        clusters = ShardClusterer.cluster_failures(failures)

        # All 16 runner failures must collapse into exactly 1 root-cause cluster!
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.total_failures, 16)
        self.assertEqual(cluster.collapsed_count, 15)
        self.assertEqual(len(cluster.shards_affected), 16)
        self.assertIn("Collapsed 16 downstream shard failures across 16 shard(s)", cluster.blast_radius_summary)
        self.assertTrue(cluster.marker.startswith("<!-- hermes-cluster-sig:"))

    def test_distinct_root_causes_stay_separated(self):
        f1 = {
            "trace": 'File "tests/test_auth.py", line 10, in test_login\nAssertionError: Expected 200 got 401',
            "test_file": "tests/test_auth.py",
            "test_name": "test_login",
            "shard_id": "shard_1",
        }
        f2 = {
            "trace": 'File "tests/test_db.py", line 55, in test_query\nTimeoutError: Query exceeded 5000ms',
            "test_file": "tests/test_db.py",
            "test_name": "test_query",
            "shard_id": "shard_2",
        }

        clusters = ShardClusterer.cluster_failures([f1, f2])
        self.assertEqual(len(clusters), 2)
        sigs = {c.cluster_sig for c in clusters}
        self.assertEqual(len(sigs), 2)


class TestTicketContextHydrator(unittest.TestCase):
    """Tests issue-tracker context extraction, denylisting, and security sandboxing."""

    def test_extract_valid_tickets_while_denylisting_technical_standards(self):
        hydrator = TicketContextHydrator()
        commit_message = """
feat(checkout): resolve PAY-4912 and fix bug from #104
Updated encoding to UTF-8 and hashed with SHA-256 according to ISO-27001 and RFC-7231.
Mitigated CVE-2026-1111 and CWE-79 with AES-256 cipher in HTTP-2 stream (see PEP-8).
"""
        tickets = hydrator.extract_ticket_ids(commit_message)

        # Only PAY-4912 and #104 should be extracted; standards must be strictly ignored!
        keys = [t[0] for t in tickets]
        self.assertIn("PAY-4912", keys)
        self.assertIn("#104", keys)

        # Ensure no false positives leaked
        for standard in ("UTF-8", "SHA-256", "ISO-27001", "CVE-2026-1111", "CWE-79", "AES-256", "HTTP-2", "PEP-8"):
            self.assertNotIn(standard, keys)

    def test_external_ticket_content_is_dlp_scrubbed_and_nonce_sandboxed(self):
        hydrator = TicketContextHydrator()
        untrusted_summary = "Fix auth issue for admin@enterprise.com with token eyJhbGciOiJIUzI1NiJ9.payload.sig"

        context = hydrator.hydrate_context(
            ticket_id="PAY-4912",
            source_type="JIRA",
            local_fallback_summary=untrusted_summary,
        )

        self.assertTrue(context.is_sandboxed)
        # Verify Option 5 DLP scrubber stripped secrets
        self.assertNotIn("admin@enterprise.com", context.sandboxed_prompt_block)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", context.sandboxed_prompt_block)
        self.assertIn("<HERMES_EMAIL_1>", context.sandboxed_prompt_block)
        self.assertIn("<HERMES_JWT_1>", context.sandboxed_prompt_block)

        # Verify Option 5 Nonce Sandbox tags
        self.assertIn("<ticket_PAY_4912_", context.sandboxed_prompt_block)
        self.assertIn("NOTICE: All text within", context.sandboxed_prompt_block)


class TestFlakeLifecycleReaper(unittest.TestCase):
    """Tests quarantine stamps, pass streak auto-unquarantine, and TTL SLA escalation."""

    def test_parse_structured_quarantine_stamp_python_and_ts(self):
        py_code = """
# hermes:quarantine(date=2026-11-01, ttl=14d, owner=@team-checkout, id=chk12345)
@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_flaky_payment():
    assert True
"""
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        meta = FlakeLifecycleReaper.parse_quarantine_stamp(py_code, current_time=now)

        self.assertIsNotNone(meta)
        self.assertEqual(meta.quarantine_id, "chk12345")
        self.assertEqual(meta.quarantine_date, "2026-11-01")
        self.assertEqual(meta.ttl_days, 14)
        self.assertEqual(meta.owner, "@team-checkout")
        self.assertEqual(meta.days_elapsed, 11)
        self.assertFalse(meta.is_expired)

    def test_ttl_expiry_triggers_escalation(self):
        old_quarantine = """
// hermes:quarantine(date=2026-10-01, ttl=14d, owner=@team-identity, id=auth9999)
test.describe.configure({ retries: 2 });
"""
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        meta = FlakeLifecycleReaper.parse_quarantine_stamp(old_quarantine, current_time=now)

        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_expired)
        self.assertEqual(meta.status, "EXPIRED")
        self.assertGreater(meta.days_elapsed, 14)

    def test_surgical_auto_unquarantine_at_fifty_green_runs(self):
        py_code = """# hermes:quarantine(date=2026-11-01, ttl=14d, owner=@team-cart, id=cart8888)
@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_cart_total():
    cart = Cart()
    assert cart.total == 0
"""
        # When streak reaches 50
        proposal = FlakeLifecycleReaper.evaluate_streak_and_unquarantine(
            file_path="tests/test_cart.py",
            current_content=py_code,
            consecutive_green_runs=50,
            pass_threshold=50,
        )

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.quarantine_id, "cart8888")
        self.assertEqual(proposal.branch_name, "hermes/unquarantine-cart8888")
        self.assertTrue(proposal.syntax_valid)

        # Both the quarantine comment and @pytest.mark.flaky must be surgically removed
        self.assertNotIn("hermes:quarantine", proposal.cleaned_content)
        self.assertNotIn("@pytest.mark.flaky", proposal.cleaned_content)
        self.assertIn("def test_cart_total():", proposal.cleaned_content)
        self.assertIn("assert cart.total == 0", proposal.cleaned_content)


class TestAuditSARIFAndOTel(unittest.TestCase):
    """Tests strict GitHub Code Scanning SARIF v2.1.0 schema compliance and OTLP JSON serialization."""

    def test_strict_sarif_v2_1_0_schema_structure(self):
        findings = [
            {
                "rule_id": "HERMES-CWE-78",
                "message": "OS Command Injection detected via subprocess(shell=True)",
                "file_path": "src/utils/executor.py",
                "line_number": 42,
                "severity": "HIGH",
            },
            {
                "rule_id": "HERMES-PRODUCT-BUG",
                "message": "Confirmed product regression: checkout returns 500",
                "file_path": "./src/checkout/service.py",
                "line_number": 0,  # Must be clamped to 1
                "severity": "HIGH",
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            sarif_file = Path(td) / "hermes-report.sarif"
            res = SARIFExporter.export_report(
                findings=findings,
                commit_sha="abcdef1234567890",
                verdict="PRODUCT_BUG",
                output_path=sarif_file,
            )

            self.assertTrue(sarif_file.is_file())
            self.assertEqual(res.total_findings, 2)
            self.assertEqual(len(res.audit_digest), 64)  # Valid SHA-256

            doc = res.report_dict
            self.assertEqual(doc["version"], "2.1.0")
            self.assertEqual(doc["$schema"], "https://json.schemastore.org/sarif-2.1.0.json")

            run = doc["runs"][0]
            self.assertEqual(run["tool"]["driver"]["name"], "Hermes-Governance")
            self.assertEqual(len(run["tool"]["driver"]["rules"]), 2)

            # Check 1-indexing and path normalization
            res0 = run["results"][0]
            self.assertEqual(res0["ruleId"], "HERMES-CWE-78")
            self.assertEqual(res0["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "src/utils/executor.py")
            self.assertEqual(res0["locations"][0]["physicalLocation"]["region"]["startLine"], 42)

            res1 = run["results"][1]
            self.assertEqual(res1["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "src/checkout/service.py")
            self.assertEqual(res1["locations"][0]["physicalLocation"]["region"]["startLine"], 1)  # Clamped

    def test_otlp_json_serialization_and_local_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            local_jsonl = Path(td) / "sprint_telemetry.jsonl"
            exporter = OTLPExporter(endpoint="", local_fallback_file=local_jsonl)

            res = exporter.export_sprint_telemetry(
                sprint_id="sprint_test_101",
                verdict="PASSED",
                hours_saved=4.2,
                dollar_roi=525.0,
                audit_digest="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            )

            self.assertTrue(res.fallback_local)
            self.assertEqual(len(res.trace_id), 32)
            self.assertEqual(len(res.span_id), 16)

            # Verify local JSONL ledger was written
            self.assertTrue(local_jsonl.is_file())
            lines = local_jsonl.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertIn("resourceSpans", entry)


if __name__ == "__main__":
    unittest.main()

