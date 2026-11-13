"""
GAP-16: Proactive Story & Reactive CI Traceback / JUnit XML Ingestor
Owner: RequirementsAgent (TIER_2)

Features:
- PytestTracebackParser: Extracts failing test node IDs, file paths, line numbers, and exceptions from pytest logs.
- JUnitXMLIngestor: Parses standard JUnit XML test reports to extract failing testcases and stacktraces.
- Automatic population of SubTaskTicket.allowed_files from failure stacktraces.
- Story & Traceback Decomposition into deterministic AC-1..N, EC-1..N, and context slices.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from context_slicer import ContextSlicer, PytestFixtureIndexer


@dataclass
class FailureFrame:
    file_path: str
    line_number: int
    function_name: str
    code_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedFailure:
    test_node_id: str
    test_file: str
    offending_files: List[str]
    exception_type: str
    error_message: str
    frames: List[FailureFrame] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PytestTracebackParser:
    """Parses real pytest terminal logs and stack traces into structured failure objects."""

    # Matches: File "path/to/file.py", line 123, in function_name
    FRAME_PATTERN = re.compile(
        r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>\w+))?', re.MULTILINE
    )

    # Matches: tests/test_calc.py:42: AssertionError: assert 1 == 2 or Failed: ...
    ASSERT_PATTERN = re.compile(
        r"(?P<file>[A-Za-z0-9_\-/\\]+\.py):(?P<line>\d+):\s*(?P<exc>[A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception|AssertionError|Failed)(?::\s*(?P<msg>.*))?",
        re.MULTILINE,
    )

    # Matches: FAILED tests/test_ledger.py::test_deposit_negative
    FAILED_LINE_PATTERN = re.compile(
        r"FAILED\s+(?P<file>[A-Za-z0-9_\-/\\]+\.py)::(?P<name>[A-Za-z0-9_\[\]\-]+)",
        re.MULTILINE,
    )

    # Matches pytest failure header: ____ test_name ____
    TEST_HEADER_PATTERN = re.compile(r"^_{3,}\s*(?P<name>[A-Za-z0-9_\[\]\-\.\:]+)\s*_{3,}$", re.MULTILINE)

    @classmethod
    def parse(cls, output: str) -> List[ParsedFailure]:
        """Extract structured failures from pytest output."""
        failures: List[ParsedFailure] = []

        # Find frames
        frames: List[FailureFrame] = []
        offending_set: Set[str] = set()
        test_file = ""

        for m in cls.FRAME_PATTERN.finditer(output):
            f_path = m.group("file").replace("\\", "/")
            l_num = int(m.group("line"))
            func = m.group("func") or ""
            frames.append(FailureFrame(file_path=f_path, line_number=l_num, function_name=func))
            if "site-packages" not in f_path and not f_path.startswith("<"):
                offending_set.add(f_path)
                if "test" in f_path.lower() and not test_file:
                    test_file = f_path

        # Find assertion / failure lines
        exc_type = "AssertionError"
        err_msg = "Test assertion failed"

        for m in cls.ASSERT_PATTERN.finditer(output):
            f_path = m.group("file").replace("\\", "/")
            exc_type = m.group("exc")
            err_msg = (m.group("msg") or "").strip()
            offending_set.add(f_path)
            if "test" in f_path.lower():
                test_file = f_path

        for m in cls.FAILED_LINE_PATTERN.finditer(output):
            f_path = m.group("file").replace("\\", "/")
            offending_set.add(f_path)
            if not test_file:
                test_file = f_path

        # Find test node header
        test_node_id = "test_run"
        header_match = cls.TEST_HEADER_PATTERN.search(output)
        if header_match:
            test_node_id = header_match.group("name")
        elif test_file:
            test_node_id = test_file

        if offending_set or frames or "FAILED" in output or "ERROR" in output:
            failures.append(
                ParsedFailure(
                    test_node_id=test_node_id,
                    test_file=test_file or (list(offending_set)[0] if offending_set else "tests/test_unknown.py"),
                    offending_files=sorted(list(offending_set)),
                    exception_type=exc_type,
                    error_message=err_msg,
                    frames=frames,
                    raw_output=output[:4000],
                )
            )

        return failures


class JUnitXMLIngestor:
    """Parses JUnit XML report files into structured test failure records."""

    @classmethod
    def parse_xml_string(cls, xml_text: str) -> List[ParsedFailure]:
        """Parse JUnit XML string."""
        failures: List[ParsedFailure] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return failures

        # Handle testsuite or testsuites root
        testcases = root.findall(".//testcase")
        for tc in testcases:
            failure_node = tc.find("failure")
            error_node = tc.find("error")
            target_node = failure_node if failure_node is not None else error_node

            if target_node is not None:
                classname = tc.get("classname", "")
                name = tc.get("name", "")
                node_id = f"{classname}::{name}" if classname else name
                msg = target_node.get("message", "")
                exc_type = target_node.get("type") or target_node.get("message") or "AssertionError"
                body_text = target_node.text or ""

                # Extract file paths from classname or body
                offending: List[str] = []
                test_file = ""
                file_match = re.search(r"([A-Za-z0-9_\-/\\]+\.py)", body_text)
                if file_match:
                    f_clean = file_match.group(1).replace("\\", "/")
                    offending.append(f_clean)
                    test_file = f_clean

                failures.append(
                    ParsedFailure(
                        test_node_id=node_id,
                        test_file=test_file or "tests/test_suite.py",
                        offending_files=offending,
                        exception_type=exc_type,
                        error_message=msg,
                        raw_output=body_text[:2000],
                    )
                )

        return failures

    @classmethod
    def parse_file(cls, xml_path: Path | str) -> List[ParsedFailure]:
        """Read and parse a JUnit XML file on disk."""
        p = Path(xml_path).resolve()
        if not p.is_file():
            return []
        try:
            return cls.parse_xml_string(p.read_text(encoding="utf-8"))
        except Exception:
            return []


class CIFailureIngestor:
    """Decomposes CI failures or user stories into structured sprint context and allowed_files."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def ingest_failure_output(
        self,
        output_or_xml: str,
        is_xml: bool = False,
    ) -> Dict[str, Any]:
        """Ingest failure text or XML and generate structured ticket context."""
        if is_xml or output_or_xml.strip().startswith("<?xml") or "<testsuite" in output_or_xml:
            failures = JUnitXMLIngestor.parse_xml_string(output_or_xml)
        else:
            failures = PytestTracebackParser.parse(output_or_xml)

        allowed_files: Set[str] = set()
        diagnostics: List[Dict[str, Any]] = []

        for f in failures:
            diagnostics.append(f.to_dict())
            candidates = [f.test_file] + f.offending_files
            for raw_p in candidates:
                if not raw_p:
                    continue
                clean = raw_p.replace("\\", "/").lstrip("/")
                if (self.workspace_root / clean).is_file():
                    allowed_files.add(clean)
                else:
                    base = Path(clean).name
                    for m in self.workspace_root.rglob(base):
                        if m.is_file() and not any(part.startswith(".") for part in m.parts):
                            allowed_files.add(str(m.relative_to(self.workspace_root)).replace("\\", "/"))

        # Automatically resolve direct imported neighbors of test files
        for f in list(allowed_files):
            if "test" in f.lower():
                neighbors = ContextSlicer.resolve_imports_to_files(self.workspace_root, f)
                for n in neighbors:
                    if n.is_file():
                        allowed_files.add(str(n.relative_to(self.workspace_root)).replace("\\", "/"))

        # Default fallback if allowed_files is empty
        if not allowed_files:
            allowed_files.add("tests/test_calc.py")

        # Decompose into Acceptance Criteria and Edge Cases
        acs = [
            f"AC-1: Resolve {f.exception_type} in {f.test_node_id} ({f.error_message[:60]})"
            for f in failures
        ] or ["AC-1: Resolve test suite failures and restore 100% pass rate."]
        acs.append("AC-2: Preserve all existing test assertions (Zero Assertion Erosion).")

        ecs = [
            "EC-1: Verify negative and boundary inputs do not raise unhandled exceptions.",
            "EC-2: Verify idempotency across multi-run sandbox executions.",
        ]

        # Context slicing and fixture indexing
        context_slice = ContextSlicer.build_sliced_context(
            workspace_root=self.workspace_root,
            target_files=list(allowed_files),
            max_context_tokens=2500,
        )

        return {
            "source": "ci_failure",
            "failures": diagnostics,
            "allowed_files": sorted(list(allowed_files)),
            "acceptance_criteria": acs,
            "edge_cases": ecs,
            "context_slice": context_slice,
        }

    def ingest_user_story(
        self,
        story: str,
        target_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Convert a proactive user story into structured Acceptance Criteria and Edge Cases."""
        allowed = target_scope or ["src/main.py", "tests/test_main.py"]
        normalized_allowed = [p.replace("\\", "/").lstrip("/") for p in allowed]

        acs = [
            f"AC-1: Implement functionality: {story.strip().splitlines()[0][:100]}",
            "AC-2: Author unit tests with verifiable assertions covering all happy paths.",
            "AC-3: Maintain constant-time crypto and safe parameter handling.",
        ]
        ecs = [
            "EC-1: Handle invalid or unexpected data types gracefully.",
            "EC-2: Reject negative boundary conditions with clear exceptions.",
        ]

        high_risk = any(
            k in story.lower() or any(k in f.lower() for f in normalized_allowed)
            for k in ("auth", "secret", "token", "crypto", "sql", "shell", "exec")
        )

        context_slice = ContextSlicer.build_sliced_context(
            workspace_root=self.workspace_root,
            target_files=normalized_allowed,
            max_context_tokens=2500,
        )

        return {
            "source": "user_story",
            "story": story,
            "allowed_files": normalized_allowed,
            "acceptance_criteria": acs,
            "edge_cases": ecs,
            "high_risk": high_risk,
            "context_slice": context_slice,
        }
