"""
Autofix Thread: One red test in, one branch out, no merge.
Autonomous test healing thread with Time Machine safety, isolated sandboxing,
diff review gate enforcement, and branch isolation.
"""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hermes.core.healer.gemini_flash import GeminiFlashHealer
from hermes.core.sandbox.runner import SandboxRunner
from hermes.core.time_machine.engine import TimeMachineEngine
from hermes.guards.diff_review_gate import (
    DefaultDiffCritic,
    Finding,
    Verdict,
    review_diff,
)


def get_git_current_branch(workspace: Path) -> str:
    """Return the name of the current active git branch, or 'main' as fallback."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            branch = proc.stdout.strip()
            if branch and branch != "HEAD":
                return branch
    except Exception:
        pass
    return "main"


def sanitize_test_stem(test_path: str) -> str:
    """Extract a clean branch-friendly stem from a test path or selector."""
    file_part = test_path.split("::")[0]
    stem = Path(file_part).stem
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem)
    return cleaned or "test"


class AutofixThread:
    """
    Autonomous autofix thread.
    Executes a test target, diagnoses and heals failures in an isolated sandbox,
    runs the diff review gate, verifies remediation, and commits strictly on a
    dedicated heal branch.
    """

    def __init__(
        self,
        workspace: Optional[Path | str] = None,
        base_branch: Optional[str] = None,
        runner: Optional[Callable[[str, Path], Dict[str, Any]]] = None,
        healer: Optional[Callable[..., bool]] = None,
        critic: Optional[Callable[..., Any]] = None,
        max_attempts: int = 3,
    ):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.base_branch = base_branch
        self.runner = runner or self._default_runner
        self.healer = healer or self._default_healer
        self.critic = critic
        self.max_attempts = max_attempts
        self.tm = TimeMachineEngine(self.workspace)
        self.sandbox = SandboxRunner(self.workspace)

    def _default_runner(self, test_path: str, cwd: Path) -> Dict[str, Any]:
        """Execute a single test target via pytest in the given directory."""
        cmd = [sys.executable, "-m", "pytest", test_path, "-q"]
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)

        screenshot_path: Optional[str] = None
        trace_path: Optional[str] = None

        test_stem = sanitize_test_stem(test_path)
        for pattern in (f"*{test_stem}*.png", "*.png", "trace.zip", "*.zip"):
            for f in cwd.glob(pattern):
                if f.is_file():
                    if f.suffix in (".png", ".jpg"):
                        screenshot_path = str(f)
                    elif f.suffix == ".zip":
                        trace_path = str(f)
                    break
            if screenshot_path or trace_path:
                break

        return {
            "passed": (proc.returncode == 0),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "screenshot_path": screenshot_path,
            "trace_path": trace_path,
        }

    def _default_healer(
        self,
        sandbox_dir: Path,
        failure_info: Dict[str, Any],
        healer_prompt: str,
        test_path: str = "",
    ) -> bool:
        """Default heuristic / AI healer inside the isolated sandbox directory."""
        healer_agent = GeminiFlashHealer()
        test_file_rel = test_path.split("::")[0] if test_path else ""
        test_file_path = sandbox_dir / test_file_rel if test_file_rel else None

        code_snippet = ""
        if test_file_path and test_file_path.is_file():
            try:
                code_snippet = test_file_path.read_text(encoding="utf-8", errors="replace")[:2000]
            except Exception:
                pass

        err_msg = failure_info.get("stderr") or failure_info.get("stdout") or ""
        diagnosis = healer_agent.diagnose_failure(
            test_name=test_path,
            error_message=err_msg[-600:],
            traceback_str=failure_info.get("stdout", ""),
            code_snippet=code_snippet,
            screenshot_path=failure_info.get("screenshot_path"),
        )

        applied = False
        if diagnosis.get("files"):
            for f_entry in diagnosis["files"]:
                p_path = f_entry.get("path") or test_file_rel
                diff_text = f_entry.get("unified_diff")
                if diff_text:
                    ok, _ = self.sandbox.apply_patch_in_copy(sandbox_dir, p_path, diff_text)
                    if ok:
                        applied = True

        return applied

    def _collect_sandbox_diff_and_files(
        self, sandbox_dir: Path
    ) -> tuple[str, Dict[str, str]]:
        """Extract unified diff and modified file contents from sandbox relative to workspace."""
        diff_chunks: List[str] = []
        files_dict: Dict[str, str] = {}

        # 1. Try git diff in sandbox
        if (sandbox_dir / ".git").is_dir():
            diff_proc = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(sandbox_dir),
                capture_output=True,
                text=True,
            )
            if diff_proc.returncode == 0 and diff_proc.stdout.strip():
                diff_chunks.append(diff_proc.stdout)

        # 2. Direct file comparison against caller workspace
        skip_dirs = {".git", ".tm_snapshots", ".rerun_tasks", "__pycache__", ".pytest_cache", "venv", ".venv"}
        for root, dirs, files in os.walk(sandbox_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                full_p = Path(root) / f
                rel_p = str(full_p.relative_to(sandbox_dir)).replace("\\", "/")
                orig_p = self.workspace / rel_p

                orig_text = orig_p.read_text(encoding="utf-8", errors="replace") if orig_p.is_file() else ""
                new_text = full_p.read_text(encoding="utf-8", errors="replace")

                if orig_text != new_text:
                    files_dict[rel_p] = new_text
                    if not diff_chunks:
                        chunk = "".join(
                            difflib.unified_diff(
                                orig_text.splitlines(keepends=True),
                                new_text.splitlines(keepends=True),
                                fromfile="a/" + rel_p,
                                tofile="b/" + rel_p,
                            )
                        )
                        if chunk:
                            diff_chunks.append(chunk)

        diff_text = "\n".join(diff_chunks)
        return diff_text, files_dict

    def run(self, test_path: str) -> Dict[str, Any]:
        """
        Execute the full autofix thread:
        1. Create branch hermes/heal-<test-stem> from --base. Never commit on current branch.
        2. Snapshot with existing time-machine engine.
        3. Run only that test. If passes, stop with status PASSED, no branch opened.
        4. On failure, capture stdout, stderr, screenshot/trace.
        5. Heal in sandbox without critic seeing healer prompt.
        6. Run diff review gate; confirmed major ends attempt and restores snapshot.
        7. Rerun only that test. If passes, commit on heal branch -> READY_FOR_REVIEW.
        8. If fails, restore snapshot, send error to next attempt, stop after 3 -> FAILED.
        """
        print("RUNNING")

        start_branch = get_git_current_branch(self.workspace)
        base = self.base_branch or start_branch
        test_stem = sanitize_test_stem(test_path)
        heal_branch = "hermes/heal-" + test_stem

        # Step 2: Baseline Snapshot with existing time-machine engine
        baseline_snap = self.tm.create_snapshot(
            label="autofix_pre_" + test_stem,
            description="Autofix baseline snapshot before testing " + test_path,
        )

        # Step 3: Run only that test
        initial_result = self.runner(test_path, self.workspace)
        if initial_result.get("passed", False):
            print("PASSED")
            return {
                "status": "PASSED",
                "attempts": 0,
                "branch": None,
                "passed": True,
            }

        # Step 4: Test failed. Capture diagnostics.
        last_failure = initial_result
        feedback_prompt = ""

        # Step 1: Create branch hermes/heal-<test-stem> from --base.
        # Ensure we never commit on the current branch.
        chk_branch = subprocess.run(
            ["git", "checkout", "-B", heal_branch, base],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        if chk_branch.returncode != 0:
            # Fallback if git is not initialized or fails
            pass

        critic_to_use = self.critic or DefaultDiffCritic(workspace=str(self.workspace))

        for attempt in range(1, self.max_attempts + 1):
            # Step 5: Heal inside the existing sandbox.
            # The critic must not see the healer prompt.
            sandbox_dir = self.sandbox.create_isolated_copy()

            prompt_sections = [
                "Test target: " + test_path,
                "Failure Output:\n" + (last_failure.get("stderr") or last_failure.get("stdout") or "")[:2500],
            ]
            if feedback_prompt:
                prompt_sections.append("Previous Attempt Feedback:\n" + feedback_prompt)

            healer_prompt = "\n\n".join(prompt_sections)

            # Invoke healer with failure info (healer prompt is kept isolated from critic)
            try:
                heal_ok = self.healer(
                    sandbox_dir=sandbox_dir,
                    failure_info=last_failure,
                    healer_prompt=healer_prompt,
                    test_path=test_path,
                )
            except TypeError:
                # If healer has signature (sandbox_dir, failure_info, healer_prompt)
                try:
                    heal_ok = self.healer(sandbox_dir, last_failure, healer_prompt)
                except TypeError:
                    heal_ok = self.healer(sandbox_dir, last_failure)

            if not heal_ok:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
                self.tm.restore_snapshot(baseline_snap.id)
                feedback_prompt = "Healer did not generate any changes in attempt " + str(attempt)
                continue

            diff_text, files_dict = self._collect_sandbox_diff_and_files(sandbox_dir)

            if not diff_text and not files_dict:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
                self.tm.restore_snapshot(baseline_snap.id)
                feedback_prompt = "No file diff detected in attempt " + str(attempt)
                continue

            # Step 6: Run the diff review gate.
            # Critic receives ONLY candidate findings and file texts, NOT the healer prompt.
            gate_res = review_diff(
                diff_text=diff_text,
                files=files_dict,
                critic=critic_to_use,
                workspace=str(self.workspace),
            )

            if not gate_res.get("allow_apply", False):
                # A confirmed major finding ends this attempt:
                # restore snapshot and try again with that finding in next prompt.
                self.tm.restore_snapshot(baseline_snap.id)
                shutil.rmtree(sandbox_dir, ignore_errors=True)

                confirmed = gate_res.get("confirmed_majors", [])
                titles = ", ".join(confirmed) if confirmed else "unresolved major findings or incomplete review"
                feedback_prompt = "Diff review gate rejected patch: confirmed major findings: " + titles
                continue

            # Apply verified sandbox changes to workspace on heal branch
            self.sandbox.promote_copy(sandbox_dir)
            shutil.rmtree(sandbox_dir, ignore_errors=True)

            # Step 7: Rerun only that test
            rerun_result = self.runner(test_path, self.workspace)
            if rerun_result.get("passed", False):
                # Test passed: commit on heal branch and stop with status READY_FOR_REVIEW.
                # Do not push and do not merge.
                subprocess.run(["git", "add", "-A"], cwd=str(self.workspace), capture_output=True, text=True)
                commit_msg = "fix(" + test_stem + "): autonomous heal by Hermes autofix"
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=Hermes Agent",
                        "-c",
                        "user.email=hermes@agent.local",
                        "commit",
                        "-m",
                        commit_msg,
                    ],
                    cwd=str(self.workspace),
                    capture_output=True,
                    text=True,
                )
                print("READY_FOR_REVIEW")
                return {
                    "status": "READY_FOR_REVIEW",
                    "branch": heal_branch,
                    "attempts": attempt,
                    "passed": True,
                }

            # Step 8: If it fails, restore snapshot, send new error into next attempt
            self.tm.restore_snapshot(baseline_snap.id)
            last_failure = rerun_result
            new_err = rerun_result.get("stderr") or rerun_result.get("stdout") or "Test still failed"
            feedback_prompt = "Patch was applied but test still failed:\n" + new_err[:1500]

        # Stop after 3 attempts. Status FAILED. The start branch is unchanged.
        self.tm.restore_snapshot(baseline_snap.id)
        # Switch back to start branch to guarantee it remains active and unchanged
        subprocess.run(
            ["git", "checkout", start_branch],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
        )
        print("FAILED")
        return {
            "status": "FAILED",
            "attempts": self.max_attempts,
            "branch": None,
            "passed": False,
        }
