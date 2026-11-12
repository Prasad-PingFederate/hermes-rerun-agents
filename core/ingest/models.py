"""
Normalized Failure Schema
Owner: CIDetectiveAgent & ShardClusterer
Phase: Phase 1 (Universal Artifact Ingestion & Playwright Trace Forensics)

Defines a canonical failure record emitted by all test artifact parsers
(JUnit XML, CTRF JSON, Playwright trace.zip, and runner stdout).
Zero external dependencies (uses standard library: dataclasses, typing, re).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FailedNetworkRequest:
    """Represents a failed network HTTP request (status >= 500 or failed XHR) captured in trace."""
    method: str
    url: str
    status: int
    response_body_snippet: str = ""
    timestamp_ms: Optional[float] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "response_body_snippet": self.response_body_snippet,
            "timestamp_ms": self.timestamp_ms,
            "correlation_id": self.correlation_id,
        }


@dataclass
class NormalizedFailure:
    """Canonical failure event emitted by all artifact parsers and runner hooks."""
    runner: str  # "pytest", "playwright", "jest", "junit", "ctrf", "go", etc.
    test_node_id: str  # e.g., "tests/test_api.py::test_checkout" or "order.spec.ts > submit"
    file_path: str
    error_message: str
    stack_trace: str
    line: Optional[int] = None
    failed_requests: List[FailedNetworkRequest] = field(default_factory=list)
    dom_excerpt: Optional[str] = None
    duration_ms: float = 0.0
    retries: int = 0
    raw_status: str = "failed"
    deterministic_verdict: Optional[str] = None
    sandboxed_trace_block: Optional[str] = None

    def __post_init__(self) -> None:
        if self.deterministic_verdict is None:
            self.deterministic_verdict = self.compute_deterministic_verdict()

    def compute_deterministic_verdict(self) -> Optional[str]:
        """Compute zero-LLM deterministic verdict from forensic signals.
        
        Rules:
        - HTTP 502/503/504 in failed_requests -> INFRA_FLAKE (transient gateway/proxy failure)
        - HTTP 500 or other 5xx in failed_requests -> PRODUCT_BUG (backend crashed during UI test)
        - Ephemeral socket / port bind or missing dependency -> ENVIRONMENT_NOISE
        """
        # 1. Inspect correlated network failures
        if self.failed_requests:
            for req in self.failed_requests:
                if req.status in (502, 503, 504):
                    return "INFRA_FLAKE"
                elif 500 <= req.status <= 599:
                    return "PRODUCT_BUG"

        # 2. Inspect error message & stack trace for environment noise
        combined = f"{self.error_message}\n{self.stack_trace}".lower()
        if any(p in combined for p in ("eaddrinuse", "address already in use", "connection refused", "port 54321")):
            return "ENVIRONMENT_NOISE"

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "runner": self.runner,
            "test_node_id": self.test_node_id,
            "file_path": self.file_path,
            "line": self.line,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "failed_requests": [req.to_dict() for req in self.failed_requests],
            "dom_excerpt": self.dom_excerpt,
            "duration_ms": round(self.duration_ms, 2),
            "retries": self.retries,
            "raw_status": self.raw_status,
            "deterministic_verdict": self.deterministic_verdict,
            "sandboxed_trace_block": self.sandboxed_trace_block,
        }

    def to_cluster_dict(self) -> Dict[str, Any]:
        """Convert to dict structure consumed directly by ShardClusterer."""
        raw_full = f"{self.error_message}\n{self.stack_trace}"
        return {
            "failing_test": self.test_node_id,
            "test_name": self.test_node_id,
            "file_path": self.file_path,
            "line": self.line,
            "error_summary": self.error_message,
            "stack_trace": self.stack_trace,
            "raw_trace": raw_full,
            "raw_logs": raw_full,
            "failed_requests": [r.to_dict() for r in self.failed_requests],
            "dom_excerpt": self.dom_excerpt,
            "duration_ms": self.duration_ms,
            "runner": self.runner,
            "deterministic_verdict": self.deterministic_verdict,
        }
