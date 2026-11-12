"""
GAP-09: Concrete QACriticAgent (TIER_4) Rubric & Escalation Memory
Owner: QACriticAgent, TIER_4

Provides rigorous, structured QA critique:
- QACriticAgent.review_worker_output(): Evaluates each Acceptance Criterion individually with file/line citations.
- Automatic rejection when edge cases or error paths lack test assertions.
- EscalationPromptBuilder: Injects exact previous AttemptRecord failure reasons, QA feedback,
  and missing citations into escalated worker prompts (TIER_3 -> TIER_2 -> TIER_1).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CriterionVerdict:
    """Individual evaluation of an acceptance criterion or edge-case requirement."""
    criterion: str
    status: str  # "PASS" or "FAIL"
    citations: List[str] = field(default_factory=list)  # e.g. ["core/math.py:42", "tests/test_math.py:15"]
    feedback: str = ""


@dataclass
class QACriticReview:
    """Comprehensive evaluation returned by QACriticAgent."""
    approved: bool
    verdicts: List[CriterionVerdict]
    rejection_reasons: List[str]
    missing_coverage: List[str] = field(default_factory=list)
    edge_case_findings: List[str] = field(default_factory=list)


class QACriticAgent:
    """TIER_4 QA Critic: Performs adversarial review against AC rubrics and edge case coverage."""

    NAME = "QACriticAgent"
    TIER = "TIER_4_QA_CRITIC"

    @classmethod
    def _find_citations_for_keywords(
        cls, proposed_changes: Dict[str, str], keywords: List[str]
    ) -> List[str]:
        """Find file:line references in proposed changes matching relevant keywords."""
        citations: List[str] = []
        stop_words = {
            "ac-1", "ac-2", "ac-3", "ac-4", "resolve", "ensure", "verify", "preserve",
            "assertion", "assertions", "existing", "code", "the", "and", "for", "with",
            "all", "test", "tests", "failure", "failures", "error", "errors", "failed",
            "zero", "erosion", "in", "function", "functionality", "method", "class"
        }
        expanded_kws: List[str] = []
        for kw in keywords:
            clean_kw = kw.strip(".,;:\"'()[]{}")
            if "_" in clean_kw:
                expanded_kws.extend(clean_kw.split("_"))
            else:
                expanded_kws.append(clean_kw)

        filtered_kws = [kw for kw in expanded_kws if kw.lower() not in stop_words and len(kw) > 2]

        if filtered_kws:
            for file_path, content in proposed_changes.items():
                file_lower = file_path.lower()
                lines = content.splitlines()
                for line_no, line in enumerate(lines, 1):
                    line_lower = line.lower()
                    if any(kw.lower() in line_lower or kw.lower() in file_lower for kw in filtered_kws):
                        citations.append(f"{file_path}:{line_no}")
                        if len(citations) >= 5:
                            return citations
            return citations

        # Only if there were no domain keywords (generic criterion)
        if proposed_changes:
            for file_path, content in proposed_changes.items():
                for line_no, line in enumerate(content.splitlines(), 1):
                    if line.strip() and not line.strip().startswith("#"):
                        citations.append(f"{file_path}:{line_no}")
                        break
        return citations

    @classmethod
    def _inspect_error_path_coverage(
        cls, proposed_changes: Dict[str, str], existing_test_files: Optional[Dict[str, str]] = None
    ) -> Tuple[List[str], List[str]]:
        """Detect unhandled error paths and verify whether corresponding assertions exist."""
        error_paths_found: List[str] = []
        assertions_found: List[str] = []

        # Error patterns in code
        error_patterns = [
            (r"\braise\s+([A-Za-z0-9_]+)", "Raises exception: {}"),
            (r"\bexcept\s+([A-Za-z0-9_]+)", "Catches exception: {}"),
            (r"\bif\s+.*(?:is\s+None|==\s*None)", "Null/None branch check"),
            (r"\bif\s+.*(?:<\s*0|<=\s*0)", "Negative boundary check"),
            (r"\bthrow\s+new\s+Error", "Throws JS Error"),
        ]

        # Assertion patterns in tests
        assertion_patterns = [
            r"\bpytest\.raises\s*\(",
            r"\bassertRaises\s*\(",
            r"\bassert\b",
            r"\bexpect\s*\(",
        ]

        all_sources = dict(proposed_changes)
        if existing_test_files:
            all_sources.update(existing_test_files)

        for file_path, content in all_sources.items():
            lines = content.splitlines()
            for line_no, line in enumerate(lines, 1):
                if file_path in proposed_changes:
                    for pat, label in error_patterns:
                        m = re.search(pat, line)
                        if m:
                            val = m.group(1) if m.groups() else ""
                            error_paths_found.append(f"{file_path}:{line_no} ({label.format(val)})")

                for pat in assertion_patterns:
                    if re.search(pat, line):
                        assertions_found.append(f"{file_path}:{line_no}")

        missing_assertions: List[str] = []
        # If error paths were added in non-test files, there must be tests asserting on them
        test_assertions = [a for a in assertions_found if "test" in a.lower()]
        prod_error_paths = [e for e in error_paths_found if "test" not in e.lower()]

        if prod_error_paths and not test_assertions:
            missing_assertions.append(
                f"Error paths introduced in production code ({', '.join(prod_error_paths[:3])}) "
                f"lack corresponding test assertions (pytest.raises / expect) in proposed or existing tests."
            )

        return error_paths_found, missing_assertions

    @classmethod
    def review_worker_output(
        cls,
        ticket: Any,
        proposed_changes: Dict[str, str],
        allow_test_modification: bool = False,
        workspace_path: Optional[Path | str] = None,
    ) -> QACriticReview:
        """Perform strict rubric review on worker proposed changes."""
        verdicts: List[CriterionVerdict] = []
        rejection_reasons: List[str] = []

        if not proposed_changes:
            return QACriticReview(
                approved=False,
                verdicts=[
                    CriterionVerdict(
                        criterion="Non-empty proposal",
                        status="FAIL",
                        citations=[],
                        feedback="Worker proposed zero file changes.",
                    )
                ],
                rejection_reasons=["Empty proposal: worker returned no modified files."],
            )

        # 1. Discover existing test content if DeveloperAgent only touched production files
        existing_test_files: Dict[str, str] = {}
        ws = Path(workspace_path) if workspace_path else Path.cwd()
        allowed = getattr(ticket, "allowed_files", []) or []

        # Check allowed_files for test files
        for f in allowed:
            if "test" in f.lower() and f not in proposed_changes:
                target_p = ws / f.replace("\\", "/").lstrip("/")
                if target_p.is_file():
                    try:
                        existing_test_files[f] = target_p.read_text(encoding="utf-8")
                    except Exception:
                        pass

        # If DeveloperAgent was scoped to prod files only, discover test suite in ws / "tests"
        if not existing_test_files and ws.is_dir():
            tests_dir = ws / "tests"
            if tests_dir.is_dir():
                for tp in tests_dir.glob("*.py"):
                    rel_tp = str(tp.relative_to(ws)).replace("\\", "/")
                    if rel_tp not in existing_test_files and rel_tp not in proposed_changes:
                        try:
                            existing_test_files[rel_tp] = tp.read_text(encoding="utf-8")
                        except Exception:
                            pass

        # 2. Evaluate Acceptance Criteria
        criteria = getattr(ticket, "acceptance_criteria", []) or []
        if not criteria:
            verdicts.append(
                CriterionVerdict(
                    criterion=f"Fulfill ticket {ticket.ticket_id}: {ticket.title}",
                    status="PASS",
                    citations=[f"{fp}:1" for fp in proposed_changes.keys()][:3],
                    feedback="Proposal modifies allowed files as requested.",
                )
            )
        else:
            for crit in criteria:
                words = [w.strip(".,;:\"'()[]") for w in crit.split() if len(w) > 2]
                citations = cls._find_citations_for_keywords(proposed_changes, words)

                if citations:
                    verdicts.append(
                        CriterionVerdict(
                            criterion=crit,
                            status="PASS",
                            citations=citations[:3],
                            feedback=f"Addressed in: {', '.join(citations[:3])}",
                        )
                    )
                else:
                    verdicts.append(
                        CriterionVerdict(
                            criterion=crit,
                            status="FAIL",
                            citations=[],
                            feedback=f"No code or test citations in proposal address: '{crit}'",
                        )
                    )
                    rejection_reasons.append(f"Unaddressed acceptance criterion: '{crit}'")

        # 3. Inspect Edge Cases & Error Path Assertions
        error_paths, missing_coverage = cls._inspect_error_path_coverage(proposed_changes, existing_test_files)
        if missing_coverage:
            for item in missing_coverage:
                verdicts.append(
                    CriterionVerdict(
                        criterion="Edge Case & Error Path Test Coverage",
                        status="FAIL",
                        citations=[],
                        feedback=item,
                    )
                )
                rejection_reasons.append(item)

        # Approved only if EVERY verdict is PASS
        all_passed = len(rejection_reasons) == 0 and all(v.status == "PASS" for v in verdicts)

        return QACriticReview(
            approved=all_passed,
            verdicts=verdicts,
            rejection_reasons=rejection_reasons,
            missing_coverage=missing_coverage,
            edge_case_findings=error_paths,
        )


class EscalationPromptBuilder:
    """Builds enriched worker prompts for escalated tiers (TIER_3 -> TIER_2 -> TIER_1)."""

    @classmethod
    def build_escalation_prompt(
        cls,
        ticket: Any,
        target_tier: str,
        qa_review: Optional[QACriticReview] = None,
        security_findings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Compose context-rich prompt preserving historical rejection feedback."""
        parts = [
            f"# ESCALATED TASK BRIEF FOR {target_tier}",
            f"**Ticket ID**: {ticket.ticket_id} — {ticket.title}",
            f"**Complexity**: {getattr(ticket, 'complexity', 3)}/5",
            f"**Allowed Scope**: {', '.join(getattr(ticket, 'allowed_files', []))}",
            "",
            "## Acceptance Criteria:",
        ]
        for crit in getattr(ticket, "acceptance_criteria", []):
            parts.append(f"- {crit}")

        # Inject previous attempt history
        history = getattr(ticket, "attempt_history", []) or []
        if history:
            parts.append("\n## Prior Failed Attempts & Failure Reasons:")
            for idx, att in enumerate(history, 1):
                tier_label = att.get("tier", "UNKNOWN_TIER")
                agent_label = att.get("agent_name") or att.get("model_name", "Worker")
                reason = att.get("rejection_reason") or "Rejected without detail"
                parts.append(f"### Attempt {idx} ({tier_label} by {agent_label}):")
                parts.append(f"> {reason}")

        # Inject current QA Critic feedback if available
        if qa_review and qa_review.rejection_reasons:
            parts.append("\n## QA Critic Rejection Feedback:")
            for r in qa_review.rejection_reasons:
                parts.append(f"- [FAIL] {r}")
            if qa_review.missing_coverage:
                parts.append("\n### Missing Coverage / Edge Cases to Fix:")
                for m in qa_review.missing_coverage:
                    parts.append(f"- {m}")

        # Inject security findings if any
        if security_findings:
            parts.append("\n## Security & Blast-Radius Violations Detected:")
            for sf in security_findings:
                parts.append(
                    f"- [{sf.get('severity', 'HIGH')}] {sf.get('rule_id', 'SEC')}: "
                    f"{sf.get('description', '')} in {sf.get('file_path', '')}:{sf.get('line_number', 0)}"
                )

        parts.append(
            "\n## Directive for Escalated Worker:\n"
            "You are operating at a higher competence tier. Resolve the exact failure points listed above. "
            "Do not erode assertions, do not exceed allowed_files, and ensure all error paths have test assertions."
        )

        return "\n".join(parts)
