"""
Hermes v1.3.0 Feature Verification Suite
Covers:
1. CLI subcommands 'console' and 'eval'.
2. Cross-platform Linux/macOS POSIX subprocess hardening.
3. Real Workspace Mode API (doctor, workspace loading, snapshots, rollback, ZIP bundle).
4. Real Workspace Heal & Shadow Mode execution.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from hermes.cli import build_parser, cmd_doctor
from hermes.console.server import app, set_active_workspace, get_active_workspace_path
from hermes.console.console_demo_manager import demo_manager


class TestV130Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HERMES_API_TOKEN"] = "test-v130-token"
        cls.client = TestClient(app)
        cls.headers = {"X-Hermes-Token": "test-v130-token"}

    @classmethod
    def tearDownClass(cls):
        demo_manager.cleanup_all()

    def test_1_cli_console_and_eval_subcommands(self):
        """Verifies hermes console and hermes eval argument parsing."""
        parser = build_parser()

        # hermes console
        args_console = parser.parse_args([
            "console",
            "--workspace", "my_automation_repo",
            "--host", "0.0.0.0",
            "--port", "9090",
            "--no-browser",
        ])
        self.assertEqual(args_console.command, "console")
        self.assertEqual(args_console.workspace, "my_automation_repo")
        self.assertEqual(args_console.host, "0.0.0.0")
        self.assertEqual(args_console.port, 9090)
        self.assertTrue(args_console.no_browser)

        # hermes eval
        args_eval = parser.parse_args(["eval"])
        self.assertEqual(args_eval.command, "eval")

    def test_2_cross_platform_posix_subprocess_handling(self):
        """Verifies Node/Playwright and test runner detection handles POSIX shell=False safely."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            parser = build_parser()
            args = parser.parse_args(["doctor", "--workspace", str(ws)])

            # Mock shutil.which to simulate environment where node is present
            with patch("shutil.which", side_effect=lambda bin_name: f"/usr/bin/{bin_name}" if bin_name in ("node", "npx") else None):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="v20.0.0\n")
                    ret = cmd_doctor(args)
                    self.assertEqual(ret, 0)
                    self.assertTrue(mock_run.called)
                    # Verify subprocess was called with binary path
                    calls = [call[0][0] for call in mock_run.call_args_list if call[0]]
                    self.assertTrue(any("/usr/bin/node" in c or "/usr/bin/npx" in c for c in calls))

    def test_3_real_workspace_doctor_api(self):
        """Verifies GET /api/real/doctor returns complete cross-platform diagnostics."""
        res = self.client.get("/api/real/doctor", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("workspace_path", data)
        self.assertIn("os_name", data)
        self.assertIn("python_version", data)
        self.assertIn("llm_provider", data)
        self.assertIn("is_live_llm", data)
        self.assertIn("diagnostics", data)
        self.assertIn("tree_sitter", data["diagnostics"])

    def test_4_real_workspace_endpoints_and_zip_export(self):
        """Verifies switching workspaces, listing snapshots, and exporting audit ZIP."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            (ws / "src").mkdir()
            (ws / "src" / "sample.py").write_text("x = 1\n", encoding="utf-8")

            # 1. Switch to real workspace
            res_ws = self.client.post(
                "/api/real/workspace",
                json={"workspace": str(ws)},
                headers=self.headers,
            )
            self.assertEqual(res_ws.status_code, 200)
            ws_data = res_ws.json()
            self.assertEqual(ws_data["status"], "success")
            self.assertTrue(ws_data["workspace_id"].startswith("real_"))

            # 2. List snapshots
            res_snaps = self.client.get("/api/real/snapshots", headers=self.headers)
            self.assertEqual(res_snaps.status_code, 200)
            snaps_data = res_snaps.json()
            self.assertIn("snapshots", snaps_data)

            # 3. Download audit bundle ZIP
            res_zip = self.client.get("/api/real/audit/export-zip", headers=self.headers)
            self.assertEqual(res_zip.status_code, 200)
            self.assertEqual(res_zip.headers.get("content-type"), "application/zip")

            with zipfile.ZipFile(io.BytesIO(res_zip.content), "r") as z:
                names = z.namelist()
                self.assertIn("audit_trail.md", names)
                self.assertIn("report.sarif", names)
                self.assertIn("telemetry.json", names)
                self.assertIn("sprint_manifest.json", names)

    def test_5_real_workspace_heal_shadow_mode(self):
        """Verifies real workspace heal in shadow mode generates suggestion without modifying disk."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            src_dir = ws / "src"
            src_dir.mkdir()
            file_to_heal = src_dir / "calc.py"
            original_code = "def add(a, b):\n    return a - b\n"
            file_to_heal.write_text(original_code, encoding="utf-8")

            failure_output = "AssertionError: assert add(2, 2) == 4\nE AssertionError: 0 == 4"

            res = self.client.post(
                "/api/real/heal",
                json={
                    "workspace_path": str(ws),
                    "failure_output": failure_output,
                    "scope": ["src/calc.py"],
                    "shadow_mode": True,
                },
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 200)
            heal_data = res.json()
            self.assertIn("sprint_id", heal_data)

            # In shadow mode, the file on disk MUST NOT be modified
            current_code = file_to_heal.read_text(encoding="utf-8")
            self.assertEqual(current_code, original_code, "Shadow mode should not mutate files on disk")


if __name__ == "__main__":
    unittest.main()
