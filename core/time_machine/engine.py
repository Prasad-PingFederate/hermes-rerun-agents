"""
Hermes Time Machine Engine: Deterministic Workspace Snapshotting, Surgical Restore & Rollback
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
    files_tracked: Optional[List[str]] = None


class TimeMachineEngine:
    """Manages workspace snapshots, surgical per-file restores, and rollback safety nets."""

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
        self.tm_dir.mkdir(parents=True, exist_ok=True)
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

    def create_snapshot(
        self,
        label: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a deterministic snapshot of the workspace."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        sanitized_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
        snap_id = f"snap_{timestamp}_{sanitized_label}"

        # Current commit hash and branch
        rev_parse = self._run_git(["rev-parse", "HEAD"])
        commit_hash = rev_parse.stdout.strip() if rev_parse.returncode == 0 else "unknown"

        branch_proc = self._run_git(["branch", "--show-current"])
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "detached"

        # List modified/staged/untracked files
        status_proc = self._run_git(["status", "--porcelain"])
        modified_files = []
        if status_proc.returncode == 0 and status_proc.stdout:
            for line in status_proc.stdout.splitlines():
                if len(line) > 3:
                    modified_files.append(line[3:].strip())

        # Capture working tree and staged diffs
        diff_proc = self._run_git(["diff", "HEAD"])
        staged_proc = self._run_git(["diff", "--staged"])
        patch_file = self.snapshots_store / f"{snap_id}.patch"
        with open(patch_file, "w", encoding="utf-8", errors="replace") as f:
            if staged_proc.stdout:
                f.write(staged_proc.stdout)
            if diff_proc.stdout:
                f.write(diff_proc.stdout)

        # Store backup copies of currently modified files for surgical restores
        snap_backup_dir = self.snapshots_store / snap_id
        snap_backup_dir.mkdir(parents=True, exist_ok=True)
        for rel_file in modified_files:
            src_f = self.workspace_path / rel_file
            if src_f.is_file():
                dest_f = snap_backup_dir / rel_file
                dest_f.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_f, dest_f)
                except Exception:
                    pass

        snapshot = Snapshot(
            id=snap_id,
            label=label,
            created_at=datetime.now().isoformat(),
            commit_hash=commit_hash,
            branch=branch,
            description=description,
            metadata=metadata or {},
            files_tracked=modified_files,
        )

        ledger = self._read_ledger()
        ledger["snapshots"].append(asdict(snapshot))
        ledger["history"].append({
            "action": "create",
            "snapshot_id": snap_id,
            "timestamp": snapshot.created_at,
            "label": label,
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

    def restore_snapshot(self, snapshot_id: str, create_safety_snapshot: bool = True) -> bool:
        """Roll back workspace to a specific snapshot with safety-snapshot protection."""
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # Safety-net: snapshot current state before rolling back ("rollback-of-a-rollback")
        if create_safety_snapshot:
            safety_label = f"pre_rollback_from_{target.label}"
            self.create_snapshot(
                label=safety_label,
                description=f"Automated safety snapshot taken immediately before rolling back to {snapshot_id}",
                metadata={"target_restored": snapshot_id},
            )

        # Reset unstaged and staged changes back to target commit, protecting snapshots
        if target.commit_hash != "unknown":
            self._run_git(["reset", "--hard", target.commit_hash])
            self._run_git(["clean", "-fd", "-e", ".tm_snapshots", "-e", ".rerun_tasks"])

        # If full file backups exist, restore them
        snap_backup_dir = self.snapshots_store / snapshot_id
        if snap_backup_dir.is_dir():
            for root, _, files in os.walk(snap_backup_dir):
                for f in files:
                    backup_f = Path(root) / f
                    rel_p = backup_f.relative_to(snap_backup_dir)
                    target_dest = self.workspace_path / rel_p
                    target_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_f, target_dest)
        else:
            # Fallback to patch apply
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

    def restore_file(self, snapshot_id: str, relative_file_path: str) -> bool:
        """Surgically restore only a single file to its snapshot state without touching other files."""
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        snap_backup_dir = self.snapshots_store / snapshot_id
        source_backup = snap_backup_dir / relative_file_path
        target_path = self.workspace_path / relative_file_path

        if source_backup.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_backup, target_path)
        else:
            # If not in backups, restore from commit
            if target.commit_hash != "unknown":
                res = self._run_git(["checkout", target.commit_hash, "--", relative_file_path])
                if res.returncode != 0:
                    raise FileNotFoundError(f"File {relative_file_path} not found in snapshot {snapshot_id}")

        ledger = self._read_ledger()
        ledger["history"].append({
            "action": "surgical_restore",
            "snapshot_id": snapshot_id,
            "file": relative_file_path,
            "timestamp": datetime.now().isoformat(),
        })
        self._write_ledger(ledger)
        return True

    def get_diff(self, snapshot_id_a: str, snapshot_id_b: Optional[str] = None) -> str:
        """Get diff between two snapshots or between a snapshot and the current working tree."""
        snap_a = self.get_snapshot(snapshot_id_a)
        if not snap_a:
            return f"Snapshot {snapshot_id_a} not found."

        if snapshot_id_b:
            snap_b = self.get_snapshot(snapshot_id_b)
            if not snap_b:
                return f"Snapshot {snapshot_id_b} not found."
            res = self._run_git(["diff", snap_a.commit_hash, snap_b.commit_hash])
            return res.stdout
        else:
            res = self._run_git(["diff", snap_a.commit_hash])
            return res.stdout
