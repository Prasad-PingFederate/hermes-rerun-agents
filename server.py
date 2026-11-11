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
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from agents.ci_detective import CIDetectiveAgent
from agents.test_healer_agent import TestHealerAgent
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine

app = FastAPI(
    title="Hermes + Rerun Autonomous AI Platform",
    description="Automated Bug Detection, Multimodal Diagnosis, and Time Machine Self-Healing Server",
    version="1.0.0",
)

WORKSPACE = Path(os.environ.get("TARGET_WORKSPACE_PATH", Path.cwd())).resolve()
tm = TimeMachineEngine(WORKSPACE)
orchestrator = RerunOrchestrator(WORKSPACE / ".rerun_tasks")
healer_agent = TestHealerAgent(WORKSPACE)

TASK_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class HealRequest(BaseModel):
    test_file: str
    auto_rollback: bool = False


class ApprovalRequest(BaseModel):
    approved_by: str = "Admin"
    comment: str = ""


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

    # Create task in AWAITING_APPROVAL and return task id without editing repo
    task = orchestrator.create_task(
        title=f"CI Failure: {Path(event.failing_test).name}",
        details={
            "run_id": event.run_id,
            "failing_test": event.failing_test,
            "recommended_job": routing["target_job"],
            "continue_on_error": routing["continue_on_error"],
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


@app.post("/api/tasks/{task_id}/apply", dependencies=[Depends(verify_hermes_token)])
def apply_task(task_id: str):
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

    try:
        res = healer_agent.apply_task(task_id)
        return {"status": "applied", "task_id": task_id, "task_status": "COMPLETED", "result": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/rollback", dependencies=[Depends(verify_hermes_token)])
def rollback_task(task_id: str):
    """Human-in-the-loop rejection: rollback workspace to baseline snapshot."""
    validate_task_id(task_id)
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        res = healer_agent.rollback_task(task_id)
        return {"status": "rolled_back", "task_id": task_id, "result": res}
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


@app.post("/api/time-machine/restore/{snapshot_id}", dependencies=[Depends(verify_hermes_token)])
def restore_snapshot(snapshot_id: str):
    """Restore workspace to any snapshot."""
    try:
        res = tm.restore_snapshot(snapshot_id)
        return {"status": "restored", "snapshot_id": snapshot_id, "details": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("RERUN_SERVER_PORT", 8000))
    host = os.environ.get("RERUN_SERVER_HOST", "127.0.0.1")
    print(f"🚀 Starting Hermes + Rerun Webhook Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
