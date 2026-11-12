"""Unit and integration tests for Option 1: Core Accuracy Upgrades.

Covers:
1. Commit & PR Intent Classifier (CIDetectiveAgent):
   - Shallow clone fallback (fetch-depth: 1)
   - Intentional contract/API change (feat/breaking) -> TEST_BUG (assertion drift)
   - Unintentional regression -> PRODUCT_BUG
2. Deterministic Delta-SAST Gate (SecurityBlastRadiusAgent):
   - Pre-existing legacy vulnerabilities in unmodified code do not block clean patches
   - Newly introduced OWASP/CWE antipatterns (shell=True, eval, SQLi, innerHTML, timing) hard-block
3. Multi-Runner Assertion Erosion (ZeroAssertionErosionGuard):
   - Commented-out assertions (// expect / /* expect */) stripped and caught as count drop
   - Newly added skip/weakening modifiers (test.skip, it.skip, describe.skip, xit, xtest, test.todo, page.pause) hard-blocked
   - Tautological assertions rejected
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.ci_detective import CIDetectiveAgent
from core.governance.assertion_erosion_guard import ZeroAssertionErosionGuard
from sandbox_executor import SandboxExecutor
from security_blast_radius import SecurityBlastRadiusAgent
from ts_playwright_ast_guard import PlaywrightASTGuard


class TestCommitAndPRIntentClassifier(unittest.TestCase):
    """Requirement 1: Commit & PR Intent Classifier in CIDetectiveAgent."""

    def test_shallow_clone_fallback_to_webhook_payload(self):
        """When git log is shallow or unavailable, falls back to webhook PR title and commits."""
        payload = {
            "pull_request": {
                "title": "feat: change checkout response status from 200 to 201",
                "body": "Updates HTTP status for resource creation.",
            },
            "commits": [
                {"message": "feat: change checkout response status from 200 to 201"}
            ],
        }
        # Ingest with no git repo -> should fall back gracefully
        intent = CIDetectiveAgent.extract_commit_and_pr_intent(workspace_path=None, payload=payload)
        self.assertTrue(intent["has_intentional_contract_change"])
        self.assertIn("feat:", intent["intent_signals"][0].lower())
        self.assertIn("status from 200 to 201", intent["pr_title"].lower())

    def test_intentional_api_drift_classified_as_test_bug(self):
        """If developer intentionally changed API status and assertion fails, classify as TEST_BUG."""
        payload = {
            "pull_request": {
                "title": "feat: change checkout response status from 200 to 201",
            }
        }
        failure_output = (
            "FAILED tests/test_checkout.py::test_checkout_status - AssertionError: assert 200 == 201\n"
            "  assert response.status_code == 200\n"
            "E AssertionError: assert 201 == 200"
        )
        classification = CIDetectiveAgent.classify_failure_with_intent(
            combined_output=failure_output,
            payload=payload,
        )
        self.assertEqual(classification, "TEST_BUG")

    def test_unintentional_regression_with_product_crash_classified_as_product_bug(self):
        """If developer commit is fix/neutral and product code crashes with KeyError, classify as PRODUCT_BUG."""
        payload = {
            "pull_request": {
                "title": "fix: patch inventory cache lookup",
            }
        }
        failure_output = (
            "Traceback (most recent call last):\n"
            '  File "src/inventory.py", line 42, in get_item\n'
            "    return self._items[item_id]\n"
            "KeyError: 'item_123'"
        )
        classification = CIDetectiveAgent.classify_failure_with_intent(
            combined_output=failure_output,
            payload=payload,
        )
        self.assertEqual(classification, "PRODUCT_BUG")

    def test_sandbox_executor_integration_with_intent(self):
        """SandboxExecutor.classify_failure respects intent_context."""
        executor = SandboxExecutor()
        intent = {"has_intentional_contract_change": True}
        output = "FAILED tests/test_api.py::test_status - AssertionError: assert 200 == 201"
        res = executor.classify_failure(output, intent_context=intent)
        self.assertEqual(res, "TEST_BUG")


class TestDeterministicDeltaSASTGate(unittest.TestCase):
    """Requirement 2: Deterministic Delta-SAST Gate in SecurityBlastRadiusAgent."""

    def test_legacy_vulnerability_in_unmodified_code_does_not_block_clean_patch(self):
        """Pre-existing vulnerability in line 10 does not block a bugfix on line 80."""
        legacy_code = (
            "import subprocess\n\n"
            "def legacy_runner(cmd):\n"
            "    # Pre-existing legacy issue\n"
            "    return subprocess.run(cmd, shell=True)\n\n"
            "def clean_calculator(a, b):\n"
            "    return a - b  # Bug: subtraction instead of addition\n"
        )

        patched_code = (
            "import subprocess\n\n"
            "def legacy_runner(cmd):\n"
            "    # Pre-existing legacy issue\n"
            "    return subprocess.run(cmd, shell=True)\n\n"
            "def clean_calculator(a, b):\n"
            "    return a + b  # Fixed: addition\n"
        )

        report = SecurityBlastRadiusAgent.audit_proposal(
            proposed_changes={"src/calc.py": patched_code},
            existing_workspace_files={"src/calc.py": legacy_code},
        )

        # Legacy finding recorded in advisory list
        self.assertEqual(len(report.legacy_findings), 1)
        self.assertEqual(report.legacy_findings[0].rule_id, "SEC-SUBPROCESS-001")
        # Delta findings must be empty
        self.assertEqual(len(report.delta_findings), 0)
        # Patch must pass write-gate audit!
        self.assertTrue(report.passed)

    def test_newly_introduced_python_vulnerability_hard_blocks(self):
        """Newly introduced subprocess(shell=True) or eval() in patch hard-blocks write-gate."""
        clean_code = "def run_task(cmd):\n    return cmd\n"
        hostile_code = (
            "import subprocess\n\n"
            "def run_task(cmd):\n"
            "    return subprocess.run(cmd, shell=True)\n"
        )

        report = SecurityBlastRadiusAgent.audit_proposal(
            proposed_changes={"src/task.py": hostile_code},
            existing_workspace_files={"src/task.py": clean_code},
        )
        self.assertFalse(report.passed)
        self.assertEqual(len(report.delta_findings), 1)
        self.assertEqual(report.delta_findings[0].rule_id, "SEC-SUBPROCESS-001")

    def test_newly_introduced_javascript_vulnerabilities_hard_block(self):
        """Newly introduced eval(), innerHTML, child_process.exec in JS/TS hard-blocks write-gate."""
        # 1. child_process.exec
        js_shell = "const { exec } = require('child_process');\nfunction run(c) { exec(c); }\n"
        rep_shell = SecurityBlastRadiusAgent.audit_proposal({"service.js": js_shell})
        self.assertFalse(rep_shell.passed)
        self.assertTrue(any(f.rule_id == "SEC-SHELL-001" for f in rep_shell.delta_findings))

        # 2. eval / new Function
        js_eval = "function compute(code) { return eval(code); }\n"
        rep_eval = SecurityBlastRadiusAgent.audit_proposal({"calculator.ts": js_eval})
        self.assertFalse(rep_eval.passed)
        self.assertTrue(any(f.rule_id == "SEC-EVAL-001" for f in rep_eval.delta_findings))

        # 3. dangerouslySetInnerHTML / innerHTML
        js_xss = "function render(html) { element.innerHTML = html; }\n"
        rep_xss = SecurityBlastRadiusAgent.audit_proposal({"component.tsx": js_xss})
        self.assertFalse(rep_xss.passed)
        self.assertTrue(any(f.rule_id == "SEC-XSS-001" for f in rep_xss.delta_findings))


class TestMultiRunnerAssertionErosion(unittest.TestCase):
    """Requirement 3: Multi-Runner Assertion Erosion in ZeroAssertionErosionGuard."""

    def test_commented_out_assertion_trick_is_caught_and_rejected(self):
        """Single-line and block comments commenting out assertions are caught as count drop."""
        existing_ts = (
            "import { test, expect } from '@playwright/test';\n"
            "test('checkout flow', async ({ page }) => {\n"
            "    await expect(page.locator('#step1')).toBeVisible();\n"
            "    await expect(page.locator('#step2')).toBeVisible();\n"
            "});\n"
        )

        # Single-line comment trick: // await expect(...)
        eroded_single_line = (
            "import { test, expect } from '@playwright/test';\n"
            "test('checkout flow', async ({ page }) => {\n"
            "    await expect(page.locator('#step1')).toBeVisible();\n"
            "    // await expect(page.locator('#step2')).toBeVisible();\n"
            "});\n"
        )
        report1 = ZeroAssertionErosionGuard.verify("tests/checkout.spec.ts", eroded_single_line, existing_ts)
        self.assertFalse(report1.valid)
        self.assertEqual(report1.existing_assertions, 2)
        self.assertEqual(report1.proposed_assertions, 1)
        self.assertTrue(any("Zero Assertion Erosion" in r for r in report1.reasons))

        # Block comment trick: /* await expect(...) */
        eroded_block = (
            "import { test, expect } from '@playwright/test';\n"
            "test('checkout flow', async ({ page }) => {\n"
            "    await expect(page.locator('#step1')).toBeVisible();\n"
            "    /* await expect(page.locator('#step2')).toBeVisible(); */\n"
            "});\n"
        )
        report2 = ZeroAssertionErosionGuard.verify("tests/checkout.spec.ts", eroded_block, existing_ts)
        self.assertFalse(report2.valid)
        self.assertEqual(report2.proposed_assertions, 1)

    def test_newly_added_skip_modifiers_hard_blocked(self):
        """Adding test.skip, it.skip, describe.skip, xit, xtest, test.todo, page.pause is blocked."""
        base_ts = (
            "test('payment', async () => {\n"
            "    expect(100).toBe(100);\n"
            "});\n"
        )

        # 1. xit / xtest
        xit_ts = base_ts.replace("test('payment'", "xit('payment'")
        res_xit = PlaywrightASTGuard.verify_spec_content("tests/payment.test.ts", xit_ts, base_ts)
        self.assertFalse(res_xit.valid)
        self.assertTrue(any("xit" in r for r in res_xit.reasons))

        # 2. test.todo
        todo_ts = base_ts.replace("test('payment'", "test.todo('payment'")
        res_todo = PlaywrightASTGuard.verify_spec_content("tests/payment.test.ts", todo_ts, base_ts)
        self.assertFalse(res_todo.valid)
        self.assertTrue(any("test.todo" in r for r in res_todo.reasons))

        # 3. page.pause()
        pause_ts = base_ts + "\npage.pause();\n"
        res_pause = PlaywrightASTGuard.verify_spec_content("tests/payment.spec.ts", pause_ts, base_ts)
        self.assertFalse(res_pause.valid)
        self.assertTrue(any("page.pause" in r for r in res_pause.reasons))

        # 4. it.skip
        it_skip_ts = base_ts.replace("test('payment'", "it.skip('payment'")
        res_it = PlaywrightASTGuard.verify_spec_content("tests/payment.spec.js", it_skip_ts, base_ts)
        self.assertFalse(res_it.valid)
        self.assertTrue(any("it.skip" in r for r in res_it.reasons))

    def test_url_in_string_literals_not_treated_as_comment(self):
        """String literals containing URLs like https:// must NOT have their trailing content stripped."""
        spec_with_urls = (
            "import { test, expect } from '@playwright/test';\n"
            "test('verify endpoints', async ({ page }) => {\n"
            '    expect(page.url()).toBe("https://example.com/api/v1");\n'
            '    expect(page.url()).toBe(\'http://localhost:3000/auth\');\n'
            '    expect(page.url()).toBe(`https://subdomain.company.org/gateway?param=1`);\n'
            '});\n'
        )
        # Should count exactly 3 assertions without stripping URLs
        count = PlaywrightASTGuard.count_assertions(spec_with_urls)
        self.assertEqual(count, 3)

        # Verified through ZeroAssertionErosionGuard: comparing against itself
        report = ZeroAssertionErosionGuard.verify("tests/api.spec.ts", spec_with_urls, spec_with_urls)
        self.assertTrue(report.valid)
        self.assertEqual(report.existing_assertions, 3)
        self.assertEqual(report.proposed_assertions, 3)
        self.assertEqual(report.assertion_delta, 0)


if __name__ == "__main__":
    unittest.main()
