"""
Hermes Tester Console — Blocked Write / Hostile Patch E2E Test (AG-9)
Drives the HostilePatch rejection workflow end-to-end:
1. Clicks HostilePatch in the inbox.
2. Runs governed heal pipeline.
3. Candidate patch attempts to introduce subprocess.run(..., shell=True).
4. Asserts SecurityBlastRadiusAgent halts execution and rejects with SEC-SUBPROCESS-001: shell=True.
5. Asserts the rail stopped at Security Blast Radius (Step 5).
6. Asserts error text is displayed in plain text on screen.
7. Asserts the Approve button is not on screen (hidden/removed).
8. Inspects temp workspace to verify zero files were modified and zero commits created.
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


class TestTesterConsoleBlocked(unittest.TestCase):
    """Playwright E2E test for AG-9 HostilePatch security rejection."""

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

    def test_hostile_patch_blocked_by_security_blast_radius(self):
        """End-to-end verification of SecurityBlastRadiusAgent blocking hostile shell=True proposal."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(self.base_url)
            self.assertIn("Hermes // Tester Console", page.title())

            # 1. Click HostilePatch row in inbox
            inbox_hostile = page.locator('[data-testid="inbox-item-hostile"]')
            self.assertTrue(inbox_hostile.is_visible())

            btn_run_hostile = page.locator('[data-testid="btn-run-hostile"]')
            btn_run_hostile.click()

            # Wait for sprint board rejection to register
            page.wait_for_selector('[data-testid="board-card-security"]', timeout=15000)

            # 2. Assert rail stopped at Security Blast Radius (Step 5)
            card_sec = page.locator('[data-testid="board-card-security"]')
            sec_text = card_sec.inner_text()
            self.assertIn("SecurityBlastRadiusAgent", sec_text)
            self.assertIn("REJECTED", sec_text)
            self.assertIn("SEC-SUBPROCESS-001", sec_text)
            self.assertIn("shell=True", sec_text)

            # 3. Assert Steps 6 and 7 are marked as blocked / not reached
            card_sandbox = page.locator('[data-testid="board-card-sandbox"]').inner_text()
            self.assertIn("BLOCKED", card_sandbox)

            card_staged = page.locator('[data-testid="board-card-staged"]').inner_text()
            self.assertIn("BLOCKED", card_staged)

            # 4. Assert the Approve button is NOT on screen (completely hidden/gone)
            btn_approve = page.locator('[data-testid="btn-approve"]')
            self.assertFalse(btn_approve.is_visible())

            # 5. Inspect temp workspace directly
            active_ws = demo_manager.get_latest_workspace()
            self.assertIsNotNone(active_ws)
            ws_path = active_ws.workspace_path

            # Verify git status is completely clean (zero untracked or modified files)
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(ws_path),
                capture_output=True,
                text=True,
            )
            self.assertEqual(status_res.stdout.strip(), "")

            # Verify git log has exactly 1 initial commit, 0 new commits
            log_res = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=str(ws_path),
                capture_output=True,
                text=True,
            )
            self.assertEqual(log_res.stdout.strip(), "1")

            # Verify service.py was NOT modified with shell=True
            service_code = (ws_path / "src" / "service.py").read_text(encoding="utf-8")
            self.assertNotIn("shell=True", service_code)
            self.assertNotIn("subprocess", service_code)

            browser.close()


if __name__ == "__main__":
    unittest.main()
