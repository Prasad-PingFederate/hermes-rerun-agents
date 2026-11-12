"""
Scrum Master Orchestrator & Human Write-Gate
Owner: ScrumMasterOrchestrator, TIER_1

Coordinates the complete Hermes multi-agent pipeline:
- Topological sprint DAG execution via SprintDAGScheduler.
- Multi-run ephemeral sandbox execution via SandboxExecutor.
- Thin Worker contract: workers return WorkerProposal (zero direct workspace mutation).
- Zero Assertion Erosion: TestCaseWriterAgent and TestHealerAgent must never reduce assertions.
- Multi-tier escalation loop: TIER_3 -> TIER_2 -> TIER_1 with EscalationPromptBuilder memory.
- Durable persistence: State and attempts flushed to SQLite + JSONL via SprintStateStore.
- Final Safety Layer: HumanWriteGate requires explicit approval and creates a TimeMachine snapshot before writing.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ast_patch_guard import ASTPatchGuard
from core.context.active_context_pruner import BillionContextManager
from core.orchestrator.scrum_hierarchy import (
    ESCALATION_CHAIN,
    ModelTier,
    SubTaskTicket,
    TIER_COST_WEIGHTS,
    route_tier_by_complexity,
)
from core.time_machine.engine import TimeMachineEngine
from hermes_workers import (
    AutomationTesterAgent,
    DeveloperAgent,
    TestCaseWriterAgent,
    TestHealerAgent,
    WorkerProposal,
)
from qa_critic_reviewer import EscalationPromptBuilder, QACriticAgent, QACriticReview
from sandbox_executor import SandboxExecutor
from security_blast_radius import SecurityBlastRadiusAgent
from sprint_dag_scheduler import PatchConflictError, SprintDAGScheduler, StagedPatchComposer
from sprint_state_store import AttemptRecord, SprintStateStore
from ticket_router import TicketRouter


class HumanWriteGate:
    """Final Safety Layer: Holds approved proposals and creates a reversible TimeMachine snapshot before workspace mutation."""

    def __init__(
        self,
        workspace_path: Path,
        tm_engine: TimeMachineEngine,
        store: Optional[SprintStateStore] = None,
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.tm = tm_engine
        self.store = store or SprintStateStore()
        self.staged_proposals: Dict[str, Dict[str, Any]] = {}

    def stage_proposal(
        self,
        sprint_id: str,
        ticket: SubTaskTicket,
        proposal: WorkerProposal,
    ) -> str:
        """Stage an approved proposal awaiting explicit human or API write approval."""
        stage_id = f"stage_{ticket.ticket_id}_{int(time.time())}"
        self.staged_proposals[stage_id] = {
            "sprint_id": sprint_id,
            "ticket_id": ticket.ticket_id,
            "proposal": proposal,
            "staged_at": time.time(),
            "status": "AWAITING_WRITE_GATE",
        }
        self.store.update_sprint_status(sprint_id, "AWAITING_WRITE_GATE")
        return stage_id

    def approve_and_apply(
        self,
        stage_id: str,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explicitly approve and write staged changes to workspace with safety snapshot."""
        if stage_id not in self.staged_proposals:
            raise KeyError(f"No staged proposal found with ID '{stage_id}'")

        item = self.staged_proposals[stage_id]
        proposal: WorkerProposal = item["proposal"]
        sprint_id = item["sprint_id"]
        ticket_id = item["ticket_id"]

        # 1. Take safety pre-apply snapshot before touching workspace (Invariant 5)
        snap_label = label or f"safety_pre_apply_{ticket_id}_{int(time.time())}"
        snapshot_meta = self.tm.create_snapshot(label=snap_label)
        snapshot_id = snapshot_meta.id if hasattr(snapshot_meta, "id") else snapshot_meta["id"]

        # Record snapshot in durable store
        files_manifest = {}
        if hasattr(snapshot_meta, "files_tracked") and snapshot_meta.files_tracked:
            files_manifest = {f: {} for f in snapshot_meta.files_tracked}
        elif isinstance(snapshot_meta, dict):
            files_manifest = snapshot_meta.get("files", {})

        self.store.save_snapshot(
            snapshot_id=snapshot_id,
            sprint_id=sprint_id,
            ticket_id=ticket_id,
            label=snap_label,
            manifest=files_manifest,
        )

        applied_files: List[str] = []
        try:
            # 2. Safely write files with path validation and symlink defenses
            for rel_path, content in proposal.proposed_changes.items():
                dest_path = self.tm._validate_safe_workspace_path(rel_path, allow_missing=True)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if dest_path.is_symlink() or dest_path.exists():
                    dest_path.unlink()
                dest_path.write_text(content, encoding="utf-8")
                applied_files.append(rel_path)

            item["status"] = "APPLIED"
            self.store.update_sprint_status(sprint_id, "COMPLETED")

            return {
                "success": True,
                "stage_id": stage_id,
                "ticket_id": ticket_id,
                "snapshot_id": snapshot_id,
                "applied_files": applied_files,
                "status": "APPLIED",
            }
        except Exception as e:
            # 3. Surgical instant rollback on failure
            self.tm.restore_snapshot(snapshot_id)
            item["status"] = "ROLLED_BACK"
            self.store.update_sprint_status(sprint_id, "ROLLED_BACK")
            return {
                "success": False,
                "stage_id": stage_id,
                "ticket_id": ticket_id,
                "snapshot_id": snapshot_id,
                "error": str(e),
                "rolled_back": True,
            }


