"""
Comprehensive Unit & Integration Test Suite for Option 4: Zero False-Green Verification
Validates:
1. Semantic Assertion Weakening Guard (AST v2): Value dilution, Exception broadening, Timeout masking.
2. Accessibility-First Locator Upgrading: Rejects nth-child, deep hierarchies, brittle XPath, hashed CSS.
3. Counterfactual Differential Verification: Proves tests fail against broken base code and catches vacuous heals.
4. ASTPatchGuard Unified Integration: End-to-end integration through dispatcher and QACriticAgent.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict
import unittest

from ast_patch_guard import ASTPatchGuard
from core.orchestrator.scrum_hierarchy import SubTaskTicket
from core.verification.accessibility_locator_guard import AccessibilityLocatorGuard
from core.verification.counterfactual_verifier import CounterfactualVerifier
from core.verification.semantic_assertion_guard import SemanticAssertionGuard
from qa_critic_reviewer import QACriticAgent


class TestSemanticAssertionGuardPython(unittest.TestCase):
    """Tests Python AST inspection for assertion weakening."""

    def test_value_dilution_assert_equal_to_is_not_none(self):
        existing = """
def test_user_role():
    user = get_user()
    assert user.role == "admin"
"""
        proposed = """
def test_user_role():
    user = get_user()
    assert user.role is not None
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/test_auth.py": proposed},
            existing_files={"tests/test_auth.py": existing},
        )
        self.assertFalse(res.valid)
        self.assertTrue(res.dilution_detected)
        self.assertEqual(len(res.findings), 1)
        self.assertEqual(res.findings[0].category, "VALUE_DILUTION")
        self.assertIn("user.role", res.findings[0].message)

    def test_value_dilution_assert_status_to_bare_truthy(self):
        existing = """
def test_checkout():
    res = post_checkout()
    assert res.status == 200
"""
        proposed = """
def test_checkout():
    res = post_checkout()
    assert res.status
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/test_checkout.py": proposed},
            existing_files={"tests/test_checkout.py": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "VALUE_DILUTION")

    def test_exception_broadening_pytest_raises(self):
        existing = """
import pytest

def test_unauthorized():
    with pytest.raises(PermissionError):
        access_vault()
"""
        proposed = """
import pytest

def test_unauthorized():
    with pytest.raises(Exception):
        access_vault()
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/test_vault.py": proposed},
            existing_files={"tests/test_vault.py": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "EXCEPTION_BROADENING")
        self.assertIn("PermissionError", res.findings[0].message)
        self.assertIn("Exception", res.findings[0].message)

    def test_timeout_masking_python_playwright(self):
        existing = """
def test_page_load(page):
    page.wait_for_selector(".dashboard", timeout=5000)
    assert page.is_visible(".dashboard")
"""
        proposed = """
def test_page_load(page):
    page.wait_for_selector(".dashboard", timeout=60000)
    assert page.is_visible(".dashboard")
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/test_ui.py": proposed},
            existing_files={"tests/test_ui.py": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "TIMEOUT_MASKING")
        self.assertIn("inflated from 5000ms to 60000ms", res.findings[0].message)

    def test_legitimate_assertion_heal_allowed(self):
        existing = """
def test_tax_calculation():
    tax = calculate_tax(100)
    assert tax == 10
"""
        proposed = """
def test_tax_calculation():
    tax = calculate_tax(100)
    assert tax == 15
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/test_tax.py": proposed},
            existing_files={"tests/test_tax.py": existing},
        )
        self.assertTrue(res.valid)
        self.assertFalse(res.dilution_detected)
        self.assertEqual(len(res.findings), 0)


class TestSemanticAssertionGuardJavaScript(unittest.TestCase):
    """Tests JS/TS matcher dilution, exception broadening, and timeout inflation."""

    def test_ts_value_dilution_toBe_to_toBeTruthy(self):
        existing = """
test('returns 200 ok', async () => {
    const res = await fetch('/api/user');
    expect(res.status).toBe(200);
});
"""
        proposed = """
test('returns 200 ok', async () => {
    const res = await fetch('/api/user');
    expect(res.status).toBeTruthy();
});
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/api.spec.ts": proposed},
            existing_files={"tests/api.spec.ts": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "VALUE_DILUTION")

    def test_ts_exception_broadening_toThrow(self):
        existing = """
