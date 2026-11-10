"""
Sandbox Execution Harness: Isolated Process Execution with Timeout and Failure Capture
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


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


class SandboxRunner:
    """Executes tests in an isolated, monitored sub-process environment."""

    def __init__(self, workspace_path: Optional[str | Path] = None, timeout_seconds: int = 300):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.timeout_seconds = timeout_seconds

    def execute_test(
        self,
        test_file: str,
        extra_args: Optional[List[str]] = None,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        """Run pytest on the given test target inside the workspace."""
        cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]
        if extra_args:
            cmd.extend(extra_args)

        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.workspace_path),
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

        # Search for failure screenshot in workspace
        target_stem = Path(test_file).stem
        shot_path = None
        possible_shots = [
            self.workspace_path / f"{target_stem}_failure.png",
            self.workspace_path / "failure.png",
            self.workspace_path / "reports" / f"{target_stem}_failure.png",
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
        )
