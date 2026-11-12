"""
FastAPI Server & Webhook Listener for Hermes + Rerun AI Platform
Coordinates autonomous bug detection, multimodal diagnosis, approval-gated healing, and safe rollback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from agents.ci_detective import CIDetectiveAgent
from agents.test_healer_agent import TestHealerAgent
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine
from core.time_machine.patch_guard import analyze_proposed_changes
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore
from write_gate_controller import HumanWriteGateController

app = FastAPI(
    title="Hermes + Rerun Autonomous AI Platform",
    description="Automated Bug Detection, Multimodal Diagnosis, and Time Machine Self-Healing Server",
    version="1.0.0",
)

WORKSPACE = Path(os.environ.get("TARGET_WORKSPACE_PATH", Path.cwd())).resolve()
tm = TimeMachineEngine(WORKSPACE)
orchestrator = RerunOrchestrator(WORKSPACE / ".rerun_tasks")
healer_agent = TestHealerAgent(WORKSPACE)
sprint_store = SprintStateStore(WORKSPACE / ".hermes_sprint_state.db")
scrum_master = ScrumMasterOrchestrator(
    workspace_path=WORKSPACE,
    tm_engine=tm,
    store=sprint_store,
)

TASK_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class SprintRunRequest(BaseModel):
    mode: str = "story"
    story: Optional[str] = None
    failure_output: Optional[str] = None
    scope: Optional[List[str]] = None
    pytest_cmd: Optional[str] = None
    auto_approve: bool = False


class SprintApproveRequest(BaseModel):
    verify: bool = True
    pytest_cmd: Optional[str] = None


class HealRequest(BaseModel):
    test_file: str
    auto_rollback: bool = False


class ApprovalRequest(BaseModel):
    approved_by: str = "Admin"
    comment: str = ""


class ApplyRequest(BaseModel):
    verify_test: bool = False
    allow_test_modification: bool = False


class SprintPlanRequest(BaseModel):
    tickets: Optional[List[Dict[str, Any]]] = None
    allowed_files: Optional[List[str]] = None


class PruneRequest(BaseModel):
    keep_last: int = 10


class ContextSearchRequest(BaseModel):
    query: str
    tier: Optional[int] = None


class ContextCompressRequest(BaseModel):
    content: str
    label: str = "custom"
    metadata: Optional[Dict[str, Any]] = None


def compute_failure_fingerprint(
    repo_or_branch: str,
    test_or_workflow: str,
    error_summary: str,
) -> str:
    """Compute a deterministic SHA-256 failure fingerprint from normalized failure metadata."""
    norm = f"{str(repo_or_branch).strip().lower()}:{str(test_or_workflow).strip().lower()}:{str(error_summary).strip().lower()}"
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def validate_task_id(task_id: str) -> str:
    """Validate task_id with strict regex ^[a-zA-Z0-9_-]{1,64}$ to prevent traversal."""
    if not task_id or not TASK_ID_REGEX.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    return task_id


def validate_test_file_path(workspace: Path, test_file: str) -> Path:
    """Reject paths starting with '-', '..', absolute paths, protected directories, and symlinks."""
    if not test_file or not str(test_file).strip():
        raise HTTPException(status_code=400, detail="test_file cannot be empty")
    rel_str = str(test_file).strip()

    if rel_str.startswith("-"):
        raise HTTPException(status_code=400, detail="Paths starting with '-' are rejected")

    if os.path.isabs(rel_str):
        raise HTTPException(status_code=400, detail="Absolute paths are rejected")

    norm = Path(rel_str)
    if any(part.startswith("-") for part in norm.parts):
        raise HTTPException(status_code=400, detail="Path segments starting with '-' are rejected")

    if ".." in norm.parts:
        raise HTTPException(status_code=400, detail="Path traversal '..' is rejected")

    # Reject protected directories (.git, .tm_snapshots, .rerun_tasks, .env*)
    protected_names = {".git", ".tm_snapshots", ".rerun_tasks", ".env"}
    for part in norm.parts:
        if part in protected_names or part.startswith(".env."):
            raise HTTPException(status_code=400, detail=f"Access to protected path '{part}' is rejected")

    # Walk from workspace down and reject symlinks
    workspace_root = workspace.resolve()
    current = workspace_root
    for part in norm.parts:
        current = current / part
        if current.is_symlink() or os.path.islink(str(current)):
            raise HTTPException(status_code=400, detail=f"Symlinks are rejected: {part}")

    resolved = (workspace / norm).resolve()
    try:
        if not resolved.is_relative_to(workspace_root):
            raise HTTPException(status_code=400, detail="Resolved path escapes workspace")
    except AttributeError:
        try:
            resolved.relative_to(workspace_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Resolved path escapes workspace")

    return (workspace / norm)


async def verify_hermes_token(request: Request):
    """Require a non-whitespace shared token from environment on all protected endpoints."""
    raw_token = (
        os.environ.get("HERMES_API_TOKEN")
        or os.environ.get("RERUN_AUTH_TOKEN")
        or os.environ.get("SHARED_TOKEN")
    )
    if not raw_token or not raw_token.strip():
        raise HTTPException(status_code=401, detail="Unauthorized: shared token not configured in environment")
    expected_token = raw_token.strip()

    provided_token = request.headers.get("X-Hermes-Token") or request.headers.get("X-Auth-Token")
    if not provided_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()

    if not provided_token:
        raise HTTPException(status_code=401, detail="Unauthorized: missing authentication token")

    if not hmac.compare_digest(provided_token.strip(), expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid token")


@app.get("/health")
def health_check():
    """Unauthenticated health status check."""
    return {
        "status": "healthy",
        "workspace": str(WORKSPACE),
        "snapshots_count": len(tm.list_snapshots()),
    }


@app.post("/api/webhook/github-actions")
async def github_actions_webhook(request: Request):
    """Receive GitHub Actions workflow events.
    
    Verifies X-Hub-Signature-256 HMAC SHA256 when WEBHOOK_SECRET is configured,
    and rejects the request when it is not.
    Creates a task in AWAITING_APPROVAL and returns the task id without modifying the repo.
    """
    raw_body = await request.body()

    # Webhook signature verification: verify when secret configured, reject when not
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    if not webhook_secret or not webhook_secret.strip():
        raise HTTPException(status_code=401, detail="Webhook secret not configured in environment")

    sig_header = request.headers.get("X-Hub-Signature-256")
    if not sig_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected_sig = "sha256=" + hmac.new(
        webhook_secret.strip().encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig_header, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid X-Hub-Signature-256 signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = CIDetectiveAgent.parse_webhook_payload(payload)
    if not event:
        return {"status": "ignored", "reason": "Not a failing workflow event"}

    # Unknown test name returns triaged=false and does not create task
    if not event.failing_test or event.failing_test == "Unknown Test":
        return {
            "status": "triaged",
            "triaged": False,
            "reason": "Unknown test name - task not created",
        }

    routing = CIDetectiveAgent.get_recommended_ci_routing(Path(event.failing_test).name)

    repo_branch = (
        payload.get("repository", {}).get("full_name")
        or payload.get("repository", {}).get("name")
        or payload.get("workflow_run", {}).get("head_branch")
        or "default_repo"
    )
    test_or_wf = event.failing_test
    err_summary = getattr(event, "error_snippet", "") or getattr(event, "conclusion", "") or ""
    fingerprint = compute_failure_fingerprint(str(repo_branch), str(test_or_wf), str(err_summary))

    # Check for existing matching task in AWAITING_APPROVAL or APPROVED
    for t in orchestrator._read_tasks():
        if t.get("status") in ("AWAITING_APPROVAL", "APPROVED"):
            t_details = t.get("details", {})
            if t_details.get("failure_fingerprint") == fingerprint:
                current_count = t_details.get("occurrence_count", 1) + 1
                orchestrator.update_task_status(
                    t["id"],
                    t["status"],
                    details={"occurrence_count": current_count},
                )
                return {
                    "status": "triaged",
                    "triaged": True,
                    "deduplicated": True,
                    "task_id": t["id"],
                    "occurrence_count": current_count,
                    "event": {
                        "run_id": event.run_id,
                        "failing_test": event.failing_test,
                        "recommended_job": routing["target_job"],
                        "continue_on_error": routing["continue_on_error"],
                    },
                }

    # Create task in AWAITING_APPROVAL and return task id without editing repo
    task = orchestrator.create_task(
        title=f"CI Failure: {Path(event.failing_test).name}",
        details={
            "run_id": event.run_id,
            "failing_test": event.failing_test,
            "recommended_job": routing["target_job"],
            "continue_on_error": routing["continue_on_error"],
            "failure_fingerprint": fingerprint,
            "occurrence_count": 1,
        },
    )
    orchestrator.update_task_status(task.id, "AWAITING_APPROVAL")

    return {
        "status": "triaged",
        "triaged": True,
        "task_id": task.id,
        "event": {
            "run_id": event.run_id,
            "failing_test": event.failing_test,
            "recommended_job": routing["target_job"],
            "continue_on_error": routing["continue_on_error"],
        },
    }


@app.post("/api/heal", dependencies=[Depends(verify_hermes_token)])
def trigger_heal(req: HealRequest, background_tasks: BackgroundTasks):
    """Trigger the autonomous healer agent on a specific test target."""
    target_path = validate_test_file_path(WORKSPACE, req.test_file)
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Test file not found: {req.test_file}")

    result = healer_agent.run_and_heal(req.test_file, auto_rollback_on_failure=req.auto_rollback)
    return result


@app.get("/api/tasks", dependencies=[Depends(verify_hermes_token)])
def list_tasks():
    """List all agent tasks and pending approvals."""
    return {
        "tasks": orchestrator._read_tasks(),
        "pending_approvals": orchestrator.list_pending_approvals(),
    }


@app.get("/api/tasks/{task_id}", dependencies=[Depends(verify_hermes_token)])
def get_task(task_id: str):
    """Get single task details."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@app.post("/api/tasks/{task_id}/approve", dependencies=[Depends(verify_hermes_token)])
