"""
Policy-as-Code Governance Engine & FinOps Circuit Breaker
Owner: ScrumMasterOrchestrator & SecurityBlastRadiusAgent
Phase: Option 5 (InfoSec, AI Governance & FinOps)

Enforces repository boundaries and budget limits defined in .hermes.yml:
1. Most-Restrictive-Wins Resolution:
   Evaluates all touched files where TRIAGE_ONLY > SHADOW_SUGGEST > HEAL.
2. Path Traversal Hardening:
   Normalizes paths (posixpath.normpath) to prevent ../ bypasses of no_heal_zones.
3. Zero-Dependency YAML/JSON Config Loader:
   Safe PyYAML loader with zero-dependency fallback for Python 3.10 environments.
4. FinOps Circuit Breakers:
   Enforces token and spend caps per PR and per day with graceful degradation (FINOPS_CIRCUIT_OPEN).
"""

from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class PolicyEvaluationResult:
    """Outcome of policy-as-code boundary check."""
    allowed: bool
    resolved_mode: str  # "HEAL", "SHADOW_SUGGEST", "TRIAGE_ONLY"
    violated_zones: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    is_finops_open: bool = False
    finops_reason: str = ""

    @property
    def is_allowed(self) -> bool:
        return self.allowed

    @property
    def blocked_files(self) -> List[str]:
        return self.violated_zones

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "resolved_mode": self.resolved_mode,
            "violated_zones": self.violated_zones,
            "reasons": self.reasons,
            "is_finops_open": self.is_finops_open,
            "finops_reason": self.finops_reason,
        }


