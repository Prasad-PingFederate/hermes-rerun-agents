"""
GAP-15: Concrete TimeMachine Snapshot Engine & Human Write-Gate Controller
Owner: ScrumMasterOrchestrator (TIER_1)

Features:
- TimeMachine pre-apply snapshots stored with SHA-256 integrity manifest.
- HumanWriteGateController: Interactive CLI approval ([y/N]), --auto-approve flag,
  and programmatic approve_sprint() / rollback_snapshot().
- Automatic surgical rollback on any post-apply verification failure.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.time_machine.engine import TimeMachineEngine
from hermes_workers import WorkerProposal
from sprint_state_store import SprintStateStore
from workspace_patch_applier import AtomicPatchApplier, UnifiedDiffGenerator, WorkspaceFileReader


class HumanWriteGateController:
    """Controls the final safety write-gate and TimeMachine snapshot lifecycle."""

    def __init__(
        self,
        workspace_path: Optional[Path | str] = None,
        tm_engine: Optional[TimeMachineEngine] = None,
        store: Optional[SprintStateStore] = None,
    ):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()
        self.tm = tm_engine or TimeMachineEngine(self.workspace_path)
        self.store = store or SprintStateStore()
        self.applier = AtomicPatchApplier(self.workspace_path)
        self.reader = WorkspaceFileReader(self.workspace_path)

        # Staged proposals in-memory cache
        self._staged: Dict[str, Dict[str, Any]] = {}

    def stage_proposal(
        self,
        sprint_id: str,
        ticket: Any,
        proposal: WorkerProposal,
    ) -> str:
        """Stage an approved proposal for write-gate review."""
        ticket_id = getattr(ticket, "ticket_id", str(ticket))
        stage_id = f"stage_{ticket_id}_{int(time.time())}"
        staged_data = {
            "stage_id": stage_id,
            "sprint_id": sprint_id,
            "ticket_id": ticket_id,
            "ticket": ticket,
            "proposal": proposal,
            "staged_at": time.time(),
            "status": "AWAITING_WRITE_GATE",
        }
        self._staged[sprint_id] = staged_data
        self._staged[stage_id] = staged_data
        # Persist proposed_changes_json in SQLite store for restart durability
        self.store.stage_proposal_state(
            sprint_id=sprint_id,
            ticket_id=ticket_id,
            proposed_changes=proposal.proposed_changes,
            assigned_tier=proposal.model_tier,
            worker_agent=proposal.worker_agent,
        )
        return stage_id

    def get_staged_proposal(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve staged proposal data for a sprint, falling back to disk store."""
        if sprint_id in self._staged:
            return self._staged[sprint_id]
        for v in self._staged.values():
            if v.get("stage_id") == sprint_id or v.get("sprint_id") == sprint_id:
                return v

        # Check disk store across process restarts
        sprint_data = self.store.load_sprint(sprint_id)
        if sprint_data and sprint_data.get("status") in ("AWAITING_WRITE_GATE", "ACTIVE"):
            tickets = sprint_data.get("tickets", [])
            for t in tickets:
                p_changes = t.get("proposed_changes", {})
                if p_changes:
                    reconstructed = {
                        "stage_id": f"stage_{t.get('ticket_id')}",
                        "sprint_id": sprint_id,
                        "ticket_id": t.get("ticket_id"),
                        "ticket": t,
                        "proposal": WorkerProposal(
                            ticket_id=t.get("ticket_id", ""),
                            worker_agent=t.get("worker_agent", "DeveloperAgent"),
                            model_tier=t.get("assigned_tier", "TIER_3_JUNIOR_SWE"),
                            proposed_changes=p_changes,
                        ),
                        "status": "AWAITING_WRITE_GATE",
                    }
                    self._staged[sprint_id] = reconstructed
                    return reconstructed
        return None

    def approve_proposal(
        self,
        sprint_id: str,
        verification_fn: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Approve staged proposal, create TimeMachine snapshot, write files, and verify."""
        return self.approve_and_apply(
            sprint_id=sprint_id,
            auto_approve=True,
            interactive=False,
            verification_fn=verification_fn,
        )

    def get_diff_summary(self, sprint_id: str) -> str:
        """Generate human-readable unified diff summary for staged proposals."""
        item = self.get_staged_proposal(sprint_id)
        if not item:
            return "No staged proposal found."

        proposal: WorkerProposal = item["proposal"]
        original_files = self.reader.read_allowed_files(list(proposal.proposed_changes.keys()))
        diffs = UnifiedDiffGenerator.generate_multi_diff(original_files, proposal.proposed_changes)

        lines = [f"=== STAGED CHANGES FOR SPRINT {sprint_id} (Ticket {proposal.ticket_id}) ==="]
        for rel_path, diff_text in diffs.items():
            lines.append(f"\n--- File: {rel_path} ---")
            lines.append(diff_text or "(File created or unmodified)")
        return "\n".join(lines)

    def prompt_cli_approval(self, sprint_id: str) -> bool:
        """Prompt interactive user for approval in terminal."""
        diff_summary = self.get_diff_summary(sprint_id)
        print("\n" + diff_summary + "\n")
        try:
            choice = input(f"Apply staged changes for sprint '{sprint_id}'? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def approve_and_apply(
        self,
        sprint_id: str,
        auto_approve: bool = True,
        interactive: bool = False,
        verification_fn: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Approve and apply staged changes with safety snapshotting and automatic rollback."""
        item = self.get_staged_proposal(sprint_id)
        if not item:
            return {"success": False, "error": f"No staged proposal found for sprint '{sprint_id}'"}

        proposal: WorkerProposal = item["proposal"]
        ticket_id = item["ticket_id"]

        # Check approval
        if not auto_approve:
            if interactive:
                approved = self.prompt_cli_approval(sprint_id)
                if not approved:
                    return {"success": False, "status": "REJECTED_BY_USER", "sprint_id": sprint_id}
            else:
                return {
                    "success": False,
                    "status": "AWAITING_APPROVAL",
                    "sprint_id": sprint_id,
                    "message": "Human approval required. Pass auto_approve=True or approve via CLI.",
                }

        # 1. Create pre-apply TimeMachine snapshot (Invariant 5)
        snap_label = f"safety_pre_apply_{ticket_id}_{int(time.time())}"
        snapshot_meta = self.tm.create_snapshot(label=snap_label)
        snapshot_id = getattr(snapshot_meta, "id", None) or (
            snapshot_meta.get("id") if isinstance(snapshot_meta, dict) else str(snapshot_meta)
        )

        files_tracked = getattr(snapshot_meta, "files_tracked", None) or []
        manifest = {f: {} for f in files_tracked} if files_tracked else {}

        self.store.save_snapshot(
            snapshot_id=snapshot_id,
            sprint_id=sprint_id,
            ticket_id=ticket_id,
            label=snap_label,
            manifest=manifest,
        )

        # 2. Atomic File Application
        try:
            applied_files, _ = self.applier.apply_proposal_patches(proposal.proposed_changes)

            # 3. Post-apply verification (if provided)
            if verification_fn:
                verified = verification_fn()
                if not verified:
                    raise RuntimeError("Post-apply verification failed.")

            self.store.update_sprint_status(sprint_id, "COMPLETED")
            item["status"] = "COMPLETED"

            return {
                "success": True,
                "status": "APPLIED",
                "sprint_id": sprint_id,
                "ticket_id": ticket_id,
                "snapshot_id": snapshot_id,
                "applied_files": applied_files,
            }
        except Exception as e:
            # 4. Surgical Automatic Rollback on Error
            rollback_res = self.tm.restore_snapshot(snapshot_id)
            self.store.update_sprint_status(sprint_id, "ROLLED_BACK")
            item["status"] = "ROLLED_BACK"

            return {
                "success": False,
                "status": "ROLLED_BACK",
                "sprint_id": sprint_id,
                "ticket_id": ticket_id,
                "snapshot_id": snapshot_id,
                "error": str(e),
                "rollback_details": rollback_res,
            }

    def rollback_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Restore workspace to specified TimeMachine snapshot."""
        return self.store.rollback_snapshot(snapshot_id, self.tm)

