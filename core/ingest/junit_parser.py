"""
JUnit XML Artifact Parser
Owner: CIDetectiveAgent & IngestionEngine
Phase: Phase 1 (Universal Artifact Ingestion & Playwright Trace Forensics)

Parses JUnit XML reports produced by Pytest, Jest (jest-junit), Maven/Gradle, Playwright, Go, etc.
Zero external dependencies (uses standard library: xml.etree.ElementTree, re, pathlib).
Security Hardened: Pre-strips <!DOCTYPE and <!ENTITY to prevent XXE injection vulnerabilities.
Pipes all untrusted failure logs through Option 5 One-Way DLP and Prompt Sandbox.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.ingest.models import NormalizedFailure
from core.security.dlp_scrubber import DLPSessionVault
from core.security.prompt_sandbox import PromptSandbox


class JUnitParser:
    """Security-hardened, multi-runner JUnit XML parser."""

    # XXE Sanitizer regexes: Disallow external entities and DTD declarations
    XXE_DOCTYPE_REGEX = re.compile(r"<!DOCTYPE(?:\s+[^[>]+)?(?:\s*\[[\s\S]*?\])?\s*>", re.IGNORECASE)
    XXE_ENTITY_REGEX = re.compile(r"<!ENTITY[\s\S]*?>", re.IGNORECASE)
    CUSTOM_ENTITY_REF_REGEX = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)[a-zA-Z0-9_]+;")

    @classmethod
    def sanitize_xml(cls, raw_xml: str) -> str:
        """Strip DOCTYPE, ENTITY declarations, and undefined entities to eliminate XXE vulnerabilities."""
        no_doctype = cls.XXE_DOCTYPE_REGEX.sub("", raw_xml)
        no_entities = cls.XXE_ENTITY_REGEX.sub("", no_doctype)
        return cls.CUSTOM_ENTITY_REF_REGEX.sub("[XXE_BLOCKED]", no_entities)

    @classmethod
    def parse_file(
        cls,
        xml_path: Union[str, Path],
        dlp_vault: Optional[DLPSessionVault] = None,
    ) -> List[NormalizedFailure]:
        """Parse a JUnit XML file on disk into normalized failures."""
        path = Path(xml_path).resolve()
        if not path.is_file():
            return []

        try:
            raw_content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        return cls.parse_string(raw_content, source_file=str(path), dlp_vault=dlp_vault)

    @classmethod
    def parse_string(
        cls,
        raw_xml: str,
        source_file: str = "junit.xml",
        dlp_vault: Optional[DLPSessionVault] = None,
    ) -> List[NormalizedFailure]:
        """Parse JUnit XML string and return list of NormalizedFailure records."""
        if not raw_xml or not raw_xml.strip():
            return []

        vault = dlp_vault or DLPSessionVault()
        safe_xml = cls.sanitize_xml(raw_xml)

        try:
            root = ET.fromstring(safe_xml)
        except ET.ParseError:
            return []

        failures: List[NormalizedFailure] = []

        # Locate all <testsuite> elements (handles <testsuites><testsuite> and root <testsuite>)
        if root.tag.lower() == "testsuite":
            testsuites = [root]
        elif root.tag.lower() == "testsuites":
            testsuites = root.findall(".//testsuite")
        else:
            testsuites = root.findall(".//testsuite")
            if not testsuites:
                testsuites = [root]

        for suite in testsuites:
            suite_file = suite.attrib.get("file") or suite.attrib.get("filepath") or ""
            for case in suite.findall(".//testcase"):
                fail_elem = case.find("failure")
                error_elem = case.find("error")
                problem_elem = fail_elem if fail_elem is not None else error_elem

                if problem_elem is None:
                    continue  # Passed or skipped test

                raw_status = "failure" if fail_elem is not None else "error"
                case_name = case.attrib.get("name", "unknown_test")
                classname = case.attrib.get("classname", "")
                case_file = case.attrib.get("file") or suite_file

                # Determine file_path and test_node_id across runners (Pytest, Jest, Playwright, JUnit)
                file_path = case_file
                if not file_path:
                    # Check if classname looks like a file path (e.g. "tests/test_api.py" or "e2e.auth.spec.ts")
                    if "/" in classname or "\\" in classname:
                        file_path = classname
                    elif classname.endswith((".py", ".ts", ".js", ".java", ".go")):
                        file_path = classname
                    else:
                        file_path = classname.replace(".", "/") + ".py" if classname else "unknown"

                file_path = file_path.replace("\\", "/")

                # Build canonical test_node_id
                if "::" in case_name:
                    test_node_id = case_name
                elif file_path and file_path != "unknown":
                    test_node_id = f"{file_path}::{case_name}"
                elif classname:
                    test_node_id = f"{classname}::{case_name}"
                else:
                    test_node_id = case_name

                # Line number
                line_val: Optional[int] = None
                if "line" in case.attrib:
                    try:
                        line_val = int(case.attrib["line"])
                    except ValueError:
                        line_val = None

                # Duration
                duration_ms = 0.0
                time_str = case.attrib.get("time") or suite.attrib.get("time")
                if time_str:
                    try:
                        duration_ms = float(time_str) * 1000.0
                    except ValueError:
                        duration_ms = 0.0

                # Extract error message and trace
                error_msg = problem_elem.attrib.get("message", "")
                raw_text = (problem_elem.text or "").strip()
                if not error_msg:
                    first_line = raw_text.splitlines()[0] if raw_text else "Test assertion failed"
                    error_msg = first_line[:200]

                stack_trace = raw_text

                # Detect runner signature
                runner = "junit"
                lower_text = (raw_text + " " + classname + " " + file_path).lower()
                if "pytest" in lower_text or file_path.endswith(".py"):
                    runner = "pytest"
                elif "playwright" in lower_text or ".spec." in file_path:
                    runner = "playwright"
                elif "jest" in lower_text or ".test." in file_path or "__tests__" in file_path:
                    runner = "jest"

                # Option 5 Security: One-Way DLP Scrubbing on runtime trace + Nonce Sandboxing
                scrubbed_msg = vault.scrub_runtime_log(error_msg).scrubbed_text
                scrubbed_trace = vault.scrub_runtime_log(stack_trace).scrubbed_text
                safe_trace_block = PromptSandbox.sandbox_untrusted_data(
                    scrubbed_trace, label="junit_failure_trace"
                ).sandboxed_text

                failure = NormalizedFailure(
                    runner=runner,
                    test_node_id=test_node_id,
                    file_path=file_path,
                    error_message=scrubbed_msg,
                    stack_trace=scrubbed_trace,
                    line=line_val,
                    duration_ms=duration_ms,
                    raw_status=raw_status,
                    sandboxed_trace_block=safe_trace_block,
                )
                failures.append(failure)

        return failures
