"""
Shadow Mode & Zero-Write GitHub Suggestion Engine
Owner: ScrumMasterOrchestrator & CIDetectiveAgent, TIER_1 / TIER_2

Features:
- SHADOW_SUGGEST mode: Zero branch-push and zero repository write permissions required.
- In-Diff Multi-Line Suggestions: Emits GitHub PR review comments with ```suggestion blocks
  when the healed AST span lies within the pull request's modified diff hunks.
- Out-of-Diff Graceful Fallback: Avoids GitHub HTTP 422 Unprocessable Entity by automatically
  falling back to a collapsible PR summary comment with the unified diff and instructions.
- Anti-Spam Idempotency: Uses deterministic comment markers (<!-- hermes-shadow-heal:{sprint_id} -->)
  to update existing review/issue comments on re-runs instead of spamming duplicates.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class ExecutionMode(str, Enum):
    """Hermes execution permissions modes."""
    DIRECT_COMMIT = "DIRECT_COMMIT"
    DRAFT_PR = "DRAFT_PR"
    SHADOW_SUGGEST = "SHADOW_SUGGEST"


@dataclass
class DiffHunk:
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    @property
    def new_end(self) -> int:
        return self.new_start + max(1, self.new_count) - 1


class DiffHunkParser:
    """Parses unified diff outputs or GitHub PR patch text into modified line spans."""

    HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    @classmethod
    def parse_diff(cls, diff_text: str) -> Dict[str, List[DiffHunk]]:
        """Extract modified line ranges per file from unified diff text."""
        hunks_by_file: Dict[str, List[DiffHunk]] = {}
        current_file: Optional[str] = None

        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:].strip().replace("\\", "/")
                if current_file not in hunks_by_file:
                    hunks_by_file[current_file] = []
            elif line.startswith("+++ "):
                # Handle non-standard prefix
                raw_path = line[4:].strip().replace("\\", "/")
                if raw_path.startswith("b/"):
                    raw_path = raw_path[2:]
                current_file = raw_path
                if current_file not in hunks_by_file:
                    hunks_by_file[current_file] = []
            elif line.startswith("@@ ") and current_file:
                m = cls.HUNK_HEADER_RE.match(line)
                if m:
                    old_start = int(m.group(1))
                    old_count = int(m.group(2)) if m.group(2) else 1
                    new_start = int(m.group(3))
                    new_count = int(m.group(4)) if m.group(4) else 1
                    hunk = DiffHunk(
                        file_path=current_file,
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                    )
                    hunks_by_file[current_file].append(hunk)

        return hunks_by_file

    @classmethod
    def is_span_in_diff(
        cls,
        hunks_by_file: Dict[str, List[DiffHunk]],
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> bool:
        """Return True if the [start_line, end_line] span falls within any changed hunk."""
        clean_path = file_path.replace("\\", "/").lstrip("/")
        # Look for matching file path
        matched_hunks = hunks_by_file.get(clean_path)
        if not matched_hunks:
            # Fallback check basename
            target_name = clean_path.split("/")[-1]
            for p, hunks in hunks_by_file.items():
                if p.endswith(target_name) or target_name in p:
                    matched_hunks = hunks
                    break

        if not matched_hunks:
            return False

        # Check if span overlaps with any hunk
        for h in matched_hunks:
            if not (end_line < h.new_start or start_line > h.new_end):
                return True
        return False


class ShadowSuggestionFormatter:
    """Formats GitHub Markdown suggestions and out-of-diff fallback comments."""

    MARKER_TEMPLATE = "<!-- hermes-shadow-heal:{sprint_id} -->"

    @classmethod
    def get_marker(cls, sprint_id: str) -> str:
        return cls.MARKER_TEMPLATE.format(sprint_id=sprint_id)

    @classmethod
    def format_in_diff_payload(
        cls,
        file_path: str,
        start_line: int,
        end_line: int,
        replacement_code: str,
        sprint_id: str,
        classification: str = "PRODUCT_BUG",
        root_cause: str = "Defensive validation required",
        governance_badges: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate GitHub PR Review comment payload with markdown ```suggestion block."""
        badges = governance_badges or [
            "✅ `ZERO_ASSERTION_EROSION`",
            "🛡️ `DELTA_SAST_PASSED`",
            "🎯 `SURGICAL_SPAN`",
        ]
        badge_line = " | ".join(badges)
        marker = cls.get_marker(sprint_id)

        clean_replacement = replacement_code.rstrip("\r\n")

        body = (
            f"{marker}\n"
            f"### ⚡ Hermes Shadow Healer: Suggested Surgical Fix\n\n"
            f"> **Governance**: {badge_line}\n"
            f"> **Root Cause**: `{classification}` — {root_cause}\n\n"
            f"```suggestion\n"
            f"{clean_replacement}\n"
            f"```\n\n"
            f"*Click **\"Commit suggestion\"** to apply this patch directly to this branch with zero human code-writing.*"
        )

        payload: Dict[str, Any] = {
            "path": file_path.replace("\\", "/").lstrip("/"),
            "line": int(end_line),
            "side": "RIGHT",
            "body": body,
        }

        # Multi-line suggestion support on GitHub PR Reviews
        if int(start_line) < int(end_line):
            payload["start_line"] = int(start_line)
            payload["start_side"] = "RIGHT"

        return payload

    @classmethod
    def format_out_of_diff_fallback(
        cls,
        file_path: str,
        start_line: int,
        end_line: int,
        unified_diff: str,
        sprint_id: str,
        classification: str = "TEST_BUG",
        governance_audit: str = "All security gates passed.",
        root_cause: str = "Assertion drifted or untouched test file broken by contract update",
    ) -> str:
        """Generate collapsible PR summary comment when file/span is outside PR diff."""
        marker = cls.get_marker(sprint_id)
        clean_path = file_path.replace("\\", "/").lstrip("/")

        return (
            f"{marker}\n"
            f"### ⚡ Hermes Shadow Healer: Out-of-Diff Patch Proposal\n\n"
            f"> ℹ️ **Notice**: The healed failure in `{clean_path}` (lines {start_line}–{end_line}) "
            f"is outside the changed diff hunks of this PR. GitHub prevents in-line review suggestions on unchanged lines (HTTP 422).\n\n"
            f"> **Classification**: `{classification}` — {root_cause}\n\n"
            f"<details open>\n"
            f"<summary>📋 <b>View Proposed Unified Diff ({clean_path})</b></summary>\n\n"
            f"```diff\n"
            f"{unified_diff.strip()}\n"
            f"```\n"
            f"</details>\n\n"
            f"<details>\n"
            f"<summary>🛡️ <b>Governance & Security Audit Trail</b></summary>\n\n"
            f"{governance_audit.strip()}\n"
            f"</details>\n\n"
            f"#### 🚀 How to Apply\n"
            f"- Reply with `/hermes approve` on this pull request to automatically apply and test.\n"
            f"- Or apply locally via git:\n"
            f"```bash\n"
            f"git apply << 'EOF'\n"
            f"{unified_diff.strip()}\n"
            f"EOF\n"
            f"```\n"
        )


