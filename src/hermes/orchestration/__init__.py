"""
Hermes Sprint Orchestration & Scheduling Subsystem
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ScrumMasterOrchestrator",
    "SprintDAGScheduler",
    "StagedPatchComposer",
    "DependencyCycleError",
    "PatchConflictError",
    "SprintStateStore",
    "AttemptRecord",
    "GitNotesStateBackend",
    "WorkerProposal",
    "AutomationTesterAgent",
    "TestCaseWriterAgent",
    "TestHealerAgent",
    "DeveloperAgent",
    "RequirementsAgent",
    "QACriticAgent",
    "QACriticReview",
    "CriterionVerdict",
    "EscalationPromptBuilder",
]


def __getattr__(name: str) -> Any:
    if name == "ScrumMasterOrchestrator":
        from hermes.orchestration.scrum_master_orchestrator import ScrumMasterOrchestrator
        return ScrumMasterOrchestrator
    if name in ("SprintDAGScheduler", "StagedPatchComposer", "DependencyCycleError", "PatchConflictError"):
        import hermes.orchestration.sprint_dag_scheduler as sds
        return getattr(sds, name)
    if name in ("SprintStateStore", "AttemptRecord", "GitNotesStateBackend"):
        import hermes.orchestration.sprint_state_store as sss
        return getattr(sss, name)
    if name in ("WorkerProposal", "AutomationTesterAgent", "TestCaseWriterAgent", "TestHealerAgent", "DeveloperAgent", "RequirementsAgent"):
        import hermes.orchestration.hermes_workers as hw
        return getattr(hw, name)
    if name in ("QACriticAgent", "QACriticReview", "CriterionVerdict", "EscalationPromptBuilder"):
        import hermes.orchestration.qa_critic_reviewer as qcr
        return getattr(qcr, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
