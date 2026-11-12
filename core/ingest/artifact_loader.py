"""
Universal Test Artifact Loader & Dispatcher
Owner: CIDetectiveAgent & IngestionEngine
Phase: Phase 1 (Universal Artifact Ingestion & Playwright Trace Forensics)

Dispatches glob patterns and file paths across supported artifact parsers:
- JUnit XML (*.xml, junit.xml) -> JUnitParser
- CTRF JSON (*.json, *ctrf*.json) -> CTRFParser
- Playwright Trace (*.zip, trace.zip) -> PlaywrightTraceForensics

Zero external dependencies (uses standard library: glob, pathlib, typing).
"""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from core.ingest.ctrf_parser import CTRFParser
from core.ingest.junit_parser import JUnitParser
from core.ingest.models import FailedNetworkRequest, NormalizedFailure
from core.ingest.trace_parser import PlaywrightTraceForensics
from core.security.dlp_scrubber import DLPSessionVault


class ArtifactLoader:
    """Dispatches test artifacts to specialized security-hardened parsers."""

    @classmethod
    def load_artifacts(
        cls,
        patterns: Union[str, List[str]],
        workspace_root: Optional[Union[Path, str]] = None,
        dlp_vault: Optional[DLPSessionVault] = None,
    ) -> List[NormalizedFailure]:
        """Discover and parse test artifacts matching glob patterns or explicit paths.
        
        Args:
            patterns: Glob pattern (e.g. '**/junit*.xml') or list of file paths/globs.
            workspace_root: Base workspace directory for relative path resolution.
            dlp_vault: Optional shared DLPSessionVault for referential tokenization.
            
        Returns:
            List of parsed NormalizedFailure records.
        """
        root = Path(workspace_root or Path.cwd()).resolve()
        vault = dlp_vault or DLPSessionVault()
        resolved_files: Set[Path] = set()

        raw_list = [patterns] if isinstance(patterns, str) else patterns

        for pat in raw_list:
            pat_str = str(pat).strip()
            if not pat_str:
                continue

            # Check if direct file exists
            direct = (root / pat_str).resolve()
            if direct.is_file():
                resolved_files.add(direct)
                continue

            # Otherwise expand glob
            search_pattern = str(root / pat_str) if not Path(pat_str).is_absolute() else pat_str
            for matched in glob.glob(search_pattern, recursive=True):
                m_path = Path(matched).resolve()
                if m_path.is_file():
                    resolved_files.add(m_path)

        failures: List[NormalizedFailure] = []

        # Parse each resolved artifact by file extension
        for f in sorted(resolved_files):
            name_lower = f.name.lower()
            try:
                if name_lower.endswith(".xml"):
                    xml_failures = JUnitParser.parse_file(f, dlp_vault=vault)
                    failures.extend(xml_failures)
                elif name_lower.endswith(".json"):
                    ctrf_failures = CTRFParser.parse_file(f, dlp_vault=vault)
                    failures.extend(ctrf_failures)
                elif name_lower.endswith(".zip"):
                    trace_failures = PlaywrightTraceForensics.parse_zip(f, dlp_vault=vault)
                    failures.extend(trace_failures)
            except Exception:
                continue

        return failures

