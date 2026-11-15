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

    def test_6_real_workspace_discovery_and_runner(self):
        """Verifies GET /api/real/discover and POST /api/real/run-test on workspace."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            test_dir = ws / "tests"
            test_dir.mkdir()
            test_file = test_dir / "test_simple.py"
            test_file.write_text("def test_ok(): assert 1 == 1\n", encoding="utf-8")

            # Also create an artifact
            artifact_file = ws / "junit_report.xml"
            artifact_file.write_text("<testsuites></testsuites>", encoding="utf-8")

            # Switch workspace
            self.client.post("/api/real/workspace", json={"workspace": str(ws)}, headers=self.headers)

            # Discover
            res_disc = self.client.get("/api/real/discover", headers=self.headers)
            self.assertEqual(res_disc.status_code, 200)
            disc_data = res_disc.json()
            self.assertEqual(disc_data["status"], "success")
            self.assertGreaterEqual(disc_data["test_count"], 1)
            self.assertTrue(any(t["rel_path"] == "tests/test_simple.py" for t in disc_data["tests"]))
            self.assertGreaterEqual(disc_data["artifact_count"], 1)

            # Run test
            res_run = self.client.post(
                "/api/real/run-test",
                json={"test_path": "tests/test_simple.py"},
                headers=self.headers,
            )
            self.assertEqual(res_run.status_code, 200)
            run_data = res_run.json()
            self.assertTrue(run_data["passed"])
            self.assertEqual(run_data["returncode"], 0)

    def test_7_real_workspace_validate_ast_endpoint(self):
        """Verifies POST /api/real/validate-ast detects syntax errors and prohibited constructs."""
        # 1. Clean valid Python code
        res_ok = self.client.post(
            "/api/real/validate-ast",
            json={"code": "def valid():\n    return 42\n", "filepath": "clean.py"},
            headers=self.headers,
        )
        self.assertEqual(res_ok.status_code, 200)
        data_ok = res_ok.json()
        self.assertTrue(data_ok["valid"])
        self.assertIsNone(data_ok["error"])

        # 2. Syntax error
        res_bad = self.client.post(
            "/api/real/validate-ast",
            json={"code": "def syntax_err(\n    return 42\n", "filepath": "bad.py"},
            headers=self.headers,
        )
        self.assertEqual(res_bad.status_code, 200)
        data_bad = res_bad.json()
        self.assertFalse(data_bad["valid"])

        # 3. Security violation: shell=True
        res_sec = self.client.post(
            "/api/real/validate-ast",
            json={"code": "import subprocess\ndef hack():\n    subprocess.run('echo hello', shell=True)\n", "filepath": "sec.py"},
            headers=self.headers,
        )
        self.assertEqual(res_sec.status_code, 200)
        data_sec = res_sec.json()
        self.assertFalse(data_sec["valid"])
        self.assertTrue(data_sec["tampering_detected"])

    def test_8_real_workspace_locator_audit_endpoint(self):
        """Verifies POST /api/real/locator-audit scores resilience and suggests Playwright upgrades."""
        # 1. Brittle CSS ID
        res_brittle = self.client.post(
            "/api/real/locator-audit",
            json={"selector": "button#checkout", "is_python": True},
            headers=self.headers,
        )
        self.assertEqual(res_brittle.status_code, 200)
        data_brittle = res_brittle.json()
        self.assertTrue(data_brittle["is_brittle"])
        self.assertLessEqual(data_brittle["resilience_score"], 50)
        self.assertIn("get_by_role", data_brittle["upgraded_python"])
        self.assertGreaterEqual(len(data_brittle["alternatives"]), 2)

        # 2. Positional nth-child
        res_nth = self.client.post(
            "/api/real/locator-audit",
            json={"selector": "div > form > button:nth-child(2)"},
            headers=self.headers,
        )
        self.assertEqual(res_nth.status_code, 200)
        data_nth = res_nth.json()
        self.assertTrue(data_nth["is_brittle"])
        self.assertEqual(data_nth["strategy"], "STRUCTURAL_POSITIONAL")
        self.assertLessEqual(data_nth["resilience_score"], 30)

        # 3. Semantic Playwright locator
        res_resilient = self.client.post(
            "/api/real/locator-audit",
            json={"selector": 'page.get_by_role("button", name="Submit")'},
            headers=self.headers,
        )
        self.assertEqual(res_resilient.status_code, 200)
        data_resilient = res_resilient.json()
        self.assertFalse(data_resilient["is_brittle"])
        self.assertGreaterEqual(data_resilient["resilience_score"], 90)

    def test_9_real_workspace_open_trace_endpoint(self):
        """Verifies POST /api/real/open-trace handles trace file paths safely."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            trace_path = ws / "trace.zip"
            trace_path.write_bytes(b"dummy zip content")

            self.client.post("/api/real/workspace", json={"workspace": str(ws)}, headers=self.headers)

            with patch("subprocess.Popen") as mock_popen:
                res = self.client.post(
                    "/api/real/open-trace",
                    json={"trace_path": "trace.zip"},
                    headers=self.headers,
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["status"], "success")
                self.assertTrue(mock_popen.called)

    def test_10_real_workspace_create_git_branch_endpoint(self):
        """Verifies POST /api/real/create-git-branch creates a branch and commits staged files."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            # Initialize git repo
            is_win = (os.name == "nt")
            subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, shell=is_win)
            subprocess.run(["git", "config", "user.email", "ci@hermes.test"], cwd=str(ws), capture_output=True, shell=is_win)
            subprocess.run(["git", "config", "user.name", "Hermes CI"], cwd=str(ws), capture_output=True, shell=is_win)
            (ws / "file.txt").write_text("initial", encoding="utf-8")
            subprocess.run(["git", "add", "file.txt"], cwd=str(ws), capture_output=True, shell=is_win)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True, shell=is_win)

            # Stage a modification
            (ws / "file.txt").write_text("healed content", encoding="utf-8")

            self.client.post("/api/real/workspace", json={"workspace": str(ws)}, headers=self.headers)

            res = self.client.post(
                "/api/real/create-git-branch",
                json={"branch_name": "hermes/test-branch", "commit_msg": "fix: self-healed test"},
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["branch"], "hermes/test-branch")
            self.assertTrue(len(data["commit_sha"]) > 0)

    def test_11_real_workspace_run_test_stream_endpoint(self):
        """Verifies GET /api/real/run-test-stream streams SSE test execution events."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            test_file = ws / "test_quick.py"
            test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

            self.client.post("/api/real/workspace", json={"workspace": str(ws)}, headers=self.headers)

            res = self.client.get(
                "/api/real/run-test-stream?test_path=test_quick.py",
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn("text/event-stream", res.headers.get("content-type", ""))
            content = res.text
            self.assertIn("event: start", content)
            self.assertIn("event: exit", content)
            self.assertIn("passed", content)


if __name__ == "__main__":
    unittest.main()
