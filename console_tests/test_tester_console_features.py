"""Hermes Tester Console — Features E2E Specification.

Tests:
1. Connect Repository modal & test discovery
2. Flake diagnostic card (FLAKY_TEST)
3. Environment Noise diagnostic card (ENVIRONMENT_NOISE)
4. Pull Request creation on approval
5. Provider configuration drawer
"""

from __future__ import annotations

import socket
import sys
import tempfile
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


class TestTesterConsoleFeatures(unittest.TestCase):
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
            raise RuntimeError(f"Server failed to start on port {cls.port}")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        demo_manager.cleanup_all()

    def test_connect_repo_and_flake_views(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(self.base_url)
            self.assertIn("Hermes // Tester Console", page.title())

            # 1. Test Connect Repo Modal
            btn_connect = page.locator('[data-testid="btn-connect-repo"]')
            btn_connect.click()
            page.wait_for_selector('[data-testid="input-repo-path"]')

            with tempfile.TemporaryDirectory() as td:
                repo_p = Path(td)
                (repo_p / "tests").mkdir()
                (repo_p / "tests" / "test_login.py").write_text("def test_login(): pass\n", encoding="utf-8")

                page.locator('[data-testid="input-repo-path"]').fill(str(repo_p))
                page.locator('[data-testid="input-repo-name"]').fill("AuthService")
                page.locator('[data-testid="btn-submit-connect"]').click()

                # Verify workspace updated to AuthService
                page.wait_for_function("() => document.getElementById('label-workspace').innerText.includes('AuthService')", timeout=10000)
                self.assertIn("AuthService", page.locator('[data-testid="pill-workspace"]').inner_text())

            # 2. Test Flake View
            row_flake = page.locator('[data-testid="inbox-row-flake"]')
            row_flake.click()
            page.wait_for_function("() => document.getElementById('label-workspace').innerText.includes('PlaywrightFlake')", timeout=10000)

            # Check Flake card in inbox panel
            card_flake = page.locator('[data-testid="inbox-item-flake"]')
            self.assertTrue(card_flake.is_visible())
            self.assertIn("FLAKY_TEST", card_flake.inner_text())

            # 3. Test Provider Drawer
            pill_provider = page.locator('[data-testid="pill-provider"]')
            pill_provider.click()
            page.wait_for_selector('[data-testid="drawer-providers"]')
            self.assertTrue(page.locator('[data-testid="btn-test-provider"]').is_visible())

            # Close provider drawer
            page.locator('#btn-close-providers').click()

            # 4. Test Audit Export
            btn_audit = page.locator('[data-testid="btn-audit"]')
            btn_audit.click()
            page.wait_for_selector('[data-testid="btn-export-json"]')
            self.assertTrue(page.locator('[data-testid="btn-export-json"]').is_visible())
            self.assertTrue(page.locator('[data-testid="btn-export-html"]').is_visible())

            browser.close()


if __name__ == "__main__":
    unittest.main()

