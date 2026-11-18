"""
Tests for AutofixThread (One red test in, one branch out, no merge).
Requirements:
- Tests, no network.
- A passing test does not create a commit.
- A green second attempt leaves the start branch clean and the heal branch with one commit.
- A third failure restores the start branch.
- A confirmed major finding does not get committed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hermes.guards.diff_review_gate import Finding, Verdict
from hermes.orchestration.autofix_thread import AutofixThread


class TestAutofixThread(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_autofix_")
        self.workspace = Path(self.temp_dir).resolve()

        # Initialize Git repository with a baseline commit on main
        subprocess.run(["git", "init"], cwd=str(self.workspace), capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=str(self.workspace), capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Hermes Tester"],
            cwd=str(self.workspace),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tester@hermes.local"],
            cwd=str(self.workspace),
            capture_output=True,
            check=True,
        )

        src_dir = self.workspace / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        self.code_file = src_dir / "calculator.py"
        self.initial_code = "def add(a, b):\n    return a - b  # buggy implementation\n"
        self.code_file.write_text(self.initial_code, encoding="utf-8")

        tests_dir = self.workspace / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        self.test_file = tests_dir / "test_calculator.py"
        self.test_content = "from src.calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n"
        self.test_file.write_text(self.test_content, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=str(self.workspace), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit on main"], cwd=str(self.workspace), capture_output=True, check=True)

        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.workspace), capture_output=True, text=True)
        self.initial_commit_sha = res.stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_1_passing_test_does_not_create_a_commit(self):
        """A passing test does not create a commit and does not open a branch."""
        # Runner reports test passed immediately
        def fake_runner(test_path: str, cwd: Path) -> Dict[str, Any]:
            return {"passed": True, "returncode": 0, "stdout": "1 passed in 0.01s", "stderr": ""}

        thread = AutofixThread(workspace=self.workspace, runner=fake_runner)
        result = thread.run("tests/test_calculator.py")

        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["attempts"], 0)

        # Main branch must have unchanged HEAD commit
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.workspace), capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), self.initial_commit_sha)

        # No heal branch should exist or be checked out
        br_res = subprocess.run(["git", "branch"], cwd=str(self.workspace), capture_output=True, text=True)
        self.assertNotIn("hermes/heal-test_calculator", br_res.stdout)

    def test_2_green_second_attempt_leaves_start_branch_clean_and_heal_branch_with_one_commit(self):
        """A green second attempt leaves the start branch clean and the heal branch with one commit."""
        # Execution plan:
        # Initial run: fails
        # Attempt 1: healer creates patch, but rerun fails
        # Attempt 2: healer creates correct patch, diff review gate allows, rerun passes
        run_count = {"calls": 0}

        def fake_runner(test_path: str, cwd: Path) -> Dict[str, Any]:
            run_count["calls"] += 1
            if run_count["calls"] == 1:
                # Initial execution before heal
                return {"passed": False, "returncode": 1, "stdout": "AssertionError: -1 != 5", "stderr": ""}
            elif run_count["calls"] == 2:
                # Attempt 1 rerun after first patch
                return {"passed": False, "returncode": 1, "stdout": "TypeError on first fix", "stderr": ""}
            else:
                # Attempt 2 rerun after second patch -> passes!
                return {"passed": True, "returncode": 0, "stdout": "1 passed", "stderr": ""}

        attempt_count = {"count": 0}

        def fake_healer(sandbox_dir: Path, failure_info: Dict[str, Any], healer_prompt: str, test_path: str = "") -> bool:
            attempt_count["count"] += 1
            target = sandbox_dir / "src" / "calculator.py"
            if attempt_count["count"] == 1:
                # Flawed patch
                target.write_text("def add(a, b):\n    return 'wrong'\n", encoding="utf-8")
            else:
                # Correct patch
                target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            return True

        def approving_critic(findings, files_map):
            return [Verdict(action="refute", reason="Safe calculation fix")]

        thread = AutofixThread(
            workspace=self.workspace,
            runner=fake_runner,
            healer=fake_healer,
            critic=approving_critic,
            max_attempts=3,
        )
        result = thread.run("tests/test_calculator.py")

        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["branch"], "hermes/heal-test_calculator")

        # Heal branch must have exactly 1 commit ahead of main
        rev_count = subprocess.run(
            ["git", "rev-list", "--count", "main..hermes/heal-test_calculator"],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        self.assertEqual(rev_count.stdout.strip(), "1")

        # Switch to start branch (main) and assert it is clean and unchanged
        subprocess.run(["git", "checkout", "main"], cwd=str(self.workspace), capture_output=True, check=True)
        head_main = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.workspace), capture_output=True, text=True)
        self.assertEqual(head_main.stdout.strip(), self.initial_commit_sha)

        # Working tree on main must have original code
        self.assertEqual(self.code_file.read_text(encoding="utf-8"), self.initial_code)

    def test_3_third_failure_restores_the_start_branch(self):
        """A third failure restores the start branch and marks status FAILED."""
        # Runner always fails
        def always_failing_runner(test_path: str, cwd: Path) -> Dict[str, Any]:
            return {"passed": False, "returncode": 1, "stdout": "Fatal error in test", "stderr": ""}

        # Healer modifies code each time
        def modifying_healer(sandbox_dir: Path, failure_info: Dict[str, Any], healer_prompt: str, test_path: str = "") -> bool:
            target = sandbox_dir / "src" / "calculator.py"
            target.write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
            return True

        def approving_critic(findings, files_map):
            return []

        thread = AutofixThread(
            workspace=self.workspace,
            runner=always_failing_runner,
            healer=modifying_healer,
            critic=approving_critic,
            max_attempts=3,
        )
        result = thread.run("tests/test_calculator.py")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["attempts"], 3)

        # Start branch (main) must be active
        br_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self.workspace), capture_output=True, text=True)
        self.assertEqual(br_res.stdout.strip(), "main")

        # Head commit on main is unchanged
        head_main = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.workspace), capture_output=True, text=True)
        self.assertEqual(head_main.stdout.strip(), self.initial_commit_sha)

        # Code is restored to initial baseline
        self.assertEqual(self.code_file.read_text(encoding="utf-8"), self.initial_code)

    def test_4_confirmed_major_finding_does_not_get_committed(self):
        """A confirmed major finding ends the attempt and does not get committed."""
        run_count = {"calls": 0}

        def fake_runner(test_path: str, cwd: Path) -> Dict[str, Any]:
            run_count["calls"] += 1
            if run_count["calls"] == 1:
                return {"passed": False, "returncode": 1, "stdout": "Test failed initially", "stderr": ""}
            # Second attempt passes
            return {"passed": True, "returncode": 0, "stdout": "Passed", "stderr": ""}

        attempt_count = {"count": 0}

        def fake_healer(sandbox_dir: Path, failure_info: Dict[str, Any], healer_prompt: str, test_path: str = "") -> bool:
            attempt_count["count"] += 1
            target = sandbox_dir / "src" / "calculator.py"
            if attempt_count["count"] == 1:
                # Write code that introduces a severe flaw
                target.write_text("def add(a, b):\n    eval('secret_bad_eval()')\n    return a + b\n", encoding="utf-8")
            else:
                # Write clean code
                target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            return True

        def selective_critic(findings, files_map):
            verdicts = []
            for f in findings:
                # If evaluating the first flawed patch
                if "eval" in f.quote or "secret_bad_eval" in f.quote or f.severity == "major":
                    verdicts.append(Verdict(action="confirm", reason="Severe security violation (eval injection)"))
                else:
                    verdicts.append(Verdict(action="refute", reason="Safe"))
            return verdicts

        thread = AutofixThread(
            workspace=self.workspace,
            runner=fake_runner,
            healer=fake_healer,
            critic=selective_critic,
            max_attempts=3,
        )
        result = thread.run("tests/test_calculator.py")

        # The attempt with eval was rejected by diff review gate and NOT committed!
        # Attempt 2 succeeded and was committed.
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["attempts"], 2)

        # Inspect commits on heal branch: ensure eval is NOT in the git log or tree
        diff_show = subprocess.run(
            ["git", "show", "hermes/heal-test_calculator"],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        self.assertNotIn("secret_bad_eval", diff_show.stdout)
        self.assertIn("return a + b", diff_show.stdout)


if __name__ == "__main__":
    unittest.main()
