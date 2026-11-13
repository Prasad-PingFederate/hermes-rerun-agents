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
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import subprocess
import sys
from hermes.guards.ast_patch_guard import ASTPatchGuard
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor
from core.context.active_context_pruner import BillionContextManager
from core.governance.policy_engine import PolicyEngine
from core.orchestrator.scrum_hierarchy import (
    ESCALATION_CHAIN,
    ModelTier,
    SubTaskTicket,
    TIER_COST_WEIGHTS,
    route_tier_by_complexity,
)
from core.time_machine.engine import TimeMachineEngine
from hermes.orchestration.hermes_workers import (
    AutomationTesterAgent,
    DeveloperAgent,
    TestCaseWriterAgent,
    TestHealerAgent,
    WorkerProposal,
)
from hermes.execution.llm_provider_adapter import AgentRole, HermesLLMAdapter
from hermes.orchestration.qa_critic_reviewer import EscalationPromptBuilder, QACriticAgent, QACriticReview
from hermes.execution.sandbox_executor import SandboxExecutor
from hermes.guards.security_blast_radius import SecurityBlastRadiusAgent
from hermes.orchestration.sprint_dag_scheduler import PatchConflictError, SprintDAGScheduler, StagedPatchComposer
from hermes.orchestration.sprint_state_store import AttemptRecord, SprintStateStore
from hermes.ingestion.ticket_router import TicketRouter
# GAP-22: Single source of truth: alias HumanWriteGate to HumanWriteGateController
def HumanWriteGate(*args: Any, **kwargs: Any) -> Any:
    from hermes.guards.write_gate_controller import HumanWriteGateController
    return HumanWriteGateController(*args, **kwargs)