def approve_task(task_id: str, req: ApprovalRequest = ApprovalRequest()):
    """Human approval: Transitions task from AWAITING_APPROVAL -> APPROVED; must not write files."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve task in status '{task.status}'. Task must be in AWAITING_APPROVAL.",
        )

    res = healer_agent.approve_task(task_id)
    return {
        "status": "approved",
        "task_id": task_id,
        "task_status": "APPROVED",
        "comment": req.comment,
        "result": res,
    }


@app.post("/api/tasks/{task_id}/sprint-plan", dependencies=[Depends(verify_hermes_token)])
def create_task_sprint_plan(task_id: str, req: SprintPlanRequest = SprintPlanRequest()):
    """Decompose failure into hierarchical sprint plan with tiered SWE routing and telemetry."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        if hasattr(req, "model_dump"):
            plan_context = req.model_dump(exclude_none=True)
        elif hasattr(req, "dict"):
            plan_context = req.dict(exclude_none=True)
        else:
            plan_context = {}
        sprint_plan = healer_agent.create_sprint_plan(task_id, plan_context)
        return {
            "status": "sprint_plan_created",
            "task_id": task_id,
            "sprint_plan": sprint_plan,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/{task_id}/sprint-board", dependencies=[Depends(verify_hermes_token)])
def get_task_sprint_board(task_id: str):
    """Get sprint board, tickets, attempt/escalation history, and cost telemetry."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        board = healer_agent.get_sprint_board(task_id)
        return {
            "status": "success",
            "task_id": task_id,
            "sprint_board": board,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sprint/{sprint_id}", dependencies=[Depends(verify_hermes_token)])
def get_sprint(sprint_id: str):
    """Retrieve sprint details and ticket states from SprintStateStore."""
    data = sprint_store.load_sprint(sprint_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")
    return {"status": "success", "sprint": data}


@app.post("/api/sprint/run", dependencies=[Depends(verify_hermes_token)])
def run_sprint_endpoint(req: SprintRunRequest):
    """Execute unified multi-agent sprint pipeline (story or heal mode)."""
    try:
        res = scrum_master.run_sprint(
            mode=req.mode,
            story=req.story,
            failure_output=req.failure_output,
            scope=req.scope,
            pytest_cmd=req.pytest_cmd,
            auto_approve=req.auto_approve,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sprint/{sprint_id}/approve", dependencies=[Depends(verify_hermes_token)])
def approve_sprint_endpoint(sprint_id: str, req: SprintApproveRequest = SprintApproveRequest()):
    """Approve staged proposal for sprint, verify via test command, and commit or rollback."""
    staged = scrum_master.write_gate.get_staged_proposal(sprint_id)
    if not staged:
        raise HTTPException(status_code=404, detail=f"No staged proposal found for sprint '{sprint_id}'")

    cmd = req.pytest_cmd or "pytest -q"
    verification_fn = None
    if req.verify:
        def _verify():
            import subprocess
            p = subprocess.run(cmd, cwd=str(WORKSPACE), shell=True, capture_output=True)
            return p.returncode == 0
        verification_fn = _verify

    try:
        res = scrum_master.write_gate.approve_proposal(sprint_id, verification_fn=verification_fn)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/apply", dependencies=[Depends(verify_hermes_token)])
def apply_task(task_id: str, req: ApplyRequest = ApplyRequest()):
    """Explicit apply endpoint: Applies proposed patch only after task is AWAITING_APPROVAL or APPROVED."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("AWAITING_APPROVAL", "APPROVED"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot apply task in status '{task.status}'. Task must be in AWAITING_APPROVAL or APPROVED.",
        )

    # 1. Collect proposed file changes
    sandbox_copy = task.details.get("sandbox_copy")
    proposed_patch = task.proposed_patch
    if not sandbox_copy and not proposed_patch:
        raise HTTPException(status_code=400, detail="Task has no proposed changes or patch to apply")

    proposed_changes: Dict[str, str] = {}
    if sandbox_copy and Path(sandbox_copy).is_dir():
        copy_dir = Path(sandbox_copy)
        for root, dirs, files in os.walk(copy_dir):
            dirs[:] = [
                d for d in dirs
                if d not in tm.SKIP_DIRS
                and not d.startswith(".env.")
                and d != ".env"
            ]
            for f in files:
                if f in tm.SKIP_FILES or f == ".env" or f.startswith(".env.") or f in tm.SKIP_DIRS:
                    continue
                full_p = Path(root) / f
                rel_p = str(full_p.relative_to(copy_dir)).replace("\\", "/")
                try:
                    proposed_changes[rel_p] = full_p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    elif proposed_patch:
        target_f = task.details.get("target_file")
        if target_f:
            proposed_changes[target_f] = proposed_patch

    # 2. Scope Gate: Enforce allowed_files from sprint_plan if present
    sprint_plan = task.details.get("sprint_plan")
    if sprint_plan:
        allowed_set: Set[str] = set()
        for t in sprint_plan.get("tickets", []):
            for af in t.get("allowed_files", []):
                allowed_set.add(af.replace("\\", "/"))

        if allowed_set:
            violating = set()
            for p_file in proposed_changes.keys():
                norm_p = p_file.replace("\\", "/")
                if norm_p not in allowed_set:
                    violating.add(norm_p)
            if violating:
                raise HTTPException(
                    status_code=400,
                    detail=f"Sprint scope violation: proposed changes modify files outside allowed_files: {sorted(list(violating))}. Allowed files: {sorted(list(allowed_set))}",
                )

    # 3. Run AST Test-Tampering Guard & Blast-Radius Analyzer
    if proposed_changes:
        try:
            report = analyze_proposed_changes(
                workspace_root=WORKSPACE,
                proposed_changes=proposed_changes,
                allow_test_modification=req.allow_test_modification,
            )
            if not report.get("valid", True):
                reasons = report.get("tampering_reasons", [])
                raise HTTPException(
                    status_code=400,
                    detail=f"Test tampering detected: {'; '.join(reasons)}",
                )
            task.details["blast_radius"] = report.get("blast_radius", {})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # 3. Apply changes safely
    try:
        res = healer_agent.apply_task(task_id)
        if "blast_radius" in task.details:
            orchestrator.update_task_status(
                task_id,
                "COMPLETED",
                details={"blast_radius": task.details["blast_radius"]},
            )
            res["blast_radius"] = task.details["blast_radius"]

        # 4. Optional Post-Apply Verification
        if req.verify_test:
            test_target = task.details.get("test_file") or task.details.get("failing_test")
            if test_target:
                exec_res = healer_agent.sandbox.execute_test(test_target)
                if not exec_res.passed:
                    snap_id = res.get("applied_snapshot") or res.get("pre_apply_snapshot_id")
                    created = res.get("created_files", [])
                    if snap_id:
                        tm.restore_snapshot(snap_id, delete_files=created)
                    orchestrator.update_task_status(
                        task_id,
                        "VERIFY_FAILED_ROLLED_BACK",
                        details={"verification": {"passed": False, "returncode": exec_res.returncode, "stderr": exec_res.stderr}},
                    )
                    return {
                        "status": "VERIFY_FAILED_ROLLED_BACK",
                        "task_id": task_id,
                        "verification": {
                            "passed": False,
                            "returncode": exec_res.returncode,
                            "stdout": exec_res.stdout,
                            "stderr": exec_res.stderr,
                        },
                    }

        return {"status": "applied", "task_id": task_id, "task_status": "COMPLETED", "result": res}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/rollback", dependencies=[Depends(verify_hermes_token)])
