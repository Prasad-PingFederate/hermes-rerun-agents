"""
Sandbox Execution Harness: Isolated Process Execution with Timeout and Failure Capture
Runs tests in temporary isolated workspace copies to protect caller tree until approval.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from sandbox_executor import ExecutionRun, SandboxExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ExecutionResult:
    command: List[str]
    returncode: int
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float
    screenshot_path: Optional[str] = None
    trace_path: Optional[str] = None
    is_tool_missing: bool = False


class SandboxRunner:
    """Executes tests in an isolated, monitored sub-process environment."""

    def __init__(self, workspace_path: Optional[str | Path] = None, timeout_seconds: int = 300):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.timeout_seconds = timeout_seconds
        self.executor = SandboxExecutor(self.workspace_path)

    @staticmethod
    def is_pytest_available() -> bool:
        """Check if pytest module is callable in the current python interpreter."""
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pytest", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False

    def create_isolated_copy(self) -> Path:
        """Create a temporary standalone copy of the workspace so patches do not touch caller tree."""
        temp_dir = Path(tempfile.mkdtemp(prefix="hermes_sandbox_")).resolve()
        ignore_patterns = shutil.ignore_patterns(
            ".tm_snapshots",
            ".rerun_tasks",
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
        )
        shutil.copytree(self.workspace_path, temp_dir, dirs_exist_ok=True, ignore=ignore_patterns)

        # Initialize git in the temp copy if needed for patch applications
        subprocess.run(["git", "init"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(["git", "config", "user.name", "HermesSandbox"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(["git", "config", "user.email", "sandbox@hermes.local"], cwd=str(temp_dir), capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(temp_dir), capture_output=True)
        subprocess.run(["git", "commit", "-m", "sandbox baseline", "--allow-empty"], cwd=str(temp_dir), capture_output=True)

        return temp_dir

    def apply_patch_in_copy(self, copy_dir: Path, rel_path: str, patch_or_content: str) -> Tuple[bool, str]:
        """Apply a patch or replacement content to a file inside the isolated sandbox copy."""
        target_file = copy_dir / rel_path
        if not target_file.is_file():
            # If unified diff has header --- a/path +++ b/path
            pass

        # Try git apply first if formatted as diff
        if patch_or_content.startswith("---") or "@@" in patch_or_content or "diff --git" in patch_or_content:
            patch_file = copy_dir / "_temp_patch.patch"
            patch_file.write_text(patch_or_content, encoding="utf-8")
            res = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=str(copy_dir),
                capture_output=True,
                text=True,
            )
            try:
                patch_file.unlink(missing_ok=True)
            except Exception:
                pass
            if res.returncode == 0:
                return True, "Diff applied successfully with git apply"

        # Direct file replacement fallback if patch_or_content is full code or block
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(patch_or_content, encoding="utf-8")
        return True, "File updated directly"

    def promote_copy(self, copy_dir: Path, files_to_promote: Optional[List[str]] = None) -> List[str]:
        """Copy verified changes from the sandbox copy back into caller workspace."""
        promoted = []
        if files_to_promote:
            for rel in files_to_promote:
                src = copy_dir / rel
                dest = self.workspace_path / rel
                if src.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    promoted.append(rel)
        else:
            # Check diff in copy
            diff_proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=str(copy_dir), capture_output=True, text=True)
            changed = [line.strip() for line in diff_proc.stdout.splitlines() if line.strip()]
            for rel in changed:
                src = copy_dir / rel
                dest = self.workspace_path / rel
                if src.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    promoted.append(rel)
        return promoted

    def execute_test(
        self,
        test_file: str,
        target_dir: Optional[Path] = None,
        extra_args: Optional[List[str]] = None,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        """Run pytest on the given test target inside the workspace (or inside target_dir)."""
        exec_dir = Path(target_dir or self.workspace_path).resolve()
        cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]
        if extra_args:
            cmd.extend(extra_args)

        # Preflight: Verify pytest is installed
        if not self.is_pytest_available():
            return ExecutionResult(
                command=cmd,
                returncode=127,
                passed=False,
                stdout="",
                stderr="[SANDBOX] pytest is not installed in the active Python environment.",
                duration_seconds=0.0,
                is_tool_missing=True,
            )

        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(exec_dir),
                capture_output=True,
                text=True,
                env=env,
                timeout=self.timeout_seconds,
            )
            duration = round(time.time() - start_time, 2)
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired as exc:
            duration = round(time.time() - start_time, 2)
            stdout = (exc.stdout or "") + f"\n[SANDBOX TIMEOUT] Test exceeded {self.timeout_seconds}s"
            stderr = exc.stderr or ""
            returncode = 124

        # Search for failure screenshot in execution directory
        target_stem = Path(test_file).stem
        shot_path = None
        possible_shots = [
            exec_dir / f"{target_stem}_failure.png",
            exec_dir / "failure.png",
            exec_dir / "reports" / f"{target_stem}_failure.png",
        ]
        for p in possible_shots:
            if p.is_file():
                shot_path = str(p)
                break

        return ExecutionResult(
            command=cmd,
            returncode=returncode,
            passed=(returncode == 0),
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            screenshot_path=shot_path,
            is_tool_missing=False,
        )
