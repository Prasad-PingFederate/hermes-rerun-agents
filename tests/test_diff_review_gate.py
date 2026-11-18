"""
Tests for diff review gate (OpenQodex-style review gate).
Requirements:
1. A major finding whose quote is not a line in the file is dropped and does not block.
2. A confirmed major blocks. apply_task writes nothing. Assert the destination file bytes are unchanged.
3. An observation, even if the model marked it major and the title says "rename", does not block.
4. A refuted major allows apply.
5. A minor finding with no verdict returns INCOMPLETE and blocks apply.
6. report.md contains the verdict and the finding line.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hermes.agents.test_healer_agent import TestHealerAgent
from hermes.guards.diff_review_gate import (
    Finding,
    Verdict,
    parse_unified_diff,
    review_diff,
)


class TestDiffReviewGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_gate_")
        self.workspace = Path(self.temp_dir).resolve()
        # Initialize basic git repository for TimeMachine and sandbox operations
        subprocess.run(["git", "init"], cwd=str(self.workspace), capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@local", "commit", "--allow-empty", "-m", "init"],
            cwd=str(self.workspace),
            capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_1_major_finding_with_non_matching_quote_is_dropped_and_does_not_block(self):
        """1. A major finding whose quote is not a line in the file is dropped and does not block."""
        diff_text = """--- a/src/math_mod.py
+++ b/src/math_mod.py
@@ -1,2 +1,2 @@
 def calc(x):
-    return x + 1
+    return x + 2
"""
        files = {
            "src/math_mod.py": "def calc(x):\n    return x + 2\n"
        }

        # The candidate quote 'return x * 999' is NOT an exact line in files["src/math_mod.py"]
        bad_finding = Finding(
            file="src/math_mod.py",
            line=2,
            severity="major",
            title="Bogus calculation bug",
            quote="    return x * 999",
        )

        def critic(findings, files_map):
            return [Verdict(action="confirm", reason="Looks bad")]

        res = review_diff(
            diff_text=diff_text,
            files=files,
            critic=critic,
            candidate_findings=[bad_finding],
            workspace=str(self.workspace),
        )

        self.assertTrue(res["allow_apply"])
        self.assertEqual(res["verdict"], "ALLOWED")
        self.assertEqual(len(res["surviving_findings"]), 0)

    def test_2_confirmed_major_blocks_and_apply_task_writes_nothing(self):
        """2. A confirmed major blocks. apply_task writes nothing. Assert the destination file bytes are unchanged."""
        src_dir = self.workspace / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        target_file = src_dir / "service.py"
        initial_content = "def serve():\n    return 'safe_v1'\n"
        target_file.write_text(initial_content, encoding="utf-8")
        initial_bytes = target_file.read_bytes()

        # Create sandbox directory with modified content
        sandbox_dir = self.workspace / "sandbox"
        sandbox_src = sandbox_dir / "src"
        sandbox_src.mkdir(parents=True, exist_ok=True)
        sandbox_target = sandbox_src / "service.py"
        sandbox_target.write_text("def serve():\n    return 'vulnerable_leak'\n", encoding="utf-8")

        agent = TestHealerAgent(workspace_path=self.workspace)
        task = agent.orchestrator.create_task(
            title="Patch service leak",
            details={
                "sandbox_copy": str(sandbox_dir),
                "target_file": "src/service.py",
                "candidate_findings": [
                    Finding(
                        file="src/service.py",
                        line=2,
                        severity="major",
                        title="Plaintext credential leak in response",
                        quote="    return 'vulnerable_leak'",
                    )
                ],
            },
        )
        agent.orchestrator.update_task_status(task.id, "AWAITING_APPROVAL")

        def confirming_critic(findings, files_map):
            return [Verdict(action="confirm", reason="Plaintext leak confirmed")]

        with self.assertRaises(ValueError) as ctx:
            agent.apply_task(task.id, critic=confirming_critic)

        self.assertIn("Diff review gate rejected patch", str(ctx.exception))
        self.assertIn("Plaintext credential leak in response", str(ctx.exception))

        # Destination file must be completely untouched
        self.assertEqual(target_file.read_bytes(), initial_bytes)
        self.assertEqual(target_file.read_text(encoding="utf-8"), initial_content)

        # Task remains in AWAITING_APPROVAL
        refreshed_task = agent.orchestrator.get_task(task.id)
        self.assertEqual(refreshed_task.status, "AWAITING_APPROVAL")

    def test_3_observation_with_rename_title_does_not_block(self):
        """3. An observation, even if the model marked it major and the title says 'rename', does not block."""
        diff_text = """--- a/src/util.py
