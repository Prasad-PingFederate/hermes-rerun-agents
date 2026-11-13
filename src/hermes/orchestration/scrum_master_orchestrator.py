"""
Scrum Master Orchestrator facade for hermes.orchestration package.
Owner: ScrumMasterOrchestrator, TIER_1
"""

from __future__ import annotations

import scrum_master_orchestrator as _smo

# Re-export singleton class definition to avoid AST duplicate class violations
ScrumMasterOrchestrator = _smo.ScrumMasterOrchestrator

__all__ = ["ScrumMasterOrchestrator"]
