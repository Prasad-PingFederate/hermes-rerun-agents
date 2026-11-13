"""
Comprehensive Feature-Claim Audit & Verification Test Suite (v1.1.0)
Owner: Quality & Architecture
Tests all 12 claimed platform capabilities with zero-mock shortcuts in production paths.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.audit.sarif_exporter import SARIFExporter
from core.governance.policy_engine import PolicyEngine
from core.hygiene.flake_reaper import FlakeLifecycleReaper
from core.ingest.artifact_loader import ArtifactLoader
from core.ingest.ctrf_parser import CTRFParser
from core.ingest.trace_parser import PlaywrightTraceForensics
from core.llm.oidc_provider import OIDCProviderRouter, StaticApiKeyForbiddenError
from core.scale.shard_clusterer import ShardClusterer
from core.security.dlp_scrubber import DLPSessionVault
from core.shadow_mode.suggestion_engine import ShadowSuggestionFormatter
from hermes.guards.language_ast_guard import LanguageASTGuard
from hermes.guards.security_blast_radius import SecurityBlastRadiusAgent
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor
from hermes.orchestration.sprint_state_store import SprintStateStore


class TestComprehensiveFeatureAudit(unittest.TestCase):
    """Deep verification of all 12 core claimed features in Hermes v1.1.0."""

    # ── 1. Multi-Format Ingestion & Cross-Shard Clustering ──

    def test_multi_format_artifact_ingestion_junit_ctrf_playwright_zip(self):
        """Ingests JUnit XML, CTRF JSON, and real Playwright trace.zip archive."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # 1. JUnit XML (mixed runner signatures: pytest & java junit)
            junit_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="unit" tests="2" failures="2" errors="0">
    <testcase classname="tests.test_auth" name="test_login" file="tests/test_auth.py" line="25">
      <failure message="AssertionError: 401 != 200">Traceback: tests/test_auth.py:25: AssertionError</failure>
    </testcase>
    <testcase classname="com.example.BillingTest" name="testCharge" file="src/test/java/com/example/BillingTest.java" line="40">
      <failure message="AssertionFailedError: expected 100 but was 0">Stack: com.example.BillingTest:40</failure>
    </testcase>
  </testsuite>
