"""
FastAPI Server & Webhook Listener for Hermes + Rerun AI Platform
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from agents.ci_detective import CIDetectiveAgent
from agents.test_healer_agent import TestHealerAgent
from core.rerun_bridge.orchestrator import RerunOrchestrator
from core.time_machine.engine import TimeMachineEngine

app = FastAPI(
    title="Hermes + Rerun Autonomous AI Platform",
    description="Automated Bug Detection, Multi-modal Diagnosis, and Time Machine Self-Healing Server",
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


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "workspace": str(WORKSPACE),
        "snapshots_count": len(tm.list_snapshots()),
    }


@app.post("/api/webhook/github-actions")
async def github_actions_webhook(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """Receive GitHub Actions workflow run events and trigger healing on failures."""
    event = CIDetectiveAgent.parse_webhook_payload(payload)
    if not event:
        return {"status": "ignored", "reason": "Not a failing workflow run"}

    routing = CIDetectiveAgent.get_recommended_ci_routing(Path(event.failing_test).name)

    # Dispatch healer agent in background
    if event.failing_test and event.failing_test != "Unknown Test":
        background_tasks.add_task(healer_agent.run_and_heal, event.failing_test)

    return {
        "status": "triaged",
        "event": {
            "run_id": event.run_id,
            "failing_test": event.failing_test,
            "recommended_job": routing["target_job"],
            "continue_on_error": routing["continue_on_error"],
        },
    }


@app.post("/api/heal")
def trigger_heal(req: HealRequest, background_tasks: BackgroundTasks):
    """Trigger the autonomous healer agent on a specific test target."""
    target_path = WORKSPACE / req.test_file
    if not target_path.exists() and not (Path.cwd() / req.test_file).exists():
        raise HTTPException(status_code=404, detail=f"Test file not found: {req.test_file}")

    result = healer_agent.run_and_heal(req.test_file, auto_rollback_on_failure=req.auto_rollback)
    return result


@app.get("/api/tasks")
def list_tasks():
    """List all agent tasks and pending approvals."""
    return {
        "tasks": orchestrator._read_tasks(),
        "pending_approvals": orchestrator.list_pending_approvals(),
    }


@app.post("/api/tasks/{task_id}/approve")
def approve_task(task_id: str, req: ApprovalRequest):
    """Human-in-the-loop approval: approve proposed patch."""
    ok = orchestrator.update_task_status(task_id, "COMPLETED")
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "approved", "task_id": task_id, "comment": req.comment}


@app.post("/api/tasks/{task_id}/rollback")
def rollback_task(task_id: str):
    """Human-in-the-loop rejection: rollback workspace to baseline snapshot."""
    tasks = orchestrator._read_tasks()
    target_task = next((t for t in tasks if t["id"] == task_id), None)
    if not target_task:
        raise HTTPException(status_code=404, detail="Task not found")

    snap_id = target_task.get("details", {}).get("baseline_snapshot")
    if snap_id:
        tm.restore_snapshot(snap_id)

    orchestrator.update_task_status(task_id, "ROLLED_BACK")
    return {"status": "rolled_back", "task_id": task_id, "restored_snapshot": snap_id}


@app.get("/api/time-machine/snapshots")
def list_snapshots(limit: int = 50):
    """List snapshots in the ledger."""
    return {"snapshots": tm.list_snapshots(limit=limit)}


@app.post("/api/time-machine/restore/{snapshot_id}")
def restore_snapshot(snapshot_id: str):
    """Manually restore workspace to any snapshot."""
    try:
        tm.restore_snapshot(snapshot_id)
        return {"status": "restored", "snapshot_id": snapshot_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("RERUN_SERVER_PORT", 8000))
    host = os.environ.get("RERUN_SERVER_HOST", "0.0.0.0")
    print(f"🚀 Starting Hermes + Rerun Webhook Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
