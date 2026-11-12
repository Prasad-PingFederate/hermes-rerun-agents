"""Unit tests for Multi-Runner Extensibility (Jest, Playwright, Pytest)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from core.runners.runner_detector import detect_runner, parse_test_failure


class TestMultiRunner(unittest.TestCase):
    """Verify test runner detection and failure parsing across runners."""

    def test_detect_playwright_runner(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "playwright.config.ts").write_text("export default {};", encoding="utf-8")
            res = detect_runner(p)
            self.assertEqual(res["runner_name"], "playwright")
            self.assertEqual(res["command"], ["npx", "playwright", "test"])
            self.assertEqual(res["config_file"], "playwright.config.ts")

    def test_detect_jest_runner_via_config(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "jest.config.js").write_text("module.exports = {};", encoding="utf-8")
            res = detect_runner(p)
            self.assertEqual(res["runner_name"], "jest")
            self.assertEqual(res["command"], ["npx", "jest"])
            self.assertEqual(res["config_file"], "jest.config.js")

    def test_detect_jest_runner_via_package_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            pkg = {
                "name": "cart-service",
                "scripts": {"test": "jest"},
                "devDependencies": {"jest": "^29.0.0"},
            }
            (p / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
            res = detect_runner(p)
            self.assertEqual(res["runner_name"], "jest")

    def test_detect_pytest_runner_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "tests").mkdir()
            (p / "tests" / "test_app.py").write_text("def test_ok(): pass", encoding="utf-8")
            res = detect_runner(p)
            self.assertEqual(res["runner_name"], "pytest")
            self.assertIn("pytest", res["command"][-2])

    def test_parse_environment_noise_failure(self):
        output = (
            "Traceback (most recent call last):\n"
            "ConnectionRefusedError: [Errno 111] Connection refused on 127.0.0.1:5432\n"
        )
        res = parse_test_failure("pytest", output)
        self.assertEqual(res["classification"], "ENVIRONMENT_NOISE")
        self.assertEqual(res["error_type"], "ConnectionRefused / ServiceOffline")

    def test_parse_flaky_test_failure(self):
        output = (
            "Error: Timeout 3000ms waiting for locator button#checkout\n"
            "Outcome: FLAKY_TEST (Intermittent locator timing instability)\n"
        )
        res = parse_test_failure("playwright", output)
        self.assertEqual(res["classification"], "FLAKY_TEST")

    def test_parse_jest_failure(self):
        output = (
            "FAIL src/cart.test.js\n"
            "  ● Shopping Cart › calculates discount\n"
            "    expect(received).toBe(expected)\n"
            "    Expected: 100\n"
            "    Received: 120\n"
        )
        res = parse_test_failure("jest", output)
        self.assertEqual(res["classification"], "PRODUCT_BUG")
        self.assertIn("src/cart.test.js", res["failing_test"])


if __name__ == "__main__":
    unittest.main()

