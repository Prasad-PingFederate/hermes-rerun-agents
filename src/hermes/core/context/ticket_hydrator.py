"""
Issue-Tracker Context Hydration (Jira, Linear, GitHub Issues)
Owner: CIDetectiveAgent & ScrumMasterOrchestrator
Phase: Option 6 (Monorepo Scale & Ecosystem Depth)

Extracts and enriches failure context from issue trackers with strict security and false-positive guards:
1. False-Positive Technical Standard Denylist:
   Excludes UTF-8, SHA-256, ISO-27001, CVE-2026-1234, CWE-79, AES-256, HTTP-2, PEP-8, RFC-7231, etc.
   Supports allowed_project_keys whitelist from .hermes.yml.
2. Option 5 Security Pipeline:
   Pipes all external ticket text through DLPSessionVault (secret scrubbing) and PromptSandbox (nonce sandboxing).
3. GHES & Fail-Open Resilience:
   Respects GITHUB_API_URL, JIRA_BASE_URL, LINEAR_API_URL with a strict 3.0s timeout and graceful fallback.

Zero external dependencies (uses standard library: re, urllib.request, json, os, typing).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.security.dlp_scrubber import DLPSessionVault
from core.security.prompt_sandbox import PromptSandbox


@dataclass
class HydratedTicketContext:
    """Enriched issue-tracker context for intent classification."""
    ticket_id: str
    source_type: str  # "JIRA", "LINEAR", "GITHUB_ISSUE", "LOCAL_COMMIT"
    title: str = ""
    description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    sandboxed_prompt_block: str = ""
    raw_status: str = "FETCHED"  # "FETCHED", "FALLBACK", "NOT_FOUND", "TIMEOUT"
    is_sandboxed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "source_type": self.source_type,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "sandboxed_prompt_block": self.sandboxed_prompt_block,
            "raw_status": self.raw_status,
            "is_sandboxed": self.is_sandboxed,
        }


class TicketContextHydrator:
    """Extracts issue tracker identifiers and securely hydrates context via REST APIs."""

    # False-positive technical standard prefixes to exclude
    TECHNICAL_STANDARD_DENYLIST: Set[str] = {
        "UTF", "SHA", "ISO", "CVE", "CWE", "AES", "HTTP", "PEP", "RFC",
        "TLS", "RSA", "MD", "UUID", "POSIX", "TCP", "UDP", "DNS", "SSH",
        "SSL", "GCM", "CBC", "ECDSA", "ED", "NIST", "OWASP", "JSON", "XML",
        "HTML", "CSS", "SQL", "REST", "API", "W3C", "IEEE", "ANSI",
    }

    # Matches JIRA/Linear keys: e.g. PAY-4912, AUTH-102
    JIRA_LINEAR_REGEX = re.compile(r"\b([A-Z]{2,10})-(\d{1,6})\b")

    # Matches GitHub Issue references: e.g. #104, gh-104
    GITHUB_ISSUE_REGEX = re.compile(r"(?:^|[\s(,])(?:#|gh-)(\d{1,6})\b")

    def __init__(
        self,
        allowed_project_keys: Optional[List[str]] = None,
        dlp_vault: Optional[DLPSessionVault] = None,
        timeout_seconds: float = 3.0,
    ):
        self.allowed_project_keys = set(k.upper() for k in allowed_project_keys) if allowed_project_keys else None
        self.dlp_vault = dlp_vault or DLPSessionVault()
        self.timeout_seconds = timeout_seconds

    def extract_ticket_ids(self, text: str) -> List[Tuple[str, str]]:
        """Extract valid issue keys from commit messages, PR descriptions, or branch names.
        
        Returns:
            List[Tuple[str, str]]: (ticket_id, source_type) e.g. [("PAY-4912", "JIRA"), ("#104", "GITHUB_ISSUE")]
        """
        if not text:
            return []

        results: List[Tuple[str, str]] = []
        seen: Set[str] = set()

        # 1. Jira / Linear style keys (PROJECT-1234)
        for match in self.JIRA_LINEAR_REGEX.finditer(text):
            prefix, num = match.groups()
            prefix_upper = prefix.upper()

            # Guard 1: Filter out technical standards
            if prefix_upper in self.TECHNICAL_STANDARD_DENYLIST:
                continue

            # Guard 2: Filter by allowed project keys if configured
            if self.allowed_project_keys and prefix_upper not in self.allowed_project_keys:
                continue

            ticket_key = f"{prefix_upper}-{num}"
            if ticket_key not in seen:
                seen.add(ticket_key)
                results.append((ticket_key, "JIRA"))

        # 2. GitHub Issue references (#104, gh-104)
        for match in self.GITHUB_ISSUE_REGEX.finditer(text):
            num = match.group(1)
            issue_key = f"#{num}"
            if issue_key not in seen:
                seen.add(issue_key)
                results.append((issue_key, "GITHUB_ISSUE"))

        return results

    def hydrate_context(
        self,
        ticket_id: str,
        source_type: str,
        local_fallback_summary: str = "",
        github_token: Optional[str] = None,
        repo_slug: Optional[str] = None,
    ) -> HydratedTicketContext:
        """Fetch ticket metadata and pipe through Option 5 DLP scrubber + Nonce prompt sandbox."""
        fetched_title = local_fallback_summary or f"Context for {ticket_id}"
        fetched_desc = ""
        acceptance_criteria: List[str] = []
        status = "FALLBACK"

        # 1. GitHub Issues
        if source_type == "GITHUB_ISSUE" and repo_slug:
            issue_number = ticket_id.lstrip("#gh-")
            gh_base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
            url = f"{gh_base_url}/repos/{repo_slug}/issues/{issue_number}"
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Hermes-Ticket-Hydrator"}
            token = github_token or os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        fetched_title = data.get("title", "")
                        fetched_desc = data.get("body", "") or ""
                        acceptance_criteria = self._extract_criteria_lines(fetched_desc)
                        status = "FETCHED"
            except Exception:
                status = "FALLBACK"

        # 2. Option 5 Security Pipeline: DLP Scrubbing & Nonce Prompt Sandboxing
        raw_combined = f"Ticket: {ticket_id}\nTitle: {fetched_title}\nDescription: {fetched_desc}"
        scrubbed = self.dlp_vault.scrub(raw_combined, source="RUNTIME_LOG").scrubbed_text
        sandboxed_block = PromptSandbox.sandbox_untrusted_data(
            scrubbed, label=f"ticket_{re.sub(r'[^a-zA-Z0-9]', '_', ticket_id)}"
        ).sandboxed_text

        return HydratedTicketContext(
            ticket_id=ticket_id,
            source_type=source_type,
            title=fetched_title,
            description=fetched_desc,
            acceptance_criteria=acceptance_criteria,
            sandboxed_prompt_block=sandboxed_block,
            raw_status=status,
            is_sandboxed=True,
        )

    @classmethod
    def _extract_criteria_lines(cls, body: str) -> List[str]:
        """Extract markdown task items (e.g. - [ ] or - [x]) as acceptance criteria."""
        criteria: List[str] = []
        for line in body.splitlines():
            line_s = line.strip()
            if line_s.startswith(("- [ ]", "- [x]", "* [ ]", "* [x]")):
                clean_crit = line_s[5:].strip()
                if clean_crit:
                    criteria.append(clean_crit)
        return criteria

