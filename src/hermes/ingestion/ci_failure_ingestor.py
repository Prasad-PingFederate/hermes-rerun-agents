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

from hermes.ingestion.context_slicer import ContextSlicer, PytestFixtureIndexer


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
    dom_excerpt: Optional[str] = None
    failed_selector: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DOMLocatorHints:
    failed_selector: Optional[str] = None
    candidate_selector: Optional[str] = None
    dom_snippet: Optional[str] = None
    aka_locator: Optional[str] = None
    all_candidates: List[str] = field(default_factory=list)

    def to_prompt_str(self) -> str:
        lines = []
        if self.failed_selector:
            lines.append(f"Failed Locator / Selector: {self.failed_selector}")
        if self.candidate_selector:
            lines.append(f"Recommended Updated Locator: {self.candidate_selector}")
        if self.aka_locator:
            lines.append(f"Playwright Alternative Suggestion: {self.aka_locator}")
        if self.all_candidates:
            lines.append(f"Available DOM Elements / TestIds: {', '.join(self.all_candidates)}")
        if self.dom_snippet:
            lines.append(f"DOM Snapshot Excerpt:\n{self.dom_snippet}")
        return "\n".join(lines)


class DOMLocatorForensicsExtractor:
    """Extracts failed selectors, DOM snapshots, and locator recommendations from error logs & traces."""

    LOCATOR_PATTERNS = [
        re.compile(r"waiting for locator\((?P<q>['\"])(?P<sel>.*?)(?P=q)\)", re.IGNORECASE),
        re.compile(r"locator\((?P<q>['\"])(?P<sel>.*?)(?P=q)\)\.(?:click|fill|check|waitFor)", re.IGNORECASE),
        re.compile(r"strict mode violation:\s*locator\((?P<q>['\"])(?P<sel>.*?)(?P=q)\)", re.IGNORECASE),
    ]
    TESTID_RE = re.compile(r'data-test(?:id|-id)=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
    ROLE_RE = re.compile(r'aka ((?:getByRole|getByText|getByTestId|getByLabel)\([^\)]+\))', re.IGNORECASE)

    @classmethod
    def extract(cls, text: str, dom_excerpt: Optional[str] = None) -> DOMLocatorHints:
        failed_sel: Optional[str] = None
        cand_sel: Optional[str] = None
        aka_loc: Optional[str] = None
        candidates: List[str] = []

        combined = f"{text}\n{dom_excerpt or ''}"

        # 1. Extract failed locator
        for pat in cls.LOCATOR_PATTERNS:
            m = pat.search(text)
            if m:
                failed_sel = m.group("sel")
                break

        # 2. Extract aka Playwright suggestions
        m_aka = cls.ROLE_RE.search(text)
        if m_aka:
            aka_loc = m_aka.group(1)

        # 3. Extract testids from DOM excerpt or error text
        testids = cls.TESTID_RE.findall(combined)
        for tid in testids:
            sel = f'[data-testid="{tid}"]'
            if sel not in candidates:
                candidates.append(sel)
            if not cand_sel and failed_sel and tid not in failed_sel:
                cand_sel = sel

        # Fallback candidate if cand_sel is not set but candidates exist
        if not cand_sel and candidates:
            for c in candidates:
                if not failed_sel or c != failed_sel:
                    cand_sel = c
                    break

        return DOMLocatorHints(
            failed_selector=failed_sel,
            candidate_selector=cand_sel or (candidates[0] if candidates else None),
            dom_snippet=dom_excerpt,
            aka_locator=aka_loc,
            all_candidates=candidates,
        )


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

    # Matches pytest traceback frame: Test_Suite3\Logout_Playwright.py:152: in test_tc02
    IN_FRAME_PATTERN = re.compile(
        r"^(?P<file>[A-Za-z0-9_\-./\\]+\.(?:py|ts|js)):(?P<line>\d+):\s+in\s+(?P<func>[A-Za-z0-9_]+)",
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

        for m in cls.IN_FRAME_PATTERN.finditer(output):
            f_path = m.group("file").replace("\\", "/")
            frames.append(FailureFrame(file_path=f_path, line_number=int(m.group("line")), function_name=m.group("func")))
            offending_set.add(f_path)
            if not test_file:
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

                # Extract file paths and frames from classname or body
                frames = PytestTracebackParser.parse_frames(body_text)
                offending: List[str] = [fr.file_path for fr in frames]
                test_file = ""
                file_match = re.search(r"([A-Za-z0-9_\-/\\]+\.(?:py|ts|js))", body_text)
                if file_match:
                    f_clean = file_match.group(1).replace("\\", "/")
                    if f_clean not in offending:
                        offending.append(f_clean)
                    test_file = f_clean
                elif frames:
                    test_file = frames[0].file_path

                failures.append(
                    ParsedFailure(
                        test_node_id=node_id,
                        test_file=test_file or "tests/test_suite.py",
                        offending_files=offending,
                        exception_type=exc_type,
                        error_message=msg,
                        frames=frames,
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

    def resolve_to_workspace(self, raw_path: str) -> str:
        """Resolve any artifact path (relative, host absolute, or container absolute) to workspace-relative path."""
        if not raw_path:
            return ""
        clean = raw_path.replace("\\", "/").strip()
        clean_rel = clean.lstrip("/")

        # Direct relative check
        if (self.workspace_root / clean_rel).is_file():
            return clean_rel

        # If clean is an absolute path that is inside workspace_root
        p_obj = Path(clean)
        if p_obj.is_absolute():
            try:
                rel = p_obj.resolve().relative_to(self.workspace_root)
                return str(rel).replace("\\", "/")
            except ValueError:
                pass

        # Subpath suffix matching (e.g. /home/runner/work/repo/repo/tests/test_x.py -> tests/test_x.py)
        parts = p_obj.parts if p_obj.is_absolute() else clean_rel.split("/")
        for idx in range(len(parts)):
            sub = Path(*parts[idx:])
            if (self.workspace_root / sub).is_file():
                return str(sub).replace("\\", "/")

        # Check classname with dots converted to slashes: tests.test_api -> tests/test_api.py
        if "." in clean and not any(clean.endswith(ext) for ext in (".py", ".ts", ".js", ".java", ".go", ".cs")):
            candidate_py = clean.replace(".", "/") + ".py"
            if (self.workspace_root / candidate_py).is_file():
                return candidate_py

        # Match by filename (or classname.py) within workspace_root
        filename = p_obj.name
        if filename:
            candidates = [filename] if "." in filename else [filename, f"{filename}.py", f"{filename}.ts", f"{filename}.js"]
            for cand_name in candidates:
                for match in self.workspace_root.rglob(cand_name):
                    if match.is_file() and not any(part.startswith(".") for part in match.parts):
                        return str(match.relative_to(self.workspace_root)).replace("\\", "/")

        return clean_rel

    def ingest_failure_output(
        self,
        output_or_xml: str,
        is_xml: bool = False,
        dom_excerpt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest failure text or XML and generate structured ticket context with DOM locator hints."""
        if is_xml or output_or_xml.strip().startswith("<?xml") or "<testsuite" in output_or_xml:
            failures = JUnitXMLIngestor.parse_xml_string(output_or_xml)
        else:
            failures = PytestTracebackParser.parse(output_or_xml)

        allowed_files: Set[str] = set()
        diagnostics: List[Dict[str, Any]] = []

        # Extract DOM and Locator forensics
        dom_hints = DOMLocatorForensicsExtractor.extract(output_or_xml, dom_excerpt=dom_excerpt)

        for f in failures:
            diagnostics.append(f.to_dict())
            candidates = [f.test_file] + f.offending_files
            for raw_p in candidates:
                if not raw_p:
                    continue
                resolved = self.resolve_to_workspace(raw_p)
                if resolved and (self.workspace_root / resolved).is_file():
                    allowed_files.add(resolved)

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

        if dom_hints.failed_selector and dom_hints.candidate_selector:
            acs.append(
                f"AC-3: Update drifted locator '{dom_hints.failed_selector}' to target '{dom_hints.candidate_selector}'."
            )

        ecs = [
            "EC-1: Verify negative and boundary inputs do not raise unhandled exceptions.",
            "EC-2: Verify idempotency across multi-run sandbox executions.",
        ]

        # Context slicing and fixture indexing with DOM context
        context_slice = ContextSlicer.build_sliced_context(
            workspace_root=self.workspace_root,
            target_files=list(allowed_files),
            max_context_tokens=2500,
            dom_context=dom_hints.to_prompt_str() if dom_hints.candidate_selector or dom_hints.dom_snippet else None,
        )

        return {
            "source": "ci_failure",
            "failures": diagnostics,
            "allowed_files": sorted(list(allowed_files)),
            "acceptance_criteria": acs,
            "edge_cases": ecs,
            "context_slice": context_slice,
            "dom_locator_hints": dom_hints.to_prompt_str(),
        }

    def ingest_artifacts(
        self,
        patterns: Union[str, List[str]],
        cluster_shards: bool = True,
    ) -> Dict[str, Any]:
        """Discover, ingest, and cluster test artifacts (JUnit XML, CTRF JSON, Playwright trace.zip)."""
        from hermes.core.ingest.artifact_loader import ArtifactLoader
        from hermes.core.scale.shard_clusterer import ShardClusterer

        normalized_failures = ArtifactLoader.load_artifacts(patterns, workspace_root=self.workspace_root)

        parsed_failures: List[ParsedFailure] = []
        collected_dom_excerpts: List[str] = []
        combined_logs_list: List[str] = []

        for nf in normalized_failures:
            resolved_test_file = self.resolve_to_workspace(nf.test_file)
            if nf.dom_excerpt:
                collected_dom_excerpts.append(nf.dom_excerpt)

            raw_trace = nf.stack_trace or nf.error_message or ""
            combined_logs_list.append(f"{nf.error_message}\n{raw_trace}")

            dom_h = DOMLocatorForensicsExtractor.extract(
                f"{nf.error_message}\n{raw_trace}",
                dom_excerpt=nf.dom_excerpt
            )

            parsed_failures.append(ParsedFailure(
                test_file=resolved_test_file or "tests/test_unknown.py",
                test_node_id=nf.test_id,
                exception_type=nf.category or "AssertionError",
                error_message=nf.error_message,
                offending_files=[resolved_test_file] if resolved_test_file else [],
                frames=[FailureFrame(file_path=resolved_test_file or "", line_number=nf.line_number or 1, code_line=raw_trace[:120], function_name="")],
                raw_output=raw_trace,
                dom_excerpt=nf.dom_excerpt,
                failed_selector=dom_h.failed_selector,
            ))

        clusters = []
        if cluster_shards and normalized_failures:
            clusters = ShardClusterer.cluster_failures([f.to_dict() for f in normalized_failures])

        combined_logs = "\n\n".join(combined_logs_list) if combined_logs_list else "Artifact test failure"
        combined_dom = "\n---\n".join(collected_dom_excerpts) if collected_dom_excerpts else None

        res = self.ingest_failure_output(combined_logs, dom_excerpt=combined_dom)
        res["source"] = "multi_format_artifacts"
        res["normalized_failures"] = [f.to_dict() for f in normalized_failures]
        res["parsed_failures"] = [f.to_dict() for f in parsed_failures]
        res["clusters"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in clusters]
        res["summary"] = combined_logs[:800]

        # Ensure all resolved files from artifacts are in allowed_files
        for pf in parsed_failures:
            if pf.test_file and (self.workspace_root / pf.test_file).is_file():
                if pf.test_file not in res["allowed_files"]:
                    res["allowed_files"].append(pf.test_file)
        res["allowed_files"] = sorted(list(set(res["allowed_files"])))

        return res

    def resolve_failure_intent(
        self,
        workspace_path: Optional[Path | str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Inspect recent git commits and PR intent to differentiate Intentional Drift from Code Regressions."""
        from hermes.agents.ci_detective import CIDetectiveAgent
        ws = workspace_path or self.workspace_root
        res = CIDetectiveAgent.extract_commit_and_pr_intent(workspace_path=ws, payload=payload)
        res["intent_category"] = "INTENTIONAL_API_DRIFT" if res.get("has_intentional_contract_change") else "CODE_REGRESSION"
        return res

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