class PolicyEngine:
    """Evaluates .hermes.yml governance rules and FinOps circuit breakers."""

    # Mode restriction precedence
    MODE_PRECEDENCE = {
        "TRIAGE_ONLY": 3,
        "SHADOW_SUGGEST": 2,
        "HEAL": 1,
    }

    DEFAULT_POLICY: Dict[str, Any] = {
        "version": 1,
        "governance": {
            "no_heal_zones": [
                "src/auth/**",
                "src/billing/**",
                "src/crypto/**",
                "**/auth/**",
                "**/billing/**",
            ],
            "mode_overrides": {},
            "require_oidc": False,
        },
        "finops": {
            "max_tokens_per_pr": 50000,
            "max_usd_per_pr": 10.0,
            "max_usd_per_day": 50.0,
            "max_heals_per_sprint": 5,
        },
    }

    def __init__(
        self,
        workspace_root: Optional[Path | str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.config = config or self.load_config(self.workspace_root)

        # In-memory FinOps ledger
        self.pr_token_usage: Dict[str, int] = {}
        self.pr_spend_usd: Dict[str, float] = {}
        self.daily_spend_usd: float = 0.0

    @classmethod
    def normalize_path(cls, file_path: str) -> str:
        """Canonicalize path and eliminate path traversal vulnerabilities (e.g. tests/../src/auth)."""
        clean = file_path.replace("\\", "/").strip()
        # posixpath.normpath resolves '.' and '..'
        normalized = posixpath.normpath(clean)
        # Strip leading slashes
        normalized = normalized.lstrip("/")
        return normalized

    @classmethod
    def load_config(cls, workspace_root: Path) -> Dict[str, Any]:
        """Load .hermes.yml, .hermes.json, or return DEFAULT_POLICY."""
        yml_path = workspace_root / ".hermes.yml"
        yaml_path = workspace_root / ".hermes.yaml"
        json_path = workspace_root / ".hermes.json"

        target_file = None
        for p in (yml_path, yaml_path, json_path):
            if p.is_file():
                target_file = p
                break

        if not target_file:
            return cls.DEFAULT_POLICY

        try:
            content = target_file.read_text(encoding="utf-8")
            if target_file.suffix == ".json":
                return json.loads(content)

            # Attempt PyYAML if available
            try:
                import yaml
                loaded = yaml.safe_load(content)
                if isinstance(loaded, dict):
                    return loaded
            except ImportError:
                pass

            # Zero-dependency subset YAML parser fallback
            return cls._parse_simple_yaml(content)
        except Exception:
            return cls.DEFAULT_POLICY

    @classmethod
    def _parse_simple_yaml(cls, text: str) -> Dict[str, Any]:
        """Minimal fallback YAML parser for standard key-value, list, and nested block structures."""
        result: Dict[str, Any] = {}
        current_section = result
        current_key = None
        section_stack: List[Tuple[int, Dict[str, Any]]] = [(0, result)]

        lines = text.splitlines()
        for line in lines:
            line_str = line.split("#")[0].rstrip()
            if not line_str.strip():
                continue

            indent = len(line_str) - len(line_str.lstrip())
            stripped = line_str.strip()

            # Adjust stack by indent
            while len(section_stack) > 1 and indent <= section_stack[-1][0]:
                section_stack.pop()
            current_dict = section_stack[-1][1]

            # List item
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip("\"'")
                if not isinstance(current_dict, list):
                    if len(section_stack) > 1:
                        parent_dict = section_stack[-2][1]
                        if current_key and parent_dict.get(current_key) is current_dict:
                            new_list: List[Any] = []
                            parent_dict[current_key] = new_list
                            section_stack[-1] = (section_stack[-1][0], new_list)
                            current_dict = new_list
                if isinstance(current_dict, list):
                    current_dict.append(val)
                elif current_key and isinstance(current_dict.get(current_key), list):
                    current_dict[current_key].append(val)
                continue

            # Key-value or block
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                key = k.strip()
                val_str = v.strip().strip("\"'")

                if not val_str:
                    # New nested block or list
                    new_dict: Dict[str, Any] = {}
                    current_dict[key] = new_dict
                    section_stack.append((indent, new_dict))
                    current_key = key
                else:
                    # Scalar value conversion
                    if val_str.lower() == "true":
                        val: Any = True
                    elif val_str.lower() == "false":
                        val = False
                    else:
                        try:
                            val = int(val_str)
                        except ValueError:
                            try:
                                val = float(val_str)
                            except ValueError:
                                val = val_str
                    current_dict[key] = val
                    current_key = key

        return result if result else cls.DEFAULT_POLICY

    # -------------------------------------------------------------------------
    # Policy Resolution
    # -------------------------------------------------------------------------

    def evaluate_file_paths(
        self,
        file_paths: List[str],
        requested_mode: str = "HEAL",
    ) -> PolicyEvaluationResult:
        """Resolve policy boundaries across all affected file paths using Most-Restrictive-Wins."""
        gov = self.config.get("governance", {})
        no_heal_zones: List[str] = gov.get("no_heal_zones", [])
        mode_overrides: Dict[str, str] = gov.get("mode_overrides", {})

        violated_zones: List[str] = []
        reasons: List[str] = []
        resolved_level = self.MODE_PRECEDENCE.get(requested_mode.upper(), 1)
        final_mode = requested_mode.upper()

        for fp in file_paths:
            norm = self.normalize_path(fp)

            # 1. Reject escape traversal
            if norm.startswith("..") or "/../" in norm:
                violated_zones.append(fp)
                reasons.append(f"Illegal path traversal detected in file path: '{fp}'")
                final_mode = "TRIAGE_ONLY"
                resolved_level = 3
                continue

            # 2. Check no_heal_zones
            for zone in no_heal_zones:
                clean_zone = zone.replace("\\", "/").lstrip("/")
                base_zone = clean_zone.rstrip("*").rstrip("/")
                if (
                    fnmatch.fnmatch(norm, clean_zone)
                    or fnmatch.fnmatch(norm, f"*/{clean_zone}")
                    or norm == base_zone
                    or norm.startswith(f"{base_zone}/")
                ):
                    violated_zones.append(fp)
                    reasons.append(f"File '{fp}' is in protected no-heal zone '{zone}'. Forcing TRIAGE_ONLY.")
                    final_mode = "TRIAGE_ONLY"
                    resolved_level = 3
                    break

            # 3. Check mode_overrides if not already locked to TRIAGE_ONLY
            if resolved_level < 3:
                for pattern, override_mode in mode_overrides.items():
                    clean_pattern = pattern.replace("\\", "/").lstrip("/")
                    if fnmatch.fnmatch(norm, clean_pattern) or fnmatch.fnmatch(norm, f"*/{clean_pattern}"):
                        override_level = self.MODE_PRECEDENCE.get(override_mode.upper(), 1)
                        if override_level > resolved_level:
                            resolved_level = override_level
                            final_mode = override_mode.upper()
                            reasons.append(f"File '{fp}' matches override '{pattern}' -> escalating to {final_mode}")

        is_allowed = (final_mode != "TRIAGE_ONLY")
        return PolicyEvaluationResult(
            allowed=is_allowed,
            resolved_mode=final_mode,
            violated_zones=violated_zones,
            reasons=reasons,
        )

    # -------------------------------------------------------------------------
    # FinOps Circuit Breaker
    # -------------------------------------------------------------------------

    def record_usage(self, pr_id: str, tokens: int, cost_usd: float) -> None:
        """Record token and dollar spend for a PR."""
        self.pr_token_usage[pr_id] = self.pr_token_usage.get(pr_id, 0) + tokens
        self.pr_spend_usd[pr_id] = self.pr_spend_usd.get(pr_id, 0.0) + cost_usd
        self.daily_spend_usd += cost_usd

    def check_finops_limits(self, pr_id: str, estimated_tokens: int = 0) -> Tuple[bool, str]:
        """Check if current or projected spend exceeds FinOps limits.
        
        Returns:
            Tuple[bool, str]: (is_circuit_open, reason)
        """
        finops = self.config.get("finops", {})
        max_tokens_pr = finops.get("max_tokens_per_pr", 50000)
        max_usd_pr = finops.get("max_usd_per_pr", 10.0)
        max_usd_day = finops.get("max_usd_per_day", 50.0)

        current_tokens = self.pr_token_usage.get(pr_id, 0) + estimated_tokens
        current_usd = self.pr_spend_usd.get(pr_id, 0.0)

        if current_tokens > max_tokens_pr:
            return True, f"FINOPS_CIRCUIT_OPEN: PR token usage ({current_tokens}) exceeds max_tokens_per_pr ({max_tokens_pr})"

        if current_usd > max_usd_pr:
            return True, f"FINOPS_CIRCUIT_OPEN: PR spend (${round(current_usd, 2)}) exceeds max_usd_per_pr (${max_usd_pr})"

        if self.daily_spend_usd > max_usd_day:
            return True, f"FINOPS_CIRCUIT_OPEN: Daily spend (${round(self.daily_spend_usd, 2)}) exceeds max_usd_per_day (${max_usd_day})"

        return False, ""

    def is_oidc_required(self) -> bool:
        """Check if policy mandates strict cloud OIDC authentication."""
        return bool(self.config.get("governance", {}).get("require_oidc", False))

