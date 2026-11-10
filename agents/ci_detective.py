"""
CI Detective Agent: Triages GitHub Actions Run Failures & Enforces Job Isolation
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CIFailureEvent:
    workflow_name: str
    run_id: str
    job_name: str
    failing_test: str
    error_summary: str
    raw_logs: Optional[str] = None


class CIDetectiveAgent:
    """Investigates CI failures and enforces parallel job isolation rules."""

    @staticmethod
    def parse_webhook_payload(payload: Dict[str, Any]) -> Optional[CIFailureEvent]:
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

            return CIFailureEvent(
                workflow_name=workflow_name,
                run_id=run_id,
                job_name=job_name,
                failing_test=failing_test,
                error_summary=f"Job {job_name} failed in {workflow_name}",
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

            return CIFailureEvent(
                workflow_name=workflow_name,
                run_id=run_id,
                job_name=job_name,
                failing_test=failing_test,
                error_summary=error_summary,
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
