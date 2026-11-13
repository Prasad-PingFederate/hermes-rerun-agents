"""
GAP-06: Isolated Sandbox Subprocess & Ephemeral Worktree Runner
Owner: AutomationTesterAgent, TIER_3

Executes test suites in isolated git worktrees or ephemeral directories with:
- Guaranteed cleanup in finally blocks.
- Multi-run execution harness (repeat=3) capturing stdout, stderr, exit code, and duration.
- JUnit XML and Playwright trace collection.
- Clean failure classification (ENVIRONMENT_NOISE vs TEST_BUG vs PRODUCT_BUG vs FLAKY_TEST).
- Invariant 3: Opens healer tickets ONLY on confirmed TEST_BUG or FLAKY_TEST.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union


@dataclass
class ExecutionRun:
    """Telemetry captured from a single test execution pass."""
    run_index: int
    command: List[str]
    exit_code: int
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    artifacts: Dict[str, str] = field(default_factory=dict)


@dataclass
class MultiRunResult:
    """Aggregated result across multi-run sandbox executions."""
    runs: List[ExecutionRun]
    classification: str  # "PASSED", "FLAKY_TEST", "TEST_BUG", "PRODUCT_BUG", "ENVIRONMENT_NOISE"
    repeat: int
    pass_count: int
    fail_count: int
    duration_seconds: float
    should_open_healer_ticket: bool  # True ONLY for TEST_BUG or FLAKY_TEST
    artifacts: Dict[str, str] = field(default_factory=dict)
    summary: str = ""


class SandboxExecutor:
    """Executes tests in an ephemeral git worktree or temporary directory."""

    # Explicit list of sensitive tokens, secrets, and cloud credentials stripped from sandbox subprocesses
    SENSITIVE_ENV_PREFIXES = (
        "AWS_",
        "AZURE_",
        "GOOGLE_",
        "ACTIONS_",
        "HERMES_AUTH_",
        "HERMES_TOKEN_",
    )

    SENSITIVE_ENV_KEYS = {
        "GITHUB_TOKEN",
        "INPUT_GITHUB_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "ACTIONS_RUNTIME_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "CLAUDE_API_KEY",
        "HERMES_SANDBOX_NONCE",
    }

    @classmethod
    def sanitize_subprocess_env(cls, raw_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Strip sensitive CI credentials, cloud tokens, and LLM keys before test execution."""
        base = dict(raw_env if raw_env is not None else os.environ)
        sanitized = {}
        for k, v in base.items():
            k_upper = k.upper()
            if k_upper in cls.SENSITIVE_ENV_KEYS:
                continue
            if any(k_upper.startswith(prefix) for prefix in cls.SENSITIVE_ENV_PREFIXES):
                continue
            if any(term in k_upper for term in ("_TOKEN", "_SECRET", "_API_KEY", "_PASSWORD", "_AUTH")):
                continue
            sanitized[k] = v
        sanitized["HERMES_SANDBOX_EXECUTION"] = "1"
        return sanitized

    def __init__(
        self,
        workspace_path: Optional[Path | str] = None,
        artifacts_dir: Optional[Path | str] = None,
        default_timeout_seconds: int = 30,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.artifacts_dir = Path(artifacts_dir or (self.workspace_path / ".hermes_artifacts")).resolve()
        self.default_timeout_seconds = default_timeout_seconds

    def is_git_repo(self) -> bool:
        """Check if workspace is inside an initialized git repository with at least one commit."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.workspace_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return False
            # Check if HEAD exists
            head_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.workspace_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return head_res.returncode == 0
        except Exception:
            return False

    def create_ephemeral_worktree(self) -> Tuple[Path, str]:
        """Create an ephemeral worktree detached at HEAD, or fallback to safe copy.
        
        Returns:
            Tuple[Path, str]: (worktree_path, mode) where mode is "worktree" or "copy".
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="hermes_worktree_")).resolve()

        if self.is_git_repo():
            try:
                # git worktree add --detach <path> HEAD
                cmd = ["git", "worktree", "add", "--detach", str(temp_dir), "HEAD"]
                res = subprocess.run(
                    cmd,
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode == 0:
                    return temp_dir, "worktree"
            except Exception:
                pass

        # Fallback to isolated directory copy
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="hermes_sandbox_copy_")).resolve()
        ignore = shutil.ignore_patterns(
            ".git",
            ".tm_snapshots",
            ".rerun_tasks",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
            ".hermes_artifacts",
        )
        shutil.copytree(self.workspace_path, temp_dir, dirs_exist_ok=True, ignore=ignore)
        return temp_dir, "copy"

    def cleanup_worktree(self, target_path: Path, mode: str) -> None:
        """Safely prune git worktree or remove temp directory with guaranteed cleanup."""
        if not target_path.exists():
            return

        if mode == "worktree" and self.is_git_repo():
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(target_path)],
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    timeout=10,
                )
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

        # Ensure directory is purged
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

    @contextlib.contextmanager
    def ephemeral_sandbox(
        self, proposed_changes: Optional[Dict[str, str]] = None
    ) -> Generator[Path, None, None]:
        """Context manager guaranteeing creation and cleanup of an ephemeral test sandbox."""
        sandbox_path, mode = self.create_ephemeral_worktree()
        try:
            if proposed_changes:
                self.apply_proposed_changes(sandbox_path, proposed_changes)
            yield sandbox_path
        finally:
            self.cleanup_worktree(sandbox_path, mode)

    def apply_proposed_changes(self, sandbox_path: Path, proposed_changes: Dict[str, str]) -> None:
        """Write proposed changes into the sandbox directory without touching caller workspace."""
        for rel_path, content in proposed_changes.items():
            clean_rel = rel_path.replace("\\", "/").lstrip("/")
            dest = sandbox_path / clean_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                dest.unlink()
            dest.write_text(content, encoding="utf-8")

    def run_single_test(
        self,
        command: List[str],
        cwd: Path,
        run_index: int = 1,
        timeout_seconds: Optional[int] = None,
        artifacts_subdir: Optional[Path] = None,
    ) -> ExecutionRun:
        """Execute a single test command with timeout enforcement and artifact collection."""
        timeout = timeout_seconds or self.default_timeout_seconds
        start_time = time.time()
        timed_out = False
        stdout_str = ""
        stderr_str = ""
        exit_code = -1

        # Prepare env with artifact paths and credential scrubbing
        env = self.sanitize_subprocess_env()
        if artifacts_subdir:
            artifacts_subdir.mkdir(parents=True, exist_ok=True)
            env["JUNIT_XML_PATH"] = str(artifacts_subdir / f"junit_run_{run_index}.xml")
            env["PLAYWRIGHT_TRACE_DIR"] = str(artifacts_subdir / f"trace_run_{run_index}")

        # Linux optional network isolation wrapper
        exec_cmd = list(command)
        if sys.platform.startswith("linux") and os.environ.get("HERMES_SANDBOX_NETWORK_ISOLATION", "").lower() == "true":
            if shutil.which("bwrap"):
                exec_cmd = ["bwrap", "--ro-bind", "/", "/", "--bind", str(cwd), str(cwd), "--unshare-net", "--"] + exec_cmd

        try:
            proc = subprocess.run(
                exec_cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            exit_code = proc.returncode
            stdout_str = proc.stdout or ""
            stderr_str = proc.stderr or ""
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = 124
            stdout_str = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_str = (
                (e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))
                + f"\n[SandboxExecutor] Execution timed out after {timeout} seconds."
            )
        except Exception as e:
            exit_code = 1
            stderr_str = f"[SandboxExecutor] Execution error: {str(e)}"

        duration = time.time() - start_time
        passed = (exit_code == 0) and not timed_out

        # Collect artifacts
        artifacts_collected: Dict[str, str] = {}
        if artifacts_subdir and artifacts_subdir.exists():
            for p in artifacts_subdir.glob("*"):
                if p.is_file():
                    artifacts_collected[p.name] = str(p)

        return ExecutionRun(
            run_index=run_index,
            command=command,
            exit_code=exit_code,
            passed=passed,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_seconds=round(duration, 3),
            timed_out=timed_out,
            artifacts=artifacts_collected,
        )

    def run_tests(
        self,
        command: List[str],
        repeat: int = 3,
        worktree_path: Optional[Path] = None,
        timeout_seconds: Optional[int] = None,
        proposed_changes: Optional[Dict[str, str]] = None,
    ) -> MultiRunResult:
        """Run multi-pass test execution (repeat=3) in an isolated sandbox with clean failure triage."""
        start_time = time.time()
        runs: List[ExecutionRun] = []

        # If a worktree_path was already provided, use it directly
        if worktree_path:
            if proposed_changes:
                self.apply_proposed_changes(worktree_path, proposed_changes)
            target_dir = worktree_path
            mode = "external"
        else:
            target_dir, mode = self.create_ephemeral_worktree()
            if proposed_changes:
                self.apply_proposed_changes(target_dir, proposed_changes)

        artifacts_session_dir = self.artifacts_dir / f"session_{int(time.time() * 1000)}"
        artifacts_session_dir.mkdir(parents=True, exist_ok=True)

        try:
            for idx in range(1, repeat + 1):
                run_artifacts = artifacts_session_dir / f"run_{idx}"
                run_res = self.run_single_test(
                    command=command,
                    cwd=target_dir,
                    run_index=idx,
                    timeout_seconds=timeout_seconds,
                    artifacts_subdir=run_artifacts,
                )
                runs.append(run_res)
        finally:
            if mode != "external":
                self.cleanup_worktree(target_dir, mode)

        total_duration = time.time() - start_time
        pass_count = sum(1 for r in runs if r.passed)
        fail_count = len(runs) - pass_count

        classification = self.classify_failure(runs)
        should_open = classification in ("TEST_BUG", "FLAKY_TEST")

        all_artifacts: Dict[str, str] = {}
        for r in runs:
            all_artifacts.update(r.artifacts)

        summary = (
            f"Executed {len(runs)} runs: {pass_count} passed, {fail_count} failed. "
            f"Classification: {classification} (Healer Ticket Needed: {should_open})"
        )

        return MultiRunResult(
            runs=runs,
            classification=classification,
            repeat=repeat,
            pass_count=pass_count,
            fail_count=fail_count,
            duration_seconds=round(total_duration, 3),
            should_open_healer_ticket=should_open,
            artifacts=all_artifacts,
            summary=summary,
        )

    def classify_failure(
        self,
        runs: Union[List[ExecutionRun], str],
        intent_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Classify test execution outcome into clean categories:
        
        - PASSED: All runs passed.
        - FLAKY_TEST: Some runs passed, some failed.
        - ENVIRONMENT_NOISE: Failed due to network, port, missing dependencies, or OS env.
        - PRODUCT_BUG: Unhandled exceptions or failures originating in application/product code.
        - TEST_BUG: Assertion failures in tests, test fixture errors, or intentional contract drift.
        """
        if isinstance(runs, str):
            combined_output = runs
            if not combined_output.strip() or ("passed" in combined_output.lower() and "failed" not in combined_output.lower()):
                return "PASSED"
        else:
            if not runs:
                return "ENVIRONMENT_NOISE"

            pass_count = sum(1 for r in runs if r.passed)
            if pass_count == len(runs):
                return "PASSED"

            # Intermittent pass/fail
            if 0 < pass_count < len(runs):
                return "FLAKY_TEST"

            combined_output = "\n".join(f"{r.stdout}\n{r.stderr}" for r in runs)

        # 1. Environment Noise patterns (network, port, permissions, missing binaries)
        env_patterns = [
            r"ConnectionRefusedError",
            r"address already in use",
            r"No such file or directory: '.*(?:node|git|docker|playwright|npm|yarn)'",
            r"PermissionError",
            r"ENOSPC",
            r"EADDRINUSE",
            r"timed out after \d+ seconds",
            r"NetworkError",
            r"socket\.gaierror",
        ]
        for pattern in env_patterns:
            if re.search(pattern, combined_output, re.IGNORECASE):
                if "AssertionError" not in combined_output:
                    return "ENVIRONMENT_NOISE"

        # Check for intentional contract / API changes in commit/PR intent
        assertion_mismatch_patterns = [
            r"AssertionError",
            r"assert .* == .*",
            r"assert .*\.status_code\s*==\s*\d+",
            r"expect\(.*\)\.to",
            r"Expected: .*\nReceived:",
            r"FAILED tests/.* - AssertionError",
        ]
        has_assertion_mismatch = any(re.search(pat, combined_output, re.IGNORECASE) for pat in assertion_mismatch_patterns)

        unhandled_product_crash_patterns = [
            r"AttributeError: '.*' object has no attribute",
            r"KeyError: '.*'",
            r"TypeError: .* missing \d+ required",
            r"ZeroDivisionError",
            r"IndexError: list index out of range",
        ]
        has_unhandled_crash = any(re.search(pat, combined_output) for pat in unhandled_product_crash_patterns)

        if intent_context and intent_context.get("has_intentional_contract_change"):
            if has_assertion_mismatch and not has_unhandled_crash:
                return "TEST_BUG"

        # 2. Product Bug patterns (exceptions originating in application/product code)
        product_bug_patterns = [
            r'File "(?:src|core|app|lib|pkg)/[^"]+\.py", line \d+',
            r"AttributeError: '.*' object has no attribute",
            r"KeyError: '.*'",
            r"TypeError: .* missing \d+ required",
            r"ZeroDivisionError",
            r"IndexError: list index out of range",
            r"ValueError: (?!Zero Assertion Erosion)",
            r"Failed: DID NOT RAISE",
            r"DID NOT RAISE",
        ]
        # Check if traceback includes product code or product failed to raise expected exception
        has_product_frames = bool(
            re.search(r'File "[^"]*(?:src|core|app|lib|pkg)[/\\].*?\.py", line \d+', combined_output, re.IGNORECASE)
            or re.search(r'(?:src|core|app|lib|pkg)[/\\].*?\.py:\d+', combined_output, re.IGNORECASE)
            or re.search(r'(?:^|\n)\s*(?!tests?[/\\_])[a-zA-Z0-9_-]+\.py:\d+:', combined_output, re.IGNORECASE)
        )
        did_not_raise = bool(re.search(r"DID NOT RAISE", combined_output))
        if has_product_frames or did_not_raise:
            # If product code is in traceback and not an import error inside the test
            if not re.search(r'ImportError: cannot import name .* from', combined_output):
                return "PRODUCT_BUG"

        for pattern in product_bug_patterns:
            if re.search(pattern, combined_output, re.IGNORECASE):
                # If exception is in product code
                if has_product_frames:
                    return "PRODUCT_BUG"

        # 3. Test Bug patterns (assertions in test_* files or pytest fixture errors)
        test_bug_patterns = [
            r"AssertionError",
            r"assert .* == .*",
            r"FixtureLookupError",
            r"Failed: .* fixture",
            r"tests/.*\.py:\d+: AssertionError",
            r"test_.*\.py:\d+: AssertionError",
            r"expect\(.*\)\.to",
            r"ImportError: cannot import name",
        ]
        for pattern in test_bug_patterns:
            if re.search(pattern, combined_output, re.IGNORECASE):
                return "TEST_BUG"

        # Fallback if product frames exist
        if has_product_frames:
            return "PRODUCT_BUG"

        return "TEST_BUG"