test('throws auth error', () => {
    expect(() => login()).toThrow(AuthenticationError);
});
"""
        proposed = """
test('throws auth error', () => {
    expect(() => login()).toThrow();
});
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/auth.test.js": proposed},
            existing_files={"tests/auth.test.js": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "EXCEPTION_BROADENING")

    def test_ts_timeout_inflation(self):
        existing = """
test('dashboard loads', async ({ page }) => {
    await page.locator('#chart').click({ timeout: 4000 });
});
"""
        proposed = """
test('dashboard loads', async ({ page }) => {
    await page.locator('#chart').click({ timeout: 60000 });
});
"""
        res = SemanticAssertionGuard.evaluate_changes(
            {"tests/dash.spec.ts": proposed},
            existing_files={"tests/dash.spec.ts": existing},
        )
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].category, "TIMEOUT_MASKING")


class TestAccessibilityLocatorGuard(unittest.TestCase):
    """Tests rejection of brittle selectors and enforcement of accessible locators."""

    def test_reject_nth_child_selector(self):
        proposed = """
import { test, expect } from '@playwright/test';

test('submit order', async ({ page }) => {
    await page.locator('div.card > button:nth-child(2)').click();
    await expect(page.locator('.success')).toBeVisible();
});
"""
        res = AccessibilityLocatorGuard.audit_changes({"e2e/order.spec.ts": proposed})
        self.assertFalse(res.valid)
        self.assertTrue(res.brittle_detected)
        self.assertEqual(res.findings[0].pattern_type, "NTH_CHILD_OR_POSITIONAL")
        self.assertIn("getByRole", res.findings[0].suggested_upgrade)

    def test_reject_deep_tag_hierarchy(self):
        proposed = """
test('click item', async ({ page }) => {
    await page.locator('div > section > form > div > span > button').click();
});
"""
        res = AccessibilityLocatorGuard.audit_changes({"e2e/catalog.spec.ts": proposed})
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].pattern_type, "DEEP_TAG_HIERARCHY")

    def test_reject_brittle_xpath(self):
        proposed = """
test('navigate', async ({ page }) => {
    await page.locator('/html/body/div[1]/div[2]/button[1]').click();
});
"""
        res = AccessibilityLocatorGuard.audit_changes({"e2e/nav.spec.ts": proposed})
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].pattern_type, "BRITTLE_XPATH")

    def test_reject_hashed_css_in_js(self):
        proposed = """
test('select tab', async ({ page }) => {
    await page.locator('.css-1a2b3c').click();
});
"""
        res = AccessibilityLocatorGuard.audit_changes({"e2e/tabs.spec.ts": proposed})
        self.assertFalse(res.valid)
        self.assertEqual(res.findings[0].pattern_type, "HASHED_CLASS_NAME")

    def test_allow_semantic_accessible_locators(self):
        proposed = """
import { test, expect } from '@playwright/test';

test('accessible login', async ({ page }) => {
    await page.getByLabel('Email address').fill('admin@corp.internal');
    await page.getByPlaceholder('Password').fill('secret');
    await page.getByRole('button', { name: 'Log in' }).click();
    await page.getByTestId('dashboard-header').waitFor();
    await expect(page.getByText('Welcome back')).toBeVisible();
});
"""
        res = AccessibilityLocatorGuard.audit_changes({"e2e/login.spec.ts": proposed})
        self.assertTrue(res.valid)
        self.assertFalse(res.brittle_detected)
        self.assertEqual(len(res.findings), 0)

    def test_preserve_unchanged_legacy_selectors(self):
        existing = "await page.locator('div > span > button:nth-child(2)').click();"
        proposed = (
            "await page.locator('div > span > button:nth-child(2)').click();\n"
            "await page.getByRole('button', { name: 'Confirm' }).click();"
        )
        res = AccessibilityLocatorGuard.audit_changes(
            {"e2e/legacy.spec.ts": proposed},
            existing_files={"e2e/legacy.spec.ts": existing},
        )
        self.assertTrue(res.valid)


