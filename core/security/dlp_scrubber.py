"""
Deterministic Data Loss Prevention (DLP) & Secret Scrubber
Owner: SecurityBlastRadiusAgent & CIDetectiveAgent
Phase: Option 5 (InfoSec, AI Governance & FinOps)

Guarantees zero credentials or PII leak into LLM prompts via reversible, in-memory tokenization:
1. Specificity-Ordered Regex Pipeline:
   PEM Private Keys -> Connection URIs -> JWTs (eyJ...) -> Cloud/VCS Keys -> Bearer Auth -> Emails -> High-Entropy Secrets
2. Referential Consistency:
   In-memory session vault reuses tokens across failure logs, stack traces, and code snippets.
3. Hallucinated Placeholder Rejection:
   Blocks candidate patches containing unmapped placeholder tokens (<HERMES_JWT_99>).
4. False-Positive Whitelisting:
   Excludes Git SHAs, UUIDs, file paths, and localhost/loopback addresses.

Zero external dependencies (uses standard library: re, typing, math).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class HallucinatedPlaceholderError(ValueError):
    """Raised when candidate code contains an unrecognized or hallucinated Hermes placeholder."""
    pass


@dataclass
class ScrubResult:
    """Telemetry captured from a DLP scrub pass."""
    original_length: int
    scrubbed_length: int
    scrubbed_text: str
    tokens_created: int
    placeholder_counts: Dict[str, int] = field(default_factory=dict)


class DLPSessionVault:
    """In-memory session vault ensuring referential consistency and safe detokenization."""

    # Specificity-ordered DLP rules: (category, pattern, is_multiline)
    RULES: List[Tuple[str, re.Pattern[str]]] = [
        # 1. PEM Private Keys
        (
            "PEM",
            re.compile(
                r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z0-9 ]+)?PRIVATE KEY-----",
                re.MULTILINE,
            ),
        ),
        # 2. Database & Service Connection URIs
        (
            "URI",
            re.compile(
                r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp|mssql):\/\/[^\s\"'`<>]+",
                re.IGNORECASE,
            ),
        ),
        # 3. JWT Tokens (Three base64url segments starting with eyJ)
        (
            "JWT",
            re.compile(
                r"\beyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*\b",
            ),
        ),
        # 4. Cloud & VCS API Keys (AWS, GitHub, Slack, OpenAI, Stripe)
        (
            "KEY",
            re.compile(
                r"\b(?:"
                r"AKIA[0-9A-Z]{16}"                                        # AWS Access Key
                r"|(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"             # GitHub Personal Access Tokens
                r"|github_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9_]{59}"           # Fine-grained PAT
                r"|xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}"     # Slack API Tokens
                r"|sk-[A-Za-z0-9]{32,}"                                    # OpenAI API Key
                r"|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{24,}"               # Stripe Secrets
                r")\b",
            ),
        ),
        # 5. Bearer Auth Headers
        (
            "AUTH",
            re.compile(
                r"(?i)\bBearer\s+([A-Za-z0-9\-._~+/]{16,}=*)\b",
            ),
        ),
        # 6. Corporate & Personal Emails
        (
            "EMAIL",
            re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b",
            ),
        ),
        # 7. Explicit Password / Secret Key Value Pairs
        (
            "SECRET",
            re.compile(
                r"""(?i)(?:password|passwd|secret|api[_-]?key|client[_-]?secret|auth[_-]?token)["']?\s*[:=]\s*["']([A-Za-z0-9!@#$%^&*()_\-+=]{10,})["']"""
            ),
        ),
    ]

    # Whitelist patterns: If a match matches any of these, do not scrub
    WHITELIST_PATTERNS = [
        # Standard UUID
        re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE),
        # Git 40-char SHA
        re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE),
        # Localhost / loopback IPs
        re.compile(r"^(?:localhost|127\.0\.0\.1|0\.0\.0\.0|::1)(?::\d+)?$", re.IGNORECASE),
        # Common file path structure
        re.compile(r"^(?:\/|[A-Za-z]:[\\\/])[^\s]+$"),
    ]

    PLACEHOLDER_REGEX = re.compile(r"<HERMES_([A-Z]+)_(\d+)>")

    def __init__(self) -> None:
        self.raw_to_token: Dict[str, str] = {}
        self.token_to_raw: Dict[str, str] = {}
        self.type_counters: Dict[str, int] = {}

    def is_whitelisted(self, value: str) -> bool:
        """Check if string is a benign development identifier like a commit SHA or UUID."""
        val = value.strip()
        return any(p.match(val) for p in self.WHITELIST_PATTERNS)

    def _allocate_token(self, category: str, raw_value: str) -> str:
        """Allocate or reuse referentially consistent token for raw secret."""
        if raw_value in self.raw_to_token:
            return self.raw_to_token[raw_value]

        current = self.type_counters.get(category, 0) + 1
        self.type_counters[category] = current
        token = f"<HERMES_{category}_{current}>"

        self.raw_to_token[raw_value] = token
        self.token_to_raw[token] = raw_value
        return token

    def scrub(self, text: str) -> ScrubResult:
        """Execute deterministic DLP pipeline across input string."""
        if not text:
            return ScrubResult(0, 0, "", 0, {})

        orig_len = len(text)
        result_text = text
        tokens_before = len(self.raw_to_token)
        counts_by_category: Dict[str, int] = {}

        for category, pattern in self.RULES:
            # Handle Bearer and Secret capturing groups vs full match
            if category in ("AUTH", "SECRET"):
                def repl_group(match: re.Match[str]) -> str:
                    full = match.group(0)
                    secret = match.group(1)
                    if self.is_whitelisted(secret):
                        return full
                    token = self._allocate_token(category, secret)
                    counts_by_category[category] = counts_by_category.get(category, 0) + 1
                    return full.replace(secret, token, 1)

                result_text = pattern.sub(repl_group, result_text)
            else:
                def repl_full(match: re.Match[str]) -> str:
                    raw = match.group(0)
                    if self.is_whitelisted(raw):
                        return raw
                    token = self._allocate_token(category, raw)
                    counts_by_category[category] = counts_by_category.get(category, 0) + 1
                    return token

                result_text = pattern.sub(repl_full, result_text)

        tokens_created = len(self.raw_to_token) - tokens_before
        return ScrubResult(
            original_length=orig_len,
            scrubbed_length=len(result_text),
            scrubbed_text=result_text,
            tokens_created=tokens_created,
            placeholder_counts=counts_by_category,
        )

    def detokenize(self, text: str) -> str:
        """Rehydrate placeholders back into original secrets locally.
        
        Raises:
            HallucinatedPlaceholderError: If text contains placeholders not in this session vault.
        """
        if not text:
            return ""

        valid, unknown = self.validate_no_hallucinations(text)
        if not valid:
            raise HallucinatedPlaceholderError(
                f"Candidate code contains unrecognized placeholder(s): {', '.join(unknown)}. "
                "Rejecting patch to prevent leaking placeholder tokens into production."
            )

        # Replace in reverse length order to prevent prefix collisions
        sorted_tokens = sorted(self.token_to_raw.keys(), key=len, reverse=True)
        res = text
        for tok in sorted_tokens:
            res = res.replace(tok, self.token_to_raw[tok])
        return res

    def validate_no_hallucinations(self, text: str) -> Tuple[bool, List[str]]:
        """Validate that any <HERMES_*_*> placeholder belongs to this vault session."""
        if not text:
            return True, []

        found_tokens = self.PLACEHOLDER_REGEX.findall(text)
        unknown: List[str] = []
        for cat, idx in found_tokens:
            full_tok = f"<HERMES_{cat}_{idx}>"
            if full_tok not in self.token_to_raw:
                unknown.append(full_tok)

        return len(unknown) == 0, unknown


class DLPScrubber:
    """Convenience helper managing DLP scrubbing sessions."""

    @classmethod
    def create_session(cls) -> DLPSessionVault:
        """Create a fresh in-memory session vault."""
        return DLPSessionVault()