class ScrumMasterOrchestrator:
    """The central hierarchical coordinator implementing the full Hermes Scrum pipeline."""

    def __init__(
        self,
        workspace_path: Optional[Path | str] = None,
        tm_engine: Optional[TimeMachineEngine] = None,
        store: Optional[SprintStateStore] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = tm_engine or TimeMachineEngine(self.workspace_path)
        self.store = store or SprintStateStore()
        self.router = TicketRouter(self.workspace_path, self.tm)
        self.write_gate = HumanWriteGate(self.workspace_path, self.tm, self.store)
        self.sandbox = SandboxExecutor(self.workspace_path)
        self.context_manager = BillionContextManager()

    def create_sprint_plan(self, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """Decompose failure context into ordered SubTaskTicket items."""
        sprint_id = f"sprint_{int(time.time())}"
        tickets: List[SubTaskTicket] = []

        raw_tickets = failure_context.get("tickets", [])
        if raw_tickets:
            for idx, raw in enumerate(raw_tickets):
                tid = raw.get("ticket_id") or f"TICK-{idx+1:03d}"
                title = raw.get("title") or f"SubTask {idx+1}"
                complexity = int(raw.get("complexity", 2))
                allowed = raw.get("allowed_files", [])
                deps = raw.get("depends_on", [])
                criteria = raw.get("acceptance_criteria", [])

                ticket = self.router.route_ticket(
                    ticket_id=tid,
                    title=title,
                    complexity=complexity,
                    allowed_files=allowed,
                    acceptance_criteria=criteria,
                    depends_on=deps,
                )
                tickets.append(ticket)
        else:
            target_f = (
                failure_context.get("test_file") or failure_context.get("failing_test") or "tests/test_app.py"
            ).replace("\\", "/")
            ticket = self.router.route_ticket(
                ticket_id="TICK-001",
                title=f"Resolve failure in {Path(target_f).name}",
                complexity=2,
                allowed_files=[target_f],
                acceptance_criteria=[f"Resolve errors reported in {target_f}"],
            )
            tickets.append(ticket)

        # Validate topological ordering
        ordered_tickets = SprintDAGScheduler.topological_sort(tickets)

        # Durably save sprint
        self.store.save_sprint(
            sprint_id=sprint_id,
            status="ACTIVE",
            failure_context=failure_context,
            tickets=ordered_tickets,
        )

        return {
            "sprint_id": sprint_id,
            "tickets": [asdict(t) for t in ordered_tickets],
        }

    def execute_ticket_with_escalation(
        self,
        sprint_id: str,
        ticket: SubTaskTicket,
        worker_fn: Callable[[SubTaskTicket, str, Optional[str]], WorkerProposal],
        allow_test_modification: bool = False,
    ) -> Tuple[SubTaskTicket, Optional[WorkerProposal]]:
        """Run worker with QA review and auto-escalation (TIER_3 -> TIER_2 -> TIER_1)."""
        current_tier = ticket.assigned_tier
        escalation_prompt: Optional[str] = None

        while current_tier:
            ticket.status = "IN_PROGRESS"
            model_name = ModelTier.get_model_name(current_tier)

            # 1. Execute worker to produce thin WorkerProposal
            try:
                proposal = worker_fn(ticket, current_tier, escalation_prompt)
            except Exception as e:
                # Capture worker failure
                att = AttemptRecord(
                    tier=current_tier,
                    agent_name=getattr(ticket, "last_worker_name", "WorkerAgent"),
                    model_name=model_name,
                    status="REJECTED",
                    rejection_reason=f"Worker exception: {str(e)}",
                )
                ticket.attempt_history.append(att.to_dict())
                self.store.record_attempt(ticket.ticket_id, sprint_id, att)

                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                    escalation_prompt = EscalationPromptBuilder.build_escalation_prompt(ticket, current_tier)
                    continue
                else:
                    ticket.status = "FAILED"
                    return ticket, None

            # 2. Scope Gate verification
            scope_ok, scope_reasons = self.router.validate_worker_scope(ticket, proposal.proposed_changes)
            if not scope_ok:
                att = AttemptRecord(
                    tier=current_tier,
                    agent_name=proposal.worker_agent,
                    model_name=model_name,
                    status="REJECTED",
                    rejection_reason="; ".join(scope_reasons),
                )
                ticket.attempt_history.append(att.to_dict())
                self.store.record_attempt(ticket.ticket_id, sprint_id, att)

                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                    escalation_prompt = EscalationPromptBuilder.build_escalation_prompt(ticket, current_tier)
                    continue
                else:
                    ticket.status = "FAILED"
                    return ticket, None

            # 3. AST Patch Guard & Security Audit
            ast_report = ASTPatchGuard.analyze(
                workspace_root=self.workspace_path,
                proposed_changes=proposal.proposed_changes,
                allow_test_modification=allow_test_modification,
                ticket=ticket,
            )
            if not ast_report.get("valid", True):
                reasons = ast_report.get("reasons", ["AST validation failed"])
                att = AttemptRecord(
                    tier=current_tier,
                    agent_name=proposal.worker_agent,
                    model_name=model_name,
                    status="REJECTED",
                    rejection_reason="; ".join(reasons),
                    security_findings=ast_report.get("security", {}).get("findings", []),
                )
                ticket.attempt_history.append(att.to_dict())
                self.store.record_attempt(ticket.ticket_id, sprint_id, att)

                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                    escalation_prompt = EscalationPromptBuilder.build_escalation_prompt(
                        ticket, current_tier, security_findings=att.security_findings
                    )
                    continue
                else:
                    ticket.status = "FAILED"
                    return ticket, None

            # 4. QA Critic Review (TIER_4)
            qa_review: QACriticReview = QACriticAgent.review_worker_output(
                ticket=ticket,
                proposed_changes=proposal.proposed_changes,
                allow_test_modification=allow_test_modification,
            )
            if not qa_review.approved:
                att = AttemptRecord(
                    tier=current_tier,
                    agent_name=proposal.worker_agent,
                    model_name=model_name,
                    status="REJECTED",
                    rejection_reason="; ".join(qa_review.rejection_reasons),
                    qa_verdicts=[asdict(v) for v in qa_review.verdicts],
                )
                ticket.attempt_history.append(att.to_dict())
                self.store.record_attempt(ticket.ticket_id, sprint_id, att)

                next_tier = ESCALATION_CHAIN.get(current_tier)
                if next_tier:
                    ticket.status = "ESCALATED"
                    current_tier = next_tier
                    ticket.assigned_tier = current_tier
                    escalation_prompt = EscalationPromptBuilder.build_escalation_prompt(
                        ticket, current_tier, qa_review=qa_review
                    )
                    continue
                else:
                    ticket.status = "FAILED"
                    return ticket, None

            # All gates passed: proposal approved!
            att = AttemptRecord(
                tier=current_tier,
                agent_name=proposal.worker_agent,
                model_name=model_name,
                status="APPROVED",
                rejection_reason=None,
                qa_verdicts=[asdict(v) for v in qa_review.verdicts],
            )
            ticket.attempt_history.append(att.to_dict())
            self.store.record_attempt(ticket.ticket_id, sprint_id, att)

            ticket.status = "DONE"
            ticket.proposed_changes = proposal.proposed_changes
            return ticket, proposal

        ticket.status = "FAILED"
        return ticket, None
