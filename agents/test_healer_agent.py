"""
Autonomous Test Failure Healer Agent with Time Machine Safety Guardrail
Executes tests in isolated sandbox copies to enforce human approval before modifying caller workspace.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from agents.breakglass_responder_healer import BreakglassResponderHealerSkill
from core.healer.gemini_flash import GeminiFlashHealer
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.sandbox.runner import SandboxRunner
from core.time_machine.engine import TimeMachineEngine


class TestHealerAgent:
    """Autonomous agent that investigates, heals, and verifies test failures with rollback safety."""

    def __init__(
        self,
        workspace_path: Optional[str | Path] = None,
        gemini_api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = TimeMachineEngine(self.workspace_path)
        self.healer = GeminiFlashHealer(api_key=gemini_api_key, ollama_base_url=ollama_base_url)
        self.sandbox = SandboxRunner(self.workspace_path)
        self.orchestrator = RerunOrchestrator(self.workspace_path / ".rerun_tasks")

    def run_and_heal(
        self,
        test_file: str,
        auto_rollback_on_failure: bool = False,
        auto_apply_fix: bool = True,
    ) -> Dict[str, Any]:
        """Execute a test; if it fails, diagnose and safely attempt remediation with rollback protection."""
        # Preflight: Verify pytest is available
        if not self.sandbox.is_pytest_available():
            err_msg = "[SANDBOX] pytest is not installed in the active Python environment."
            print(f"[AGENT] ⚠️ {err_msg}")
            return {
                "status": "TOOL_MISSING",
                "error": err_msg,
                "is_tool_missing": True,
            }

        stem = Path(test_file).stem
        print(f"[AGENT] 📸 Taking baseline Time Machine snapshot before running: {test_file}")
        baseline_snap = self.tm.create_snapshot(
            label=f"pre_test_{stem}",
            description=f"Baseline state before executing {test_file}",
        )

        task = self.orchestrator.create_task(
            title=f"Test & Heal: {test_file}",
            details={"test_file": test_file, "baseline_snapshot": baseline_snap.id},
        )
        self.orchestrator.update_task_status(task.id, "RUNNING")

        # Create isolated workspace copy for safe execution and patching
        sandbox_dir = self.sandbox.create_isolated_copy()

        # 1. Execute initial test inside isolated sandbox copy
        print(f"[AGENT] 🧪 Executing test in sandbox copy: {test_file} ...")
        res1 = self.sandbox.execute_test(test_file, target_dir=sandbox_dir)

        if res1.passed:
            print("[AGENT] ✅ Test passed cleanly on first attempt.")
            shutil.rmtree(sandbox_dir, ignore_errors=True)
            self.orchestrator.update_task_status(task.id, "COMPLETED")
            return {
                "status": "PASSED",
                "snapshot_id": baseline_snap.id,
                "task_id": task.id,
                "duration": res1.duration_seconds,
            }

        # 2. Test failed - extract failure context
        print(f"[AGENT] ❌ Test failed (code {res1.returncode}). Initiating Failure Diagnosis...")
        target_in_sandbox = sandbox_dir / test_file
        code_snippet = ""
        if target_in_sandbox.is_file():
            try:
                code_snippet = target_in_sandbox.read_text(encoding="utf-8", errors="replace")[:1500]
            except Exception:
                pass

        applied_skill = False
        diagnosis: Dict[str, Any] = {}

        # Check domain-specific skill first (e.g. Breakglass QR Expired preview bug)
        if BreakglassResponderHealerSkill.is_matching_failure(test_file, res1.stderr or res1.stdout, res1.stdout):
            print("[AGENT] 💡 Breakglass Preview Handshake / QR Expired pattern detected! Applying specialized skill in sandbox copy...")
            ok, msg = BreakglassResponderHealerSkill.apply_recovery_patch(target_in_sandbox)
            applied_skill = ok
            diagnosis = {
                "engine": "Breakglass Skill",
                "category": "Stage Preview Crypto Handshake Timeout",
                "root_cause": msg,
            }
        else:
            err_snip = res1.stderr or res1.stdout[-400:]
            diagnosis = self.healer.diagnose_failure(
                test_name=test_file,
                error_message=err_snip,
                traceback_str=res1.stdout,
                code_snippet=code_snippet,
                screenshot_path=res1.screenshot_path,
            )
            # If model returned files with diffs, apply them inside the sandbox copy
            if auto_apply_fix and diagnosis.get("files"):
                applied_any = False
                for f_entry in diagnosis["files"]:
                    p_path = f_entry.get("path") or test_file
                    diff_text = f_entry.get("unified_diff")
                    if diff_text:
                        ok, _ = self.sandbox.apply_patch_in_copy(sandbox_dir, p_path, diff_text)
                        if ok:
                            applied_any = True
                applied_skill = applied_any

        print("\n" + "=" * 60)
        print("🤖 [AI DIAGNOSIS RESULT]")
        print(f"Engine:   {diagnosis.get('engine')}")
        print(f"Category: {diagnosis.get('category')}")
        if diagnosis.get("analysis"):
            print(f"Analysis: {diagnosis.get('analysis')[:300]}...")
        elif diagnosis.get("root_cause"):
            print(f"Root Cause: {diagnosis.get('root_cause')}")
        print("=" * 60 + "\n")

        # 3. If a patch was applied, re-verify in sandbox copy
        if applied_skill:
            print("[AGENT] 🔄 Re-executing test in sandbox copy to verify patch...")
            res2 = self.sandbox.execute_test(test_file, target_dir=sandbox_dir)
            if res2.passed:
                print("[AGENT] 🏆 Patch verified! Test passed in sandbox copy. Holding for Human Approval.")
                diff_proc = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=str(sandbox_dir),
                    capture_output=True,
                    text=True,
                )
                patch_content = diff_proc.stdout

                self.orchestrator.update_task_status(
                    task.id,
                    "AWAITING_APPROVAL",
                    proposed_patch=patch_content,
                    details={
                        "test_file": test_file,
                        "baseline_snapshot": baseline_snap.id,
                        "sandbox_copy": str(sandbox_dir),
                        "diagnosis": diagnosis,
                    },
                )
                return {
                    "status": "HEALED_VERIFIED",
                    "baseline_snapshot": baseline_snap.id,
                    "task_id": task.id,
                    "diagnosis": diagnosis,
                    "proposed_patch": patch_content,
                    "sandbox_copy": str(sandbox_dir),
                }
            else:
                print(f"[AGENT] ⚠️ Patch did not resolve the failure. Return code {res2.returncode}.\nOutput:\n{res2.stdout}\n{res2.stderr}")

        # Discard sandbox copy on failure
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        self.orchestrator.update_task_status(task.id, "FAILED")

        # Safe rollback check if caller workspace had changes
        if auto_rollback_on_failure:
            print(f"[AGENT] 🛡️ Safety Guardrail Triggered: Ensuring workspace remains at baseline {baseline_snap.id}...")
            self.tm.restore_snapshot(baseline_snap.id)

        return {
            "status": "FAILED_DIAGNOSED",
            "snapshot_id": baseline_snap.id,
            "task_id": task.id,
            "diagnosis": diagnosis,
        }

    def approve_task(self, task_id: str) -> Dict[str, Any]:
        """Human approval write-gate: Transitions task from AWAITING_APPROVAL to APPROVED without writing files."""
        task = self.orchestrator.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        if task.status != "AWAITING_APPROVAL":
            raise ValueError(f"Cannot approve task in state '{task.status}'. Task must be in AWAITING_APPROVAL.")

        self.orchestrator.update_task_status(task_id, "APPROVED")
        return {
            "status": "APPROVED",
            "task_id": task_id,
        }

    def apply_task(self, task_id: str) -> Dict[str, Any]:
        """Explicit apply: Applies proposed patch to workspace only after task is AWAITING_APPROVAL or APPROVED."""
        task = self.orchestrator.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        if task.status not in ("AWAITING_APPROVAL", "APPROVED"):
            raise ValueError(f"Cannot apply task in state '{task.status}'. Task must be in AWAITING_APPROVAL or APPROVED.")

        sandbox_copy = task.details.get("sandbox_copy")
        proposed_patch = task.proposed_patch

        if not sandbox_copy and not proposed_patch:
            raise ValueError("Task has no proposed changes or patch to apply")

        files_to_apply: List[str] = []
        if sandbox_copy and Path(sandbox_copy).is_dir():
            copy_dir = Path(sandbox_copy)
            if (copy_dir / ".git").is_dir():
                diff_proc = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD"],
                    cwd=str(copy_dir),
                    capture_output=True,
                    text=True,
                )
                if diff_proc.returncode == 0:
                    for line in diff_proc.stdout.splitlines():
                        line = line.strip()
                        if line:
                            files_to_apply.append(line.replace("\\", "/"))

                untracked_proc = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=str(copy_dir),
                    capture_output=True,
                    text=True,
                )
                if untracked_proc.returncode == 0:
                    for line in untracked_proc.stdout.splitlines():
                        line = line.strip()
                        if line:
                            files_to_apply.append(line.replace("\\", "/"))

            # Fallback or supplementary walk if git returned no files
            if not files_to_apply:
                for root, dirs, files in os.walk(copy_dir):
                    dirs[:] = [
                        d for d in dirs
                        if d not in self.tm.SKIP_DIRS
                        and not d.startswith(".env.")
                        and d != ".env"
                    ]
                    for f in files:
                        if f in self.tm.SKIP_FILES or f == ".env" or f.startswith(".env.") or f in self.tm.SKIP_DIRS:
                            continue
                        full_p = Path(root) / f
                        rel_p = str(full_p.relative_to(copy_dir)).replace("\\", "/")
                        files_to_apply.append(rel_p)
        elif proposed_patch:
            target_f = task.details.get("target_file")
            if target_f:
                files_to_apply.append(target_f)

        # Sanitize and ensure no protected path is ever included
        safe_files_to_apply = []
        for rel_f in files_to_apply:
            parts = Path(rel_f).parts
            if any(part in self.tm.SKIP_DIRS or part == ".env" or part.startswith(".env.") for part in parts):
                continue
            if rel_f not in safe_files_to_apply:
                safe_files_to_apply.append(rel_f)
        files_to_apply = safe_files_to_apply

        if not files_to_apply:
            raise ValueError("Task has no proposed file changes to apply")

        # Validate every target file path in proposed changes using workspace path validator
        for rel_file in files_to_apply:
            self.tm._validate_safe_workspace_path(rel_file, allow_missing=True)

        # Take a snapshot via TimeMachine before writing files
        pre_apply_snap = self.tm.create_snapshot(
            label=f"pre_apply_{task_id}",
            description=f"Snapshot before applying patch for task {task_id}",
        )

        created_files = []
        modified_files = []

        # Write changes safely
        for rel_file in files_to_apply:
            dest = self.workspace_path / rel_file
            if dest.exists():
                modified_files.append(rel_file)
            else:
                created_files.append(rel_file)

            if sandbox_copy:
                src = Path(sandbox_copy) / rel_file
                if not src.is_file():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_symlink() or os.path.islink(str(dest)) or dest.is_file():
                    dest.unlink()
                shutil.copy2(src, dest)

        if sandbox_copy and Path(sandbox_copy).is_dir():
            shutil.rmtree(sandbox_copy, ignore_errors=True)

        task.details["created_files"] = created_files
        task.details["modified_files"] = modified_files
        task.details["applied_snapshot"] = pre_apply_snap.id

        # Only then set status to COMPLETED
        self.orchestrator.update_task_status(task_id, "COMPLETED")
        return {
            "status": "COMPLETED",
            "task_id": task_id,
            "created_files": created_files,
            "modified_files": modified_files,
            "applied_snapshot": pre_apply_snap.id,
        }

    def rollback_task(self, task_id: str) -> Dict[str, Any]:
        """Human rejection: Restores workspace to baseline snapshot and marks ROLLED_BACK."""
        task = self.orchestrator.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        sandbox_copy = task.details.get("sandbox_copy")
        if sandbox_copy and Path(sandbox_copy).is_dir():
            shutil.rmtree(sandbox_copy, ignore_errors=True)

        baseline_id = task.details.get("baseline_snapshot")
        if baseline_id:
            self.tm.restore_snapshot(baseline_id, create_safety_snapshot=True)

        self.orchestrator.update_task_status(task_id, "ROLLED_BACK")
        return {
            "status": "ROLLED_BACK",
            "task_id": task_id,
            "restored_snapshot": baseline_id,
        }