HumanWriteGateController = HumanWriteGate


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
        self.policy_engine = PolicyEngine(self.workspace_path)

    def create_sprint_plan(self, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """Decompose failure context into ordered SubTaskTicket items."""
        sprint_id = f"sprint_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
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

        # Policy-as-code boundary evaluation (Option 5: .hermes.yml)
        all_target_files: List[str] = []
        for t in ordered_tickets:
            all_target_files.extend(t.allowed_files)
        policy_res = self.policy_engine.evaluate_file_paths(all_target_files)
        sprint_status = "TRIAGE_ONLY" if policy_res.resolved_mode == "TRIAGE_ONLY" else "ACTIVE"

        # Durably save sprint
        self.store.save_sprint(
            sprint_id=sprint_id,
            status=sprint_status,
            failure_context={**failure_context, "policy": policy_res.to_dict()},
            tickets=ordered_tickets,
        )

        telemetry = self.summarize_sprint_telemetry(ordered_tickets)
        return {
            "sprint_id": sprint_id,
            "status": sprint_status,
            "tickets": [asdict(t) for t in ordered_tickets],
            "telemetry": telemetry,
            "policy": policy_res.to_dict(),
        }

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

    def execute_ticket_with_escalation(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run worker with QA review and auto-escalation (TIER_3 -> TIER_2 -> TIER_1).
        
        Supports both signatures:
        1. (sprint_id, ticket, worker_fn, allow_test_modification) -> (ticket, proposal)
        2. (ticket, worker_fn, allow_test_modification) -> ticket
        Also supports keyword invocation (sprint_id=..., ticket=..., worker_fn=..., allow_test_modification=...).
        """
        return_tuple = True
        sprint_id = kwargs.get("sprint_id")
        ticket = kwargs.get("ticket")
        fn = kwargs.get("worker_fn")
        allow_test_modification = kwargs.get("allow_test_modification", False)

        if len(args) >= 1:
            if isinstance(args[0], str):
                sprint_id = args[0]
                return_tuple = True
                if len(args) >= 2:
                    ticket = args[1]
                if len(args) >= 3:
                    fn = args[2]
                if len(args) >= 4:
                    allow_test_modification = args[3]
            elif isinstance(args[0], SubTaskTicket):
                ticket = args[0]
                return_tuple = False
                if len(args) >= 2:
                    fn = args[1]
                if len(args) >= 3:
                    allow_test_modification = args[2]

        if not sprint_id:
            sprint_id = getattr(ticket, "sprint_id", None) or f"sprint_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

        current_tier = ticket.assigned_tier
        escalation_prompt: Optional[str] = None

        while current_tier:
            ticket.status = "IN_PROGRESS"
            model_name = ModelTier.get_model_name(current_tier)

            # 1. Execute worker to produce thin WorkerProposal
            try:
                try:
                    res = fn(ticket, current_tier, escalation_prompt)
                except TypeError:
                    try:
                        res = fn(ticket, ModelTier(current_tier))
                    except TypeError:
                        res = fn(ticket, current_tier)

                if isinstance(res, WorkerProposal):
                    proposal = res
                elif isinstance(res, dict):
                    proposal = WorkerProposal(
                        ticket_id=ticket.ticket_id,
                        worker_agent=getattr(ticket, "last_worker_name", f"Worker_{current_tier}"),
                        model_tier=current_tier,
                        proposed_changes=res,
                    )
                else:
                    proposal = res
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
                    return (ticket, None) if return_tuple else ticket

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
                    return (ticket, None) if return_tuple else ticket

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
                    return (ticket, None) if return_tuple else ticket

            # 4. QA Critic Review (TIER_4)
            qa_review: QACriticReview = QACriticAgent.review_worker_output(
                ticket=ticket,
                proposed_changes=proposal.proposed_changes,
                allow_test_modification=allow_test_modification,
                workspace_path=self.workspace_path,
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
                    return (ticket, None) if return_tuple else ticket

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
            return (ticket, proposal) if return_tuple else ticket

        ticket.status = "FAILED"
        return (ticket, None) if return_tuple else ticket

    def run_sprint(
        self,
        *,
        mode: str,                         # "story" | "heal"
        story: Optional[str] = None,
        failure_output: Optional[str] = None,
        scope: Optional[List[str]] = None,
        pytest_cmd: Optional[List[str]] = None,
        auto_approve: bool = False,
    ) -> Dict[str, Any]:
        """Single unified sprint pipeline coordinating decomposition, topological execution,
        multi-gate validation, sandboxing, write-gate staging, and safety snapshots.
        """
        ingestor = CIFailureIngestor(self.workspace_path)
        tickets: List[SubTaskTicket] = []

        if mode == "story":
            story_text = story or "Implement feature requirements"
            story_context = ingestor.ingest_user_story(story_text, target_scope=scope)
            all_allowed = story_context.get("allowed_files", [])
            test_files = [f for f in all_allowed if "test" in f.lower() or f.endswith("_test.py")]
            impl_files = [f for f in all_allowed if not ("test" in f.lower() or f.endswith("_test.py"))]

            if not test_files:
                test_files = ["tests/test_feature.py"]
            if not impl_files:
                impl_files = ["src/feature.py"]

            # 1. TestCaseWriter ticket (tests/* only)
            t_writer = self.router.route_ticket(
                ticket_id="TICK-WRITER-001",
                title=f"Author test cases: {story_text[:50]}",
                complexity=2,
                allowed_files=test_files,
                acceptance_criteria=story_context.get("acceptance_criteria", []),
                depends_on=[],
            )
            # 2. Developer ticket (impl files only, depends on writer)
            t_dev = self.router.route_ticket(
                ticket_id="TICK-DEV-001",
                title=f"Implement functionality: {story_text[:50]}",
                complexity=3,
                allowed_files=impl_files,
                acceptance_criteria=story_context.get("acceptance_criteria", []),
                depends_on=["TICK-WRITER-001"],
            )
            tickets = [t_writer, t_dev]

        elif mode == "heal":
            raw_output = failure_output or ""
            if not raw_output and pytest_cmd:
                proc = subprocess.run(pytest_cmd, cwd=str(self.workspace_path), capture_output=True, text=True)
                raw_output = f"{proc.stdout}\n{proc.stderr}"
                if proc.returncode == 0:
                    return {
                        "status": "PASSED",
                        "classification": "PASSED",
                        "message": "All tests passed cleanly. No healing needed.",
                        "tickets": [],
                    }

            from agents.ci_detective import CIDetectiveAgent
            intent_context = CIDetectiveAgent.extract_commit_and_pr_intent(workspace_path=self.workspace_path)
            classification = self.sandbox.classify_failure(raw_output, intent_context=intent_context)
            if classification == "PASSED":
                return {
                    "status": "PASSED",
                    "classification": "PASSED",
                    "message": "All tests passed cleanly. No healing needed.",
                    "tickets": [],
                }
            if classification == "ENVIRONMENT_NOISE":
                return {
                    "status": "ENVIRONMENT_NOISE",
                    "classification": "ENVIRONMENT_NOISE",
                    "message": "Environment issue detected (missing dependency, port in use, or permissions). Aborting heal.",
                    "tickets": [],
                }

            failure_context = ingestor.ingest_failure_output(raw_output)
            all_allowed = failure_context.get("allowed_files", [])

            if classification == "PRODUCT_BUG":
                impl_files = [
                    f for f in all_allowed
                    if not (f.startswith("tests/") or Path(f).name.startswith("test_") or f.endswith("_test.py"))
                ]
                if not impl_files:
                    for fail in failure_context.get("failures", []):
                        for off in fail.get("offending_files", []):
                            clean = off.replace("\\", "/").lstrip("/")
                            if not (clean.startswith("tests/") or Path(clean).name.startswith("test_") or clean.endswith("_test.py")):
                                impl_files.append(clean)
                if not impl_files:
                    impl_files = ["src/main.py"]

                t_heal = self.router.route_ticket(
                    ticket_id="HEAL-PROD-001",
                    title="Repair product bug causing test failure",
                    complexity=2,
                    allowed_files=list(dict.fromkeys(impl_files)),
                    acceptance_criteria=failure_context.get("acceptance_criteria", []),
                    depends_on=[],
                )
                tickets = [t_heal]
            elif classification == "FLAKY_TEST":
                test_files = [
                    f for f in all_allowed
                    if (f.startswith("tests/") or Path(f).name.startswith("test_") or f.endswith("_test.py") or f.endswith(".ts") or f.endswith(".js"))
                ]
                if not test_files:
                    test_files = ["tests/test_calc.py"]

                t_heal = self.router.route_ticket(
                    ticket_id="QUARANTINE-001",
                    title=f"Quarantine flaky test ({test_files[0]})",
                    complexity=2,
                    allowed_files=list(dict.fromkeys(test_files)),
                    acceptance_criteria=[
                        "AC-1: Apply non-erosive retry quarantine policy (reruns=2).",
                        "AC-2: Preserve all existing assertions and inject zero skip modifiers.",
                    ],
                    depends_on=[],
                )
                tickets = [t_heal]
            else:  # TEST_BUG
                test_files = [
                    f for f in all_allowed
                    if (f.startswith("tests/") or Path(f).name.startswith("test_") or f.endswith("_test.py") or f.endswith(".ts") or f.endswith(".js"))
                ]
                if not test_files:
                    test_files = ["tests/test_calc.py"]

                t_heal = self.router.route_ticket(
                    ticket_id="HEAL-TEST-001",
                    title=f"Repair test file ({classification})",
                    complexity=2,
                    allowed_files=list(dict.fromkeys(test_files)),
                    acceptance_criteria=failure_context.get("acceptance_criteria", []),
                    depends_on=[],
                )
                tickets = [t_heal]
        else:
            raise ValueError(f"Unknown sprint mode '{mode}'. Must be 'story' or 'heal'.")

        # 2. Schedule tickets with SprintDAGScheduler.topological_sort
        ordered_tickets = SprintDAGScheduler.topological_sort(tickets)
        sprint_id = f"sprint_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        self.store.save_sprint(
            sprint_id=sprint_id,
            status="ACTIVE",
            failure_context={"mode": mode, "raw_output": failure_output or ""},
            tickets=ordered_tickets,
        )

        adapter = HermesLLMAdapter(self.workspace_path)
        reader = self.write_gate.reader
        accumulated_patches: Dict[str, str] = {}

        # 3. Execute tickets with escalation loop
        for ticket in ordered_tickets:
            if "WRITER" in ticket.ticket_id:
                agent_role = AgentRole.TEST_CASE_WRITER_AGENT
            elif "QUARANTINE" in ticket.ticket_id:
                agent_role = AgentRole.FLAKE_QUARANTINE_AGENT
            elif "HEAL-TEST" in ticket.ticket_id:
                agent_role = AgentRole.TEST_HEALER_AGENT
            else:
                agent_role = AgentRole.DEVELOPER_AGENT

            def worker_fn(t: SubTaskTicket, tier: str, esc_prompt: Optional[str]) -> WorkerProposal:
                f_contents = reader.read_allowed_files(t.allowed_files)
                for f, content in accumulated_patches.items():
                    if f in t.allowed_files:
                        f_contents[f] = content
                patch_map = adapter.propose_patch(
                    agent_role=agent_role,
                    ticket=t,
                    tier=tier,
                    file_contents=f_contents,
                    instruction=esc_prompt or "",
                )
                return WorkerProposal(
                    ticket_id=t.ticket_id,
                    worker_agent=agent_role.value,
                    model_tier=tier,
                    proposed_changes=patch_map,
                )

            allow_tests = agent_role in (
                AgentRole.TEST_CASE_WRITER_AGENT,
                AgentRole.TEST_HEALER_AGENT,
                AgentRole.FLAKE_QUARANTINE_AGENT,
            )
            executed_ticket, proposal = self.execute_ticket_with_escalation(
                sprint_id=sprint_id,
                ticket=ticket,
                worker_fn=worker_fn,
                allow_test_modification=allow_tests,
            )

            if executed_ticket.status != "DONE" or not proposal:
                return {
                    "status": "FAILED",
                    "sprint_id": sprint_id,
                    "ticket_id": ticket.ticket_id,
                    "error": f"Ticket failed all escalation tiers: {ticket.ticket_id}",
                    "attempts": ticket.attempt_history,
                }

            accumulated_patches.update(proposal.proposed_changes)

        # 4. Stage approved changes into HumanWriteGateController
        combined_proposal = WorkerProposal(
            ticket_id=ordered_tickets[-1].ticket_id,
            worker_agent="ScrumMasterOrchestrator",
            model_tier=ordered_tickets[-1].assigned_tier,
            proposed_changes=accumulated_patches,
        )
        stage_id = self.write_gate.stage_proposal(
            sprint_id=sprint_id,
            ticket=ordered_tickets[-1],
            proposal=combined_proposal,
        )

        # 5. Handle approval / verification
        cmd = pytest_cmd or [sys.executable, "-m", "pytest", "-q"]

        def verify_fn() -> bool:
            v_proc = subprocess.run(cmd, cwd=str(self.workspace_path), capture_output=True, text=True)
            return v_proc.returncode == 0

        if auto_approve:
            res = self.write_gate.approve_proposal(sprint_id, verification_fn=verify_fn)
            return res

        # 6. Awaiting manual approval
        return {
            "status": "AWAITING_WRITE_GATE",
            "sprint_id": sprint_id,
            "proposal_id": stage_id,
            "classification": classification if mode == "heal" else None,
            "diff": self.write_gate.get_diff_summary(sprint_id),
            "tickets": [asdict(t) for t in ordered_tickets],
        }
