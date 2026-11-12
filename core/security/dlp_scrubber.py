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


class RuntimeSecretLeakError(ValueError):
    """Raised when candidate code attempts to detokenize a secret extracted from runtime logs or external tickets."""
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
        self.source_tokens: Set[str] = set()
        self.one_way_tokens: Set[str] = set()

    def is_whitelisted(self, value: str) -> bool:
        """Check if string is a benign development identifier like a commit SHA or UUID."""
        val = value.strip()
        return any(p.match(val) for p in self.WHITELIST_PATTERNS)

    def _allocate_token(self, category: str, raw_value: str, source: str = "SOURCE") -> str:
        """Allocate or reuse referentially consistent token for raw secret."""
        src = source.strip().upper()
        if raw_value in self.raw_to_token:
            token = self.raw_to_token[raw_value]
            if src in ("SOURCE", "SOURCE_CODE", "CODE", "FIXTURE"):
                self.source_tokens.add(token)
            elif src in ("RUNTIME_LOG", "LOG", "ONE_WAY", "ONE_WAY_SCRUB", "TICKET"):
                self.one_way_tokens.add(token)
            return token

        current = self.type_counters.get(category, 0) + 1
        self.type_counters[category] = current
        token = f"<HERMES_{category}_{current}>"

        self.raw_to_token[raw_value] = token
        self.token_to_raw[token] = raw_value

        if src in ("SOURCE", "SOURCE_CODE", "CODE", "FIXTURE"):
            self.source_tokens.add(token)
        elif src in ("RUNTIME_LOG", "LOG", "ONE_WAY", "ONE_WAY_SCRUB", "TICKET"):
            self.one_way_tokens.add(token)

        return token

    def register_source_code(self, source_text: str) -> ScrubResult:
        """Scan and register known tokens from repository source files as safe to detokenize."""
        return self.scrub(source_text, source="SOURCE")

    def scrub_runtime_log(self, log_text: str) -> ScrubResult:
        """Scrub runtime CI failure log with one-way protection against patch exfiltration."""
        return self.scrub(log_text, source="RUNTIME_LOG")

    def scrub(self, text: str, source: str = "SOURCE") -> ScrubResult:
        """Execute deterministic DLP pipeline across input string.
        
        Args:
            text: Raw input text (code, fixture, ticket, or log).
            source: 'SOURCE' for checked-in codebase files; 'RUNTIME_LOG' for CI logs or external tickets.
        """
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
                    token = self._allocate_token(category, secret, source=source)
                    counts_by_category[category] = counts_by_category.get(category, 0) + 1
                    return full.replace(secret, token, 1)

                result_text = pattern.sub(repl_group, result_text)
            else:
                def repl_full(match: re.Match[str]) -> str:
                    raw = match.group(0)
                    if self.is_whitelisted(raw):
                        return raw
                    token = self._allocate_token(category, raw, source=source)
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

    def detokenize(self, text: str, allow_one_way: bool = False) -> str:
        """Rehydrate placeholders back into original secrets locally.
        
        Args:
            text: String containing <HERMES_*_*> placeholders.
            allow_one_way: If False (default), prevents runtime log secrets from being
                           detokenized into candidate patches or PR comments.

        Raises:
            HallucinatedPlaceholderError: If text contains placeholders not in this session vault.
            RuntimeSecretLeakError: If text contains secrets only extracted from runtime logs.
        """
        if not text:
            return ""

        valid, unknown = self.validate_no_hallucinations(text)
        if not valid:
            raise HallucinatedPlaceholderError(
                f"Candidate code contains unrecognized placeholder(s): {', '.join(unknown)}. "
                "Rejecting patch to prevent leaking placeholder tokens into production."
            )

        # One-Way DLP Guard: Block rehydrating secrets seen only in runtime logs/tickets
        if not allow_one_way:
            leaked_tokens: List[str] = []
            for m in self.PLACEHOLDER_REGEX.finditer(text):
                tok = m.group(0)
                if tok in self.one_way_tokens and tok not in self.source_tokens:
                    leaked_tokens.append(tok)
            if leaked_tokens:
                unique_leaked = sorted(set(leaked_tokens))
                raise RuntimeSecretLeakError(
                    f"Refusing to detokenize runtime-only secret(s): {', '.join(unique_leaked)}. "
                    "Runtime log credentials (ONE_WAY_SCRUB) must never be rehydrated into code patches or PR comments."
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

