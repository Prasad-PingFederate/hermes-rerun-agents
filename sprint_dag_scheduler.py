"""
GAP-08: Cross-Ticket Dependency DAG & Staged Patch Composer
Owner: ScrumMasterOrchestrator, TIER_1

Coordinates multi-ticket sprint execution:
- SprintDAGScheduler: Resolves topological execution order and rejects cyclic dependencies.
- Halts downstream tickets if upstream dependencies fail.
- StagedPatchComposer: Combines unified diffs and file changes across multiple tickets (e.g. test patch + feature patch).
- Conflict detector: Flags overlapping line edits or conflicting file mutations.
"""

from __future__ import annotations

import difflib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class DependencyCycleError(ValueError):
    """Raised when a circular dependency is detected in sprint tickets."""
    pass


class PatchConflictError(ValueError):
    """Raised when two tickets propose conflicting changes to the same file."""
    pass


class SprintDAGScheduler:
    """Computes topological execution order and dependency gating for sprint tickets."""

    @classmethod
    def topological_sort(cls, tickets: List[Any]) -> List[Any]:
        """Sort tickets by dependencies in topological order.
        
        Raises DependencyCycleError if a cycle is detected.
        """
        ticket_map = {t.ticket_id: t for t in tickets}
        in_degree: Dict[str, int] = {t.ticket_id: 0 for t in tickets}
        graph: Dict[str, List[str]] = defaultdict(list)

        for t in tickets:
            deps = getattr(t, "depends_on", []) or []
            for dep in deps:
                if dep in ticket_map:
                    graph[dep].append(t.ticket_id)
                    in_degree[t.ticket_id] += 1

        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        ordered_ids: List[str] = []

        while queue:
            node = queue.popleft()
            ordered_ids.append(node)

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered_ids) != len(tickets):
            cycle_nodes = [tid for tid, deg in in_degree.items() if deg > 0]
            raise DependencyCycleError(
                f"Cyclic ticket dependency detected among tickets: {sorted(cycle_nodes)}"
            )

        return [ticket_map[tid] for tid in ordered_ids]

    @classmethod
    def get_ready_tickets(
        cls, tickets: List[Any], completed_ids: Set[str], failed_ids: Set[str]
    ) -> List[Any]:
        """Return tickets whose dependencies are satisfied and not blocked by upstream failures."""
        ready = []
        for t in tickets:
            if t.ticket_id in completed_ids or t.ticket_id in failed_ids:
                continue
            deps = set(getattr(t, "depends_on", []) or [])
            # If any dependency failed, this ticket cannot proceed
            if deps.intersection(failed_ids):
                continue
            # If all dependencies are completed, ticket is ready
            if deps.issubset(completed_ids):
                ready.append(t)
        return ready

    @classmethod
    def is_ticket_blocked(
        cls, ticket: Any, completed_ids: Set[str], failed_ids: Set[str]
    ) -> Tuple[bool, Optional[str]]:
        """Check if a ticket is blocked by upstream dependencies."""
        deps = set(getattr(ticket, "depends_on", []) or [])
        failed_upstream = deps.intersection(failed_ids)
        if failed_upstream:
            return True, f"Blocked by failed upstream ticket(s): {sorted(list(failed_upstream))}"

        uncompleted = deps - completed_ids
        if uncompleted:
            return True, f"Waiting on uncompleted dependency: {sorted(list(uncompleted))}"

        return False, None


class StagedPatchComposer:
    """Composes unified diffs and file patches across multiple staged tickets."""

    @classmethod
    def detect_conflicts(
        cls, ticket_a: Any, ticket_b: Any, base_files: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """Detect conflicts between two tickets touching the same file."""
        changes_a = getattr(ticket_a, "proposed_changes", {}) or {}
        changes_b = getattr(ticket_b, "proposed_changes", {}) or {}

        shared_files = set(changes_a.keys()).intersection(set(changes_b.keys()))
        conflicts = []

        for f in sorted(list(shared_files)):
            content_a = changes_a[f]
            content_b = changes_b[f]
            if content_a != content_b:
                conflicts.append(
                    f"Conflict in '{f}': Both ticket {ticket_a.ticket_id} and {ticket_b.ticket_id} "
                    f"modify the same file with differing content."
                )

        return conflicts

    @classmethod
    def compose_patches(
        cls, tickets: List[Any], base_files: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Compose proposed changes from an ordered list of tickets.
        
        Example: Combines HERMES-101 (test patch) and HERMES-102 (feature patch)
        into a unified dictionary for sandbox testing.
        """
        composed: Dict[str, str] = {}
        ticket_file_origin: Dict[str, str] = {}

        for ticket in tickets:
            changes = getattr(ticket, "proposed_changes", {}) or {}
            for rel_path, new_content in changes.items():
                clean_path = rel_path.replace("\\", "/").lstrip("/")

                # If already modified by an earlier ticket in this sprint
                if clean_path in composed:
                    prev_tid = ticket_file_origin[clean_path]
                    # If identical, keep
                    if composed[clean_path] != new_content:
                        raise PatchConflictError(
                            f"Staged patch conflict on file '{clean_path}' between "
                            f"ticket {prev_tid} and ticket {ticket.ticket_id}."
                        )

                composed[clean_path] = new_content
                ticket_file_origin[clean_path] = ticket.ticket_id

        return composed

    @classmethod
    def apply_composed_to_sandbox(
        cls, composed_changes: Dict[str, str], sandbox_dir: Path
    ) -> None:
        """Write composed changes to the isolated sandbox directory."""
        for rel_path, content in composed_changes.items():
            clean_rel = rel_path.replace("\\", "/").lstrip("/")
            dest = sandbox_dir / clean_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                dest.unlink()
            dest.write_text(content, encoding="utf-8")
