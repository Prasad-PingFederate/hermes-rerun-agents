"""
GAP-12: Persistent Sprint Ledger & Resumable Human Write-Gate Store
Owner: ScrumMasterOrchestrator, TIER_1

Provides durable SQLite + JSONL audit store for multi-agent sprints:
- Full serialization/deserialization of SubTaskTicket, AttemptRecord, and TimeMachineSnapshot.
- Durably flushes attempt_history before escalating to next ModelTier.
- CLI/API resume capability to pick up paused sprints at AWAITING_WRITE_GATE.
- Snapshot rollback coordination via TimeMachineEngine.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AttemptRecord:
    """Telemetry record for an execution attempt by a specialized worker or evaluator."""
    tier: str
    agent_name: str
    model_name: str
    status: str  # "APPROVED", "REJECTED", "ESCALATED", "FAILED"
    rejection_reason: Optional[str] = None
    security_findings: List[Dict[str, Any]] = field(default_factory=list)
    qa_verdicts: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SprintStateStore:
    """Durable state storage backed by SQLite and append-only JSONL audit logging."""

    def __init__(self, db_path: Optional[Path | str] = None, audit_log_path: Optional[Path | str] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            tasks_dir = Path.cwd() / ".rerun_tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = tasks_dir / "sprint_store.db"

        if audit_log_path:
            self.audit_log_path = Path(audit_log_path).resolve()
        else:
            self.audit_log_path = self.db_path.parent / "sprint_audit.jsonl"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database tables with schema definitions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sprints (
                    sprint_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    failure_context_json TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT,
                    sprint_id TEXT,
                    title TEXT,
                    complexity INTEGER,
                    assigned_tier TEXT,
                    allowed_files_json TEXT,
                    acceptance_criteria_json TEXT,
                    depends_on_json TEXT,
                    status TEXT,
                    proposed_changes_json TEXT,
                    PRIMARY KEY (ticket_id, sprint_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attempt_history (
                    attempt_id TEXT PRIMARY KEY,
                    ticket_id TEXT,
                    sprint_id TEXT,
                    tier TEXT,
                    agent_name TEXT,
                    model_name TEXT,
                    status TEXT,
                    rejection_reason TEXT,
                    security_findings_json TEXT,
                    qa_verdicts_json TEXT,
                    created_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    sprint_id TEXT,
                    ticket_id TEXT,
                    label TEXT,
                    manifest_json TEXT,
                    created_at REAL
                )
            """)
            conn.commit()

    def _append_audit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Append immutable audit log entry to JSONL file."""
        record = {
            "timestamp": time.time(),
            "event": event_type,
            "data": data,
        }
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def save_sprint(
        self,
        sprint_id: str,
        status: str,
        failure_context: Dict[str, Any],
        tickets: List[Any],
    ) -> None:
        """Persist or update sprint and all its associated tickets."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sprints (sprint_id, status, failure_context_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sprint_id) DO UPDATE SET
                    status=excluded.status,
                    failure_context_json=excluded.failure_context_json,
                    updated_at=excluded.updated_at
                """,
                (sprint_id, status, json.dumps(failure_context), now, now),
            )

            for t in tickets:
                cursor.execute(
                    """
                    INSERT INTO tickets (
                        ticket_id, sprint_id, title, complexity, assigned_tier,
                        allowed_files_json, acceptance_criteria_json, depends_on_json,
                        status, proposed_changes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticket_id, sprint_id) DO UPDATE SET
                        title=excluded.title,
                        complexity=excluded.complexity,
                        assigned_tier=excluded.assigned_tier,
                        allowed_files_json=excluded.allowed_files_json,
                        acceptance_criteria_json=excluded.acceptance_criteria_json,
                        depends_on_json=excluded.depends_on_json,
                        status=excluded.status,
                        proposed_changes_json=excluded.proposed_changes_json
                    """,
                    (
                        t.ticket_id,
                        sprint_id,
                        t.title,
                        getattr(t, "complexity", 2),
                        t.assigned_tier,
                        json.dumps(getattr(t, "allowed_files", [])),
                        json.dumps(getattr(t, "acceptance_criteria", [])),
                        json.dumps(getattr(t, "depends_on", [])),
                        t.status,
                        json.dumps(getattr(t, "proposed_changes", {})),
                    ),
                )
            conn.commit()

        self._append_audit("SAVE_SPRINT", {"sprint_id": sprint_id, "status": status, "ticket_count": len(tickets)})

    def update_sprint_status(self, sprint_id: str, status: str) -> None:
        """Update lifecycle status of a sprint."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sprints SET status = ?, updated_at = ? WHERE sprint_id = ?",
                (status, now, sprint_id),
            )
            conn.commit()
        self._append_audit("UPDATE_SPRINT_STATUS", {"sprint_id": sprint_id, "status": status})

    def record_attempt(
        self,
        ticket_id: str,
        sprint_id: str,
        attempt: AttemptRecord | Dict[str, Any],
    ) -> str:
        """Durably flush an execution attempt before escalating to next tier (AC-1)."""
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        att_dict = attempt.to_dict() if isinstance(attempt, AttemptRecord) else attempt

        now = att_dict.get("timestamp") or time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO attempt_history (
                    attempt_id, ticket_id, sprint_id, tier, agent_name, model_name,
                    status, rejection_reason, security_findings_json, qa_verdicts_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    ticket_id,
                    sprint_id,
                    att_dict.get("tier", ""),
                    att_dict.get("agent_name", ""),
                    att_dict.get("model_name", ""),
                    att_dict.get("status", ""),
                    att_dict.get("rejection_reason"),
                    json.dumps(att_dict.get("security_findings", [])),
                    json.dumps(att_dict.get("qa_verdicts", [])),
                    now,
                ),
            )
            conn.commit()

        self._append_audit("RECORD_ATTEMPT", {
            "attempt_id": attempt_id,
            "ticket_id": ticket_id,
            "sprint_id": sprint_id,
            "tier": att_dict.get("tier"),
            "status": att_dict.get("status"),
        })
        return attempt_id

    def save_snapshot(
        self,
        snapshot_id: str,
        sprint_id: str,
        ticket_id: str,
        label: str,
        manifest: Dict[str, Any],
    ) -> None:
        """Record a TimeMachine snapshot associated with a sprint write-gate."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO snapshots (snapshot_id, sprint_id, ticket_id, label, manifest_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    manifest_json=excluded.manifest_json
                """,
                (snapshot_id, sprint_id, ticket_id, label, json.dumps(manifest), now),
            )
            conn.commit()

        self._append_audit("SAVE_SNAPSHOT", {"snapshot_id": snapshot_id, "sprint_id": sprint_id, "ticket_id": ticket_id})

    def load_sprint(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        """Reconstruct full sprint context, tickets, attempt histories, and snapshots."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sprints WHERE sprint_id = ?", (sprint_id,))
            sprint_row = cursor.fetchone()
            if not sprint_row:
                return None

            cursor.execute("SELECT * FROM tickets WHERE sprint_id = ?", (sprint_id,))
            ticket_rows = cursor.fetchall()

            tickets = []
            for tr in ticket_rows:
                tid = tr["ticket_id"]
                cursor.execute(
                    "SELECT * FROM attempt_history WHERE ticket_id = ? AND sprint_id = ? ORDER BY created_at ASC",
                    (tid, sprint_id),
                )
                att_rows = cursor.fetchall()
                attempts = []
                for ar in att_rows:
                    attempts.append({
                        "tier": ar["tier"],
                        "agent_name": ar["agent_name"],
                        "model_name": ar["model_name"],
                        "status": ar["status"],
                        "rejection_reason": ar["rejection_reason"],
                        "security_findings": json.loads(ar["security_findings_json"] or "[]"),
                        "qa_verdicts": json.loads(ar["qa_verdicts_json"] or "[]"),
                        "timestamp": ar["created_at"],
                    })

                tickets.append({
                    "ticket_id": tr["ticket_id"],
                    "sprint_id": tr["sprint_id"],
                    "title": tr["title"],
                    "complexity": tr["complexity"],
                    "assigned_tier": tr["assigned_tier"],
                    "allowed_files": json.loads(tr["allowed_files_json"] or "[]"),
                    "acceptance_criteria": json.loads(tr["acceptance_criteria_json"] or "[]"),
                    "depends_on": json.loads(tr["depends_on_json"] or "[]"),
                    "status": tr["status"],
                    "proposed_changes": json.loads(tr["proposed_changes_json"] or "{}"),
                    "attempt_history": attempts,
                })

            cursor.execute("SELECT * FROM snapshots WHERE sprint_id = ?", (sprint_id,))
            snap_rows = cursor.fetchall()
            snapshots = []
            for sr in snap_rows:
                snapshots.append({
                    "snapshot_id": sr["snapshot_id"],
                    "ticket_id": sr["ticket_id"],
                    "label": sr["label"],
                    "manifest": json.loads(sr["manifest_json"] or "{}"),
                    "created_at": sr["created_at"],
                })

            return {
                "sprint_id": sprint_row["sprint_id"],
                "status": sprint_row["status"],
                "failure_context": json.loads(sprint_row["failure_context_json"] or "{}"),
                "created_at": sprint_row["created_at"],
                "updated_at": sprint_row["updated_at"],
                "tickets": tickets,
                "snapshots": snapshots,
            }

    def list_paused_sprints(self, status: str = "AWAITING_WRITE_GATE") -> List[Dict[str, Any]]:
        """List sprints waiting at the human write-gate (AC-2)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sprint_id FROM sprints WHERE status = ? ORDER BY updated_at DESC", (status,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                sprint_data = self.load_sprint(r["sprint_id"])
                if sprint_data:
                    results.append(sprint_data)
            return results

    def resume_sprint(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve paused sprint state to allow resumed execution."""
        return self.load_sprint(sprint_id)

    def rollback_snapshot(self, snapshot_id: str, tm_engine: Any) -> Dict[str, Any]:
        """Restore workspace to an associated TimeMachine snapshot."""
        res = tm_engine.restore_snapshot(snapshot_id)
        self._append_audit("ROLLBACK_SNAPSHOT", {"snapshot_id": snapshot_id, "result": res})
        return res
