"""
GAP-14: Real Workspace File Reader & Atomic Unified Diff Applier
Owner: DeveloperAgent (TIER_2)

Features:
- WorkspaceFileReader: Resolves allowed_files globs safely inside repo_root and reads current contents.
- UnifiedDiffGenerator: Uses difflib.unified_diff to compute clean unified diffs with git-style headers.
- AtomicPatchApplier: Writes approved files atomically via temp files and os.replace() with symlink defenses.
"""

from __future__ import annotations

import difflib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class SafePathViolationError(ValueError):
    """Raised when a path escapes the repository root or traverses symlinks."""
    pass


class WorkspaceFileReader:
    """Reads allowed workspace files safely while rejecting symlink escapes and directory traversal."""

    def __init__(self, repo_root: Optional[Path | str] = None):
        self.repo_root = Path(repo_root or Path.cwd()).resolve()

    def validate_safe_path(self, rel_path: str, allow_missing: bool = True) -> Path:
        """Verify that rel_path is contained within repo_root and contains no symlink hops."""
        clean = rel_path.replace("\\", "/").strip()
        if not clean or clean.startswith("/") or clean.startswith("-"):
            raise SafePathViolationError(f"Invalid path format: '{rel_path}'")

        parts = clean.split("/")
        if ".." in parts or "." in parts:
            raise SafePathViolationError(f"Directory traversal forbidden: '{rel_path}'")

        # Protected root paths
        top_name = parts[0]
        if top_name in (".git", ".tm_snapshots", ".rerun_tasks", ".env") or top_name.startswith(".env."):
            raise SafePathViolationError(f"Access to protected path forbidden: '{rel_path}'")

        # Walk components
        current = self.repo_root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise SafePathViolationError(f"Symlink traversal forbidden at '{part}' in '{rel_path}'")

        resolved = current.resolve()
        if not resolved.is_relative_to(self.repo_root):
            raise SafePathViolationError(f"Resolved path '{resolved}' escapes repo root '{self.repo_root}'")

        if not allow_missing and not resolved.exists():
            raise FileNotFoundError(f"File not found: '{rel_path}'")

        return resolved

    def read_allowed_files(self, allowed_files: List[str]) -> Dict[str, str]:
        """Read current content for each allowed file path (or glob)."""
        file_contents: Dict[str, str] = {}

        for pattern in allowed_files:
            clean_pattern = pattern.replace("\\", "/").lstrip("/")
            if "*" in clean_pattern or "?" in clean_pattern:
                # Handle globbing safely
                matched = list(self.repo_root.glob(clean_pattern))
                for m in matched:
                    if m.is_file():
                        rel = str(m.relative_to(self.repo_root)).replace("\\", "/")
                        try:
                            self.validate_safe_path(rel, allow_missing=False)
                            file_contents[rel] = m.read_text(encoding="utf-8")
                        except Exception:
                            continue
            else:
                try:
                    safe_path = self.validate_safe_path(clean_pattern, allow_missing=True)
                    if safe_path.is_file():
                        file_contents[clean_pattern] = safe_path.read_text(encoding="utf-8")
                    else:
                        file_contents[clean_pattern] = ""  # File does not exist yet
                except Exception as e:
                    file_contents[clean_pattern] = ""

        return file_contents


class UnifiedDiffGenerator:
    """Generates clean unified diffs using standard library difflib."""

    @classmethod
    def generate_diff(
        cls,
        rel_path: str,
        original_content: str,
        new_content: str,
    ) -> str:
        """Compute unified diff with standard --- a/... +++ b/... headers."""
        clean_path = rel_path.replace("\\", "/").lstrip("/")
        from_lines = original_content.splitlines(keepends=True)
        to_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"a/{clean_path}",
            tofile=f"b/{clean_path}",
            lineterm="\n",
        )
        return "".join(diff)

    @classmethod
    def generate_multi_diff(
        cls,
        original_files: Dict[str, str],
        proposed_files: Dict[str, str],
    ) -> Dict[str, str]:
        """Generate diffs across all modified or added files."""
        diffs: Dict[str, str] = {}
        all_paths = set(original_files.keys()).union(set(proposed_files.keys()))

        for p in sorted(list(all_paths)):
            orig = original_files.get(p, "")
            prop = proposed_files.get(p, "")
            if orig != prop:
                diffs[p] = cls.generate_diff(p, orig, prop)

        return diffs


class AtomicPatchApplier:
    """Applies file modifications atomically via sibling temp files and os.replace()."""

    def __init__(self, repo_root: Optional[Path | str] = None):
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.reader = WorkspaceFileReader(self.repo_root)

    def apply_single_file(self, rel_path: str, new_content: str) -> Path:
        """Atomically write new_content to rel_path inside repo_root."""
        target_path = self.reader.validate_safe_path(rel_path, allow_missing=True)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary sibling in the same directory to guarantee same filesystem mount
        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=".tmp_atomic_",
            dir=str(target_path.parent),
        )
        temp_path = Path(temp_path_str)

        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Unlink target if it exists or is a symlink (preventing symlink overwriting)
            if target_path.is_symlink() or target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass

            # Atomic rename / replace
            os.replace(temp_path, target_path)
            return target_path
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def apply_proposal_patches(
        self, proposed_changes: Dict[str, str]
    ) -> Tuple[List[str], Dict[str, str]]:
        """Apply all proposed changes atomically. Returns (applied_paths, backup_content)."""
        backup: Dict[str, str] = {}
        applied: List[str] = []

        # Read backups first
        for rel_path in proposed_changes.keys():
            try:
                safe_p = self.reader.validate_safe_path(rel_path, allow_missing=True)
                if safe_p.is_file():
                    backup[rel_path] = safe_p.read_text(encoding="utf-8")
                else:
                    backup[rel_path] = ""
            except Exception:
                backup[rel_path] = ""

        # Apply atomically
        try:
            for rel_path, content in proposed_changes.items():
                self.apply_single_file(rel_path, content)
                applied.append(rel_path)
            return applied, backup
        except Exception as e:
            # Revert any partially applied files
            for rel_path, orig in backup.items():
                try:
                    safe_p = self.reader.validate_safe_path(rel_path, allow_missing=True)
                    if orig:
                        self.apply_single_file(rel_path, orig)
                    elif safe_p.exists():
                        safe_p.unlink()
                except Exception:
                    pass
            raise RuntimeError(f"Atomic application failed, rolled back changes: {str(e)}") from e
