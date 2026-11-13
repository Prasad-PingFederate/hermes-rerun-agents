"""
Core LLM Routing Subsystem
Phase: Option 5 (Cloud OIDC & Zero-Static-Key Router)
"""

from __future__ import annotations

from hermes.core.llm.oidc_provider import (
    OIDCProviderRouter,
    FederatedCredentials,
    StaticApiKeyForbiddenError,
)

__all__ = [
    "OIDCProviderRouter",
    "FederatedCredentials",
    "StaticApiKeyForbiddenError",
]

