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

from core.audit.otel_exporter import OTLPExporter
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
from core.time_machine.engine import TimeMachineEngine
from core.verification.counterfactual_verifier import CounterfactualVerifier
from hermes.console.server import dispatch_webhook_event
from hermes.guards.language_ast_guard import LanguageASTGuard
from hermes.guards.security_blast_radius import SecurityBlastRadiusAgent
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor
from hermes.orchestration.scrum_master_orchestrator import ScrumMasterOrchestrator
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
                "stack_trace": ("File '/home/runner/work/app/app/api.py', line 45, in call\n" f"  connect(0x7fff{i:04x})"),
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

    # ── 11. Counterfactual Differential Verification in Real Worktree ──

    def test_counterfactual_differential_verification_worktree(self):
        """Verifies healed tests pass against fixed code, but are rejected if vacuous."""
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td).resolve()
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "ci@hermes.ai"], cwd=str(repo_root), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Hermes CI"], cwd=str(repo_root), check=True, capture_output=True)

            # Broken product code & initial failing test
            calc_py = repo_root / "calc.py"
            calc_py.write_text("def add(a, b):\n    return a + b + 1  # broken\n", encoding="utf-8")
            test_dir = repo_root / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_calc = test_dir / "test_calc.py"
            test_calc.write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")

            subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "broken base"], cwd=str(repo_root), check=True, capture_output=True)

            # Now repair product code on HEAD
            calc_py.write_text("def add(a, b):\n    return a + b  # fixed\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "fixed head"], cwd=str(repo_root), check=True, capture_output=True)

            verifier = CounterfactualVerifier(repo_root)

            # 1. Genuine heal: passes on fixed HEAD, fails against broken base (HEAD~1)
            valid_healed_test = "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
            res_valid = verifier.verify_differential(
                test_file="tests/test_calc.py",
                healed_test_content=valid_healed_test,
                base_git_ref="HEAD~1",
                product_file_paths=["calc.py"],
            )
            self.assertTrue(res_valid.verified)
            self.assertFalse(res_valid.is_vacuous)
            self.assertTrue(res_valid.forward_passed)
            self.assertTrue(res_valid.counterfactual_failed)

            # 2. Vacuous heal: assert True passes on both fixed HEAD and broken base (HEAD~1)
            vacuous_healed_test = "from calc import add\n\ndef test_add():\n    assert True\n"
            res_vacuous = verifier.verify_differential(
                test_file="tests/test_calc.py",
                healed_test_content=vacuous_healed_test,
                base_git_ref="HEAD~1",
                product_file_paths=["calc.py"],
            )
            self.assertFalse(res_vacuous.verified)
            self.assertTrue(res_vacuous.is_vacuous)
            self.assertTrue(res_vacuous.forward_passed)
            self.assertFalse(res_vacuous.counterfactual_failed)
            self.assertIn("vacuous", res_vacuous.summary.lower())

    # ── 12. Go & C# AST Guards (Zero Assertion Erosion & Skip Injection) ──

    def test_language_ast_guard_go_and_csharp(self):
        """Blocks t.Skip() / [Ignore] injection and assertion erosion in Go & C#."""
        # 1. Go AST guard
        orig_go = """package calc_test
import (
    "testing"
    "github.com/stretchr/testify/assert"
)
func TestAdd(t *testing.T) {
    assert.Equal(t, 5, Add(2, 3))
    assert.True(t, IsPositive(5))
}
"""
        # Go skip injection
        skip_go = """package calc_test
import "testing"
func TestAdd(t *testing.T) {
    t.Skip("skipping flaky test")
}
"""
        res_go_skip = LanguageASTGuard.check_assertion_erosion(orig_go, skip_go, language="go")
        self.assertFalse(res_go_skip["passed"])
        self.assertTrue(any("Skip" in v for v in res_go_skip["violations"]))

        # Go assertion erosion (2 assertions down to 1)
        eroded_go = """package calc_test
import (
    "testing"
    "github.com/stretchr/testify/assert"
)
func TestAdd(t *testing.T) {
    assert.Equal(t, 5, Add(2, 3))
}
"""
        res_go_eroded = LanguageASTGuard.check_assertion_erosion(orig_go, eroded_go, language="go")
        self.assertFalse(res_go_eroded["passed"])
        self.assertTrue(any("eroded" in v.lower() or "assertion" in v.lower() for v in res_go_eroded["violations"]))

        # 2. C# AST guard
        orig_cs = """using NUnit.Framework;
namespace Tests {
    public class CalcTests {
        [Test]
        public void TestAdd() {
            Assert.AreEqual(5, Calc.Add(2, 3));
            Assert.That(Calc.IsPositive(5), Is.True);
        }
    }
}
"""
        # C# [Ignore] skip injection
        skip_cs = """using NUnit.Framework;
namespace Tests {
    public class CalcTests {
        [Test]
        [Ignore]
        public void TestAdd() {
            Assert.AreEqual(5, Calc.Add(2, 3));
        }
    }
}
"""
        res_cs_skip = LanguageASTGuard.check_assertion_erosion(orig_cs, skip_cs, language="csharp")
        self.assertFalse(res_cs_skip["passed"])
        self.assertTrue(any("Ignore" in v or "skip" in v.lower() for v in res_cs_skip["violations"]))

        # C# assertion removal
        eroded_cs = """using NUnit.Framework;
namespace Tests {
    public class CalcTests {
        [Test]
        public void TestAdd() {
            Assert.AreEqual(5, Calc.Add(2, 3));
        }
    }
}
"""
        res_cs_eroded = LanguageASTGuard.check_assertion_erosion(orig_cs, eroded_cs, language="csharp")
        self.assertFalse(res_cs_eroded["passed"])
        self.assertTrue(any("eroded" in v.lower() or "assertion" in v.lower() for v in res_cs_eroded["violations"]))

    # ── 13. OpenTelemetry Pipeline Spans & Metrics Export ──

    def test_opentelemetry_pipeline_spans_and_metrics(self):
        """Emits structured OTel spans, tokens, latencies, and fallback JSON ledger."""
        with tempfile.TemporaryDirectory() as td:
            local_ledger = Path(td) / "otel_telemetry.jsonl"
            exporter = OTLPExporter(endpoint="http://localhost:4318/v1/traces", local_ledger_path=local_ledger)

            res = exporter.export_sprint_telemetry(
                sprint_id="sprint_test_otel_123",
                verdict="APPROVED",
                hours_saved=1.5,
                dollar_roi=187.5,
                audit_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                additional_attributes={
                    "stage_duration_s": 2.45,
                    "tokens_used": 1420,
                    "ast_verdict": "PASSED",
                    "delta_sast_count": 0,
                },
            )
            self.assertEqual(len(res.trace_id), 32)
            self.assertEqual(len(res.span_id), 16)
            self.assertTrue(local_ledger.is_file())

            ledger_content = local_ledger.read_text(encoding="utf-8")
            self.assertIn("sprint_test_otel_123", ledger_content)
            self.assertIn("hermes.hours_saved", ledger_content)
            self.assertIn("hermes.dollar_roi", ledger_content)
            self.assertIn("hermes.tokens_used", ledger_content)
            self.assertIn("hermes.stage_duration_s", ledger_content)

    # ── 14. SHA-256 Time Machine Snapshot & /hermes rewind Restoration ──

    def test_time_machine_snapshot_and_rewind_restoration(self):
        """Bit-for-bit SHA-256 state restore and webhook author association authorization."""
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td).resolve()
            src_file = repo / "main.py"
            src_file.write_text("print('clean baseline')\n", encoding="utf-8")

            initial_sha = hashlib.sha256(src_file.read_bytes()).hexdigest()

            # Record TimeMachine snapshot
            tm = TimeMachineEngine(repo)
            snap_id = tm.create_snapshot("pre-heal baseline")

            # Mutate worktree
            src_file.write_text("print('mutated breaking code')\n", encoding="utf-8")
            mutated_sha = hashlib.sha256(src_file.read_bytes()).hexdigest()
            self.assertNotEqual(initial_sha, mutated_sha)

            # Revert snapshot
            tm.revert_snapshot(snap_id)
            restored_sha = hashlib.sha256(src_file.read_bytes()).hexdigest()
            self.assertEqual(initial_sha, restored_sha)

            # Test comment author association security check
            untrusted_payload = {
                "action": "created",
                "comment": {
                    "body": "/hermes rewind",
                    "author_association": "CONTRIBUTOR",
                },
                "sender": {"login": "untrusted_user"},
            }
            res_unauth = dispatch_webhook_event(untrusted_payload)
            self.assertEqual(res_unauth.get("status"), "unauthorized")
            self.assertIn("Unauthorized comment author association", res_unauth.get("error", ""))

            first_time_payload = {
                "action": "created",
                "comment": {
                    "body": "/hermes rewind",
                    "author_association": "FIRST_TIME_CONTRIBUTOR",
                },
                "sender": {"login": "attacker"},
            }
            res_first = dispatch_webhook_event(first_time_payload)
            self.assertEqual(res_first.get("status"), "unauthorized")

    # ── 15. Full 5-Stage Live Pipeline E2E Wiring ──

    def test_full_5_stage_pipeline_e2e_wiring(self):
        """Executes the complete 6 stages in sequence and asserts full pipeline telemetry."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            src_dir = ws / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            tests_dir = ws / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)

            calc_file = src_dir / "calculator.py"
            calc_file.write_text("def multiply(a, b):\n    return a * b\n", encoding="utf-8")

            test_file = tests_dir / "test_calculator.py"
            test_file.write_text("from src.calculator import multiply\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n", encoding="utf-8")

            # .hermes.yml policy
            policy_file = ws / ".hermes.yml"
            policy_file.write_text("boundaries:\n  allowed_paths:\n    - 'src/**'\n    - 'tests/**'\n", encoding="utf-8")

            orchestrator = ScrumMasterOrchestrator(ws)
            raw_failure = "FAILED tests/test_calculator.py::test_multiply - AssertionError: 5 != 6"

            healed_code = (
                "from src.calculator import multiply\n\n"
                "def test_multiply():\n"
                "    assert multiply(2, 3) == 6\n"
            )
            from hermes.execution.llm_provider_adapter import HermesLLMAdapter
            with patch.object(HermesLLMAdapter, "propose_patch", return_value={"tests/test_calculator.py": healed_code}):
                res = orchestrator.run_sprint(
                    mode="heal",
                    failure_output=raw_failure,
                    auto_approve=False,
                )

            # Assert all 6 stages executed in sequence
            self.assertEqual(
                res.get("stages_executed"),
                [
                    "ingestion",
                    "policy_gate",
                    "dlp_redaction",
                    "ast_delta_sast",
                    "counterfactual_verification",
                    "observability_and_reporting",
                ],
            )
            self.assertEqual(res.get("status"), "AWAITING_WRITE_GATE")
            self.assertTrue(res.get("sprint_id").startswith("sprint_"))
            self.assertIsNotNone(res.get("proposal_id"))
            self.assertIsNotNone(res.get("sarif_report"))
            self.assertIn("2.1.0", res.get("sarif_report"))
            self.assertEqual(len(res.get("audit_digest")), 64)
            self.assertEqual(len(res.get("otel_trace_id")), 32)
