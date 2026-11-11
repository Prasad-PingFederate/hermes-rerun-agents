"""
Hierarchical Multi-Model Orchestration: Scrum Master -> Tiered SWE Workers -> QA Critic
Deterministic, provider-agnostic multi-model task delegation and auto-escalation.
Zero external dependencies (uses standard library: dataclasses, enum, typing, pathlib, os).
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core.time_machine.engine import TimeMachineEngine
from core.time_machine.patch_guard import analyze_proposed_changes


class ModelTier(str, Enum):
    """Hierarchical Model Tiers for Tech Lead, Senior SWE, Junior SWE, and QA Critic."""
    TIER_1_TECH_LEAD = "TIER_1_TECH_LEAD"
    TIER_2_SENIOR_SWE = "TIER_2_SENIOR_SWE"
    TIER_3_JUNIOR_SWE = "TIER_3_JUNIOR_SWE"
    TIER_4_QA_CRITIC = "TIER_4_QA_CRITIC"

    @classmethod
    def get_model_name(cls, tier: "ModelTier" | str) -> str:
        """Resolve model name from environment variables with fallback defaults."""
        val = tier.value if isinstance(tier, ModelTier) else str(tier)
        if val == cls.TIER_1_TECH_LEAD.value:
            return os.environ.get("RERUN_TIER1_MODEL", "tier1-tech-lead")
        elif val == cls.TIER_2_SENIOR_SWE.value:
            return os.environ.get("RERUN_TIER2_MODEL", "tier2-senior-swe")
        elif val == cls.TIER_3_JUNIOR_SWE.value:
            return os.environ.get("RERUN_TIER3_MODEL", "tier3-junior-swe")
        elif val == cls.TIER_4_QA_CRITIC.value:
            return os.environ.get("RERUN_TIER4_MODEL", "tier4-qa-critic")
        return "unknown-model"


TIER_COST_WEIGHTS: Dict[str, float] = {
    ModelTier.TIER_1_TECH_LEAD.value: 1.0,
    ModelTier.TIER_2_SENIOR_SWE.value: 0.35,
    ModelTier.TIER_3_JUNIOR_SWE.value: 0.10,
    ModelTier.TIER_4_QA_CRITIC.value: 0.15,
}

ESCALATION_CHAIN: Dict[str, Optional[str]] = {
    ModelTier.TIER_3_JUNIOR_SWE.value: ModelTier.TIER_2_SENIOR_SWE.value,
    ModelTier.TIER_2_SENIOR_SWE.value: ModelTier.TIER_1_TECH_LEAD.value,
    ModelTier.TIER_1_TECH_LEAD.value: None,
}


def route_tier_by_complexity(complexity: int) -> str:
    """Route complexity (1-5) to the appropriate ModelTier.
    
    complexity <= 2 -> TIER_3_JUNIOR_SWE
    complexity 3-4 -> TIER_2_SENIOR_SWE
    complexity == 5 -> TIER_1_TECH_LEAD
    """
    if complexity <= 2:
        return ModelTier.TIER_3_JUNIOR_SWE.value
    elif complexity <= 4:
        return ModelTier.TIER_2_SENIOR_SWE.value
    else:
        return ModelTier.TIER_1_TECH_LEAD.value


@dataclass
class SubTaskTicket:
    ticket_id: str
    title: str
    complexity: int  # 1 to 5
    assigned_tier: str  # TIER_1_TECH_LEAD, TIER_2_SENIOR_SWE, TIER_3_JUNIOR_SWE
    allowed_files: List[str]  # strict file scope boundary enforced by Scrum Master
    acceptance_criteria: List[str] = field(default_factory=list)
    status: str = "TODO"  # "TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "ESCALATED", "FAILED"
    attempt_history: List[Dict[str, Any]] = field(default_factory=list)  # {tier, model_name, status, rejection_reason}
    proposed_changes: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize paths in allowed_files
        self.allowed_files = [f.replace("\\", "/") for f in self.allowed_files]


class ScrumMasterOrchestrator:
    """Coordinates Tech Lead sprint planning, worker ticket delegation, QA critique, and auto-escalation."""

    def __init__(
        self,
        workspace_path: Optional[Path | str] = None,
        tm_engine: Optional[TimeMachineEngine] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = tm_engine or TimeMachineEngine(self.workspace_path)

    def create_sprint_plan(self, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """Acts as the Tier-1 Tech Lead / Scrum Master:
        
        Decomposes a failure diagnosis into ordered SubTaskTicket items, assigns
        complexity (1-5) and assigned_tier, and locks allowed_files (validating each
        path with _validate_safe_workspace_path).
        """
        tickets: List[SubTaskTicket] = []

        raw_tickets = failure_context.get("tickets")
        if raw_tickets and isinstance(raw_tickets, list):
            for idx, raw in enumerate(raw_tickets):
                tid = raw.get("ticket_id") or f"TICK-{idx+1:03d}"
                title = raw.get("title") or f"SubTask {idx+1}"
                complexity = int(raw.get("complexity", 2))
                complexity = max(1, min(5, complexity))
                assigned_tier = raw.get("assigned_tier") or route_tier_by_complexity(complexity)
                allowed = raw.get("allowed_files", [])

                # Validate every allowed path with TM engine
                for f in allowed:
                    self.tm._validate_safe_workspace_path(f, allow_missing=True)

                ticket = SubTaskTicket(
                    ticket_id=tid,
                    title=title,
                    complexity=complexity,
                    assigned_tier=assigned_tier,
                    allowed_files=allowed,
                    acceptance_criteria=raw.get("acceptance_criteria", []),
                    status=raw.get("status", "TODO"),
                    attempt_history=raw.get("attempt_history", []),
                    proposed_changes=raw.get("proposed_changes", {}),
                )
                tickets.append(ticket)
        elif failure_context.get("diagnosis"):
            diag = failure_context["diagnosis"]
            diag_files = diag.get("files", [])
            if diag_files:
                for idx, f_info in enumerate(diag_files):
                    f_path = (f_info.get("path") or f_info.get("file") or "").replace("\\", "/")
                    if not f_path:
                        continue
                    self.tm._validate_safe_workspace_path(f_path, allow_missing=True)
                    complexity = int(f_info.get("complexity", 2))
                    complexity = max(1, min(5, complexity))
                    ticket = SubTaskTicket(
                        ticket_id=f"TICK-{idx+1:03d}",
                        title=f"Repair {Path(f_path).name}",
                        complexity=complexity,
                        assigned_tier=route_tier_by_complexity(complexity),
                        allowed_files=[f_path],
                        acceptance_criteria=[f"Resolve errors reported in {f_path}"],
                    )
                    tickets.append(ticket)
            else:
                target_f = (failure_context.get("test_file") or failure_context.get("failing_test") or "app.py").replace("\\", "/")
                self.tm._validate_safe_workspace_path(target_f, allow_missing=True)
                ticket = SubTaskTicket(
                    ticket_id="TICK-001",
                    title=f"Resolve failure in {Path(target_f).name}",
                    complexity=3,
                    assigned_tier=route_tier_by_complexity(3),
                    allowed_files=[target_f],
                    acceptance_criteria=[f"Fix failing test execution for {target_f}"],
                )
                tickets.append(ticket)
        else:
            target_f = (failure_context.get("test_file") or failure_context.get("failing_test") or "app.py").replace("\\", "/")
            self.tm._validate_safe_workspace_path(target_f, allow_missing=True)
            ticket = SubTaskTicket(
                ticket_id="TICK-001",
                title=f"Resolve failure in {Path(target_f).name}",
                complexity=2,
                assigned_tier=route_tier_by_complexity(2),
                allowed_files=[target_f],
                acceptance_criteria=[f"Verify passes in {target_f}"],
            )
            tickets.append(ticket)

        sprint_id = f"sprint_{int(time.time())}"
        telemetry = self.summarize_sprint_telemetry(tickets)

        return {
            "sprint_id": sprint_id,
            "tickets": [asdict(t) for t in tickets],
            "telemetry": telemetry,
        }

    def review_worker_output(
        self,
        ticket: SubTaskTicket,
        worker_changes: Dict[str, str],
        allow_test_modification: bool = False,
    ) -> Dict[str, Any]:
        """Acts as the Tier-4 QA Critic + Tech Lead gate:
        
        1. Scope Gate: Rejects if worker_changes modifies any file outside ticket.allowed_files.
        2. Safety & AST Gate: Runs analyze_proposed_changes from patch_guard. Rejects if
           SyntaxError, test tampering, or risk_level == 'HIGH' when executed by TIER_3_JUNIOR_SWE.
        """
        # 1. Scope Gate
        allowed_set = {f.replace("\\", "/") for f in ticket.allowed_files}
        worker_files = {f.replace("\\", "/") for f in worker_changes.keys()}
        violating_files = worker_files - allowed_set

        if violating_files:
            return {
                "approved": False,
                "reasons": [
                    f"Scope violation: worker modified unauthorized file(s): {sorted(list(violating_files))}. Allowed: {sorted(list(allowed_set))}"
                ],
                "blast_radius": {},
            }

        # 2. Safety & AST Gate
        try:
            report = analyze_proposed_changes(
                workspace_root=self.workspace_path,
                proposed_changes=worker_changes,
                allow_test_modification=allow_test_modification,
            )
        except ValueError as e:
            return {
                "approved": False,
                "reasons": [str(e)],
                "blast_radius": {},
            }

        reasons: List[str] = []
        if not report.get("valid", True):
            reasons.extend(report.get("tampering_reasons", ["Test tampering detected"]))

        # Junior SWE restriction: HIGH blast radius not permitted
        blast_radius = report.get("blast_radius", {})
        if (
            ticket.assigned_tier == ModelTier.TIER_3_JUNIOR_SWE.value
            and blast_radius.get("risk_level") == "HIGH"
        ):
            reasons.append("Risk level 'HIGH' is not permitted for TIER_3_JUNIOR_SWE worker")

        if reasons:
            return {
                "approved": False,
                "reasons": reasons,
                "blast_radius": blast_radius,
            }

        return {
            "approved": True,
            "reasons": [],
            "blast_radius": blast_radius,
        }

    def execute_ticket_with_escalation(
        self,
        ticket: SubTaskTicket,
        worker_fn: Callable[[SubTaskTicket, ModelTier], Dict[str, str]],
        allow_test_modification: bool = False,
    ) -> SubTaskTicket:
        """Executes ticket starting at ticket.assigned_tier.
        
        On QA rejection, records failed attempt in attempt_history and automatically
        escalates to next higher tier (TIER_3 -> TIER_2 -> TIER_1) until approved
        or tiers exhausted.
        """
        current_tier = ticket.assigned_tier

        while current_tier:
            ticket.status = "IN_PROGRESS"
            model_name = ModelTier.get_model_name(current_tier)

            try:
                worker_changes = worker_fn(ticket, ModelTier(current_tier))
            except Exception as e:
                # Capture unhandled worker exception as rejection
                worker_changes = {}
                rejection_msg = f"Worker exception: {str(e)}"
                ticket.attempt_history.append({
                    "tier": current_tier,
                    "model_name": model_name,
                    "status": "REJECTED",
                    "rejection_reason": rejection_msg,
                })
                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                    continue
                else:
                    ticket.status = "FAILED"
                    return ticket

            ticket.status = "IN_REVIEW"
            review = self.review_worker_output(
                ticket,
                worker_changes,
                allow_test_modification=allow_test_modification,
            )

            if review["approved"]:
                ticket.attempt_history.append({
                    "tier": current_tier,
                    "model_name": model_name,
                    "status": "APPROVED",
                    "rejection_reason": None,
                })
                ticket.proposed_changes = worker_changes
                ticket.status = "DONE"
                return ticket
            else:
                rejection_reasons = review.get("reasons", ["Rejected by QA Critic"])
                ticket.attempt_history.append({
                    "tier": current_tier,
                    "model_name": model_name,
                    "status": "REJECTED",
                    "rejection_reason": "; ".join(rejection_reasons),
                })
                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                else:
                    ticket.status = "FAILED"
                    return ticket

        ticket.status = "FAILED"
        return ticket

    def summarize_sprint_telemetry(self, tickets: List[SubTaskTicket]) -> Dict[str, Any]:
        """Computes total_tickets, tier_distribution, escalations_triggered, all_approved,
        and estimated_cost_savings_pct (Tier 1 = 1.0, Tier 2 = 0.35, Tier 3 = 0.10).
        """
        total_tickets = len(tickets)
        tier_distribution: Dict[str, int] = {
            ModelTier.TIER_1_TECH_LEAD.value: 0,
            ModelTier.TIER_2_SENIOR_SWE.value: 0,
            ModelTier.TIER_3_JUNIOR_SWE.value: 0,
        }

        escalations_triggered = 0
        all_approved = True if total_tickets > 0 else False

        actual_cost = 0.0
        baseline_cost = float(total_tickets) * TIER_COST_WEIGHTS[ModelTier.TIER_1_TECH_LEAD.value]

        for t in tickets:
            tier_val = t.assigned_tier
            if tier_val in tier_distribution:
                tier_distribution[tier_val] += 1

            if t.status != "DONE":
                all_approved = False

            # If ticket had rejections before approval or escalation occurred
            if len(t.attempt_history) > 1 or any(a.get("status") == "REJECTED" for a in t.attempt_history):
                escalations_triggered += 1

            if t.attempt_history:
                for att in t.attempt_history:
                    att_tier = att.get("tier", t.assigned_tier)
                    actual_cost += TIER_COST_WEIGHTS.get(att_tier, 1.0)
            else:
                actual_cost += TIER_COST_WEIGHTS.get(t.assigned_tier, 1.0)

        if baseline_cost > 0.0:
            savings_pct = max(0.0, ((baseline_cost - actual_cost) / baseline_cost) * 100.0)
        else:
            savings_pct = 0.0

        return {
            "total_tickets": total_tickets,
            "tier_distribution": tier_distribution,
            "escalations_triggered": escalations_triggered,
            "all_approved": all_approved,
            "estimated_cost_savings_pct": round(savings_pct, 2),
        }

