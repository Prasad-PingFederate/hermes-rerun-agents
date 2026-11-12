"""
Hierarchical Multi-Model Orchestration: Model Tiers, SubTaskTicket, and Escalation Chain
Deterministic, provider-agnostic multi-model task delegation and auto-escalation.
Zero external dependencies (uses standard library: dataclasses, enum, typing, os).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