def rollback_task(task_id: str):
    """Surgical task rollback: Restores pre_apply_snapshot_id and deletes created files."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rollback task in status '{task.status}'. Task must be COMPLETED.",
        )

    snap_id = (
        task.details.get("pre_apply_snapshot_id")
        or task.details.get("applied_snapshot")
        or task.details.get("baseline_snapshot")
    )
    if not snap_id:
        raise HTTPException(status_code=400, detail="No snapshot found on task to roll back to.")

    created_files = task.details.get("created_files", [])
    try:
        res = tm.restore_snapshot(snap_id, delete_files=created_files)
        from datetime import datetime
        rolled_back_at = datetime.now().isoformat()
        orchestrator.update_task_status(
            task_id,
            "ROLLED_BACK",
            details={"rolled_back_at": rolled_back_at},
        )
        return {
            "status": "rolled_back",
            "task_id": task_id,
            "restored_snapshot": snap_id,
            "rolled_back_at": rolled_back_at,
            "details": res,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/time-machine/snapshots", dependencies=[Depends(verify_hermes_token)])
@app.get("/api/time-machine/snapshot", dependencies=[Depends(verify_hermes_token)])
def list_snapshots(limit: int = 50):
    """List snapshots in the ledger."""
    return {"snapshots": tm.list_snapshots(limit=limit)}


@app.post("/api/time-machine/snapshot", dependencies=[Depends(verify_hermes_token)])
def create_snapshot(label: str = "manual_snapshot"):
    """Create a new snapshot."""
    snap = tm.create_snapshot(label)
    return {"snapshot": snap}


@app.get("/api/time-machine/snapshots/{snapshot_id}/diff", dependencies=[Depends(verify_hermes_token)])
def snapshot_diff_endpoint(snapshot_id: str):
    """Diff live workspace against snapshot without git."""
    try:
        res = tm.diff_snapshot(snapshot_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/time-machine/restore/{snapshot_id}", dependencies=[Depends(verify_hermes_token)])
def restore_snapshot(snapshot_id: str):
    """Restore workspace to any snapshot."""
    try:
        res = tm.restore_snapshot(snapshot_id)
        return {"status": "restored", "snapshot_id": snapshot_id, "details": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/time-machine/prune", dependencies=[Depends(verify_hermes_token)])
def prune_snapshots_endpoint(req: PruneRequest = PruneRequest()):
    """Prunes old snapshots while protecting snapshots pinned by any task in .rerun_tasks/."""
    tasks = orchestrator._read_tasks()
    pinned_ids: Set[str] = set()
    for t in tasks:
        td = t.get("details", {})
        for key in ("pre_apply_snapshot_id", "applied_snapshot", "baseline_snapshot"):
            sid = td.get(key)
            if sid:
                pinned_ids.add(sid)

    res = tm.prune_snapshots(keep_last=req.keep_last, pinned_ids=pinned_ids)
    return {
        "status": "pruned",
        "keep_last": req.keep_last,
        "kept": res["kept"],
        "deleted": res["deleted"],
        "pinned_ids": list(pinned_ids),
    }


@app.get("/api/context/status", dependencies=[Depends(verify_hermes_token)])
def get_context_status():
    """Active Context Pruning (ACP) / Billion-Context memory telemetry."""
    return {
        "status": "success",
        "acp": healer_agent.context_manager.acp_status(),
    }


@app.post("/api/context/search", dependencies=[Depends(verify_hermes_token)])
def search_context_endpoint(req: ContextSearchRequest):
    """Query compressed context memory blocks without active window inflation."""
    results = healer_agent.context_manager.search_context(req.query, tier=req.tier)
    return {
        "status": "success",
        "query": req.query,
        "results": results,
    }


@app.post("/api/context/decompress/{block_id}", dependencies=[Depends(verify_hermes_token)])
def decompress_block_endpoint(block_id: str):
    """Reversibly retrieve unabridged raw content for any historical block."""
    try:
        raw = healer_agent.context_manager.decompress(block_id)
        return {
            "status": "success",
            "block_id": block_id,
            "raw_content": raw,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/context/compress", dependencies=[Depends(verify_hermes_token)])
def compress_context_endpoint(req: ContextCompressRequest):
    """Ingest and compress context using Active Context Pruning."""
    from dataclasses import asdict
    blk = healer_agent.context_manager.ingest(
        content=req.content,
        label=req.label,
        metadata=req.metadata,
    )
    return {
        "status": "compressed",
        "block": asdict(blk),
        "acp": healer_agent.context_manager.acp_status(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("RERUN_SERVER_PORT", 8000))
    host = os.environ.get("RERUN_SERVER_HOST", "127.0.0.1")
    print(f"🚀 Starting Hermes + Rerun Webhook Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