class TestCounterfactualVerifier(unittest.TestCase):
    """Tests differential verification: forward pass + counterfactual broken base fail."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "tests").mkdir(parents=True)

        # Baseline workspace state (Feature updated: get_status returns 201)
        (self.ws / "src" / "api.py").write_text("def get_status():\n    return 201\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_counterfactual_verified_on_discriminating_heal(self):
        # Healed test expects 201
        healed_test = """
from src.api import get_status

def test_status():
    assert get_status() == 201
"""
        # Baseline broken source returned 500
        baseline_broken = {"src/api.py": "def get_status():\n    return 500\n"}

        verifier = CounterfactualVerifier(workspace_root=self.ws)
        res = verifier.verify_differential(
            test_file="tests/test_api.py",
            healed_test_content=healed_test,
            baseline_source_files=baseline_broken,
        )

        self.assertTrue(res.verified)
        self.assertFalse(res.is_vacuous)
        self.assertTrue(res.forward_passed)
        self.assertTrue(res.counterfactual_failed)
        self.assertEqual(res.forward_exit_code, 0)
        self.assertNotEqual(res.counterfactual_exit_code, 0)
        self.assertIn("COUNTERFACTUAL_VERIFIED", res.summary)

    def test_counterfactual_catches_vacuous_heal(self):
        # Vacuous healed test that passes unconditionally (e.g. assert is not None)
        vacuous_test = """
from src.api import get_status

def test_status():
    val = get_status()
    assert val is not None
"""
        # Baseline broken source returned 500
        baseline_broken = {"src/api.py": "def get_status():\n    return 500\n"}

        verifier = CounterfactualVerifier(workspace_root=self.ws)
        res = verifier.verify_differential(
            test_file="tests/test_api.py",
            healed_test_content=vacuous_test,
            baseline_source_files=baseline_broken,
        )

        self.assertFalse(res.verified)
        self.assertTrue(res.is_vacuous)
        self.assertTrue(res.forward_passed)
        self.assertFalse(res.counterfactual_failed)  # Passed on broken code!
        self.assertEqual(res.forward_exit_code, 0)
        self.assertEqual(res.counterfactual_exit_code, 0)
        self.assertIn("COUNTERFACTUAL_FAILED", res.summary)
        self.assertIn("Vacuous test detected", res.reasons[0])

    def test_qa_critic_review_blocks_vacuous_heal(self):
        ticket = SubTaskTicket(
            ticket_id="TICK-099",
            title="Heal test_api failure",
            complexity=2,
            assigned_tier="TIER_3_AUTOMATION_TESTER",
            allowed_files=["tests/test_api.py"],
            acceptance_criteria=["Verify status response"],
        )
        vacuous_patch = {
            "tests/test_api.py": (
                "from src.api import get_status\n\n"
                "def test_status():\n"
                "    assert get_status() is not None\n"
            )
        }
        baseline_broken = {"src/api.py": "def get_status():\n    return 500\n"}

        review = QACriticAgent.review_worker_output(
            ticket=ticket,
            proposed_changes=vacuous_patch,
            allow_test_modification=True,
            workspace_path=self.ws,
            baseline_source_files=baseline_broken,
        )

        self.assertFalse(review.approved)
        self.assertIsNotNone(review.counterfactual_result)
        self.assertTrue(review.counterfactual_result["is_vacuous"])
        self.assertTrue(any("Vacuous test heal rejected" in r for r in review.rejection_reasons))


class TestASTPatchGuardOption4Integration(unittest.TestCase):
    """Verifies ASTPatchGuard dispatches Option 4 semantic and locator guards."""

    def test_ast_guard_blocks_weakened_assertion_proposal(self):
        existing = "def test_val():\n    assert obj.prop == 42\n"
        proposed = "def test_val():\n    assert obj.prop is not None\n"

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "tests").mkdir()
            (ws / "tests" / "test_val.py").write_text(existing, encoding="utf-8")

            report = ASTPatchGuard.analyze(
                workspace_root=ws,
                proposed_changes={"tests/test_val.py": proposed},
                allow_test_modification=True,
            )

            self.assertFalse(report["valid"])
            self.assertTrue(report["tampering_detected"])
            self.assertTrue(any("VALUE_DILUTION" in r for r in report["reasons"]))
            self.assertEqual(len(report["semantic_findings"]), 1)


if __name__ == "__main__":
    unittest.main()