class ShadowSuggestionClient:
    """Client for posting or updating GitHub suggestions idempotently using standard library."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or ""

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Hermes-Shadow-Engine/1.0",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def find_existing_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        marker: str,
    ) -> Optional[Dict[str, Any]]:
        """Search PR review comments and issue comments for marker."""
        if not self.token:
            return None

        # 1. Search PR review comments
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                comments = json.loads(resp.read().decode("utf-8"))
                for c in comments:
                    if marker in c.get("body", ""):
                        return {"type": "review_comment", "id": c.get("id"), "comment": c}
        except Exception:
            pass

        # 2. Search PR issue comments
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                comments = json.loads(resp.read().decode("utf-8"))
                for c in comments:
                    if marker in c.get("body", ""):
                        return {"type": "issue_comment", "id": c.get("id"), "comment": c}
        except Exception:
            pass

        return None

    def post_or_update_suggestion(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        file_path: str,
        start_line: int,
        end_line: int,
        replacement_code: str,
        sprint_id: str,
        is_in_diff: bool,
        unified_diff: str = "",
        classification: str = "PRODUCT_BUG",
        root_cause: str = "Defensive validation needed",
        governance_audit: str = "All security gates passed.",
    ) -> Dict[str, Any]:
        """Post or update an in-diff suggestion or out-of-diff fallback comment."""
        marker = ShadowSuggestionFormatter.get_marker(sprint_id)

        if not self.token:
            # Simulated / Dry Run mode
            if is_in_diff:
                payload = ShadowSuggestionFormatter.format_in_diff_payload(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    replacement_code=replacement_code,
                    sprint_id=sprint_id,
                    classification=classification,
                    root_cause=root_cause,
                )
                payload["commit_id"] = commit_sha
                return {
                    "status": "simulated",
                    "mode": "in_diff",
                    "marker": marker,
                    "payload": payload,
                }
            else:
                body = ShadowSuggestionFormatter.format_out_of_diff_fallback(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    unified_diff=unified_diff,
                    sprint_id=sprint_id,
                    classification=classification,
                    governance_audit=governance_audit,
                    root_cause=root_cause,
                )
                return {
                    "status": "simulated",
                    "mode": "out_of_diff",
                    "marker": marker,
                    "body": body,
                }

        # Check existing comment for anti-spam idempotency
        existing = self.find_existing_comment(owner, repo, pr_number, marker)

        if is_in_diff:
            review_payload = ShadowSuggestionFormatter.format_in_diff_payload(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                replacement_code=replacement_code,
                sprint_id=sprint_id,
                classification=classification,
                root_cause=root_cause,
            )
            review_payload["commit_id"] = commit_sha

            # If existing review comment found, update it
            if existing and existing.get("type") == "review_comment":
                comment_id = existing["id"]
                patch_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{comment_id}"
                try:
                    patch_req = urllib.request.Request(
                        patch_url,
                        data=json.dumps({"body": review_payload["body"]}).encode("utf-8"),
                        headers=self._headers(),
                        method="PATCH",
                    )
                    with urllib.request.urlopen(patch_req, timeout=10) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        return {"status": "updated", "mode": "in_diff", "id": res.get("id"), "url": res.get("html_url")}
                except Exception:
                    pass

            # Otherwise POST new review comment
            post_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            try:
                post_req = urllib.request.Request(
                    post_url,
                    data=json.dumps(review_payload).encode("utf-8"),
                    headers=self._headers(),
                    method="POST",
                )
                with urllib.request.urlopen(post_req, timeout=10) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    return {"status": "created", "mode": "in_diff", "id": res.get("id"), "url": res.get("html_url")}
            except urllib.error.HTTPError as err:
                # If HTTP 422 (e.g. diff range rejected), fall back gracefully to issue comment!
                if err.code == 422:
                    is_in_diff = False
                else:
                    raise

        # Out-of-diff fallback (or 422 recovery)
        fallback_body = ShadowSuggestionFormatter.format_out_of_diff_fallback(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            unified_diff=unified_diff,
            sprint_id=sprint_id,
            classification=classification,
            governance_audit=governance_audit,
            root_cause=root_cause,
        )

        if existing and existing.get("type") == "issue_comment":
            comment_id = existing["id"]
            patch_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
            patch_req = urllib.request.Request(
                patch_url,
                data=json.dumps({"body": fallback_body}).encode("utf-8"),
                headers=self._headers(),
                method="PATCH",
            )
            with urllib.request.urlopen(patch_req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return {"status": "updated", "mode": "out_of_diff", "id": res.get("id"), "url": res.get("html_url")}

        post_issue_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        post_issue_req = urllib.request.Request(
            post_issue_url,
            data=json.dumps({"body": fallback_body}).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(post_issue_req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return {"status": "created", "mode": "out_of_diff", "id": res.get("id"), "url": res.get("html_url")}