+++ b/src/util.py
@@ -1,2 +1,2 @@
 def process():
-    foo = 1
+    foo = 2
"""
        files = {
            "src/util.py": "def process():\n    foo = 2\n"
        }

        # Model labeled as major, but title mentions "rename" -> downgraded to observation
        finding = Finding(
            file="src/util.py",
            line=2,
            severity="major",
            title="rename variable foo to count for readability",
            quote="    foo = 2",
        )

        def critic(findings, files_map):
            return [Verdict(action="confirm", reason="Naming style suggestion")]

        res = review_diff(
            diff_text=diff_text,
            files=files,
            critic=critic,
            candidate_findings=[finding],
            workspace=str(self.workspace),
        )

        self.assertTrue(res["allow_apply"])
        self.assertEqual(res["verdict"], "ALLOWED")
        self.assertEqual(len(res["surviving_findings"]), 1)
        self.assertEqual(res["surviving_findings"][0].severity, "observation")

    def test_4_refuted_major_allows_apply(self):
        """4. A refuted major allows apply."""
        diff_text = """--- a/src/db.py
+++ b/src/db.py
@@ -1,2 +1,2 @@
 def connect():
-    return None
+    return 'active_conn'
"""
        files = {
            "src/db.py": "def connect():\n    return 'active_conn'\n"
        }

        finding = Finding(
            file="src/db.py",
            line=2,
            severity="major",
            title="Unsafe unpooled connection",
            quote="    return 'active_conn'",
        )

        def refuting_critic(findings, files_map):
            return [Verdict(action="refute", reason="Factory handles connection pooling downstream")]

        res = review_diff(
            diff_text=diff_text,
            files=files,
            critic=refuting_critic,
            candidate_findings=[finding],
            workspace=str(self.workspace),
        )

        self.assertTrue(res["allow_apply"])
        self.assertEqual(res["verdict"], "ALLOWED")
        self.assertEqual(len(res["surviving_findings"]), 1)
        self.assertEqual(res["verdicts"][0].action, "refute")

    def test_5_minor_finding_with_no_verdict_returns_incomplete_and_blocks_apply(self):
        """5. A minor finding with no verdict returns INCOMPLETE and blocks apply."""
        diff_text = """--- a/src/handler.py
+++ b/src/handler.py
@@ -1,2 +1,2 @@
 def handle():
-    pass
+    val = 1
"""
        files = {
            "src/handler.py": "def handle():\n    val = 1\n"
        }

        minor_finding = Finding(
            file="src/handler.py",
            line=2,
            severity="minor",
            title="Unused local assignment",
            quote="    val = 1",
        )

        # Critic returns an empty list, omitting the required verdict
        def silent_critic(findings, files_map):
            return []

        res = review_diff(
            diff_text=diff_text,
            files=files,
            critic=silent_critic,
            candidate_findings=[minor_finding],
            workspace=str(self.workspace),
        )

        self.assertFalse(res["allow_apply"])
        self.assertEqual(res["verdict"], "INCOMPLETE")

    def test_6_report_md_contains_verdict_and_finding_line(self):
        """6. report.md contains the verdict and the finding line."""
        diff_text = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,2 @@
 def verify(token):
-    return check_hmac(token)
+    return True
"""
        files = {
            "src/auth.py": "def verify(token):\n    return True\n"
        }

        critical_finding = Finding(
            file="src/auth.py",
            line=2,
            severity="major",
            title="Authentication Bypass with Hardcoded True",
            quote="    return True",
        )

        def critic(findings, files_map):
            return [Verdict(action="confirm", reason="Critical security vulnerability")]

        res = review_diff(
            diff_text=diff_text,
            files=files,
            critic=critic,
            candidate_findings=[critical_finding],
            workspace=str(self.workspace),
        )

        report_file = Path(res["report_path"])
        self.assertTrue(report_file.exists())

        report_lines = report_file.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(report_lines), 3)

        # First line: verdict
        self.assertEqual(report_lines[0].strip(), "BLOCKED")

        # Finding line: severity, action, file:line, title
        finding_line = report_lines[1]
        self.assertIn("major", finding_line)
        self.assertIn("confirm", finding_line)
        self.assertIn("src/auth.py:2", finding_line)
        self.assertIn("Authentication Bypass with Hardcoded True", finding_line)

        # Last line: apply_allowed
        self.assertEqual(report_lines[-1].strip(), "apply_allowed false")


if __name__ == "__main__":
    unittest.main()
