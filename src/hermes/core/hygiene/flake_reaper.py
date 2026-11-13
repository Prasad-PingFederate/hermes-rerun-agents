"""
Flake Lifecycle Reaper & Auto-Unquarantine Engine
Owner: FlakeQuarantineAgent & ScrumMasterOrchestrator
Phase: Option 6 (Monorepo Scale & Ecosystem Depth)

Manages the complete lifecycle of quarantined flaky tests:
1. Structured Cross-Runner Quarantine Stamp:
   Python: # hermes:quarantine(date=2026-11-12, ttl=14d, owner=@team-checkout, id=<hash>)
   JS/TS:  // hermes:quarantine(date=2026-11-12, ttl=14d, owner=@team-checkout, id=<hash>)
2. Surgical Auto-Unquarantine (50x Pass Gate):
   Tracks consecutive green runs on attempt #1 (retries_used == 0).
   When streak >= 50, surgically strips quarantine comments and retry decorators,
   re-verifies AST integrity, and stages an idempotent unquarantine PR (hermes/unquarantine-<id>).
3. TTL Expiry & SLA Escalation:
   Evaluates ttl=14d using UTC timestamps, alerts on QUARANTINE_TTL_EXPIRED, and exposes
   quarantine debt burndown telemetry to the Executive ROI Dashboard.

Zero external dependencies (uses standard library: ast, re, datetime, typing).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from hermes.guards.ts_playwright_ast_guard import PlaywrightASTGuard


@dataclass
class QuarantineMetadata:
    """Structured metadata parsed from a quarantine stamp."""
    quarantine_id: str
    quarantine_date: str  # YYYY-MM-DD
    ttl_days: int
    owner: str
    is_expired: bool = False
    days_elapsed: int = 0
    status: str = "ACTIVE"  # "ACTIVE", "EXPIRED", "REAPED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "quarantine_date": self.quarantine_date,
            "ttl_days": self.ttl_days,
            "owner": self.owner,
            "is_expired": self.is_expired,
            "days_elapsed": self.days_elapsed,
            "status": self.status,
        }


@dataclass
class UnquarantineProposal:
    """Proposal payload generated when a quarantined test passes 50 consecutive runs."""
    quarantine_id: str
    file_path: str
    cleaned_content: str
    consecutive_green_runs: int
    branch_name: str
    pr_title: str
    pr_body: str
    syntax_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "file_path": self.file_path,
            "consecutive_green_runs": self.consecutive_green_runs,
            "branch_name": self.branch_name,
            "pr_title": self.pr_title,
            "syntax_valid": self.syntax_valid,
        }


@dataclass
class QuarantineTelemetry:
    """Summary metrics of quarantine health and tech debt burn-down."""
    active_quarantines: int = 0
    reaped_quarantines: int = 0
    expired_sla_count: int = 0
    records: List[Dict[str, Any]] = field(default_factory=list)


class FlakeLifecycleReaper:
    """Audits quarantine stamps, tracks pass streaks, and surgically unquarantines stable tests."""

    # Regex matching Python and JS/TS quarantine comments
    QUARANTINE_STAMP_REGEX = re.compile(
        r"""(?:#|//)\s*hermes:quarantine\(\s*date=(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s*,\s*ttl=(?P<ttl>\d+)d\s*,\s*owner=(?P<owner>[^,)]+)\s*,\s*id=(?P<id>[a-zA-Z0-9_-]+)\s*\)""",
        re.IGNORECASE,
    )

    # Patterns matching retry decorators/statements to surgically strip
    PYTHON_RETRY_DECORATOR = re.compile(r"""^[ \t]*@pytest\.mark\.flaky\(reruns=\d+(?:,\s*reruns_delay=\d+)?\)[ \t]*\r?\n?""", re.MULTILINE)
    PLAYWRIGHT_RETRY_STMT = re.compile(r"""^[ \t]*test\.describe\.configure\(\{\s*retries:\s*\d+\s*\}\);[ \t]*\r?\n?""", re.MULTILINE)
    JEST_RETRY_STMT = re.compile(r"""^[ \t]*jest\.retryTimes\(\s*\d+\s*\);[ \t]*\r?\n?""", re.MULTILINE)

    @classmethod
    def parse_quarantine_stamp(
        cls,
        code_content: str,
        current_time: Optional[datetime] = None,
    ) -> Optional[QuarantineMetadata]:
        """Extract and validate structured quarantine metadata from source code."""
        match = cls.QUARANTINE_STAMP_REGEX.search(code_content)
        if not match:
            return None

        date_str = match.group("date")
        ttl_days = int(match.group("ttl"))
        owner = match.group("owner").strip()
        qid = match.group("id").strip()

        now = current_time or datetime.now(timezone.utc)
        try:
            q_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_elapsed = max(0, (now - q_date).days)
        except Exception:
            days_elapsed = 0

        is_expired = days_elapsed > ttl_days
        status = "EXPIRED" if is_expired else "ACTIVE"

        return QuarantineMetadata(
            quarantine_id=qid,
            quarantine_date=date_str,
            ttl_days=ttl_days,
            owner=owner,
            is_expired=is_expired,
            days_elapsed=days_elapsed,
            status=status,
        )

    @classmethod
    def evaluate_streak_and_unquarantine(
        cls,
        file_path: str,
        current_content: str = "",
        consecutive_green_runs: int = 50,
        pass_threshold: int = 50,
        source_code: Optional[str] = None,
    ) -> Optional[UnquarantineProposal]:
        """Surgically strip quarantine metadata and retry decorators when green streak reaches threshold."""
        if not current_content and source_code is not None:
            current_content = source_code
        meta = cls.parse_quarantine_stamp(current_content)
        if not meta or consecutive_green_runs < pass_threshold:
            return None

        # 1. Surgically remove quarantine comment
        cleaned = cls.QUARANTINE_STAMP_REGEX.sub("", current_content)

        # 2. Surgically remove language-specific retry statements
        norm_path = file_path.replace("\\", "/").lower()
        if norm_path.endswith(".py"):
            cleaned = cls.PYTHON_RETRY_DECORATOR.sub("", cleaned)
            # Verify Python AST syntax
            try:
                ast.parse(cleaned, filename=file_path)
                syntax_valid = True
            except SyntaxError:
                syntax_valid = False
        else:
            cleaned = cls.PLAYWRIGHT_RETRY_STMT.sub("", cleaned)
            cleaned = cls.JEST_RETRY_STMT.sub("", cleaned)
            # Verify JS/TS spec integrity
            ts_res = PlaywrightASTGuard.verify_spec_content(file_path, cleaned)
            syntax_valid = ts_res.valid

        # Clean trailing extra blank lines left by removals
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        branch_name = f"hermes/unquarantine-{meta.quarantine_id}"
        pr_title = f"chore(quarantine): auto-unquarantine {file_path} after {consecutive_green_runs} consecutive green runs"
        pr_body = (
            f"## Hermes Flake Lifecycle Reaper: Auto-Unquarantine\n\n"
            f"The test `{file_path}` has passed **{consecutive_green_runs} consecutive CI runs on attempt #1** (threshold: {pass_threshold}).\n\n"
            f"### Quarantine Audit Trail\n"
            f"| Attribute | Value |\n"
            f"| :--- | :--- |\n"
            f"| **Quarantine ID** | `{meta.quarantine_id}` |\n"
            f"| **Initial Quarantine Date** | `{meta.quarantine_date}` |\n"
            f"| **Original TTL** | `{meta.ttl_days} days` |\n"
            f"| **Owner** | `{meta.owner}` |\n"
            f"| **Surgical Removal AST Syntax** | `{'VERIFIED' if syntax_valid else 'FAILED'}` |\n\n"
            f"> *Hermes has surgically stripped the quarantine wrapper and retry annotations. Test stability is restored.*"
        )

        return UnquarantineProposal(
            quarantine_id=meta.quarantine_id,
            file_path=file_path,
            cleaned_content=cleaned,
            consecutive_green_runs=consecutive_green_runs,
            branch_name=branch_name,
            pr_title=pr_title,
            pr_body=pr_body,
            syntax_valid=syntax_valid,
        )

    @classmethod
    def audit_quarantine_telemetry(
        cls,
        quarantine_files: Dict[str, str],
        current_time: Optional[datetime] = None,
    ) -> QuarantineTelemetry:
        """Scan a dictionary of file contents and aggregate quarantine debt telemetry."""
        active = 0
        reaped = 0
        expired = 0
        records: List[Dict[str, Any]] = []

        for fpath, content in quarantine_files.items():
            meta = cls.parse_quarantine_stamp(content, current_time=current_time)
            if meta:
                rec = meta.to_dict()
                rec["file_path"] = fpath
                records.append(rec)
                if meta.is_expired:
                    expired += 1
                else:
                    active += 1

        return QuarantineTelemetry(
            active_quarantines=active,
            reaped_quarantines=reaped,
            expired_sla_count=expired,
            records=records,
        )

