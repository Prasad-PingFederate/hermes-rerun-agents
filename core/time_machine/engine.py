"""
Hermes Time Machine Engine: Deterministic Workspace Snapshotting & Rollback
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Snapshot:
    id: str
    label: str
    created_at: str
    commit_hash: str
    branch: str
    description: str = ""
    metadata: Optional[Dict[str, Any]] = None


class TimeMachineEngine:
    """Manages workspace snapshots and rollbacks with zero risk to untracked code."""

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = (
            Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        )
        self.tm_dir = self.workspace_path / ".tm_snapshots"
        self.ledger_file = self.tm_dir / "ledger.json"
        self.snapshots_store = self.tm_dir / "store"
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.tm_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_store.mkdir(parents=True, exist_ok=True)
        if not self.ledger_file.exists():
            self._write_ledger({"snapshots": [], "history": []})

    def _read_ledger(self) -> Dict[str, Any]:
        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"snapshots": [], "history": []}

    def _write_ledger(self, data: Dict[str, Any]) -> None:
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(self.workspace_path),
            capture_output=True,
            text=True,
            check=False,
        )

    def create_snapshot(self, label: str, description: str = "", metadata: Optional[Dict[str, Any]] = None) -> Snapshot:
        """Create a deterministic snapshot of the workspace."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
        snap_id = f"snap_{timestamp}_{sanitized_label}"

        # Current commit hash and branch
        rev_parse = self._run_git(["rev-parse", "HEAD"])
        commit_hash = rev_parse.stdout.strip() if rev_parse.returncode == 0 else "unknown"

        branch_proc = self._run_git(["branch", "--show-current"])
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "detached"

        # Capture working tree diff
        diff_proc = self._run_git(["diff", "HEAD"])
        staged_proc = self._run_git(["diff", "--staged"])
        patch_file = self.snapshots_store / f"{snap_id}.patch"
        with open(patch_file, "w", encoding="utf-8", errors="replace") as f:
            f.write(staged_proc.stdout)
            f.write(diff_proc.stdout)

        snapshot = Snapshot(
            id=snap_id,
            label=label,
            created_at=datetime.now().isoformat(),
            commit_hash=commit_hash,
            branch=branch,
            description=description,
            metadata=metadata or {},
        )

        ledger = self._read_ledger()
        ledger["snapshots"].append(asdict(snapshot))
        ledger["history"].append({
            "action": "create",
            "snapshot_id": snap_id,
            "timestamp": snapshot.created_at,
        })
        self._write_ledger(ledger)

        return snapshot

    def list_snapshots(self, limit: int = 50) -> List[Snapshot]:
        """List available snapshots from newest to oldest."""
        ledger = self._read_ledger()
        snapshots = [Snapshot(**item) for item in ledger.get("snapshots", [])]
        snapshots.reverse()
        return snapshots[:limit]

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        ledger = self._read_ledger()
        for item in ledger.get("snapshots", []):
            if item.get("id") == snapshot_id:
                return Snapshot(**item)
        return None

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Roll back workspace to a specific snapshot."""
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # Reset unstaged and staged changes back to the target commit
        if target.commit_hash != "unknown":
            self._run_git(["checkout", target.commit_hash])

        # If a patch was stored, apply it
        patch_file = self.snapshots_store / f"{snapshot_id}.patch"
        if patch_file.exists() and patch_file.stat().st_size > 0:
            self._run_git(["apply", "--whitespace=nowarn", str(patch_file)])

        # Log restoration in history
        ledger = self._read_ledger()
        ledger["history"].append({
            "action": "restore",
            "snapshot_id": snapshot_id,
            "timestamp": datetime.now().isoformat(),
        })
        self._write_ledger(ledger)

        return True