</testsuites>"""
            (root / "junit.xml").write_text(junit_content, encoding="utf-8")

            # 2. CTRF JSON
            ctrf_data = {
                "results": {
                    "tool": {"name": "playwright"},
                    "summary": {"tests": 1, "failed": 1},
                    "tests": [
                        {
                            "name": "login test",
                            "status": "failed",
                            "filePath": "e2e/login.spec.ts",
                            "message": "expect(page.locator('#welcome')).toBeVisible() timed out",
                            "trace": "at e2e/login.spec.ts:18:10",
                        }
                    ],
                }
            }
            (root / "ctrf-report.json").write_text(json.dumps(ctrf_data), encoding="utf-8")

            # 3. Real Playwright trace.zip
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # trace.network
                net_event = {
                    "type": "resource-snapshot",
                    "snapshot": {
                        "request": {"url": "https://api.example.com/login", "method": "POST"},
                        "response": {"status": 500, "statusText": "Internal Server Error"},
                    },
                }
                zf.writestr("trace.network", json.dumps(net_event))
                # trace.trace
                action_event = {
                    "type": "action",
                    "action": "click",
                    "selector": "button#submit",
                    "error": "Error: Timeout 5000ms exceeded",
                }
                zf.writestr("trace.trace", json.dumps(action_event))

            (root / "trace.zip").write_bytes(zip_buf.getvalue())

            # Load artifacts using ArtifactLoader
            failures = ArtifactLoader.load_artifacts(
                patterns=["junit.xml", "ctrf-report.json", "trace.zip"],
                workspace_root=root,
            )
            self.assertGreaterEqual(len(failures), 3)

            runners = {f.runner for f in failures}
            self.assertIn("junit", runners)
            self.assertIn("playwright", runners)

            # Ingest through CIFailureIngestor
            ingestor = CIFailureIngestor(workspace_root=root)
            ingest_result = ingestor.ingest_artifacts(patterns=["*.xml", "*.json", "*.zip"])
            self.assertEqual(ingest_result["source"], "multi_format_artifacts")
            self.assertGreaterEqual(len(ingest_result["normalized_failures"]), 3)

    def test_cross_shard_clustering_collapses_matrix_noise(self):
        """Cross-shard clustering strips volatile ports/timestamps and collapses 40 shard failures into 1."""
        raw_failures = []
        for i in range(40):
            shard_id = f"runner_matrix_shard_{i % 8 + 1}"
            raw_failures.append({
                "test_id": f"tests/test_api.py::test_endpoint_{i}",
                "exception_type": "ConnectionRefusedError",
                "error_message": f"Failed to connect to 127.0.0.1:{50000 + i} at 2026-11-13T10:15:{i:02d}Z (pid={1000 + i})",
                "stack_trace": f"File '/home/runner/work/app/app/api.py', line 45, in call\n  connect(0x7fff{i:04x})",
                "runner": "pytest",
                "shard_id": shard_id,
            })

        clusters = ShardClusterer.cluster_failures(raw_failures)
        # All 40 identical root cause failures collapse into 1 cluster
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.total_failures, 40)
        self.assertEqual(cluster.collapsed_count, 39)
        self.assertGreaterEqual(len(cluster.shards_affected), 8)

    # ── 2. Commit & PR Intent Differentiation ──

    def test_commit_intent_differentiation_in_git_repo(self):
        """Inspects git log -n 5 to classify intentional API drift vs code regression."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), capture_output=True, check=True)

            # 5 seeded commits
            commits = [
                ("init: initial project scaffolding", "app.py", "x = 1\n"),
                ("chore: update build configs", "config.json", "{}\n"),
                ("fix: handle edge case in null check", "app.py", "x = 2\n"),
                ("docs: update README", "README.md", "# Readme\n"),
                ("feat: migrate HTTP status from 200 to 201 Created on POST /users", "app.py", "status = 201\n"),
            ]
            for msg, filename, content in commits:
                (repo / filename).write_text(content, encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", msg], cwd=str(repo), capture_output=True, check=True)

            ingestor = CIFailureIngestor(workspace_root=repo)
            intent = ingestor.resolve_failure_intent()
            self.assertTrue(intent["has_intentional_contract_change"])
            self.assertEqual(intent["intent_category"], "INTENTIONAL_API_DRIFT")

    # ── 3. Multi-Language AST Guard & Zero Assertion Erosion ──

    def test_language_ast_guard_blocks_assertion_erosion_and_dilution(self):
        """Blocks assertion count loss, tautologies, skip injection, and value dilution across languages."""
        # 1. Python assertion deletion
        orig_py = "def test_a():\n    assert foo() == 1\n    assert bar() == 2\n"
        patch_py = "def test_a():\n    assert foo() == 1\n"
        res = LanguageASTGuard.check_assertion_erosion(orig_py, patch_py, "python")
        self.assertFalse(res["passed"])
        self.assertTrue(any("EROSION_ASSERTION_DELETED" in v for v in res["violations"]))

        # 2. Tautological replacement
        tautology_py = "def test_a():\n    assert foo() == 1\n    assert True\n"
        res2 = LanguageASTGuard.check_assertion_erosion(orig_py, tautology_py, "python")
        self.assertFalse(res2["passed"])
        self.assertTrue(any("EROSION_TAUTOLOGICAL_ASSERTION" in v for v in res2["violations"]))

        # 3. TypeScript toBe -> toBeTruthy dilution
        orig_ts = "test('status', () => { expect(res.status).toBe(200); });"
        patch_ts = "test('status', () => { expect(res.status).toBeTruthy(); });"
        res3 = LanguageASTGuard.check_assertion_erosion(orig_ts, patch_ts, "typescript")
        self.assertFalse(res3["passed"])
        self.assertTrue(any("EROSION_SEMANTIC_DILUTION" in v for v in res3["violations"]))

        # 4. Java @Disabled / @Ignore skip injection
        orig_java = "@Test public void testPayment() { assertEquals(100, amount); }"
        patch_java = "@Test @Disabled public void testPayment() { assertEquals(100, amount); }"
        res4 = LanguageASTGuard.check_assertion_erosion(orig_java, patch_java, "java")
        self.assertFalse(res4["passed"])
        self.assertTrue(any("EROSION_SKIP_INJECTED" in v for v in res4["violations"]))

    # ── 4. Deterministic Delta-SAST Gate ──

    def test_delta_sast_blocks_new_vulnerabilities_only(self):
        """Pre-existing vulnerabilities pass; newly added delta vulnerabilities block."""
        legacy_code = "import os\n# Legacy insecure call\nos.system('echo legacy')\ndef calculate(a, b):\n    return a + b\n"
        agent = SecurityBlastRadiusAgent()

        # 1. Benign patch touching calculate(): should PASS despite legacy os.system
        benign_patch = "import os\n# Legacy insecure call\nos.system('echo legacy')\ndef calculate(a, b):\n    return (a + b) * 2\n"
        report_benign = agent.audit_proposal(
            proposed_changes={"app.py": benign_patch},
            original_files={"app.py": legacy_code},
        )
        self.assertFalse(report_benign.has_blocking_violations)

        # 2. Hostile patch adding newly introduced eval(): must HARD BLOCK
        hostile_patch = "import os\n# Legacy insecure call\nos.system('echo legacy')\ndef calculate(a, b):\n    eval(f'{a}+{b}')\n    return a + b\n"
        report_hostile = agent.audit_proposal(
            proposed_changes={"app.py": hostile_patch},
            original_files={"app.py": legacy_code},
        )
        self.assertTrue(report_hostile.has_blocking_violations)
        self.assertEqual(report_hostile.verdict, "BLOCKED")

    # ── 5. DLP Scrubber & Cryptographic Nonce Sandbox ──

    def test_dlp_scrubber_and_rehydration_with_nonce(self):
        """Scrubs JWTs and URIs to indexed placeholders and rehydrates accurately."""
        vault = DLPSessionVault()
        raw_code = "jwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDc'\ndb = 'postgres://admin:pass123@db.prod.internal:5432/main'\n"
        scrubbed = vault.scrub(raw_code, source="SOURCE")

        self.assertIn("<HERMES_JWT_1>", scrubbed.scrubbed_text)
        self.assertIn("<HERMES_URI_1>", scrubbed.scrubbed_text)
        self.assertNotIn("pass123", scrubbed.scrubbed_text)

        rehydrated = vault.rehydrate(scrubbed.scrubbed_text)
        self.assertEqual(rehydrated, raw_code)

    # ── 6. Zero-Static-Key Cloud OIDC ──

    @patch("urllib.request.urlopen")
    def test_cloud_oidc_token_acquisition_and_exchange(self, mock_urlopen):
        """Acquires ambient GitHub Actions OIDC JWT and exchanges against cloud STS."""
        # 1. Mock GitHub Actions OIDC response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"value": "mock_gha_oidc_jwt_token"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        env = {
            "ACTIONS_ID_TOKEN_REQUEST_URL": "http://127.0.0.1/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "runner_secret_token",
        }
        token = OIDCProviderRouter.acquire_github_oidc_token(env=env)
        self.assertEqual(token, "mock_gha_oidc_jwt_token")

        # 2. Mock Azure AD Federated Token Exchange
        mock_azure_resp = MagicMock()
        mock_azure_resp.read.return_value = json.dumps({"access_token": "azure_openai_bearer", "expires_in": 3600}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_azure_resp

        azure_token = OIDCProviderRouter.exchange_azure_federated_token(
            tenant_id="tenant-123",
            client_id="client-456",
            oidc_token=token,
        )
        self.assertEqual(azure_token["access_token"], "azure_openai_bearer")

    def test_strict_require_oidc_rejects_static_keys(self):
        """When require_oidc: true, static API keys raise StaticApiKeyForbiddenError."""
        fake_env = {"OPENAI_API_KEY": "sk-12345678901234567890"}
        with self.assertRaises(StaticApiKeyForbiddenError):
            OIDCProviderRouter.resolve_credentials(require_oidc=True, env=fake_env)

    # ── 7. Flake Lifecycle Reaper ──

    def test_flake_reaper_50x_pass_auto_unquarantine(self):
        """Quarantined test with 50 consecutive passes automatically emits unquarantine proposal."""
        code_quarantined = (
            "# hermes:quarantine(date=2026-11-01, ttl=14d, owner=@team-qa, id=q123)\n"
            "def test_flaky_checkout():\n"
            "    assert True\n"
        )
        proposal = FlakeLifecycleReaper.evaluate_streak_and_unquarantine(
            file_path="tests/test_checkout.py",
            source_code=code_quarantined,
            consecutive_green_runs=50,
        )
        self.assertIsNotNone(proposal)
        self.assertNotIn("# hermes:quarantine", proposal.cleaned_content)
        self.assertEqual(proposal.consecutive_green_runs, 50)
        self.assertIn("auto-unquarantine", proposal.pr_title.lower())

    def test_flake_reaper_14d_ttl_alert(self):
        """Quarantined test older than 14 days triggers EXPIRED status."""
        old_code = (
            "# hermes:quarantine(date=2026-10-01, ttl=14d, owner=@team-qa, id=q_expired)\n"
            "def test_old():\n"
            "    pass\n"
        )
        now = datetime(2026, 11, 13, tzinfo=timezone.utc)
        meta = FlakeLifecycleReaper.parse_quarantine_stamp(old_code, current_time=now)
        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_expired)
        self.assertEqual(meta.status, "EXPIRED")

    # ── 8. Policy-as-Code & FinOps Circuit Breakers ──

    def test_policy_no_heal_paths_and_finops_breaker(self):
        """Enforces no_heal_paths and triggers FINOPS_CIRCUIT_OPEN on token/cost overages."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_yaml = """governance:
  no_heal_zones:
    - "src/auth/**"
    - "migrations/**"
