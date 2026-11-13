"""
Ticket Router & Scope Enforcer
Owner: ScrumMasterOrchestrator

Routes tickets to ModelTiers based on complexity and enforces allowed_files scope boundaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from hermes.core.orchestrator.scrum_hierarchy import (
    ModelTier,
    SubTaskTicket,
    route_tier_by_complexity,
)
from hermes.core.time_machine.engine import TimeMachineEngine


class TicketRouter:
    """Manages ticket routing and safe workspace scope validation."""

    def __init__(self, workspace_path: Optional[Path | str] = None, tm_engine: Optional[TimeMachineEngine] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = tm_engine or TimeMachineEngine(self.workspace_path)

    def route_ticket(
        self,
        ticket_id: str,
        title: str,
        complexity: int,
        allowed_files: List[str],
        acceptance_criteria: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> SubTaskTicket:
        """Create and route a SubTaskTicket with validated file paths."""
        complexity_clamped = max(1, min(5, int(complexity)))
        assigned_tier = route_tier_by_complexity(complexity_clamped)

        normalized_allowed: List[str] = []
        for f in allowed_files:
            clean_f = f.replace("\\", "/").lstrip("/")
            # Validate through TimeMachine path security
            self.tm._validate_safe_workspace_path(clean_f, allow_missing=True)
            normalized_allowed.append(clean_f)

        ticket = SubTaskTicket(
            ticket_id=ticket_id,
            title=title,
            complexity=complexity_clamped,
            assigned_tier=assigned_tier,
            allowed_files=normalized_allowed,
            acceptance_criteria=acceptance_criteria or [],
            status="TODO",
        )
        setattr(ticket, "depends_on", depends_on or [])
        return ticket

    def validate_worker_scope(self, ticket: SubTaskTicket, proposed_changes: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Verify that proposed changes do not violate ticket.allowed_files."""
        allowed_set = {f.replace("\\", "/").lstrip("/") for f in ticket.allowed_files}
        worker_files = {f.replace("\\", "/").lstrip("/") for f in proposed_changes.keys()}
        violations = worker_files - allowed_set

        if violations:
            return False, [
                f"Scope violation: Worker modified unauthorized file(s): {sorted(list(violations))}. "
                f"Allowed files: {sorted(list(allowed_set))}"
            ]
        return True, []
