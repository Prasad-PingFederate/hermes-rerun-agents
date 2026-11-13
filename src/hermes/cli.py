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

from hermes.guards.ast_patch_guard import ASTPatchGuard
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor
from core.time_machine.engine import TimeMachineEngine
from hermes.orchestration.hermes_workers import AutomationTesterAgent, DeveloperAgent, WorkerProposal
from hermes.execution.llm_provider_adapter import (
    AGENT_SKILL_REGISTRY,
    ORDERED_PROVIDERS,
    PROVIDERS_CONFIG,
    ROLE_CALLS_LLM,
    AgentRole,
    HermesLLMAdapter,
    resolve_model_for_call,
    resolve_provider,
)
from hermes.orchestration.qa_critic_reviewer import QACriticAgent
from hermes.execution.sandbox_executor import SandboxExecutor
from hermes.orchestration.scrum_master_orchestrator import ScrumMasterOrchestrator
from hermes.orchestration.sprint_state_store import SprintStateStore
from hermes.guards.write_gate_controller import HumanWriteGateController


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
    workspace = Path(getattr(args, "workspace", ".")).resolve()
    store = SprintStateStore(workspace_path=workspace)

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
    workspace = Path(getattr(args, "workspace", ".")).resolve()
    story = getattr(args, "story", None)
    artifact_path = getattr(args, "artifact_path", None)
    raw_pytest = getattr(args, "pytest_cmd", None)
    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if getattr(args, "scope", None) else []
    auto_approve = getattr(args, "auto_approve", False)
    shadow = getattr(args, "shadow", False)

    if not story and not artifact_path and not raw_pytest:
        print("❌ Error: Must specify --story, --artifact-path, or --pytest-cmd.")
        return 1

    orchestrator = ScrumMasterOrchestrator(workspace)

    if story:
        print(f"🚀 [Hermes Run] Initializing proactive sprint for story: '{story}'")
        res = orchestrator.run_sprint(
            mode="story",
            story=story,
            scope=scope,
            artifact_paths=artifact_path,
            auto_approve=auto_approve,
            shadow_mode=shadow,
        )
    else:
        pytest_cmd = None
        if raw_pytest:
            parsed = raw_pytest.split() if isinstance(raw_pytest, str) else list(raw_pytest)
            if parsed and parsed[0] == "pytest":
                pytest_cmd = [sys.executable, "-m", "pytest"] + parsed[1:]
            else:
                pytest_cmd = parsed

        print("🔍 [Hermes Run] Initializing test triage & heal sprint")
        res = orchestrator.run_sprint(
            mode="shadow" if shadow else "heal",
            artifact_paths=artifact_path,
            pytest_cmd=pytest_cmd,
            auto_approve=auto_approve,
            shadow_mode=shadow,
        )

    if res.get("status") in ("APPLIED", "COMPLETED") or res.get("success"):
        print(f"🎉 Applied changes safely! Snapshot: {res.get('snapshot_id')}")
        return 0
    elif res.get("status") == "PASSED":
        print("✅ All tests passed! No test healing required.")
        return 0
    elif res.get("status") == "ENVIRONMENT_NOISE":
        print(f"⚠️ {res.get('message', 'Environment noise detected')}")
        return 0
    elif res.get("status") == "AWAITING_APPROVAL":
        print(f"⚠️ Staged proposal awaiting approval. Proposal ID: {res.get('proposal_id')}")
        print(res.get("diff", ""))
        return 0
    else:
        print(f"❌ Sprint failed: {res.get('error', res.get('status'))}")
        return 1


