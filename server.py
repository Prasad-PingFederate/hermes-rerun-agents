"""
FastAPI Server & Webhook Listener for Hermes + Rerun AI Platform
Coordinates autonomous bug detection, multimodal diagnosis, approval-gated healing, and safe rollback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
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


class HealRequest(BaseModel):
    test_file: str
    auto_rollback: bool = True


class ApprovalRequest(BaseModel):
    approved_by: str = "Admin"
    comment: str = ""


async def verify_hermes_token(request: Request):
    """Enforces X-Hermes-Token authorization when HERMES_API_TOKEN is configured."""
    expected_token = os.environ.get("HERMES_API_TOKEN")
    if expected_token:
        provided_token = request.headers.get("X-Hermes-Token")
        if not provided_token or provided_token != expected_token:
            raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing X-Hermes-Token")


@app.get("/health")
def health_check():
    """Unauthenticated health status check."""
    return {
        "status": "healthy",
        "workspace": str(WORKSPACE),
        "snapshots_count": len(tm.list_snapshots()),
    }


@app.post("/api/webhook/github-actions")
async def github_actions_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive GitHub Actions workflow events and trigger healing on failures.
    
    Verifies X-Hub-Signature-256 HMAC SHA256 when WEBHOOK_SECRET is configured.
    """
    raw_body = await request.body()

    # Webhook signature verification
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    if webhook_secret:
        sig_header = request.headers.get("X-Hub-Signature-256")
        if not sig_header:
            raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")
        expected_sig = "sha256=" + hmac.new(
            webhook_secret.encode("utf-8"),
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

    # Unknown test name returns triaged=false and does not dispatch healer
    if not event.failing_test or event.failing_test == "Unknown Test":
        return {
            "status": "triaged",
            "triaged": False,
            "reason": "Unknown test name - healer not dispatched",
        }

    routing = CIDetectiveAgent.get_recommended_ci_routing(Path(event.failing_test).name)

    # Dispatch healer agent in background for triaged failure
    background_tasks.add_task(healer_agent.run_and_heal, event.failing_test)

    return {
        "status": "triaged",
        "triaged": True,
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
    target_path = WORKSPACE / req.test_file
    if not target_path.exists() and not (Path.cwd() / req.test_file).exists():
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


@app.post("/api/tasks/{task_id}/approve", dependencies=[Depends(verify_hermes_token)])
def approve_task(task_id: str, req: ApprovalRequest):
    """Human-in-the-loop approval: write gate that applies verified patch to workspace."""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve task in status '{task.status}'. Task must be in AWAITING_APPROVAL.",
        )

    try:
        res = healer_agent.approve_task(task_id)
        return {"status": "approved", "task_id": task_id, "comment": req.comment, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/{task_id}/rollback", dependencies=[Depends(verify_hermes_token)])
def rollback_task(task_id: str):
    """Human-in-the-loop rejection: rollback workspace to baseline snapshot."""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        res = healer_agent.rollback_task(task_id)
        return {"status": "rolled_back", "task_id": task_id, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/time-machine/snapshots", dependencies=[Depends(verify_hermes_token)])
def list_snapshots(limit: int = 50):
    """List snapshots in the ledger."""
    return {"snapshots": tm.list_snapshots(limit=limit)}


@app.post("/api/time-machine/restore/{snapshot_id}", dependencies=[Depends(verify_hermes_token)])
def restore_snapshot(snapshot_id: str):
    """Manually restore workspace to any snapshot."""
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
