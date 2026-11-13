"""
Common Test Report Format (CTRF) JSON Parser
Owner: CIDetectiveAgent & IngestionEngine
Phase: Phase 1 (Universal Artifact Ingestion & Playwright Trace Forensics)

Parses standard CTRF JSON test reports (emitted by Playwright, Jest, Cypress, Pytest-CTRF, etc.).
Zero external dependencies (uses standard library: json, pathlib, typing).
Pipes untrusted failure traces through Option 5 One-Way DLP and Nonce Prompt Sandbox.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from hermes.core.ingest.models import NormalizedFailure
from hermes.core.security.dlp_scrubber import DLPSessionVault
from hermes.core.security.prompt_sandbox import PromptSandbox


class CTRFParser:
    """Security-hardened parser for standard CTRF JSON test artifacts."""

    @classmethod
    def parse_file(
        cls,
        json_path: Union[str, Path],
        dlp_vault: Optional[DLPSessionVault] = None,
    ) -> List[NormalizedFailure]:
        """Parse a CTRF JSON file on disk into normalized failures."""
        path = Path(json_path).resolve()
        if not path.is_file():
            return []

        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        return cls.parse_string(raw_text, source_file=str(path), dlp_vault=dlp_vault)

    @classmethod
    def parse_string(
        cls,
        raw_json: str,
        source_file: str = "ctrf-report.json",
        dlp_vault: Optional[DLPSessionVault] = None,
    ) -> List[NormalizedFailure]:
        """Parse CTRF JSON string and extract failing test records."""
        if not raw_json or not raw_json.strip():
            return []

        vault = dlp_vault or DLPSessionVault()

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, dict):
            return []

        # CTRF schema: root -> results -> tests[] or top-level tests[]
        results = data.get("results") if isinstance(data.get("results"), dict) else data
        tests = results.get("tests", [])
        if not isinstance(tests, list):
            return []

        # Tool runner hint
        tool_info = results.get("tool", {}) if isinstance(results.get("tool"), dict) else {}
        default_runner = tool_info.get("name", "ctrf").lower()

        failures: List[NormalizedFailure] = []

        for t in tests:
            if not isinstance(t, dict):
                continue

            status = str(t.get("status", "")).lower()
            if status not in ("failed", "broken", "error"):
                continue

            name = str(t.get("name", "unnamed_test"))
            file_path = str(t.get("filePath", "") or t.get("file", "")).replace("\\", "/")
            raw_status = str(t.get("rawStatus", status))
            duration_ms = float(t.get("duration", 0.0))
            retries = int(t.get("retries", 0))

            line_val: Optional[int] = None
            if "line" in t:
                try:
                    line_val = int(t["line"])
                except (ValueError, TypeError):
                    line_val = None

            error_msg = str(t.get("message", "") or "")
            stack_trace = str(t.get("trace", "") or "")

            if not error_msg and stack_trace:
                error_msg = stack_trace.splitlines()[0][:200]
            if not error_msg:
                error_msg = f"CTRF Test '{name}' failed"

            # Determine test_node_id
            if file_path and file_path not in name:
                test_node_id = f"{file_path}::{name}"
            else:
                test_node_id = name

            # Runner detection
            runner = default_runner
            if file_path.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js")):
                runner = "playwright"
            elif file_path.endswith(".py"):
                runner = "pytest"

            # Option 5 Security: One-Way DLP Scrubbing on runtime logs + Nonce Sandboxing
            scrubbed_msg = vault.scrub_runtime_log(error_msg).scrubbed_text
            scrubbed_trace = vault.scrub_runtime_log(stack_trace).scrubbed_text
            sandboxed_trace = PromptSandbox.sandbox_untrusted_data(
                scrubbed_trace, label="ctrf_failure_trace"
            ).sandboxed_text

            failure = NormalizedFailure(
                runner=runner,
                test_node_id=test_node_id,
                file_path=file_path or "unknown",
                error_message=scrubbed_msg,
                stack_trace=scrubbed_trace,
                line=line_val,
                duration_ms=duration_ms,
                retries=retries,
                raw_status=raw_status,
                sandboxed_trace_block=sandboxed_trace,
            )
            failures.append(failure)

        return failures

