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
from llm_provider_adapter import (
    AGENT_SKILL_REGISTRY,
    ORDERED_PROVIDERS,
    PROVIDERS_CONFIG,
    ROLE_CALLS_LLM,
    AgentRole,
    HermesLLMAdapter,
    resolve_model_for_call,
    resolve_provider,
)
from qa_critic_reviewer import QACriticAgent
from sandbox_executor import SandboxExecutor
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore
from write_gate_controller import HumanWriteGateController


def print_agents_table() -> None:
    """Print the 8-Agent Role, Tier, Skills & Boundaries table with resolved provider and model."""
    print("=" * 80)
    print("               HERMES MULTI-AGENT ORCHESTRATOR — 8-AGENT REGISTRY")
    print("=" * 80)

    for idx, (role_name, defn) in enumerate(AGENT_SKILL_REGISTRY.items(), 1):
        calls_llm = ROLE_CALLS_LLM.get(role_name, False)
        prov = resolve_provider(role_name)
        if calls_llm and prov != "none":
            try:
                resolved_prov, resolved_model = resolve_model_for_call(role_name, defn.tier, prov)
            except Exception:
                resolved_prov, resolved_model = prov, "unconfigured"
        elif calls_llm:
            resolved_prov = "none"
            resolved_model = "LocalHeuristicEngine"
        else:
            resolved_prov = "none"
            resolved_model = "No LLM (Deterministic Code / Python Gate)"

        print(f"\n[{idx}] {role_name.upper()}")
        print(f"    Tier:             {defn.tier}")
        print(f"    Calls LLM:        {calls_llm}")
        print(f"    Provider:         {resolved_prov}")
        print(f"    Model:            {resolved_model}")
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


def cmd_providers(args: argparse.Namespace) -> int:
    active = resolve_provider()
    print("=" * 105)
    print("                 HERMES MULTI-AGENT ORCHESTRATOR — LLM PROVIDER REGISTRY")
    print("=" * 105)
    print(f"{'PROVIDER':<18} | {'WIRE':<12} | {'BASE URL ENV / DEFAULT':<35} | {'KEY ENV':<20} | {'MODEL ENV'}")
    print("-" * 105)
    for p in ORDERED_PROVIDERS:
        cfg = PROVIDERS_CONFIG[p]
        wire = cfg["wire"]
        base = cfg.get("base_url_env") or cfg.get("default_base_url") or "custom"
        key = cfg.get("key_env") or "none"
        model = cfg.get("model_env") or "none"
        marker = " [*ACTIVE*]" if p == active else ""
        print(f"{p:<18} | {wire:<12} | {base:<35} | {key:<20} | {model}{marker}")
    print("-" * 105)
    print(f"\nActive / Resolved Provider: {active.upper() if active != 'none' else 'NONE (LocalHeuristicEngine offline)'}")
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
    orchestrator = ScrumMasterOrchestrator(workspace)
    res = orchestrator.run_sprint(
        mode="story",
        story=story,
        scope=scope,
        auto_approve=auto_approve,
    )
    if res.get("status") in ("APPLIED", "COMPLETED") or res.get("success"):
        print(f"🎉 Applied changes safely! Snapshot: {res.get('snapshot_id')}")
        return 0
    elif res.get("status") == "AWAITING_APPROVAL":
        print(f"⚠️ Staged proposal awaiting approval. Proposal ID: {res.get('proposal_id')}")
        print(res.get("diff", ""))
        return 0
    else:
        print(f"❌ Sprint failed: {res.get('error', res.get('status'))}")
        return 1


def cmd_heal(args: argparse.Namespace) -> int:
    workspace = Path.cwd().resolve()
    pytest_cmd = args.pytest_cmd.split() if args.pytest_cmd else ["pytest", "-q"]
    auto_approve = args.auto_approve

    print(f"🔍 [Hermes Heal] Running test suite: {' '.join(pytest_cmd)}")
    orchestrator = ScrumMasterOrchestrator(workspace)
    res = orchestrator.run_sprint(
        mode="heal",
        pytest_cmd=pytest_cmd,
        auto_approve=auto_approve,
    )
    if res.get("status") in ("APPLIED", "COMPLETED") or res.get("success"):
        print(f"🎉 Heal complete and verified! Snapshot: {res.get('snapshot_id')}")
        return 0
    elif res.get("status") == "PASSED":
        print("✅ All tests passed! No test healing required.")
        return 0
    elif res.get("status") == "ENVIRONMENT_NOISE":
        print(f"⚠️ {res.get('message', 'Environment noise detected')}")
        return 0
    elif res.get("status") == "AWAITING_APPROVAL":
        print(f"⚠️ Staged heal proposal awaiting approval. Proposal ID: {res.get('proposal_id')}")
        print(res.get("diff", ""))
        return 0
    else:
        print(f"❌ Heal failed: {res.get('error', res.get('status'))}")
        return 1


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

    # providers
    subparsers.add_parser("providers", help="List supported LLM providers and show active provider")

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
        "providers": cmd_providers,
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

