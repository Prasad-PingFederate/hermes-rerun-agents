"""
Hermes Tester Console — Session Persistence & Refresh Survival E2E Test (AG-10)
Validates that demo state persists across page reloads and process restarts:
1. Runs heal on InMemoryLedger and approves: status is APPLIED, snapshot is snap_xxx.
2. Reloads page (page.reload()): board still says APPLIED, showing same snapshot and diff.
3. Mid-sprint restart: kills uvicorn server mid-sprint, restarts on same port, reloads /: board is preserved.
4. Clean exit: demo_manager.cleanup_all() deletes all temporary workspace directories from disk.
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


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except Exception:
            time.sleep(0.1)
    return False


class TestTesterConsoleRefresh(unittest.TestCase):
    """Playwright E2E test for AG-10 session persistence across reloads and server restarts."""

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

        if not wait_for_server(cls.port):
            raise RuntimeError(f"Uvicorn server failed to start on port {cls.port}")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        demo_manager.cleanup_all()

    def test_1_reload_preserves_applied_state_and_snapshot(self):
        """Approve patch -> APPLIED -> reload page -> board still APPLIED with same snap_id and diff."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Open console
            page.goto(self.base_url)
            self.assertIn("Hermes // Tester Console", page.title())

            # 2. Run heal pipeline on ledger
            btn_run_heal = page.locator('[data-testid="btn-run-heal"]')
            btn_run_heal.click()

            page.wait_for_selector('[data-testid="board-card-staged"]', timeout=15000)

            # 3. Approve proposal
            nav_diff = page.locator('[data-testid="nav-diff"]')
            nav_diff.click()
            page.wait_for_selector('[data-testid="diff-container"]')

            btn_approve = page.locator('[data-testid="btn-approve"]')
            btn_approve.click()

            # Wait for APPLIED (status-green)
            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-green')",
                timeout=15000,
            )
            pill_status = page.locator('[data-testid="pill-status"]')
            self.assertIn("APPLIED", pill_status.inner_text())

            snap_display = page.locator('[data-testid="snapshot-id-display"]')
            snap_id_before = snap_display.inner_text().strip()
            self.assertTrue(snap_id_before.startswith("snap_"))

            diff_text_before = page.locator('[data-testid="diff-container"]').inner_text()
            self.assertIn("ValueError", diff_text_before)

            # 4. Reload page
            page.reload()
            page.wait_for_selector('[data-testid="pill-status"]', timeout=10000)

            # Verify board still says APPLIED (GREEN)
            pill_status_after = page.locator('[data-testid="pill-status"]')
            self.assertIn("APPLIED", pill_status_after.inner_text())

            # Verify same snapshot ID preserved
            snap_display_after = page.locator('[data-testid="snapshot-id-display"]')
            snap_id_after = snap_display_after.inner_text().strip()
            self.assertEqual(snap_id_before, snap_id_after)

            # Verify diff preserved
            nav_diff.click()
            page.wait_for_selector('[data-testid="diff-container"]')
            diff_text_after = page.locator('[data-testid="diff-container"]').inner_text()
            self.assertIn("ValueError", diff_text_after)

            # Verify active workspace test still passes
            active_ws = demo_manager.get_latest_workspace()
            self.assertIsNotNone(active_ws)
            test_res = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_ledger.py", "-v"],
                cwd=str(active_ws.workspace_path),
                capture_output=True,
                text=True,
            )
            self.assertEqual(test_res.returncode, 0)

            browser.close()

    def test_2_process_restart_mid_sprint_preserves_board(self):
        """Kill uvicorn server mid-sprint, restart on same port, reload /, board preserved and approvable."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(self.base_url)

            # Run heal on PlaywrightDrift
            inbox_drift = page.locator('[data-testid="inbox-item-drift"]')
            btn_run_drift = page.locator('[data-testid="btn-run-drift"]')
            btn_run_drift.click()

            page.wait_for_selector('[data-testid="board-card-staged"]', timeout=15000)
            page.wait_for_function(
                "() => document.getElementById('pill-status').innerText.includes('AWAITING')",
                timeout=15000,
            )
            pill_status = page.locator('[data-testid="pill-status"]')
            self.assertIn("AWAITING", pill_status.inner_text())

            # Stop the uvicorn server mid-sprint
            self.__class__.server.should_exit = True
            if self.__class__.server_thread.is_alive():
                self.__class__.server_thread.join(timeout=5)
            time.sleep(0.5)

            # Restart uvicorn server on the same port
            new_server = uvicorn.Server(self.__class__.server_config)
            self.__class__.server = new_server
            new_thread = threading.Thread(target=new_server.run, daemon=True)
            self.__class__.server_thread = new_thread
            new_thread.start()

            self.assertTrue(wait_for_server(self.__class__.port, timeout=10.0))

            # Reload page in browser
            page.reload()
            page.wait_for_function(
                "() => document.getElementById('pill-status').innerText.includes('AWAITING')",
                timeout=15000,
            )

            # Preserved state: still AWAITING approval
            reloaded_status = page.locator('[data-testid="pill-status"]').inner_text()
            self.assertIn("AWAITING", reloaded_status)

            # Diff is preserved
            nav_diff = page.locator('[data-testid="nav-diff"]')
            nav_diff.click()
            page.wait_for_selector('[data-testid="diff-container"]')
            diff_text = page.locator('[data-testid="diff-container"]').inner_text()
            self.assertIn("CONFIRMED", diff_text)

            # Approve on restarted server
            btn_approve = page.locator('[data-testid="btn-approve"]')
            btn_approve.click()

            page.wait_for_function(
                "() => document.getElementById('pill-status').className.includes('status-green')",
                timeout=15000,
            )
            self.assertIn("APPLIED", page.locator('[data-testid="pill-status"]').inner_text())

            browser.close()

    def test_3_cleanup_all_deletes_temp_directories(self):
        """cleanup_all() removes temporary workspace directories when demo exits."""
        # Ensure at least one workspace exists
        ws = demo_manager.create_ledger_workspace()
        self.assertTrue(ws.workspace_path.exists())

        demo_manager.cleanup_all()
        self.assertFalse(ws.workspace_path.exists())


if __name__ == "__main__":
    unittest.main()
