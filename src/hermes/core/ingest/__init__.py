"""
Universal Artifact Ingestion & Playwright Trace Forensics
Phase: Phase 1 (Enterprise Decoupled Post-Run Observer Mode)
"""

from __future__ import annotations

from core.ingest.artifact_loader import ArtifactLoader
from core.ingest.ctrf_parser import CTRFParser
from core.ingest.junit_parser import JUnitParser
from core.ingest.models import FailedNetworkRequest, NormalizedFailure
from core.ingest.trace_parser import PlaywrightTraceForensics

__all__ = [
    "ArtifactLoader",
    "CTRFParser",
    "JUnitParser",
    "FailedNetworkRequest",
    "NormalizedFailure",
    "PlaywrightTraceForensics",
]

