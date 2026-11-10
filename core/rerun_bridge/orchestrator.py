"""
Rerun Bridge: Agent Task Orchestration & Human Approval Gate
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AgentTask:
    id: str
    title: str
    status: str  # PENDING, RUNNING, AWAITING_APPROVAL, COMPLETED, ROLLED_BACK
    created_at: str
    details: Dict[str, Any]
    approval_needed: bool = False
    proposed_patch: Optional[str] = None


class RerunOrchestrator:
    """Coordinates autonomous AI coworker tasks and enforces human approval gates."""

    def __init__(self, storage_dir: Optional[Path | str] = None):
        self.storage_dir = Path(storage_dir or Path.cwd() / ".rerun_tasks").resolve()
        self.tasks_file = self.storage_dir / "tasks.json"
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if not self.tasks_file.exists():
            with open(self.tasks_file, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, indent=2)

    def _read_tasks(self) -> List[Dict[str, Any]]:
        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                return json.load(f).get("tasks", [])
        except Exception:
            return []

    def _write_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)

    def create_task(self, title: str, details: Dict[str, Any], approval_needed: bool = True) -> AgentTask:
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._read_tasks()) + 1}"
        task = AgentTask(
            id=task_id,
            title=title,
            status="PENDING",
            created_at=datetime.now().isoformat(),
            details=details,
            approval_needed=approval_needed,
        )
        tasks = self._read_tasks()
        tasks.append(asdict(task))
        self._write_tasks(tasks)
        return task

    def update_task_status(self, task_id: str, status: str, proposed_patch: Optional[str] = None) -> bool:
        tasks = self._read_tasks()
        found = False
        for t in tasks:
            if t["id"] == task_id:
                t["status"] = status
                if proposed_patch:
                    t["proposed_patch"] = proposed_patch
                found = True
                break
        if found:
            self._write_tasks(tasks)
        return found

    def list_pending_approvals(self) -> List[AgentTask]:
        tasks = self._read_tasks()
        return [
            AgentTask(**t)
            for t in tasks
            if t.get("status") == "AWAITING_APPROVAL" and t.get("approval_needed")
        ]
