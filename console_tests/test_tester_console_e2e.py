"""
Hermes Tester Console — Playwright Product E2E Specification (AG-5)
Tests the complete 6-step QA Lead / Investor Demo against a live uvicorn server:
1. Failure Inbox: InMemoryLedger test failing (PRODUCT_BUG, DeveloperAgent, src/ only)
2. Run heal: Governed multi-agent board fills in order
3. Staged diff: Negative amount guard with zero assertion erosion
4. Approve & verify: Test turns green, snapshot id on screen -> capture board_green.png
5. Rewind: Microsecond rollback restores baseline bug, test turns red -> capture board_rolled_back.png
6. Audit Drawer: Structured audit trail inspection and copy-as-markdown
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import server


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestTesterConsoleE2E(unittest.TestCase):
    """Playwright E2E product test for Hermes Tester Console."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Screenshots directory
        cls.artifacts_dir = REPO_ROOT / "artifacts" / "screenshots"
        cls.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Run uvicorn in background thread
        cls.server_config = uvicorn.Config(
            app=server.app,
            host="127.0.0.1",
            port=cls.port,
            log_level="warning",
        )
        cls.server = uvicorn.Server(cls.server_config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # Wait for server to accept connections
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
        server.demo_manager.cleanup_all()

    def test_complete_investor_and_tester_90_second_demo_flow(self):
        """The single happy path: Seeded failure -> Heal -> Green -> Rewind -> Red."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # -------------------------------------------------------------
            # STEP 1: Open Console Shell (AG-1 & AG-2)
            # -------------------------------------------------------------
            page.goto(self.base_url)
            self.assertIn("Hermes // Tester Console", page.title())

            # Verify Inbox shows InMemoryLedger with PRODUCT_BUG
            page.wait_for_selector('[data-testid="inbox-item-ledger"]')
            badge_prod = page.locator('[data-testid="badge-product-bug"]')
            self.assertTrue(badge_prod.is_visible())
            self.assertEqual(badge_prod.inner_text().strip(), "PRODUCT_BUG")

            # Verify AG-6 second fixture: PlaywrightDrift with TEST_BUG
            badge_test = page.locator('[data-testid="badge-test-bug"]')
            self.assertTrue(badge_test.is_visible())
            self.assertEqual(badge_test.inner_text().strip(), "TEST_BUG")

            # Verify initial status is FAILING (RED)
            pill_status = page.locator('[data-testid="pill-status"]')
            self.assertIn("FAILING", pill_status.inner_text())

            # -------------------------------------------------------------
            # STEP 2 & 3: Click 'Run Heal' and Observe Board (AG-3)
            # -------------------------------------------------------------
            btn_run_heal = page.locator('[data-testid="btn-run-heal"]')
            btn_run_heal.click()

            # Wait for board cards to populate in order
            page.wait_for_selector('[data-testid="board-card-classify"]', timeout=15000)
            page.wait_for_selector('[data-testid="board-card-route"]')
            page.wait_for_selector('[data-testid="board-card-proposal"]')
            page.wait_for_selector('[data-testid="board-card-critic"]')
            page.wait_for_selector('[data-testid="board-card-security"]')
            page.wait_for_selector('[data-testid="board-card-sandbox"]')
            page.wait_for_selector('[data-testid="board-card-staged"]')

            # -------------------------------------------------------------
            # STEP 4: Staged Diff Review (AG-4)
            # -------------------------------------------------------------
            nav_diff = page.locator('[data-testid="nav-diff"]')
            nav_diff.click()

            diff_container = page.locator('[data-testid="diff-container"]')
            page.wait_for_selector('[data-testid="diff-container"]')
            diff_text = diff_container.inner_text()
            self.assertTrue("amount <= 0" in diff_text or "ValueError" in diff_text)
            self.assertIn("Test assertions preserved (2/2)", diff_text)

            # -------------------------------------------------------------
            # STEP 5: Approve & Verify Sandbox (AG-4) -> Turns Green
            # -------------------------------------------------------------
            btn_approve = page.locator('[data-testid="btn-approve"]')
            btn_approve.click()

            # Wait for status pill to turn APPLIED (GREEN)
            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-green')",
                timeout=15000,
            )
            self.assertIn("APPLIED", pill_status.inner_text())

            # Confirm Snapshot ID is rendered on screen
            snap_display = page.locator('[data-testid="snapshot-id-display"]')
            snap_id = snap_display.inner_text().strip()
            self.assertTrue(snap_id.startswith("snap_"))

            # Save Screenshot 1: Green Board
            green_shot_path = self.artifacts_dir / "board_green.png"
            page.screenshot(path=str(green_shot_path), full_page=True)
            self.assertTrue(green_shot_path.exists())

            # -------------------------------------------------------------
            # STEP 6: Rewind Workspace via Time Machine (AG-4) -> Turns Red
            # -------------------------------------------------------------
            btn_rewind = page.locator('[data-testid="btn-rewind"]')
            btn_rewind.click()

            # Wait for status pill to return to ROLLED_BACK (RED)
            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-red')",
                timeout=15000,
            )
            self.assertIn("ROLLED_BACK", pill_status.inner_text())

            # Save Screenshot 2: Rolled-back Board
            rollback_shot_path = self.artifacts_dir / "board_rolled_back.png"
            page.screenshot(path=str(rollback_shot_path), full_page=True)
            self.assertTrue(rollback_shot_path.exists())

            # -------------------------------------------------------------
            # STEP 7: Audit Drawer Inspection & Markdown Copy (AG-6)
            # -------------------------------------------------------------
            btn_audit = page.locator('[data-testid="btn-audit"]')
            btn_audit.click()

            page.wait_for_selector('[data-testid="audit-drawer"]')
            audit_drawer = page.locator('[data-testid="audit-drawer"]')
            self.assertTrue(audit_drawer.is_visible())
            self.assertIn("HERMES SPRINT AUDIT REPORT", audit_drawer.inner_text())

            btn_copy = page.locator('[data-testid="btn-copy-markdown"]')
            self.assertTrue(btn_copy.is_visible())

            browser.close()


if __name__ == "__main__":
    unittest.main()
