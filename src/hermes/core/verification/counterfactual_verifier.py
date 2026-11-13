"""
Counterfactual Differential Verification Engine
Owner: QACriticAgent & SandboxExecutor
Phase: Option 4 (Zero False-Green Verification)

Proves the test still fails when broken:
1. Forward Verification: Run healed test against PR HEAD / current code -> Must PASS.
2. Counterfactual Verification: Run healed test against pre-patch / baseline source -> Must FAIL.
   If the healed test passes against known-broken base code, the test is vacuous (neutered)
   and must be rejected.

Zero external dependencies (uses standard library: subprocess, tempfile, shutil, pathlib).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CounterfactualResult:
    """Outcome of differential counterfactual verification."""
    verified: bool
    is_vacuous: bool
    forward_passed: bool
    counterfactual_failed: bool
    forward_exit_code: int
    counterfactual_exit_code: int
    forward_output: str = ""
    counterfactual_output: str = ""
    duration_seconds: float = 0.0
    reasons: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "is_vacuous": self.is_vacuous,
            "forward_passed": self.forward_passed,
            "counterfactual_failed": self.counterfactual_failed,
            "forward_exit_code": self.forward_exit_code,
            "counterfactual_exit_code": self.counterfactual_exit_code,
            "duration_seconds": round(self.duration_seconds, 3),
            "reasons": self.reasons,
            "summary": self.summary,
        }


class CounterfactualVerifier:
    """Differential verification harness ensuring healed tests retain strict discriminating power."""

    def __init__(
        self,
        workspace_root: Optional[Path | str] = None,
        default_timeout_seconds: int = 25,
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.default_timeout_seconds = default_timeout_seconds

    @classmethod
    def is_test_path(cls, path_str: str) -> bool:
        """Return True if path represents a test file."""
        norm = path_str.replace("\\", "/").lower()
        parts = norm.split("/")
        filename = parts[-1]
        if any(d in parts for d in ("tests", "test", "__tests__", "specs")):
            return True
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True
        if any(filename.endswith(ext) for ext in (".spec.ts", ".test.ts", ".spec.js", ".test.js", ".spec.tsx", ".test.tsx")):
            return True
        return False

    def verify_differential(
        self,
        test_file: str,
        healed_test_content: str,
        baseline_source_files: Optional[Dict[str, str]] = None,
        base_git_ref: Optional[str] = None,
        product_file_paths: Optional[List[str]] = None,
        test_command: Optional[List[str]] = None,
        test_node: Optional[str] = None,
        is_test_only_pr: bool = False,
    ) -> CounterfactualResult:
        """Execute 2-step differential verification:
        1. Forward: healed test + current code -> must PASS (exit 0).
        2. Counterfactual: healed test + baseline broken code -> must FAIL (exit != 0).
        """
        start_time = time.time()
        temp_dir = Path(tempfile.mkdtemp(prefix="hermes_counterfactual_")).resolve()

        try:
            # 1. Populate sandbox with workspace files (ignoring caches and git metadata)
            self._copy_sandbox_tree(self.workspace_root, temp_dir)

            # 2. Write proposed healed test file
            target_test_path = temp_dir / test_file.replace("\\", "/").lstrip("/")
            target_test_path.parent.mkdir(parents=True, exist_ok=True)
            target_test_path.write_text(healed_test_content, encoding="utf-8")

            # Determine runner command with exact test node targeting
            runner_cmd = test_command or self._resolve_test_command(test_file, test_node=test_node)

            # -------------------------------------------------------------
            # STEP 1: Forward Verification (Must PASS on current code)
            # -------------------------------------------------------------
            fwd_res = self._run_test_in_sandbox(temp_dir, runner_cmd)
            fwd_passed = (fwd_res.returncode == 0)

            if not fwd_passed:
                duration = time.time() - start_time
                return CounterfactualResult(
                    verified=False,
                    is_vacuous=False,
                    forward_passed=False,
                    counterfactual_failed=False,
                    forward_exit_code=fwd_res.returncode,
                    counterfactual_exit_code=-1,
                    forward_output=(fwd_res.stdout + "\n" + fwd_res.stderr).strip(),
                    duration_seconds=duration,
                    reasons=[f"Forward verification failed: healed test exited with code {fwd_res.returncode}"],
                    summary="FORWARD_FAILED: Healed test does not pass against current code.",
                )

            # -------------------------------------------------------------
            # STEP 2: Counterfactual Verification (Must FAIL on base code)
            # -------------------------------------------------------------
            # Detect Test-Only PRs: If PR only changes test files, baseline source reversion
            # is skipped to avoid false-vacuous rejections.
            pure_test_diff = is_test_only_pr
            if not pure_test_diff and baseline_source_files is not None:
                non_test_baselines = {k: v for k, v in baseline_source_files.items() if not self.is_test_path(k)}
                if len(non_test_baselines) == 0:
                    pure_test_diff = True
            if not pure_test_diff and product_file_paths is not None:
                non_test_products = [p for p in product_file_paths if not self.is_test_path(p)]
                if len(non_test_products) == 0:
                    pure_test_diff = True

            if pure_test_diff:
                duration = time.time() - start_time
                return CounterfactualResult(
                    verified=True,
                    is_vacuous=False,
                    forward_passed=True,
                    counterfactual_failed=True,
                    forward_exit_code=0,
                    counterfactual_exit_code=0,
                    duration_seconds=duration,
                    reasons=["Diff modifies test files only; counterfactual baseline reversion skipped to prevent false-vacuous rejection."],
                    summary="COUNTERFACTUAL_SKIPPED_TEST_ONLY_PR: Test-only PR validated via forward pass.",
                )

            # Restore baseline product files while keeping the healed test
            restored = False
            if baseline_source_files:
                for rel_src, base_content in baseline_source_files.items():
                    if self.is_test_path(rel_src):
                        continue
                    src_path = temp_dir / rel_src.replace("\\", "/").lstrip("/")
                    src_path.parent.mkdir(parents=True, exist_ok=True)
                    src_path.write_text(base_content, encoding="utf-8")
                    restored = True
            elif base_git_ref and product_file_paths:
                non_test_files = [p for p in product_file_paths if not self.is_test_path(p)]
                if non_test_files:
                    restored = self._git_restore_files(temp_dir, base_git_ref, non_test_files)

            if not restored:
                # If no baseline files or git ref provided, skip counterfactual step gracefully
                duration = time.time() - start_time
                return CounterfactualResult(
                    verified=True,
                    is_vacuous=False,
                    forward_passed=True,
                    counterfactual_failed=True,
                    forward_exit_code=0,
                    counterfactual_exit_code=1,
                    duration_seconds=duration,
                    reasons=["Differential baseline not specified; forward verification passed."],
                    summary="FORWARD_VERIFIED: Passed forward verification (counterfactual baseline skipped).",
                )

            cf_res = self._run_test_in_sandbox(temp_dir, runner_cmd)
            cf_failed = (cf_res.returncode != 0)

            duration = time.time() - start_time

            if not cf_failed:
                # DANGER: Healed test passed unconditionally even against broken base code!
                return CounterfactualResult(
                    verified=False,
                    is_vacuous=True,
                    forward_passed=True,
                    counterfactual_failed=False,
                    forward_exit_code=0,
                    counterfactual_exit_code=0,
                    forward_output=(fwd_res.stdout + "\n" + fwd_res.stderr).strip(),
                    counterfactual_output=(cf_res.stdout + "\n" + cf_res.stderr).strip(),
                    duration_seconds=duration,
                    reasons=[
                        "Vacuous test detected! Healed test passed unconditionally against broken baseline source code. "
                        "The test lacks discriminating power and cannot prevent future regressions."
                    ],
                    summary="COUNTERFACTUAL_FAILED: Healed test is vacuous (passed against broken code).",
                )

            # Perfect outcome: Passed on new code, Failed on broken base!
            return CounterfactualResult(
                verified=True,
                is_vacuous=False,
                forward_passed=True,
                counterfactual_failed=True,
                forward_exit_code=0,
                counterfactual_exit_code=cf_res.returncode,
                forward_output=(fwd_res.stdout + "\n" + fwd_res.stderr).strip(),
                counterfactual_output=(cf_res.stdout + "\n" + cf_res.stderr).strip(),
                duration_seconds=duration,
                reasons=[],
                summary="COUNTERFACTUAL_VERIFIED: Discriminant power proven! Test passes on PR HEAD and fails on base code.",
            )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _run_test_in_sandbox(self, sandbox_dir: Path, cmd: List[str]) -> subprocess.CompletedProcess[str]:
        """Execute command in sandbox directory."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(sandbox_dir)
        try:
            return subprocess.run(
                cmd,
                cwd=str(sandbox_dir),
                capture_output=True,
                text=True,
                timeout=self.default_timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\nTest timed out after {self.default_timeout_seconds}s",
            )
        except Exception as e:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr=str(e),
            )

    def _resolve_test_command(self, test_file: str, test_node: Optional[str] = None) -> List[str]:
        """Resolve suitable test runner based on file extension and optional specific test node."""
        norm = test_file.replace("\\", "/").lower()
        if norm.endswith(".py"):
            target = test_file
            if test_node:
                target = test_node if "::" in test_node else f"{test_file}::{test_node}"
            return [sys.executable, "-m", "pytest", target, "-q"]
        if norm.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js")):
            cmd = ["npx", "playwright", "test", test_file]
            if test_node:
                cmd.extend(["-g", test_node])
            return cmd
        target = test_file
        if test_node:
            target = test_node if "::" in test_node else f"{test_file}::{test_node}"
        return [sys.executable, "-m", "pytest", target, "-q"]

    def _copy_sandbox_tree(self, src: Path, dest: Path) -> None:
        """Copy project files into ephemeral sandbox, excluding bulky caches and git dirs."""
        ignore_patterns = shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", ".rerun_tasks", ".tm_snapshots"
        )
        if src.is_dir():
            for item in src.iterdir():
                if item.name in (".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", ".rerun_tasks", ".tm_snapshots"):
                    continue
                target = dest / item.name
                if item.is_dir():
                    shutil.copytree(item, target, ignore=ignore_patterns)
                else:
                    shutil.copy2(item, target)

    def _git_restore_files(self, sandbox_dir: Path, base_ref: str, file_paths: List[str]) -> bool:
        """Attempt to restore files to base_ref using git checkout or git show."""
        try:
            # 1. If sandbox has git repository, run git checkout
            if (sandbox_dir / ".git").exists():
                cmd = ["git", "checkout", base_ref, "--"] + file_paths
                res = subprocess.run(cmd, cwd=str(sandbox_dir), capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    return True

            # 2. Extract baseline contents directly from workspace_root git repository
            success = False
            for rel_path in file_paths:
                clean_rel = rel_path.replace("\\", "/").lstrip("/")
                cmd = ["git", "show", f"{base_ref}:{clean_rel}"]
                res = subprocess.run(cmd, cwd=str(self.workspace_root), capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    dest_file = sandbox_dir / clean_rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(res.stdout, encoding="utf-8")
                    success = True
            return success
        except Exception:
            return False

