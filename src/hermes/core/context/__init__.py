"""
Billion-Context / Active Context Pruning (ACP) Engine
Hierarchical multi-generational context compression (LSM over prose) for long-running AI agent sessions.
"""

from core.context.active_context_pruner import (
    BillionContextManager,
    ContextBlock,
    estimate_tokens,
    prune_dom,
    prune_logs,
    prune_traceback,
)
from core.context.ticket_hydrator import (
    HydratedTicketContext,
    TicketContextHydrator,
)

__all__ = [
    "BillionContextManager",
    "ContextBlock",
    "estimate_tokens",
    "prune_dom",
    "prune_logs",
    "prune_traceback",
    "TicketContextHydrator",
    "HydratedTicketContext",
]

