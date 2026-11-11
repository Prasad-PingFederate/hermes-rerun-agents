"""
Hermes Time Machine Engine: Deterministic Workspace Snapshotting, Surgical Restore & Rollback
Safe, non-destructive file-tree snapshots with zero git reset --hard, git clean, or git apply.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


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
    """Manages workspace snapshots, surgical per-file restores, and rollback safety nets without destructive git calls."""

    SKIP_DIRS: Set[str] = {
        ".git",
        ".tm_snapshots",
        ".rerun_tasks",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
    }
    SKIP_FILES: Set[str] = {".env"}
    PROTECTED_TOP_LEVEL: Set[str] = {
        ".git",
        ".tm_snapshots",
        ".rerun_tasks",
        ".env",
    }

    def __init__(self, workspace_path: Optional[Path | str] = None, require_git: bool = False):
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

    def _read_git_head(self) -> tuple[str, str]:
        """Read commit hash and branch directly from .git metadata without running git subprocess."""
        git_dir = self.workspace_path / ".git"
        if not git_dir.is_dir():
            return "unknown", "detached"
        head_file = git_dir / "HEAD"
        if not head_file.is_file():
            return "unknown", "detached"
        try:
            content = head_file.read_text(encoding="utf-8").strip()
            if content.startswith("ref: refs/heads/"):
                branch = content[len("ref: refs/heads/"):].strip()
                ref_path = git_dir / "refs" / "heads" / branch
                if ref_path.is_file():
                    commit_hash = ref_path.read_text(encoding="utf-8").strip()
                else:
                    commit_hash = "unknown"
                    packed = git_dir / "packed-refs"
                    if packed.is_file():
                        for line in packed.read_text(encoding="utf-8").splitlines():
                            if line and not line.startswith("#") and not line.startswith("^"):
                                parts = line.split()
                                if len(parts) == 2 and parts[1] == f"refs/heads/{branch}":
                                    commit_hash = parts[0]
                                    break
                return commit_hash, branch
            else:
                return content, "detached"
        except Exception:
            return "unknown", "detached"

    def _validate_safe_workspace_path(self, rel_path: str, allow_missing: bool = True) -> Path:
        """Centralized workspace path validation.

        1. Rejects empty paths, absolute paths, paths starting with '-', and paths with '..' segments.
        2. Rejects protected top-level names: .git, .tm_snapshots, .rerun_tasks, .env, and .env.*.
        3. Walks every existing parent component from workspace_root down to target and raises
           ValueError if any parent directory or the target itself is a symlink.
        4. Verifies resolved_path.is_relative_to(workspace_root.resolve()).
        """
        if not rel_path or not str(rel_path).strip():
            raise ValueError("Path cannot be empty")
        rel_str = str(rel_path).strip()

        if rel_str.startswith("-"):
            raise ValueError(f"Paths starting with '-' are rejected: {rel_str}")

        if os.path.isabs(rel_str):
            raise ValueError(f"Absolute paths are rejected: {rel_str}")

        norm = Path(rel_str)
        if any(part.startswith("-") for part in norm.parts):
            raise ValueError(f"Path segments starting with '-' are rejected: {rel_str}")

        if ".." in norm.parts:
            raise ValueError(f"Path traversal '..' is rejected: {rel_str}")

        # Check protected top-level and component names
        parts = norm.parts
        top = parts[0]
        if top in self.PROTECTED_TOP_LEVEL or top.startswith(".env."):
            raise ValueError(f"Access to protected path '{top}' is rejected: {rel_str}")

        for part in parts:
            if part in self.PROTECTED_TOP_LEVEL or part.startswith(".env."):
                raise ValueError(f"Access to protected component '{part}' is rejected: {rel_str}")

        workspace_root = self.workspace_path.resolve()

        # Walk every existing component from workspace_root down to target
        current = workspace_root
        for part in parts:
            current = current / part
            if current.is_symlink() or os.path.islink(str(current)):
                raise ValueError(f"Symlink in path is rejected: {current}")

        resolved_path = (self.workspace_path / norm).resolve()
        try:
            if not resolved_path.is_relative_to(workspace_root):
                raise ValueError(f"Resolved path escapes workspace: {rel_str}")
        except AttributeError:
            try:
                resolved_path.relative_to(workspace_root)
            except ValueError:
                raise ValueError(f"Resolved path escapes workspace: {rel_str}")

        if not allow_missing and not (self.workspace_path / norm).exists():
            raise FileNotFoundError(f"Path does not exist: {rel_str}")

        return (self.workspace_path / norm)

    # Alias for backward compatibility
    def _validate_safe_path(self, relative_file_path: str) -> Path:
        return self._validate_safe_workspace_path(relative_file_path, allow_missing=True)

    def _collect_workspace_files(self) -> List[str]:
        """Walk workspace, skipping ignored folders and refusing escaping symlinks/paths."""
        files_to_save: List[str] = []

        for root, dirs, files in os.walk(self.workspace_path, followlinks=False):
            root_path = Path(root)

            # 1. Prune skipped directories FIRST before descending or checking symlinks
            dirs[:] = [
                d for d in dirs
                if d not in self.SKIP_DIRS
                and not d.startswith(".env.")
                and d != ".env"
            ]

            # Validate directory symlinks for remaining unskipped directories
            for d in list(dirs):
                dir_path = root_path / d
                if dir_path.is_symlink() or os.path.islink(str(dir_path)):
                    target_resolved = Path(os.path.realpath(dir_path))
                    try:
                        target_resolved.relative_to(self.workspace_path.resolve())
                    except ValueError:
                        raise ValueError(f"Symlink directory escapes workspace: {dir_path} -> {target_resolved}")

            # Validate and collect files
            for f in files:
                if (
                    f in self.SKIP_FILES
                    or f == ".env"
                    or f.startswith(".env.")
                    or f in self.SKIP_DIRS
                ):
                    continue

                file_path = root_path / f

                # Check if symlink target escapes workspace
                if file_path.is_symlink() or os.path.islink(str(file_path)):
                    target_resolved = Path(os.path.realpath(file_path))
                    try:
                        target_resolved.relative_to(self.workspace_path.resolve())
                    except ValueError:
                        raise ValueError(f"Symlink target escapes workspace: {file_path} -> {target_resolved}")

                # Check if resolved file escapes workspace
                try:
                    file_path.resolve().relative_to(self.workspace_path.resolve())
                except ValueError:
                    raise ValueError(f"File path escapes workspace: {file_path}")

                rel_p = str(file_path.relative_to(self.workspace_path)).replace("\\", "/")
                files_to_save.append(rel_p)

        return sorted(files_to_save)

    def create_snapshot(
        self,
        label: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Snapshot:
        """Create a deterministic snapshot by copying workspace files into .tm_snapshots/store/<id>/."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        sanitized_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
        snap_id = f"snap_{timestamp}_{sanitized_label}"

        commit_hash, branch = self._read_git_head()

        # Discover all eligible workspace files
        files_to_save = self._collect_workspace_files()

        # Store file copies in .tm_snapshots/store/<id>/
        snap_dir = self.snapshots_store / snap_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        saved_files: List[str] = []

        for rel_file in files_to_save:
            src_f = self.workspace_path / rel_file
            if src_f.is_file():
                dest_f = snap_dir / rel_file
                dest_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_f, dest_f)
                saved_files.append(rel_file)

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

        # Save manifest.json inside store/<id>/
        manifest_file = snap_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "snapshot_id": snap_id,
                "label": label,
                "created_at": snapshot.created_at,
                "files": saved_files,
            }, f, indent=2)

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
        delete_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Restore workspace to a specific snapshot by copying files back from store.

        Never runs git reset, git clean, git checkout, git commit, git push, or git apply.
        Does not delete files created after the snapshot unless explicitly passed in delete_files.
        """
        target = self.get_snapshot(snapshot_id)
        if not target:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        snap_dir = self.snapshots_store / snapshot_id
        # Check both store/<id> and legacy store/<id>/tree
        data_dir = snap_dir / "tree" if (snap_dir / "tree").is_dir() else snap_dir
        if not data_dir.is_dir():
            raise FileNotFoundError(f"Snapshot data store missing for {snapshot_id}")

        # Prefer reading from manifest.json if present
        manifest_file = snap_dir / "manifest.json"
        if manifest_file.is_file():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                    files_to_restore = manifest_data.get("files", [])
            except Exception:
                files_to_restore = []
        else:
            files_to_restore = []
            for root, _, files in os.walk(data_dir):
                for f in files:
                    if f.endswith(".patch") or f in ("metadata.json", "manifest.json"):
                        continue
                    backup_f = Path(root) / f
                    rel_p = str(backup_f.relative_to(data_dir)).replace("\\", "/")
                    files_to_restore.append(rel_p)

        if dry_run:
            return {
                "dry_run": True,
                "snapshot_id": snapshot_id,
                "files_to_restore": files_to_restore,
                "safety_snapshot_would_be_created": create_safety_snapshot,
            }

        # Safety-net: snapshot current state before rolling back without invoking git
        safety_snap_id = None
        if create_safety_snapshot:
            safety_label = f"pre_rollback_from_{target.label}"
            safety_snap = self.create_snapshot(
                label=safety_label,
                description=f"Automated safety snapshot taken immediately before rolling back to {snapshot_id}",
                metadata={"target_restored": snapshot_id},
            )
            safety_snap_id = safety_snap.id

        # Restore files by copying from store safely
        restored_files = []
        for rel_file in files_to_restore:
            source_file = data_dir / rel_file

            # If destination path or symlink exists in workspace, unlink it first
            dest_file = self.workspace_path / rel_file
            if dest_file.is_symlink() or os.path.islink(str(dest_file)):
                dest_file.unlink()

            safe_dest = self._validate_safe_workspace_path(rel_file, allow_missing=True)
            safe_dest.parent.mkdir(parents=True, exist_ok=True)
            if safe_dest.is_symlink() or os.path.islink(str(safe_dest)) or safe_dest.is_file():
                safe_dest.unlink()

            shutil.copy2(source_file, safe_dest)
            restored_files.append(rel_file)

        # Only delete files if caller passed an explicit list
        if delete_files:
            for rel_file in delete_files:
                del_path = self._validate_safe_workspace_path(rel_file, allow_missing=True)
                if del_path.is_symlink() or os.path.islink(str(del_path)) or del_path.is_file():
                    del_path.unlink()
                elif del_path.is_dir():
                    shutil.rmtree(del_path)

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

        snap_dir = self.snapshots_store / snapshot_id
        data_dir = snap_dir / "tree" if (snap_dir / "tree").is_dir() else snap_dir
        source_backup = data_dir / relative_file_path

        # Verify source_backup does not escape snapshot data store
        try:
            source_backup.resolve().relative_to(data_dir.resolve())
        except ValueError:
            raise ValueError(f"File path escapes snapshot store: {relative_file_path}")

        if not source_backup.is_file():
            raise FileNotFoundError(f"File {relative_file_path} not found in snapshot {snapshot_id}")

        # If existing target in workspace is a symlink, unlink it first
        dest_file = self.workspace_path / relative_file_path
        if dest_file.is_symlink() or os.path.islink(str(dest_file)):
            dest_file.unlink()

        # Validate target path: reject absolute paths, "..", protected paths, and symlink parents
        target_path = self._validate_safe_workspace_path(relative_file_path, allow_missing=True)

        if dry_run:
            return {
                "dry_run": True,
                "snapshot_id": snapshot_id,
                "file": relative_file_path,
                "target_exists": target_path.exists(),
            }

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.is_symlink() or os.path.islink(str(target_path)) or target_path.is_file():
            target_path.unlink()
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
        """Compare snapshots or snapshot against workspace."""
        snap_a = self.get_snapshot(snapshot_id_a)
        if not snap_a:
            return f"Snapshot {snapshot_id_a} not found."

        snap_dir_a = self.snapshots_store / snapshot_id_a
        data_a = snap_dir_a / "tree" if (snap_dir_a / "tree").is_dir() else snap_dir_a

        if snapshot_id_b:
            snap_b = self.get_snapshot(snapshot_id_b)
            if not snap_b:
                return f"Snapshot {snapshot_id_b} not found."
            snap_dir_b = self.snapshots_store / snapshot_id_b
            data_b = snap_dir_b / "tree" if (snap_dir_b / "tree").is_dir() else snap_dir_b
            return f"Comparing {data_a} and {data_b}"
        else:
            return f"Comparing {data_a} and current workspace"
