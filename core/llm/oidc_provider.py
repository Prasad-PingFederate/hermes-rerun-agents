"""
Cloud OIDC & Zero-Static-Key Provider Router
Owner: LLMProviderAdapter & ScrumMasterOrchestrator
Phase: Option 5 (InfoSec, AI Governance & FinOps)

Enables enterprise zero-static-key deployments via GitHub Actions OIDC and Workload Identity:
1. Federated Credential Chain:
   - AWS Bedrock: AWS_ROLE_ARN + AWS_WEB_IDENTITY_TOKEN_FILE / ACTIONS_ID_TOKEN_REQUEST_URL
   - Azure OpenAI: AZURE_CLIENT_ID + AZURE_TENANT_ID + AZURE_FEDERATED_TOKEN_FILE
   - Google Vertex AI: GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_OIDC_TOKEN
   - Air-Gapped VPC Gateway: HERMES_LLM_BASE_URL (vLLM / Ollama / local proxy)
2. Strict CISO Mode (require_oidc: true):
   Enforces that no static keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.) are accepted in regulated repos.

Zero external dependencies (uses standard library: os, urllib.request, json, typing).
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class StaticApiKeyForbiddenError(PermissionError):
    """Raised when static API keys are used in a repository configured with require_oidc: true."""
    pass


@dataclass
class FederatedCredentials:
    """Discovered ambient cloud OIDC or workload identity credentials."""
    provider: str  # "AWS_BEDROCK", "AZURE_OPENAI", "VERTEX_AI", "AIRGAPPED_VPC", "STATIC_API_KEY", "DETERMINISTIC_LOCAL"
    is_federated: bool
    identity_ref: str
    base_url: Optional[str] = None
    token_preview: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class OIDCProviderRouter:
    """Discovers and validates ambient cloud OIDC federation tokens across providers."""

    STATIC_KEY_ENV_VARS = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    ]

    @classmethod
    def resolve_credentials(
        cls,
        require_oidc: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> FederatedCredentials:
        """Resolve ambient cloud credentials and enforce require_oidc policy."""
        environ = env if env is not None else os.environ

        # 1. Air-Gapped Internal VPC Gateway (vLLM, Ollama, Internal Proxy)
        vpc_base = environ.get("HERMES_LLM_BASE_URL")
        if vpc_base:
            return FederatedCredentials(
                provider="AIRGAPPED_VPC",
                is_federated=True,
                identity_ref=vpc_base,
                base_url=vpc_base,
                metadata={"type": "on_prem_or_vpc_gateway"},
            )

        # 2. AWS Bedrock Workload Identity (IAM Roles for Service Accounts / GHA OIDC)
        aws_role = environ.get("AWS_ROLE_ARN")
        aws_token_file = environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")
        gha_token_url = environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")

        if aws_role and (aws_token_file or gha_token_url):
            token_sample = f"token_file:{Path(aws_token_file).name}" if aws_token_file else "gha_oidc_active"
            return FederatedCredentials(
                provider="AWS_BEDROCK",
                is_federated=True,
                identity_ref=aws_role,
                token_preview=token_sample,
                metadata={
                    "role_arn": aws_role,
                    "web_identity_token_file": aws_token_file,
                    "gha_oidc_url": gha_token_url,
                },
            )

        # 3. Azure OpenAI Workload Identity Federation
        azure_client_id = environ.get("AZURE_CLIENT_ID")
        azure_tenant_id = environ.get("AZURE_TENANT_ID")
        azure_fed_file = environ.get("AZURE_FEDERATED_TOKEN_FILE")

        if azure_client_id and azure_tenant_id and azure_fed_file:
            return FederatedCredentials(
                provider="AZURE_OPENAI",
                is_federated=True,
                identity_ref=f"azure://{azure_tenant_id}/{azure_client_id}",
                token_preview=f"token_file:{Path(azure_fed_file).name}",
                metadata={
                    "client_id": azure_client_id,
                    "tenant_id": azure_tenant_id,
                    "federated_token_file": azure_fed_file,
                },
            )

        # 4. Google Vertex AI Workload Identity Federation
        gcp_creds_file = environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        gcp_token = environ.get("GOOGLE_OIDC_TOKEN")
        if gcp_creds_file or gcp_token:
            id_ref = gcp_creds_file or "gcp_oidc_token"
            return FederatedCredentials(
                provider="VERTEX_AI",
                is_federated=True,
                identity_ref=id_ref,
                token_preview="gcp_workload_identity",
                metadata={"credentials_file": gcp_creds_file},
            )

        # 5. Check for Static API Keys
        active_static_keys = [k for k in cls.STATIC_KEY_ENV_VARS if environ.get(k)]
        if active_static_keys:
            if require_oidc:
                raise StaticApiKeyForbiddenError(
                    f"STATIC_API_KEY_FORBIDDEN: Repository policy (.hermes.yml) mandates strict OIDC federation "
                    f"(require_oidc: true). Found prohibited static key(s): {', '.join(active_static_keys)}. "
                    "Configure AWS Bedrock, Azure Workload Identity, or Vertex AI OIDC instead."
                )

            first_key = active_static_keys[0]
            val = environ.get(first_key, "")
            preview = f"{val[:6]}...{val[-4:]}" if len(val) > 10 else "***"
            return FederatedCredentials(
                provider="STATIC_API_KEY",
                is_federated=False,
                identity_ref=first_key,
                token_preview=preview,
                metadata={"active_keys": active_static_keys},
            )

        # 6. Default: Deterministic Local / Zero-API-Key Engine
        return FederatedCredentials(
            provider="DETERMINISTIC_LOCAL",
            is_federated=True,
            identity_ref="hermes://local/deterministic_engine",
            metadata={"description": "Standard zero-API-key deterministic fallback"},
        )

