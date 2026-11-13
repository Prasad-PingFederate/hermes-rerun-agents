"""
CI Detective Agent: Triages GitHub Actions Run Failures, Enforces Job Isolation,
and Resolves Commit & PR Intent for Deterministic Failure Classification.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class CIFailureEvent:
    workflow_name: str
    run_id: str
    job_name: str
    failing_test: str
    error_summary: str
    raw_logs: Optional[str] = None
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    commit_messages: List[str] = field(default_factory=list)
    intent_context: Dict[str, Any] = field(default_factory=dict)


class CIDetectiveAgent:
    """Investigates CI failures, extracts commit/PR intent, and enforces parallel job isolation rules."""

    # Patterns indicating deliberate contract / feature / API updates
    INTENTIONAL_CHANGE_PATTERNS = [
        re.compile(r"\bfeat(?:ure)?(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\brefactor(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bbreaking(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bupdate(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bchange(?:d)?(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\brename(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bstatus\s+(?:from\s+)?\d+\s+to\s+\d+", re.IGNORECASE),
        re.compile(r"\b(?:api|contract|schema|response)\s+(?:drift|change|update|redesign|migration)", re.IGNORECASE),
        re.compile(r"\bnew\s+(?:status|endpoint|response|behavior|format|payload)", re.IGNORECASE),
    ]

    # Patterns indicating standard bugfixes or maintenance (should NOT drift tests)
    MAINTENANCE_PATTERNS = [
        re.compile(r"\bfix(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bbug(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bchore(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bdocs(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bperf(?:\([^)]*\))?:", re.IGNORECASE),
        re.compile(r"\bci(?:\([^)]*\))?:", re.IGNORECASE),
    ]

    @classmethod
    def extract_commit_and_pr_intent(
        cls,
        workspace_path: Optional[Union[Path, str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ingests git log -n 5 alongside optional PR title/body metadata.

        Gracefully handles the GitHub Actions shallow-clone trap (fetch-depth: 1)
        by falling back to webhook payload commit messages, PR title, and PR body.
        """
        commits: List[str] = []
        is_shallow = False
        ws = Path(workspace_path).resolve() if workspace_path else None

        # 1. Attempt git log -n 5 in workspace
        if ws and (ws / ".git").exists():
            try:
                # Check for shallow repository
                shallow_file = ws / ".git" / "shallow"
                if shallow_file.is_file():
                    is_shallow = True

                res = subprocess.run(
                    ["git", "log", "-n", "5", "--pretty=format:%s%n%b---HERMES_COMMIT_DELIM---"],
                    cwd=str(ws),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    raw_chunks = res.stdout.split("---HERMES_COMMIT_DELIM---")
                    for c in raw_chunks:
                        msg = c.strip()
                        if msg:
                            commits.append(msg)
                    if len(commits) <= 1:
                        is_shallow = True
            except Exception:
                is_shallow = True

        # 2. Extract PR title and body from webhook payload
        payload = payload or {}
        pr_data = {}
        if isinstance(payload.get("pull_request"), dict):
            pr_data = payload["pull_request"]
        elif payload.get("workflow_run", {}).get("pull_requests"):
            pr_data = payload["workflow_run"]["pull_requests"][0]
        elif payload.get("check_run", {}).get("check_suite", {}).get("pull_requests"):
            pr_data = payload["check_run"]["check_suite"]["pull_requests"][0]

        pr_title = str(pr_data.get("title") or "")
        pr_body = str(pr_data.get("body") or "")

        # 3. Webhook commits fallback for shallow clones
        if is_shallow or not commits:
            for c_obj in payload.get("commits", []):
                msg = c_obj.get("message", "").strip()
                if msg and msg not in commits:
                    commits.append(msg)
            # Head commit in workflow_run
            head_c = payload.get("workflow_run", {}).get("head_commit", {}).get("message") or payload.get("head_commit", {}).get("message")
            if head_c and head_c.strip() and head_c.strip() not in commits:
                commits.insert(0, head_c.strip())

        # 4. Analyze combined intent signals
        all_context_text = "\n".join(commits + [pr_title, pr_body]).strip()

        has_intentional_contract_change = False
        matching_intent_signals: List[str] = []

        for pat in cls.INTENTIONAL_CHANGE_PATTERNS:
            match = pat.search(all_context_text)
            if match:
                has_intentional_contract_change = True
                matching_intent_signals.append(match.group(0).strip())

        is_maintenance = False
        for pat in cls.MAINTENANCE_PATTERNS:
            if pat.search(all_context_text):
                is_maintenance = True
                break

        # If maintenance pattern (e.g. fix:) is explicit and no breaking/feat signal, suppress contract drift
        if is_maintenance and not any("breaking" in s.lower() or "status" in s.lower() for s in matching_intent_signals):
            has_intentional_contract_change = False

        intent_summary = "Intentional contract/feature update detected" if has_intentional_contract_change else "Regression/maintenance or neutral intent"

        return {
            "commits": commits,
            "pr_title": pr_title,
            "pr_body": pr_body,
            "is_shallow": is_shallow,
            "has_intentional_contract_change": has_intentional_contract_change,
            "intent_signals": matching_intent_signals,
            "intent_summary": intent_summary,
        }

    @classmethod
    def classify_failure_with_intent(
        cls,
        combined_output: str,
        intent_context: Optional[Dict[str, Any]] = None,
        workspace_path: Optional[Union[Path, str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Deterministically classifies test failures into 5 categories, factoring in commit and PR intent.

        Categories:
        - PASSED: Clean run
        - FLAKY_TEST: Intermittent timing/ordering
        - ENVIRONMENT_NOISE: Network, port, missing dependencies, external services
        - TEST_BUG: Assertion failures caused by intentional API/contract drift, obsolete tests, or test fixtures
        - PRODUCT_BUG: Unexpected application bugs, crashes, or unhandled exceptions in product code
        """
        # Auto-extract intent if not provided
        if intent_context is None and (workspace_path or payload):
            intent_context = cls.extract_commit_and_pr_intent(workspace_path=workspace_path, payload=payload)

        # 1. Environment Noise patterns (network, port, permissions, missing binaries)
        env_patterns = [
            r"ConnectionRefusedError",
            r"address already in use",
            r"No such file or directory: '.*(?:node|git|docker|playwright|npm|yarn)'",
            r"PermissionError",
            r"ENOSPC",
            r"EADDRINUSE",
            r"timed out after \d+ seconds",
            r"NetworkError",
            r"socket\.gaierror",
        ]
        for pattern in env_patterns:
            if re.search(pattern, combined_output, re.IGNORECASE):
                if "AssertionError" not in combined_output:
                    return "ENVIRONMENT_NOISE"

        # 2. Check for Assertion Mismatch / Drift in output
        assertion_mismatch_patterns = [
            r"AssertionError",
            r"assert .* == .*",
            r"assert .*\.status_code\s*==\s*\d+",
            r"expect\(.*\)\.to",
            r"Expected: .*\nReceived:",
            r"Expected status \d+, received \d+",
            r"FAILED tests/.* - AssertionError",
        ]
        has_assertion_mismatch = any(re.search(pat, combined_output, re.IGNORECASE) for pat in assertion_mismatch_patterns)

        # Check for unhandled exceptions in product code
        unhandled_product_crash_patterns = [
            r"AttributeError: '.*' object has no attribute",
            r"KeyError: '.*'",
            r"TypeError: .* missing \d+ required",
            r"ZeroDivisionError",
            r"IndexError: list index out of range",
            r"NullPointerException",
            r"ReferenceError: .* is not defined",
            r"TypeError: Cannot read propert",
        ]
        has_unhandled_product_crash = any(re.search(pat, combined_output) for pat in unhandled_product_crash_patterns)

        # 3. Intentional Contract Change -> TEST_BUG (Assertion Drift)
        if intent_context and intent_context.get("has_intentional_contract_change"):
            # If developer changed API/status code and assertion failed, it's assertion drift (TEST_BUG)
            if has_assertion_mismatch and not has_unhandled_product_crash:
                return "TEST_BUG"

        # 4. Check product code frames in traceback
        has_product_frames = bool(
            re.search(r'File "[^"]*(?:src|core|app|lib|pkg)[/\\].*?\.py", line \d+', combined_output, re.IGNORECASE)
            or re.search(r'(?:src|core|app|lib|pkg)[/\\].*?\.py:\d+', combined_output, re.IGNORECASE)
            or re.search(r'(?:^|\n)\s*(?!tests?[/\\_])[a-zA-Z0-9_-]+\.py:\d+:', combined_output, re.IGNORECASE)
        )
        did_not_raise = bool(re.search(r"DID NOT RAISE", combined_output))

        if has_product_frames or did_not_raise or has_unhandled_product_crash:
            # If not an import error inside the test file itself
            if not re.search(r'ImportError: cannot import name .* from', combined_output):
                return "PRODUCT_BUG"

        # 5. Default to TEST_BUG if assertion error or fixture issue
        test_bug_patterns = [
            r"AssertionError",
            r"assert .* == .*",
            r"FixtureLookupError",
            r"Failed: .* fixture",
            r"tests/.*\.py:\d+: AssertionError",
            r"test_.*\.py:\d+: AssertionError",
            r"expect\(.*\)\.to",
            r"ImportError: cannot import name",
        ]
        for pattern in test_bug_patterns:
            if re.search(pattern, combined_output, re.IGNORECASE):
                return "TEST_BUG"

        if has_product_frames:
            return "PRODUCT_BUG"

        return "TEST_BUG"

    @classmethod
    def parse_webhook_payload(cls, payload: Dict[str, Any]) -> Optional[CIFailureEvent]:
        """Extract failure information from GitHub Actions webhook payload (workflow_job or workflow_run)."""
        # Case 1: workflow_job event
        if "workflow_job" in payload:
            wj = payload.get("workflow_job", {})
            conclusion = wj.get("conclusion")
            if conclusion != "failure":
                return None

            run_id = str(wj.get("run_id") or wj.get("id", "unknown"))
            workflow_name = wj.get("workflow_name", "Unknown Workflow")
            job_name = wj.get("name", "Unknown Job")

            failing_test = "Unknown Test"
            # Inspect steps
            for step in wj.get("steps", []):
                s_name = step.get("name", "")
                if ".py" in s_name:
                    for part in s_name.split():
                        clean_part = part.strip(":,;'\"")
                        if clean_part.endswith(".py"):
                            failing_test = clean_part
                            break
                if failing_test != "Unknown Test":
                    break

            # Inspect job name if step didn't reveal test
            if failing_test == "Unknown Test" and ".py" in job_name:
                for part in job_name.split():
                    clean_part = part.strip(":,;'\"")
                    if clean_part.endswith(".py"):
                        failing_test = clean_part
                        break

            intent = cls.extract_commit_and_pr_intent(payload=payload)
            return CIFailureEvent(
                workflow_name=workflow_name,
                run_id=run_id,
                job_name=job_name,
                failing_test=failing_test,
                error_summary=f"Job {job_name} failed in {workflow_name}",
                pr_title=intent.get("pr_title"),
                pr_body=intent.get("pr_body"),
                commit_messages=intent.get("commits", []),
                intent_context=intent,
            )

        # Case 2: workflow_run event
        if "workflow_run" in payload:
            workflow_run = payload.get("workflow_run", {})
            conclusion = workflow_run.get("conclusion")
            if conclusion != "failure":
                return None

            run_id = str(workflow_run.get("id", "unknown"))
            workflow_name = workflow_run.get("name", "Unknown Workflow")

            check_run = payload.get("check_run", {})
            job_name = check_run.get("name", "Unknown Job")
            output = check_run.get("output", {})
            error_summary = output.get("summary") or output.get("text") or "CI Run Failed"

            failing_test = "Unknown Test"
            for line in error_summary.splitlines():
                if "FAILED" in line and ".py" in line:
                    parts = line.split("FAILED")
                    if len(parts) > 1:
                        target = parts[1].strip().split()[0]
                        failing_test = target.split("::")[0].strip()
                        break

            if failing_test == "Unknown Test":
                for job in payload.get("jobs", []):
                    j_name = job.get("name", "")
                    if ".py" in j_name:
                        for part in j_name.split():
                            clean_part = part.strip(":,;'\"")
                            if clean_part.endswith(".py"):
                                failing_test = clean_part
                                break

            intent = cls.extract_commit_and_pr_intent(payload=payload)
            return CIFailureEvent(
                workflow_name=workflow_name,
                run_id=run_id,
                job_name=job_name,
                failing_test=failing_test,
                error_summary=error_summary,
                pr_title=intent.get("pr_title"),
                pr_body=intent.get("pr_body"),
                commit_messages=intent.get("commits", []),
                intent_context=intent,
            )

        return None

    @staticmethod
    def get_recommended_ci_routing(test_file_basename: str) -> Dict[str, Any]:
        """Enforces job isolation rules so critical prerequisites stay pure."""
        if test_file_basename.startswith("A_"):
            return {
                "target_job": "registration",
                "is_critical_prerequisite": True,
                "continue_on_error": False,
                "reason": "Pure account provisioning required for parallel vault runs.",
            }
        elif "Responder_Signup" in test_file_basename or "Subscriber" in test_file_basename:
            return {
                "target_job": "rolebased-subscribers",
                "is_critical_prerequisite": False,
                "continue_on_error": True,
                "reason": "Preview/subscriber test with external network dependencies.",
            }
        elif "TrustedHelper" in test_file_basename:
            return {
                "target_job": "rolebased-trusted-helpers",
                "is_critical_prerequisite": False,
                "continue_on_error": True,
                "reason": "Trusted helper role tests.",
            }
        return {
            "target_job": "functional-vaults",
            "is_critical_prerequisite": False,
            "continue_on_error": True,
            "reason": "Standard vault test execution.",
        }
