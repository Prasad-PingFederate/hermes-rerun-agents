"""
Hermes Time Machine Engine: Deterministic Workspace Snapshotting, Surgical Restore & Rollback
Safe, non-destructive file-tree snapshots with zero git reset --hard or git clean.
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
    """Manages workspace snapshots, surgical per-file restores, and rollback safety nets without destructive git resets."""

    def __init__(self, workspace_path: Optional[Path | str] = None, require_git: bool = True):
        self.workspace_path = (
            Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        )
        if not self.workspace_path.is_dir():
            raise ValueError(f"Workspace path does not exist or is not a directory: {self.workspace_path}")

        if require_git:
            git_dir = self.workspace_path / ".git"
            if not git_dir.exists():
                raise ValueError(f"Workspace is not a valid git repository: {self.workspace_path}")

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

    def _get_project_files(self) -> List[str]:
        """List all tracked and non-ignored untracked project files."""
        tracked_proc = self._run_git(["ls-files"])
        tracked = [f.strip() for f in tracked_proc.stdout.splitlines() if f.strip()]

        untracked_proc = self._run_git(["ls-files", "--others", "--exclude-standard"])
        untracked = [f.strip() for f in untracked_proc.stdout.splitlines() if f.strip()]

        all_files: List[str] = []
        for rel in sorted(set(tracked + untracked)):
            normalized = rel.replace("\\", "/")
            if (
                normalized.startswith(".tm_snapshots/")
                or normalized.startswith(".rerun_tasks/")
                or normalized.startswith(".git/")
            ):
                continue
            all_files.append(rel)
        return all_files

    def create_snapshot(
        self,
        label: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a deterministic snapshot of all project files without modifying git index."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        sanitized_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
        snap_id = f"snap_{timestamp}_{sanitized_label}"

        # Current commit hash and branch
        rev_parse = self._run_git(["rev-parse", "HEAD"])
        commit_hash = rev_parse.stdout.strip() if rev_parse.returncode == 0 else "unknown"

        branch_proc = self._run_git(["branch", "--show-current"])
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "detached"

        # Discover all project files (tracked + non-ignored untracked)
        files_to_save = self._get_project_files()

        # Capture working tree and staged diffs
        diff_proc = self._run_git(["diff", "HEAD"])
        staged_proc = self._run_git(["diff", "--staged"])
        patch_file = self.snapshots_store / f"{snap_id}.patch"
        with open(patch_file, "w", encoding="utf-8", errors="replace") as f:
            if staged_proc.stdout:
                f.write(staged_proc.stdout)
            if diff_proc.stdout:
                f.write(diff_proc.stdout)

        # Store full file copies in isolated snapshot store
        snap_tree_dir = self.snapshots_store / snap_id / "tree"
        snap_tree_dir.mkdir(parents=True, exist_ok=True)
        saved_files: List[str] = []

        for rel_file in files_to_save:
            src_f = self.workspace_path / rel_file
            if src_f.is_file():
                dest_f = snap_tree_dir / rel_file
                dest_f.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_f, dest_f)
                    saved_files.append(rel_file)
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
            files_tracked=saved_files,
        )

        ledger = self._read_ledger()
        ledger["snapshots"].append(asdict(snapshot))
        ledger["history"].append({
            "action": "create",
            "snapshot_id": snap_id,
            "timestamp": snapshot.created_at,
            "label": label,
            "file_count": len(saved_files),
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

    def restore_snapshot(
        self,
        snapshot_id: str,
        create_safety_snapshot: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Roll back workspace to a specific snapshot safely.

        Restores all files present in the snapshot.
        Does NOT execute 'git reset --hard' or 'git clean', so unrelated untracked
        files created after the snapshot survive intact.
        """
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        snap_tree_dir = self.snapshots_store / snapshot_id / "tree"
        if not snap_tree_dir.is_dir():
            # Check legacy location
            snap_tree_dir = self.snapshots_store / snapshot_id
            if not snap_tree_dir.is_dir():
                raise FileNotFoundError(f"Snapshot data store missing for {snapshot_id}")

        # Find all files in the snapshot store
        files_to_restore = []
        for root, _, files in os.walk(snap_tree_dir):
            for f in files:
                backup_f = Path(root) / f
                rel_p = str(backup_f.relative_to(snap_tree_dir)).replace("\\", "/")
                files_to_restore.append(rel_p)

        if dry_run:
            return {
                "dry_run": True,
                "snapshot_id": snapshot_id,
                "files_to_restore": files_to_restore,
                "safety_snapshot_would_be_created": create_safety_snapshot,
            }

        # Safety-net: snapshot current state before rolling back ("rollback-of-a-rollback")
        safety_snap_id = None
        if create_safety_snapshot:
            safety_label = f"pre_rollback_from_{target.label}"
            safety_snap = self.create_snapshot(
                label=safety_label,
                description=f"Automated safety snapshot taken immediately before rolling back to {snapshot_id}",
                metadata={"target_restored": snapshot_id},
            )
            safety_snap_id = safety_snap.id

        # Restore all snapshot files by copying from store (safe file overwrite)
        restored_files = []
        for rel_file in files_to_restore:
            source_file = snap_tree_dir / rel_file
            dest_file = self.workspace_path / rel_file
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, dest_file)
            restored_files.append(rel_file)

        # Log restoration in history
        ledger = self._read_ledger()
        ledger["history"].append({
            "action": "restore",
            "snapshot_id": snapshot_id,
            "safety_snapshot_id": safety_snap_id,
            "timestamp": datetime.now().isoformat(),
            "restored_count": len(restored_files),
        })
        self._write_ledger(ledger)

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "safety_snapshot_id": safety_snap_id,
            "restored_files": restored_files,
        }

    def restore_file(
        self,
        snapshot_id: str,
        relative_file_path: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Surgically restore only a single file to its snapshot state without touching other files."""
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        snap_tree_dir = self.snapshots_store / snapshot_id / "tree"
        source_backup = snap_tree_dir / relative_file_path
        if not source_backup.is_file():
            # Legacy fallback
            source_backup = self.snapshots_store / snapshot_id / relative_file_path
            if not source_backup.is_file():
                raise FileNotFoundError(f"File {relative_file_path} not found in snapshot {snapshot_id}")

        target_path = self.workspace_path / relative_file_path

        if dry_run:
            return {
                "dry_run": True,
                "snapshot_id": snapshot_id,
                "file": relative_file_path,
                "target_exists": target_path.exists(),
            }

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_backup, target_path)

        ledger = self._read_ledger()
        ledger["history"].append({
            "action": "surgical_restore",
            "snapshot_id": snapshot_id,
            "file": relative_file_path,
            "timestamp": datetime.now().isoformat(),
        })
        self._write_ledger(ledger)

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "file": relative_file_path,
        }

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
