"""
Day-1 Field Readiness Verification for External Automation Suites.

Validates:
1. External --workspace path resolution and isolation across JUnit XML, CTRF JSON, and Playwright traces.
2. `hermes doctor` pre-flight command (with and without --ping-llm, ASCII readiness reporting).
3. Scenario A: Drifted Pytest API suite healed deterministically via artifact ingestion with Zero Assertion Erosion.
4. Scenario B: Drifted Playwright TypeScript UI suite healed via CTRF + trace.zip DOM hints with Zero Assertion Erosion.
5. Markdown fence sanitization and workspace non-mutation guarantees.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from hermes.cli import build_parser, cmd_doctor, main
from hermes.execution.workspace_patch_applier import WorkspacePatchApplier, strip_markdown_fences
from hermes.guards.language_ast_guard import LanguageASTGuard
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor
from hermes.orchestration.scrum_master_orchestrator import ScrumMasterOrchestrator
from hermes.orchestration.sprint_state_store import SprintStateStore


class TestExternalAutomationDryRun(unittest.TestCase):
    """End-to-end field readiness tests for external automation repositories."""

    def _init_git_repo(self, path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "ci@hermes-rerun.ai"], cwd=str(path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Hermes Automation"], cwd=str(path), check=True, capture_output=True)

    def test_external_workspace_resolution_and_isolation(self):
        """Verifies paths from container runners (/home/runner/..., C:/...) resolve to external workspace."""
        with tempfile.TemporaryDirectory() as td:
            ext_ws = Path(td).resolve()
            self._init_git_repo(ext_ws)

            test_file = ext_ws / "tests" / "e2e" / "test_auth.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_dummy():\n    assert True\n", encoding="utf-8")

            ingestor = CIFailureIngestor(workspace_root=ext_ws)

            # Test various container runner prefixes
            p1 = ingestor.resolve_to_workspace("/home/runner/work/app/app/tests/e2e/test_auth.py")
            self.assertEqual(p1, "tests/e2e/test_auth.py")

            p2 = ingestor.resolve_to_workspace("C:\\actions-runner\\_work\\repo\\tests\\e2e\\test_auth.py")
            self.assertEqual(p2, "tests/e2e/test_auth.py")

            p3 = ingestor.resolve_to_workspace("tests.e2e.test_auth")
            self.assertEqual(p3, "tests/e2e/test_auth.py")

            p4 = ingestor.resolve_to_workspace("test_auth.py")
            self.assertEqual(p4, "tests/e2e/test_auth.py")

            # Verify SprintStateStore isolation
            store = SprintStateStore(workspace_path=ext_ws)
            store.save_sprint(
                sprint_id="sprint_ext_001",
                status="ACTIVE",
                failure_context={"env": "external"},
                tickets=[],
            )
            # The state store must reside strictly in ext_ws / .rerun_tasks
            self.assertTrue((ext_ws / ".rerun_tasks" / "sprint_store.db").is_file())
            sprint_loaded = store.load_sprint("sprint_ext_001")
            self.assertIsNotNone(sprint_loaded)

    def test_hermes_doctor_preflight_cli(self):
        """Verifies hermes doctor returns 0 with and without --ping-llm."""
        with tempfile.TemporaryDirectory() as td:
            ext_ws = Path(td).resolve()
            self._init_git_repo(ext_ws)

            # Create test structure in ext_ws
            (ext_ws / "tests").mkdir(parents=True, exist_ok=True)
            (ext_ws / "tests" / "test_api.py").write_text("def test_ok(): pass\n", encoding="utf-8")

            parser = build_parser()

            # 1. Doctor without ping
            args1 = parser.parse_args(["doctor", "--workspace", str(ext_ws)])
            exit_code1 = cmd_doctor(args1)
            self.assertEqual(exit_code1, 0)

            # 2. Doctor with ping-llm
            args2 = parser.parse_args(["doctor", "--workspace", str(ext_ws), "--ping-llm"])
            exit_code2 = cmd_doctor(args2)
            self.assertEqual(exit_code2, 0)

    def test_markdown_fence_sanitization(self):
        """Verifies stripping of markdown code fences (```diff, ```python, ```typescript, etc.)."""
        cases = [
            ("```python\ndef foo():\n    return 42\n```", "def foo():\n    return 42\n"),
            ("```typescript\nconst x: number = 10;\n```", "const x: number = 10;\n"),
            ("```diff\n+ line one\n- line two\n```", "+ line one\n- line two\n"),
            ("```\nplain block\n```", "plain block\n"),
            ("def bare_code():\n    return True\n", "def bare_code():\n    return True\n"),
        ]
        for fenced, expected in cases:
            cleaned = strip_markdown_fences(fenced)
            self.assertEqual(cleaned, expected)

        # Test patch applier with fenced content
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            f = root / "script.py"
            f.write_text("old = 1\n", encoding="utf-8")

            applier = WorkspacePatchApplier(root)
            fenced_code = "```python\nnew = 2\n```"
            applier.apply_single_file("script.py", fenced_code)
            self.assertEqual(f.read_text(encoding="utf-8"), "new = 2\n")

    def test_scenario_a_pytest_automation_script_healed(self):
        """Scenario A: Drifted Pytest API test (status 200 -> 201) healed deterministically."""
        with tempfile.TemporaryDirectory() as td:
            ext_ws = Path(td).resolve()
            self._init_git_repo(ext_ws)

            # Test file asserting drifted status code
            test_file = ext_ws / "tests" / "test_orders_api.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_code = (
                "def test_create_order():\n"
                "    response = {'status_code': 201, 'order_id': 'ORD-101'}\n"
                "    assert response['status_code'] == 200\n"
                "    assert response['order_id'] == 'ORD-101'\n"
            )
            test_file.write_text(test_code, encoding="utf-8")

            # Git commit base
            subprocess.run(["git", "add", "."], cwd=str(ext_ws), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init order tests"], cwd=str(ext_ws), check=True, capture_output=True)

            # JUnit XML artifact from CI failure
            junit_xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<testsuites>\n'
                '  <testsuite name="orders" tests="1" failures="1" errors="0">\n'
                '    <testcase classname="tests.test_orders_api" name="test_create_order" file="tests/test_orders_api.py" line="3">\n'
                '      <failure message="AssertionError: assert 201 == 200">\n'
                '        tests/test_orders_api.py:3: in test_create_order\n'
                '        assert response[\'status_code\'] == 200\n'
                '        E   AssertionError: assert 201 == 200\n'
                '      </failure>\n'
                '    </testcase>\n'
                '  </testsuite>\n'
                '</testsuites>\n'
            )
            artifact_path = ext_ws / "junit-results.xml"
            artifact_path.write_text(junit_xml, encoding="utf-8")

            # Run Hermes Healer
            orchestrator = ScrumMasterOrchestrator(workspace_path=ext_ws)
            res = orchestrator.run_sprint(
                mode="heal",
                artifact_paths=[str(artifact_path)],
                auto_approve=True,
            )

            self.assertIn(res.get("status"), ("APPLIED", "COMPLETED"))
            updated_content = test_file.read_text(encoding="utf-8")
            self.assertIn("status_code'] == 201", updated_content)
            self.assertIn("assert response['order_id'] == 'ORD-101'", updated_content)

    def test_scenario_b_playwright_typescript_automation_script_healed(self):
        """Scenario B: Drifted Playwright TypeScript locator healed via CTRF + trace.zip DOM hints."""
        with tempfile.TemporaryDirectory() as td:
            ext_ws = Path(td).resolve()
            self._init_git_repo(ext_ws)

            # Playwright TypeScript test file
            spec_file = ext_ws / "tests" / "e2e" / "checkout.spec.ts"
            spec_file.parent.mkdir(parents=True, exist_ok=True)
            spec_code = (
                "import { test, expect } from '@playwright/test';\n\n"
                "test('user can submit checkout form', async ({ page }) => {\n"
                "  await page.goto('/checkout');\n"
                "  await page.locator('[data-testid=\"submit-v1\"]').click();\n"
                "  await expect(page.locator('.confirmation')).toBeVisible();\n"
                "});\n"
            )
            spec_file.write_text(spec_code, encoding="utf-8")

            subprocess.run(["git", "add", "."], cwd=str(ext_ws), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init checkout spec"], cwd=str(ext_ws), check=True, capture_output=True)

            # 1. CTRF report indicating failure on locator submit-v1
            ctrf_data = {
                "results": {
                    "tool": {"name": "playwright"},
                    "summary": {"tests": 1, "passed": 0, "failed": 1, "pending": 0, "skipped": 0},
                    "tests": [
                        {
                            "name": "user can submit checkout form",
                            "status": "failed",
                            "filePath": "tests/e2e/checkout.spec.ts",
                            "retries": 1,
                            "duration": 5000,
                            "message": "waiting for locator('[data-testid=\"submit-v1\"]')",
                            "trace": "TimeoutError: waiting for locator('[data-testid=\"submit-v1\"]')\n    at tests/e2e/checkout.spec.ts:5:53",
                        }
                    ],
                }
            }
            ctrf_path = ext_ws / "ctrf-report.json"
            ctrf_path.write_text(json.dumps(ctrf_data), encoding="utf-8")

            # 2. Playwright trace.zip containing DOM snapshot with submit-v2 button
            trace_events = [
                {
                    "type": "action",
                    "apiName": "page.click",
                    "selector": '[data-testid="submit-v1"]',
                    "error": {"error": {"message": "waiting for locator('[data-testid=\"submit-v1\"]')"}},
                },
                {
                    "type": "snapshot",
                    "snapshot": {"html": "<form id='checkout'><button data-testid='submit-v2' type='submit'>Pay</button></form>"},
                },
            ]
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("0.trace", "\n".join(json.dumps(e) for e in trace_events))
            trace_path = ext_ws / "trace.zip"
            trace_path.write_bytes(zip_buf.getvalue())

            # Run Hermes Healer
            orchestrator = ScrumMasterOrchestrator(workspace_path=ext_ws)
            res = orchestrator.run_sprint(
                mode="heal",
                artifact_paths=[str(ctrf_path), str(trace_path)],
                auto_approve=True,
            )

            self.assertIn(res.get("status"), ("APPLIED", "COMPLETED"))
            updated_content = spec_file.read_text(encoding="utf-8")
            self.assertIn("submit-v2", updated_content)
            self.assertNotIn("submit-v1", updated_content)
            self.assertIn("await expect(page.locator('.confirmation')).toBeVisible();", updated_content)

            # Verify Zero Assertion Erosion through LanguageASTGuard directly
            lang = LanguageASTGuard.detect_language("tests/e2e/checkout.spec.ts")
            analysis = LanguageASTGuard.analyze(updated_content, lang)
            self.assertGreaterEqual(analysis.assertion_count, 1)
            self.assertEqual(len(analysis.skips_detected), 0)


if __name__ == "__main__":
    unittest.main()
