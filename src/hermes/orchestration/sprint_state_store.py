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
from contextlib import contextmanager
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

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        audit_log_path: Optional[Path | str] = None,
        workspace_path: Optional[Path | str] = None,
    ):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            base_dir = Path(workspace_path).resolve() if workspace_path else Path.cwd()
            tasks_dir = base_dir / ".rerun_tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = tasks_dir / "sprint_store.db"

        if audit_log_path:
            self.audit_log_path = Path(audit_log_path).resolve()
        else:
            self.audit_log_path = self.db_path.parent / "sprint_audit.jsonl"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

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

    def stage_proposal_state(
        self,
        sprint_id: str,
        ticket_id: str,
        proposed_changes: Dict[str, str],
        assigned_tier: str = "TIER_3_JUNIOR_SWE",
        worker_agent: str = "DeveloperAgent",
    ) -> None:
        """Persist staged proposal to database so it can be resumed/approved across process restarts."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Ensure sprint exists or update status
            cursor.execute("SELECT sprint_id FROM sprints WHERE sprint_id = ?", (sprint_id,))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE sprints SET status = 'AWAITING_WRITE_GATE', updated_at = ? WHERE sprint_id = ?",
                    (now, sprint_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO sprints (sprint_id, status, failure_context_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (sprint_id, "AWAITING_WRITE_GATE", "{}", now, now),
                )

            cursor.execute(
                "SELECT ticket_id FROM tickets WHERE ticket_id = ? AND sprint_id = ?",
                (ticket_id, sprint_id),
            )
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE tickets SET
                        proposed_changes_json = ?,
                        status = 'AWAITING_WRITE_GATE'
                    WHERE ticket_id = ? AND sprint_id = ?
                    """,
                    (json.dumps(proposed_changes), ticket_id, sprint_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO tickets (
                        ticket_id, sprint_id, title, complexity, assigned_tier,
                        allowed_files_json, acceptance_criteria_json, depends_on_json,
                        status, proposed_changes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        sprint_id,
                        f"Staged Ticket {ticket_id}",
                        2,
                        assigned_tier,
                        json.dumps(list(proposed_changes.keys())),
                        json.dumps(["AC-1: Staged change approval"]),
                        json.dumps([]),
                        "AWAITING_WRITE_GATE",
                        json.dumps(proposed_changes),
                    ),
                )
            conn.commit()
        self._append_audit("STAGE_PROPOSAL", {
            "sprint_id": sprint_id,
            "ticket_id": ticket_id,
            "files": list(proposed_changes.keys()),
        })

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

    def export_state_bundle(self) -> Dict[str, Any]:
        """Export a portable JSON state bundle for cross-run CI caching."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sprints")
            sprints = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT * FROM tickets")
            tickets = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT * FROM attempt_history")
            attempts = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT * FROM snapshots")
            snapshots = [dict(r) for r in cursor.fetchall()]

        return {
            "version": "1.0",
            "timestamp": time.time(),
            "sprints": sprints,
            "tickets": tickets,
            "attempts": attempts,
            "snapshots": snapshots,
        }

    def import_state_bundle(self, bundle: Dict[str, Any]) -> None:
        """Import a state bundle from an upstream CI run."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for s in bundle.get("sprints", []):
                cursor.execute(
                    "INSERT OR REPLACE INTO sprints VALUES (?, ?, ?, ?, ?)",
                    (s["sprint_id"], s["status"], s["failure_context_json"], s["created_at"], s["updated_at"]),
                )
            for t in bundle.get("tickets", []):
                cursor.execute(
                    "INSERT OR REPLACE INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        t["ticket_id"],
                        t["sprint_id"],
                        t["title"],
                        t["complexity"],
                        t["assigned_tier"],
                        t["allowed_files_json"],
                        t["acceptance_criteria_json"],
                        t["depends_on_json"],
                        t["status"],
                        t["proposed_changes_json"],
                    ),
                )
            for a in bundle.get("attempts", []):
                cursor.execute(
                    "INSERT OR REPLACE INTO attempt_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        a["attempt_id"],
                        a["ticket_id"],
                        a["tier"],
                        a["agent_name"],
                        a["model_name"],
                        a["status"],
                        a["rejection_reason"],
                        a["audit_telemetry_json"],
                        a["timestamp"],
                    ),
                )
            for sn in bundle.get("snapshots", []):
                cursor.execute(
                    "INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                    (sn["snapshot_id"], sn["sprint_id"], sn["ticket_id"], sn["label"], sn["manifest_json"]),
                )

    def record_test_pass_and_check_unquarantine(
        self,
        test_id: str,
        file_path: str,
        source_code: str,
    ) -> Optional[Any]:
        """Increment consecutive green pass counter and trigger surgical unquarantine if streak >= 50."""
        from core.hygiene.flake_reaper import FlakeLifecycleReaper
        streak_file = self.db_path.parent / "flake_streaks.json"
        streaks = {}
        if streak_file.is_file():
            try:
                streaks = json.loads(streak_file.read_text(encoding="utf-8"))
            except Exception:
                streaks = {}

        current_streak = streaks.get(test_id, 0) + 1
        streaks[test_id] = current_streak
        streak_file.write_text(json.dumps(streaks, indent=2), encoding="utf-8")

        return FlakeLifecycleReaper.evaluate_streak_and_unquarantine(
            file_path=file_path,
            source_code=source_code,
            consecutive_green_runs=current_streak,
        )

    def check_quarantine_ttls(
        self,
        quarantined_files: List[Tuple[str, str]],
        current_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate 14-day TTL across quarantined tests, raising SLA alerts for expired tests."""
        from core.hygiene.flake_reaper import FlakeLifecycleReaper
        results = []
        for file_path, content in quarantined_files:
            meta = FlakeLifecycleReaper.parse_quarantine_stamp(content, current_time=current_time)
            if meta:
                meta_dict = meta.to_dict()
                meta_dict["file_path"] = file_path
                results.append(meta_dict)
        return results


class GitNotesStateBackend:
    """Stores and retrieves state across ephemeral CI runs using git notes (refs/notes/hermes-state).
    
    Includes optimistic concurrency control with CRDT-style deep merge and exponential
    backoff retry for parallel CI runner matrix shards pushing concurrently.
    """

    DEFAULT_REF = "refs/notes/hermes-state"

    def __init__(self, repo_root: Optional[Path | str] = None, ref: str = DEFAULT_REF):
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.ref = ref

    def save(
        self,
        state_data: Dict[str, Any],
        push: bool = True,
        remote: str = "origin",
        max_retries: int = 4,
    ) -> bool:
        """Persist state data to git notes with automatic OCC deep merge and push retry."""
        existing = self.load()
        if existing:
            state_data = self.deep_merge_states(existing, state_data)
        if push:
            return self.push_state_with_retry(
                repo_root=self.repo_root,
                state_data=state_data,
                ref=self.ref,
                remote=remote,
                max_retries=max_retries,
            )
        return self.export_state_to_git_notes(self.repo_root, state_data, ref=self.ref)

    def load(self, target_commit: str = "HEAD") -> Optional[Dict[str, Any]]:
        """Load state data from git notes."""
        return self.import_state_from_git_notes(self.repo_root, ref=self.ref, target_commit=target_commit)

    @classmethod
    def deep_merge_states(
        cls,
        base_state: Dict[str, Any],
        incoming_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform a deterministic CRDT-style deep merge of state bundles.
        
        Merge semantics:
        - consecutive_green_runs: max() across streaks (int or per-test dict).
        - quarantined_tests: union by test ID preserving active metadata.
        - finops_ledger: union by run_id; sum/max token & cost counters.
        - snapshots / attempts: append-only deduplication by unique ID.
        - sprints / tickets: union by ID, taking latest updated_at.
        """
        merged = dict(base_state)

        # 1. Timestamps & version
        merged["version"] = max(base_state.get("version", "1.0"), incoming_state.get("version", "1.0"))
        merged["timestamp"] = max(base_state.get("timestamp", 0.0), incoming_state.get("timestamp", 0.0))

        # 2. Consecutive green runs (max streak invariant)
        base_green = base_state.get("consecutive_green_runs")
        inc_green = incoming_state.get("consecutive_green_runs")
        if isinstance(base_green, dict) or isinstance(inc_green, dict):
            b_dict = base_green if isinstance(base_green, dict) else {}
            i_dict = inc_green if isinstance(inc_green, dict) else {}
            all_keys = set(b_dict.keys()) | set(i_dict.keys())
            merged["consecutive_green_runs"] = {
                k: max(b_dict.get(k, 0), i_dict.get(k, 0)) for k in all_keys
            }
        elif base_green is not None or inc_green is not None:
            merged["consecutive_green_runs"] = max(int(base_green or 0), int(inc_green or 0))

        # 3. Quarantined tests (union by test_id/quarantine_id)
        base_q = base_state.get("quarantined_tests", [])
        inc_q = incoming_state.get("quarantined_tests", [])
        q_map: Dict[str, Any] = {}
        if isinstance(base_q, list):
            for item in base_q:
                qid = item.get("test_id") or item.get("quarantine_id") or str(item)
                q_map[qid] = item
        elif isinstance(base_q, dict):
            q_map.update(base_q)
        if isinstance(inc_q, list):
            for item in inc_q:
                qid = item.get("test_id") or item.get("quarantine_id") or str(item)
                q_map[qid] = item
        elif isinstance(inc_q, dict):
            q_map.update(inc_q)
        merged["quarantined_tests"] = list(q_map.values()) if isinstance(base_q, list) or isinstance(inc_q, list) else q_map

        # 4. FinOps ledger (union by run_id, sum token and cost spend)
        base_ledger = base_state.get("finops_ledger", {})
        inc_ledger = incoming_state.get("finops_ledger", {})
        merged_ledger: Dict[str, Any] = {}
        if isinstance(base_ledger, dict) and isinstance(inc_ledger, dict):
            merged_ledger = dict(base_ledger)
            for run_id, entry in inc_ledger.items():
                if run_id in merged_ledger and isinstance(entry, dict) and isinstance(merged_ledger[run_id], dict):
                    merged_entry = dict(merged_ledger[run_id])
                    merged_entry["tokens"] = merged_entry.get("tokens", 0) + entry.get("tokens", 0)
                    merged_entry["cost_usd"] = merged_entry.get("cost_usd", 0.0) + entry.get("cost_usd", 0.0)
                    merged_ledger[run_id] = merged_entry
                else:
                    merged_ledger[run_id] = entry
        elif isinstance(base_ledger, list) or isinstance(inc_ledger, list):
            b_list = base_ledger if isinstance(base_ledger, list) else []
            i_list = inc_ledger if isinstance(inc_ledger, list) else []
            seen_runs = {}
            for e in b_list + i_list:
                rid = e.get("run_id") or str(e)
                seen_runs[rid] = e
            merged_ledger = list(seen_runs.values())
        merged["finops_ledger"] = merged_ledger

        # 5. Snapshots (append-only deduplicated by snapshot_id)
        base_sn = {sn.get("snapshot_id", str(i)): sn for i, sn in enumerate(base_state.get("snapshots", []))}
        inc_sn = {sn.get("snapshot_id", str(i)): sn for i, sn in enumerate(incoming_state.get("snapshots", []))}
        base_sn.update(inc_sn)
        merged["snapshots"] = list(base_sn.values())

        # 6. Attempt history (append-only deduplicated by attempt_id)
        base_att = {a.get("attempt_id", str(i)): a for i, a in enumerate(base_state.get("attempts", []))}
        inc_att = {a.get("attempt_id", str(i)): a for i, a in enumerate(incoming_state.get("attempts", []))}
        base_att.update(inc_att)
        merged["attempts"] = list(base_att.values())

        # 7. Sprints (union by sprint_id)
        base_sp = {s.get("sprint_id", str(i)): s for i, s in enumerate(base_state.get("sprints", []))}
        inc_sp = {s.get("sprint_id", str(i)): s for i, s in enumerate(incoming_state.get("sprints", []))}
        base_sp.update(inc_sp)
        merged["sprints"] = list(base_sp.values())

        # 8. Tickets (union by ticket_id)
        base_tk = {t.get("ticket_id", str(i)): t for i, t in enumerate(base_state.get("tickets", []))}
        inc_tk = {t.get("ticket_id", str(i)): t for i, t in enumerate(incoming_state.get("tickets", []))}
        base_tk.update(inc_tk)
        merged["tickets"] = list(base_tk.values())

        return merged

    @classmethod
    def export_state_to_git_notes(
        cls,
        repo_root: Path | str,
        state_data: Dict[str, Any],
        ref: str = DEFAULT_REF,
        target_commit: str = "HEAD",
    ) -> bool:
        """Export serialized JSON state to git notes attached to target_commit."""
        import subprocess
        try:
            payload = json.dumps(state_data, indent=2)
            res = subprocess.run(
                ["git", "notes", f"--ref={ref}", "add", "-f", "-m", payload, target_commit],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def import_state_from_git_notes(
        cls,
        repo_root: Path | str,
        ref: str = DEFAULT_REF,
        target_commit: str = "HEAD",
    ) -> Optional[Dict[str, Any]]:
        """Read serialized JSON state from git notes attached to target_commit."""
        import subprocess
        try:
            res = subprocess.run(
                ["git", "notes", f"--ref={ref}", "show", target_commit],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

    @classmethod
    def push_state_with_retry(
        cls,
        repo_root: Path | str,
        state_data: Dict[str, Any],
        ref: str = DEFAULT_REF,
        remote: str = "origin",
        max_retries: int = 4,
        base_backoff: float = 0.05,
    ) -> bool:
        """Push notes to remote with optimistic concurrency control, deep merge & exponential retry."""
        import random
        import subprocess
        import time

        current_state = dict(state_data)
        repo_dir = str(repo_root)

        # First stage local note
        cls.export_state_to_git_notes(repo_dir, current_state, ref=ref)

        for attempt in range(max_retries):
            # Attempt push
            push_res = subprocess.run(
                ["git", "push", remote, f"{ref}:{ref}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if push_res.returncode == 0:
                return True

            # If push failed due to conflict / non-fast-forward, fetch and merge
            fetch_res = subprocess.run(
                ["git", "fetch", remote, f"{ref}:{ref}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if fetch_res.returncode == 0:
                remote_state = cls.import_state_from_git_notes(repo_dir, ref=ref, target_commit="HEAD")
                if remote_state:
                    current_state = cls.deep_merge_states(remote_state, current_state)
                    cls.export_state_to_git_notes(repo_dir, current_state, ref=ref)

            # Jittered exponential backoff
            sleep_duration = base_backoff * (2 ** attempt) + random.uniform(0.01, 0.05)
            time.sleep(sleep_duration)

        return False
