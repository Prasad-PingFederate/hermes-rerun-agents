"""
Hermes Tester Console — Playwright Drift (Test Bug) E2E Test (AG-8)
Drives the PlaywrightDrift workflow end-to-end:
1. Selects PlaywrightDrift in the inbox.
2. Runs governed heal pipeline.
3. Asserts owner is TestHealerAgent and DeveloperAgent is visibly unavailable.
4. Asserts scope is strictly tests/test_cart.py.
5. Approves -> test turns green.
6. Verifies src/cart.py remains byte-for-byte identical before and after.
7. Rewinds -> test turns red again and drifted assertion is restored.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import server
from console_demo_manager import demo_manager


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestTesterConsoleTestBug(unittest.TestCase):
    """Playwright E2E test for AG-8 PlaywrightDrift healing."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_config = uvicorn.Config(
            app=server.app,
            host="127.0.0.1",
            port=cls.port,
            log_level="warning",
        )
        cls.server = uvicorn.Server(cls.server_config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        deadline = time.time() + 10
        ready = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=1):
                    ready = True
                    break
            except Exception:
                time.sleep(0.1)

        if not ready:
            raise RuntimeError(f"Uvicorn server failed to start on port {cls.port}")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        demo_manager.cleanup_all()

    def test_playwright_drift_healed_by_test_healer_agent(self):
        """End-to-end test bug healing by TestHealerAgent with zero product modification."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(self.base_url)
            self.assertIn("Hermes // Tester Console", page.title())

            # 1. Click drift item in inbox
            inbox_drift = page.locator('[data-testid="inbox-item-drift"]')
            self.assertTrue(inbox_drift.is_visible())

            # Verify badge shows TEST_BUG
            badge_test = page.locator('[data-testid="badge-test-bug"]')
            self.assertEqual(badge_test.inner_text().strip(), "TEST_BUG")

            # Verify DeveloperAgent is visibly unavailable on this card
            badge_dev_prohibited = page.locator('[data-testid="badge-dev-prohibited"]')
            self.assertTrue(badge_dev_prohibited.is_visible())
            self.assertIn("DeveloperAgent Visibly Unavailable", badge_dev_prohibited.inner_text())

            # 2. Run Heal Pipeline for PlaywrightDrift
            btn_run_drift = page.locator('[data-testid="btn-run-drift"]')
            btn_run_drift.click()

            # Wait for sprint board cards
            page.wait_for_selector('[data-testid="board-card-classify"]', timeout=15000)
            page.wait_for_selector('[data-testid="board-card-route"]')
            page.wait_for_selector('[data-testid="board-card-proposal"]')
            page.wait_for_selector('[data-testid="board-card-staged"]')

            # 3. Check owner is TestHealerAgent and DeveloperAgent prohibited
            card_route = page.locator('[data-testid="board-card-route"]').inner_text()
            self.assertIn("TestHealerAgent", card_route)
            self.assertIn("DeveloperAgent visibly unavailable", card_route)

            card_worker = page.locator('[data-testid="board-card-proposal"]').inner_text()
            self.assertIn("TestHealerAgent", card_worker)

            # Retrieve active demo workspace path to verify src/cart.py bytes
            active_ws = demo_manager.get_latest_workspace()
            self.assertIsNotNone(active_ws)
            cart_py = active_ws.workspace_path / "src" / "cart.py"
            test_cart_py = active_ws.workspace_path / "tests" / "test_cart.py"
            self.assertTrue(cart_py.exists())
            self.assertTrue(test_cart_py.exists())

            cart_bytes_before = cart_py.read_bytes()

            # 4. Review Staged Diff
            nav_diff = page.locator('[data-testid="nav-diff"]')
            nav_diff.click()
            diff_container = page.locator('[data-testid="diff-container"]')
            page.wait_for_selector('[data-testid="diff-container"]')
            diff_text = diff_container.inner_text()
            self.assertIn("ORDER_CONFIRMED", diff_text)
            self.assertIn("CONFIRMED", diff_text)

            # 5. Approve proposal
            btn_approve = page.locator('[data-testid="btn-approve"]')
            btn_approve.click()

            # Wait for status to turn APPLIED (GREEN)
            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-green')",
                timeout=15000,
            )
            pill_status = page.locator('[data-testid="pill-status"]')
            self.assertIn("APPLIED", pill_status.inner_text())

            # 6. Verify src/cart.py is byte-for-byte identical before and after
            cart_bytes_after = cart_py.read_bytes()
            self.assertEqual(cart_bytes_before, cart_bytes_after)

            # Verify tests/test_cart.py now has ORDER_CONFIRMED and test passes
            test_res = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_cart.py", "-v"],
                cwd=str(active_ws.workspace_path),
                capture_output=True,
                text=True,
            )
            self.assertEqual(test_res.returncode, 0)
            self.assertIn("passed", test_res.stdout)

            # 7. Rewind Workspace
            btn_rewind = page.locator('[data-testid="btn-rewind"]')
            btn_rewind.click()

            # Wait for status to turn ROLLED_BACK (RED)
            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-red')",
                timeout=15000,
            )
            self.assertIn("ROLLED_BACK", pill_status.inner_text())

            # Verify test fails again (red)
            post_rewind_res = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_cart.py", "-v"],
                cwd=str(active_ws.workspace_path),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(post_rewind_res.returncode, 0)
            self.assertIn("AssertionError", post_rewind_res.stdout)

            # And src/cart.py is STILL byte-for-byte identical
            self.assertEqual(cart_bytes_before, cart_py.read_bytes())

            browser.close()


if __name__ == "__main__":
    unittest.main()
