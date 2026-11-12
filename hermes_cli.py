"""
GAP-17: Unified Hermes CLI Entrypoint
Owner: ScrumMasterOrchestrator (TIER_1)

Commands:
- hermes_cli.py agents: Prints the 8-Agent Role, Tier, Skills & Boundaries table.
- hermes_cli.py run --story "..." --scope "src/..." [--auto-approve]: Runs full proactive sprint.
- hermes_cli.py heal --pytest-cmd "pytest -q" [--auto-approve]: End-to-end test failure triage and healing.
- hermes_cli.py status: Displays active/paused sprints, snapshots, and audit records.
- hermes_cli.py approve --sprint-id <id>: Approves staged write-gate proposal.
- hermes_cli.py rollback --snapshot-id <id>: Rolls back workspace to specified snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ast_patch_guard import ASTPatchGuard
from ci_failure_ingestor import CIFailureIngestor
from core.time_machine.engine import TimeMachineEngine
from hermes_workers import AutomationTesterAgent, DeveloperAgent, WorkerProposal
from llm_provider_adapter import AGENT_SKILL_REGISTRY, AgentRole, HermesLLMAdapter
from qa_critic_reviewer import QACriticAgent
from sandbox_executor import SandboxExecutor
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore
from write_gate_controller import HumanWriteGateController


def print_agents_table() -> None:
    """Print the 8-Agent Role, Tier, Skills & Boundaries table."""
    print("=" * 80)
    print("               HERMES MULTI-AGENT ORCHESTRATOR — 8-AGENT REGISTRY")
    print("=" * 80)

    for idx, (role_name, defn) in enumerate(AGENT_SKILL_REGISTRY.items(), 1):
        print(f"\n[{idx}] {role_name.upper()}")
        print(f"    Tier:             {defn.tier}")
        print(f"    Escalation Path:  {defn.escalation_path}")
        print(f"    Role:             {defn.role_description}")
        print("    Core Skills:")
        for s in defn.skills:
            print(f"      * {s}")
        print(f"    Owned Modules:    {', '.join(defn.owned_modules)}")
        print("    Strict Boundaries:")
        for b in defn.strict_boundaries:
            print(f"      ! {b}")
        print("-" * 80)


def cmd_agents(args: argparse.Namespace) -> int:
    print_agents_table()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    store = SprintStateStore()

    print("=== HERMES SPRINT STATUS ===")
    paused = store.list_paused_sprints("AWAITING_WRITE_GATE")
    print(f"\n[Awaiting Write-Gate Sprints]: {len(paused)}")
    for p in paused:
        print(f"  - Sprint ID: {p['sprint_id']} | Status: {p['status']} | Updated: {time.ctime(p['updated_at'])}")
        for t in p.get("tickets", []):
            print(f"      * Ticket: {t['ticket_id']} - {t['title']} ({t['assigned_tier']})")

    # Audit log tail
    audit_file = workspace / ".rerun_tasks" / "sprint_audit.jsonl"
    if audit_file.is_file():
        lines = audit_file.read_text(encoding="utf-8").splitlines()
        print(f"\n[Recent Audit Log Events] (Last 5 of {len(lines)}):")
        for l in lines[-5:]:
            try:
                rec = json.loads(l)
                print(f"  - [{rec.get('event')}] {time.ctime(rec.get('timestamp', 0))}: {rec.get('data')}")
            except Exception:
                pass
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    story = args.story
    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else []
    auto_approve = args.auto_approve

    print(f"🚀 [Hermes Run] Initializing proactive sprint for story: '{story}'")
    print(f"   Scope: {scope or 'auto-inferred'}")

    ingestor = CIFailureIngestor(workspace)
    story_context = ingestor.ingest_user_story(story, target_scope=scope)

    orchestrator = ScrumMasterOrchestrator(workspace)
    sprint_data = orchestrator.create_sprint_plan({
        "tickets": [
            {
                "ticket_id": "STORY-001",
                "title": f"Implement story: {story[:40]}",
                "complexity": 3,
                "allowed_files": story_context["allowed_files"],
                "acceptance_criteria": story_context["acceptance_criteria"],
            }
        ]
    })
    sprint_id = sprint_data["sprint_id"]
    tickets = sprint_data["tickets"]
    ticket_obj = orchestrator.router.route_ticket(
        ticket_id=tickets[0]["ticket_id"],
        title=tickets[0]["title"],
        complexity=tickets[0]["complexity"],
        allowed_files=tickets[0]["allowed_files"],
        acceptance_criteria=tickets[0]["acceptance_criteria"],
    )

    # DeveloperAgent synthesizes solution
    adapter = HermesLLMAdapter(workspace)
    gate_controller = HumanWriteGateController(workspace, orchestrator.tm, orchestrator.store)

    file_contents = gate_controller.reader.read_allowed_files(ticket_obj.allowed_files)
    proposed_files = adapter.propose_patch(AgentRole.DEVELOPER_AGENT, ticket_obj, ticket_obj.assigned_tier, file_contents)

    proposal = WorkerProposal(
        ticket_id=ticket_obj.ticket_id,
        worker_agent=AgentRole.DEVELOPER_AGENT.value,
        model_tier=ticket_obj.assigned_tier,
        proposed_changes=proposed_files,
    )

    # Review with AST Patch Guard and QA Critic
    ast_res = ASTPatchGuard.analyze(workspace, proposed_files, ticket=ticket_obj)
    if not ast_res["valid"]:
        print(f"❌ AST Patch Guard Rejected: {ast_res['reasons']}")
        return 1

    qa_res = QACriticAgent.review_worker_output(ticket_obj, proposed_files)
    if not qa_res.approved:
        print(f"❌ QA Critic Rejected: {qa_res.rejection_reasons}")
        return 1

    # Stage proposal
    gate_controller.stage_proposal(sprint_id, ticket_obj, proposal)
    print(f"✅ Staged proposal for sprint '{sprint_id}' awaiting write gate.")

    # Approve and Apply
    res = gate_controller.approve_and_apply(sprint_id, auto_approve=auto_approve, interactive=not auto_approve)
    if res["success"]:
        print(f"🎉 Applied changes safely! Pre-apply snapshot: {res['snapshot_id']}")
        return 0
    else:
        print(f"⚠️ Staged: {res.get('status')} - {res.get('message', res.get('error'))}")
        return 0 if res.get("status") == "AWAITING_APPROVAL" else 1


def cmd_heal(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    pytest_cmd = args.pytest_cmd.split()
    auto_approve = args.auto_approve

    print(f"🔍 [Hermes Heal] Running test suite: {' '.join(pytest_cmd)}")
    proc = subprocess.run(pytest_cmd, cwd=str(workspace), capture_output=True, text=True)

    if proc.returncode == 0:
        print("✅ All tests passed! No test healing required.")
        return 0

    print("⚠️ Test failure detected. Initiating Hermes reactive healing...")
    ingestor = CIFailureIngestor(workspace)
    failure_context = ingestor.ingest_failure_output(proc.stdout + "\n" + proc.stderr)

    orchestrator = ScrumMasterOrchestrator(workspace)
    sprint_data = orchestrator.create_sprint_plan({
        "tickets": [
            {
                "ticket_id": "HEAL-001",
                "title": "Repair failing tests and offending application code",
                "complexity": 3,
                "allowed_files": failure_context["allowed_files"],
                "acceptance_criteria": failure_context["acceptance_criteria"],
            }
        ]
    })
    sprint_id = sprint_data["sprint_id"]
    ticket_dict = sprint_data["tickets"][0]
    ticket_obj = orchestrator.router.route_ticket(
        ticket_id=ticket_dict["ticket_id"],
        title=ticket_dict["title"],
        complexity=ticket_dict["complexity"],
        allowed_files=ticket_dict["allowed_files"],
        acceptance_criteria=ticket_dict["acceptance_criteria"],
    )

    adapter = HermesLLMAdapter(workspace)
    gate_controller = HumanWriteGateController(workspace, orchestrator.tm, orchestrator.store)
    file_contents = gate_controller.reader.read_allowed_files(ticket_obj.allowed_files)

    proposed_files = adapter.propose_patch(AgentRole.DEVELOPER_AGENT, ticket_obj, ticket_obj.assigned_tier, file_contents)
    proposal = WorkerProposal(
        ticket_id=ticket_obj.ticket_id,
        worker_agent=AgentRole.DEVELOPER_AGENT.value,
        model_tier=ticket_obj.assigned_tier,
        proposed_changes=proposed_files,
    )

    # Test proposal in isolated sandbox first (repeat=3)
    sandbox = SandboxExecutor(workspace)
    print("🧪 Testing proposed fix in isolated ephemeral sandbox (repeat=3)...")
    multi_res = sandbox.run_tests(pytest_cmd, repeat=3, proposed_changes=proposed_files)

    if multi_res.classification != "PASSED":
        print(f"❌ Sandbox verification failed: {multi_res.classification} ({multi_res.pass_count}/3 passed)")
        return 1

    print("✅ Sandbox tests passed (3/3 green). Staging at write gate...")
    gate_controller.stage_proposal(sprint_id, ticket_obj, proposal)

    res = gate_controller.approve_and_apply(sprint_id, auto_approve=auto_approve, interactive=not auto_approve)
    if res["success"]:
        print(f"🎉 Healed successfully! Snapshot ID: {res['snapshot_id']}")
        return 0
    else:
        print(f"ℹ️ Status: {res.get('status')} - {res.get('message', res.get('error'))}")
        return 0 if res.get("status") == "AWAITING_APPROVAL" else 1


def cmd_approve(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    sprint_id = args.sprint_id
    gate_controller = HumanWriteGateController(workspace)
    res = gate_controller.approve_and_apply(sprint_id, auto_approve=True)
    if res["success"]:
        print(f"✅ Sprint '{sprint_id}' approved and applied! Snapshot: {res['snapshot_id']}")
        return 0
    else:
        print(f"❌ Failed to approve sprint: {res.get('error', res.get('status'))}")
        return 1


def cmd_rollback(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    snapshot_id = args.snapshot_id
    gate_controller = HumanWriteGateController(workspace)
    res = gate_controller.rollback_snapshot(snapshot_id)
    print(f"✅ Workspace restored to snapshot '{snapshot_id}': {res}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes_cli.py",
        description="Hermes Multi-Agent Orchestrator CLI Entrypoint",
    )
    subparsers = parser.add_subparsers(dest="command", help="Hermes command to execute")

    # agents
    subparsers.add_parser("agents", help="List the 8 agent roles, tiers, skills, and safety boundaries")

    # status
    subparsers.add_parser("status", help="Show sprint store status and audit events")

    # run
    run_p = subparsers.add_parser("run", help="Run proactive sprint for a story")
    run_p.add_argument("--story", required=True, help="User story or requirement description")
    run_p.add_argument("--scope", default="", help="Comma-separated allowed files scope")
    run_p.add_argument("--auto-approve", action="store_true", help="Auto-approve without CLI prompt")

    # heal
    heal_p = subparsers.add_parser("heal", help="Triage and heal failing pytest tests")
    heal_p.add_argument("--pytest-cmd", default="pytest -q", help="Test command to run")
    heal_p.add_argument("--auto-approve", action="store_true", help="Auto-approve verified patch")

    # approve
    app_p = subparsers.add_parser("approve", help="Approve paused sprint at write-gate")
    app_p.add_argument("--sprint-id", required=True, help="Sprint ID to approve")

    # rollback
    rb_p = subparsers.add_parser("rollback", help="Restore workspace to a snapshot")
    rb_p.add_argument("--snapshot-id", required=True, help="Snapshot ID to restore")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "agents": cmd_agents,
        "status": cmd_status,
        "run": cmd_run,
        "heal": cmd_heal,
        "approve": cmd_approve,
        "rollback": cmd_rollback,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