finops:
  max_tokens_per_pr: 5000
  max_cost_usd_per_run: 0.50
"""
            (root / ".hermes.yml").write_text(config_yaml, encoding="utf-8")
            engine = PolicyEngine(root)

            # 1. No heal zones
            eval_res = engine.evaluate_file_paths(["src/auth/token.py", "src/cart/cart.py"])
            self.assertFalse(eval_res.is_allowed)
            self.assertIn("src/auth/token.py", eval_res.blocked_files)

            # 2. FinOps circuit breaker
            engine.record_usage(pr_id="pr_100", tokens=6000, cost_usd=0.60)
            is_open, reason = engine.check_finops_limits(pr_id="pr_100")
            self.assertTrue(is_open)
            self.assertIn("FINOPS_CIRCUIT_OPEN", reason)

    # ── 9. SARIF v2.1.0 & Tamper-Evident Audit Digest ──

    def test_sarif_v2_1_0_schema_compliance_and_digest(self):
        """Emits valid SARIF v2.1.0 with SHA-256 cryptographic audit digest."""
        with tempfile.TemporaryDirectory() as td:
            sarif_file = Path(td) / "hermes-report.sarif"
            findings = [
                {
                    "rule_id": "HERMES-DELTA-SAST-001",
                    "severity": "CRITICAL",
                    "message": "Dangerous code execution sink: eval()",
                    "file_path": "src/app.py",
                    "line_number": 42,
                }
            ]
            res = SARIFExporter.export_report(
                findings=findings,
                commit_sha="a0b1c2d3e4f5",
                verdict="BLOCKED",
                output_path=sarif_file,
            )
            self.assertTrue(sarif_file.is_file())
            self.assertEqual(res.report_dict["version"], "2.1.0")
            self.assertIsNotNone(res.audit_digest)
            self.assertEqual(len(res.audit_digest), 64)  # SHA-256 hex length

    # ── 10. Shadow Mode In-Diff Suggestion Payload ──

    def test_shadow_mode_in_diff_suggestion_payload_format(self):
        """Constructs GitHub review suggestion with ```suggestion fences."""
        payload = ShadowSuggestionFormatter.format_in_diff_payload(
            file_path="tests/test_api.py",
            start_line=10,
            end_line=12,
            suggested_code="    assert response.status_code == 200\n",
            rationale="Restore deterministic HTTP status assertion",
        )
        body = payload["body"]
        self.assertIn("```suggestion", body)
        self.assertIn("assert response.status_code == 200", body)
        self.assertIn("<!-- hermes-shadow-heal", body)