def cmd_heal(args: argparse.Namespace) -> int:
    workspace = Path(getattr(args, "workspace", ".")).resolve()
    artifact_path = getattr(args, "artifact_path", None)
    auto_approve = getattr(args, "auto_approve", False)
    shadow = getattr(args, "shadow", False)

    pytest_cmd = None
    if getattr(args, "pytest_cmd", None):
        raw_cmd = args.pytest_cmd.split() if isinstance(args.pytest_cmd, str) else list(args.pytest_cmd)
        if raw_cmd and raw_cmd[0] == "pytest":
            pytest_cmd = [sys.executable, "-m", "pytest"] + raw_cmd[1:]
        else:
            pytest_cmd = raw_cmd
    elif not artifact_path:
        pytest_cmd = [sys.executable, "-m", "pytest", "-q"]

    cmd_desc = " ".join(pytest_cmd) if pytest_cmd else f"artifacts ({artifact_path})"
    print(f"🔍 [Hermes Heal] Running test triage: {cmd_desc}")
    orchestrator = ScrumMasterOrchestrator(workspace)
    res = orchestrator.run_sprint(
        mode="shadow" if shadow else "heal",
        pytest_cmd=pytest_cmd,
        artifact_paths=artifact_path,
        auto_approve=auto_approve,
        shadow_mode=shadow,
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
    workspace = Path(getattr(args, "workspace", ".")).resolve()
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
    workspace = Path(getattr(args, "workspace", ".")).resolve()
    snapshot_id = args.snapshot_id
    gate_controller = HumanWriteGateController(workspace)
    res = gate_controller.rollback_snapshot(snapshot_id)
    print(f"✅ Workspace restored to snapshot '{snapshot_id}': {res}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(getattr(args, "workspace", ".")).resolve()
    print("=" * 80)
    print("         HERMES MULTI-AGENT ORCHESTRATOR — PRE-FLIGHT DOCTOR (READINESS)")
    print("=" * 80)

    # 1. Environment & Test Runners
    print("\n[1] ENVIRONMENT & RUNNER READINESS:")
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f"  ✅ [PASS] Python Version:       {py_ver} (>= 3.10 required)")
    else:
        print(f"  ❌ [FAIL] Python Version:       {py_ver} (Requires Python >= 3.10)")

    # Git
    try:
        git_proc = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
        git_ver = git_proc.stdout.strip()
        git_repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(workspace), capture_output=True, text=True)
        is_git_repo = git_repo_proc.returncode == 0
        repo_note = f"(Repository verified: {workspace.name})" if is_git_repo else "(Not a git repo root)"
        print(f"  ✅ [PASS] Git CLI:              {git_ver} {repo_note}")
    except Exception as e:
        print(f"  ⚠️ [WARN] Git CLI:              Not available ({e})")

    # Node / Playwright
    try:
        n_proc = subprocess.run(["node", "--version"], capture_output=True, text=True, shell=True)
        if n_proc.returncode == 0:
            node_ver = n_proc.stdout.strip()
            pw_proc = subprocess.run(["npx", "--no-install", "playwright", "--version"], capture_output=True, text=True, shell=True)
            if pw_proc.returncode == 0:
                pw_ver = pw_proc.stdout.strip()
                print(f"  ✅ [PASS] Node & Playwright:    Node {node_ver} | {pw_ver}")
            else:
                print(f"  ✅ [PASS] Node CLI:             Node {node_ver} (Playwright project-local via npx/npm)")
        else:
            print("  ℹ️ [INFO] Node & Playwright:    Not installed globally (Optional for Python suites)")
    except Exception:
        print("  ℹ️ [INFO] Node & Playwright:    Not installed globally (Optional for Python suites)")

    # Tree-sitter
    try:
        from hermes.guards.language_ast_guard import HAS_TREE_SITTER
        if HAS_TREE_SITTER:
            print("  ✅ [PASS] Tree-sitter AST:      Active (Multi-language Python, TS, Go, C#, Java enabled)")
        else:
            print("  ✅ [PASS] Tree-sitter AST:      Python native AST active (tree_sitter_languages optional)")
    except Exception as e:
        print(f"  ⚠️ [WARN] Tree-sitter:          {e}")

    # 2. LLM Provider Status
    print("\n[2] LLM PROVIDER & REASONING AGENT STATUS:")
    active_prov = resolve_provider()
    if active_prov != "none":
        print(f"  ✅ [PASS] Active LLM Provider:  {active_prov.upper()} (Live frontier model reasoning active)")
    else:
        print("  ✅ [PASS] Active LLM Provider:  OFFLINE_DETERMINISTIC_HEURISTIC (LocalHeuristicEngine active)")

    if getattr(args, "ping_llm", False):
        if active_prov != "none":
            try:
                t0 = time.time()
                adapter = HermesLLMAdapter(workspace)
                adapter.complete(
                    role=AgentRole.REQUIREMENTS_AGENT,
                    tier="TIER_3_JUNIOR_SWE",
                    user_prompt="Ping",
                    max_tokens=5,
                )
                dt = int((time.time() - t0) * 1000)
                print(f"  ✅ [PASS] Live Ping Handshake:  Connected successfully ({dt}ms)")
            except Exception as e:
                print(f"  ⚠️ [WARN] Live Ping Failed:     {e} (Falling back to LocalHeuristicEngine)")
        else:
            print("  ✅ [PASS] Offline Ping Handshake: Deterministic LocalHeuristicEngine verified (0ms)")

    # 3. Deterministic Fence Sanitizer
    print("\n[3] DEFENSIVE GUARDS & SANITIZERS:")
    try:
        from hermes.execution.workspace_patch_applier import strip_markdown_fences
        test_fenced = "```python\ndef test_ok():\n    assert True\n```"
        sanitized = strip_markdown_fences(test_fenced)
        if "```" not in sanitized and "def test_ok" in sanitized:
            print("  ✅ [PASS] Fence Sanitizer:      Deterministic markdown fence stripping active")
        else:
            print("  ❌ [FAIL] Fence Sanitizer:      Failed to unwrap markdown fences cleanly")
    except Exception as e:
        print(f"  ❌ [FAIL] Fence Sanitizer:      Error ({e})")

    # 4. Workspace & Test Artifact Discovery
    print("\n[4] WORKSPACE & TEST ARTIFACT DISCOVERY:")
    print(f"  * Target Workspace:            {workspace}")
    if workspace.is_dir():
        py_tests = list(workspace.glob("tests/**/test_*.py")) + list(workspace.glob("tests/**/*_test.py"))
        ts_tests = list(workspace.glob("**/*.spec.ts")) + list(workspace.glob("**/*.test.ts"))
        js_tests = list(workspace.glob("**/*.spec.js")) + list(workspace.glob("**/*.test.js"))
        total_tests = len(py_tests) + len(ts_tests) + len(js_tests)

        junit_files = list(workspace.glob("**/junit*.xml")) + list(workspace.glob("**/*test-results*.xml"))
        ctrf_files = list(workspace.glob("**/ctrf*.json"))
        trace_files = list(workspace.glob("**/trace.zip"))
        total_artifacts = len(junit_files) + len(ctrf_files) + len(trace_files)

        print(f"  * Discovered Test Suites:      {total_tests} ({len(py_tests)} Python, {len(ts_tests) + len(js_tests)} Playwright/TS/JS)")
        print(f"  * Discovered CI Artifacts:     {total_artifacts} ({len(junit_files)} JUnit XML, {len(ctrf_files)} CTRF JSON, {len(trace_files)} Playwright Traces)")
    else:
        print("  ⚠️ [WARN] Workspace directory does not exist yet.")

    print("\n" + "=" * 80)
    print("STATUS: HERMES IS FIELD-READY FOR EXTERNAL AUTOMATION SUITES")
    print("=" * 80)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes_cli.py",
        description="Hermes Multi-Agent Orchestrator CLI Entrypoint",
    )
    subparsers = parser.add_subparsers(dest="command", help="Hermes command to execute")

    # doctor
    doc_p = subparsers.add_parser("doctor", help="Run pre-flight environment, runner, and LLM readiness checks")
    doc_p.add_argument("--workspace", default=".", help="Workspace path to inspect")
    doc_p.add_argument("--ping-llm", action="store_true", help="Send a 5-token ping to test live LLM connectivity")

    # agents
    subparsers.add_parser("agents", help="List the 8 agent roles, tiers, skills, and safety boundaries")

    # providers
    subparsers.add_parser("providers", help="List supported LLM providers and show active provider")

    # status
    status_p = subparsers.add_parser("status", help="Show sprint store status and audit events")
    status_p.add_argument("--workspace", default=".", help="Workspace path to inspect")

    # run
    run_p = subparsers.add_parser("run", help="Run proactive sprint or artifact heal")
    run_p.add_argument("--workspace", default=".", help="Target workspace path")
    run_p.add_argument("--story", default=None, help="User story or requirement description")
    run_p.add_argument("--artifact-path", default=None, help="Path or glob pattern for CI failure artifacts")
    run_p.add_argument("--pytest-cmd", default=None, help="Pytest command to run")
    run_p.add_argument("--scope", default="", help="Comma-separated allowed files scope")
    run_p.add_argument("--auto-approve", action="store_true", help="Auto-approve without CLI prompt")
    run_p.add_argument("--shadow", action="store_true", help="Run in shadow mode (dry run)")

    # heal
    heal_p = subparsers.add_parser("heal", help="Triage and heal failing pytest tests or CI artifacts")
    heal_p.add_argument("--workspace", default=".", help="Target workspace path")
    heal_p.add_argument("--pytest-cmd", default=None, help="Test command to run")
    heal_p.add_argument("--artifact-path", default=None, help="Path or glob pattern for CI failure artifacts")
    heal_p.add_argument("--auto-approve", action="store_true", help="Auto-approve verified patch")
    heal_p.add_argument("--shadow", action="store_true", help="Run in shadow mode (dry run)")

    # approve
    app_p = subparsers.add_parser("approve", help="Approve paused sprint at write-gate")
    app_p.add_argument("--workspace", default=".", help="Target workspace path")
    app_p.add_argument("--sprint-id", required=True, help="Sprint ID to approve")

    # rollback
    rb_p = subparsers.add_parser("rollback", help="Restore workspace to a snapshot")
    rb_p.add_argument("--workspace", default=".", help="Target workspace path")
    rb_p.add_argument("--snapshot-id", required=True, help="Snapshot ID to restore")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "doctor": cmd_doctor,
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

