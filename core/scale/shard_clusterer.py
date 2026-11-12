"""
Cross-Shard Failure Clustering & Matrix Deduplication
Owner: CIDetectiveAgent & ScrumMasterOrchestrator
Phase: Option 6 (Monorepo Scale & Ecosystem Depth)

Collapses duplicate failures across parallel CI matrix shards (e.g. shard: 1/16 ... 16/16):
1. Volatile Noise Stripping:
   Strips ephemeral ports (localhost:54321), hex memory addresses (0x7f9a...), timestamps,
   PIDs, durations, and runner workspace paths (/home/runner/work/repo/) before hashing.
2. Canonical Root-Cause Signature:
   ClusterSig = SHA256(ExceptionType || TopAppFrames_normalized || FailedSelectorOrSymbol || SourceDiffHunkHash)
3. Token & Comment Deduplication:
   Collapses N parallel failures into 1 root-cause investigation, saving (N - 1) redundant LLM calls
   against the Option 5 FinOps budget, and embeds <!-- hermes-cluster-sig: <sha256> --> in suggestions.

Zero external dependencies (uses standard library: hashlib, re, typing, posixpath).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class NormalizedFailureTrace:
    """Canonicalized failure trace with volatile runtime noise stripped."""
    exception_type: str
    normalized_frames: List[str]
    failed_symbol_or_selector: str
    diff_hunk_hash: str
    cluster_sig: str
    raw_trace: str = ""
    shard_id: str = "shard_1"


@dataclass
class FailureCluster:
    """Represents a cluster of identical root-cause failures across runners/shards."""
    cluster_sig: str
    exception_type: str
    failed_symbol_or_selector: str
    primary_failure: Dict[str, Any]
    all_failures: List[Dict[str, Any]] = field(default_factory=list)
    shards_affected: List[str] = field(default_factory=list)
    total_failures: int = 1
    collapsed_count: int = 0
    blast_radius_summary: str = ""
    marker: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_sig": self.cluster_sig,
            "exception_type": self.exception_type,
            "failed_symbol_or_selector": self.failed_symbol_or_selector,
            "total_failures": self.total_failures,
            "collapsed_count": self.collapsed_count,
            "shards_affected": self.shards_affected,
            "blast_radius_summary": self.blast_radius_summary,
            "marker": self.marker,
        }


class ShardClusterer:
    """Clusters and deduplicates failures across parallel test shards."""

    # Volatile noise regexes to strip before computing signature
    PORT_REGEX = re.compile(r":\d{4,5}\b")
    HEX_ADDR_REGEX = re.compile(r"\b0x[0-9a-fA-F]{6,16}\b")
    TIMESTAMP_REGEX = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b")
    PID_REGEX = re.compile(r"\b(?:pid|process|worker)\s*[:=]?\s*\d+\b", re.IGNORECASE)
    DURATION_REGEX = re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|seconds)\b", re.IGNORECASE)
    RUNNER_PATH_REGEX = re.compile(
        r"(?:\/home\/runner\/work\/[^\/]+\/[^\/]+\/|[A-Za-z]:\\[^\r\n]+?\\runneradmin\\[^\r\n]+?\\|\/tmp\/runner_[^\/]+\/)",
        re.IGNORECASE,
    )

    # Frame filtering patterns
    FRAME_LINE_REGEX = re.compile(r'File "([^"]+)", line (\d+), in ([a-zA-Z0-9_<>]+)')
    JS_FRAME_REGEX = re.compile(r'at (?:async )?([a-zA-Z0-9_$.<>]+) \(([^)]+):(\d+):(\d+)\)')

    @classmethod
    def canonicalize_trace(cls, raw_trace: str) -> str:
        """Strip volatile runner artifacts, timestamps, memory addresses, and ephemeral ports."""
        if not raw_trace:
            return ""

        text = raw_trace
        text = cls.RUNNER_PATH_REGEX.sub("", text)
        text = cls.PORT_REGEX.sub(":<PORT>", text)
        text = cls.HEX_ADDR_REGEX.sub("<ADDR>", text)
        text = cls.TIMESTAMP_REGEX.sub("<TIMESTAMP>", text)
        text = cls.PID_REGEX.sub("<PID>", text)
        text = cls.DURATION_REGEX.sub("<DURATION>", text)
        return text

    @classmethod
    def extract_top_app_frames(cls, canonical_trace: str, max_frames: int = 5) -> List[str]:
        """Extract top application stack frames, ignoring system/runtime internals."""
        frames: List[str] = []

        # Check Python frames
        for match in cls.FRAME_LINE_REGEX.finditer(canonical_trace):
            fpath, _, func = match.groups()
            norm_fpath = fpath.replace("\\", "/")
            if not any(skip in norm_fpath for skip in ("site-packages", "dist-packages", "lib/python", "pytest")):
                frames.append(f"{norm_fpath}:{func}")

        # Check JS/TS frames if no python frames found
        if not frames:
            for match in cls.JS_FRAME_REGEX.finditer(canonical_trace):
                func, fpath, _, _ = match.groups()
                norm_fpath = fpath.replace("\\", "/")
                if not any(skip in norm_fpath for skip in ("node_modules", "internal/")):
                    frames.append(f"{norm_fpath}:{func}")

        return frames[:max_frames] if frames else [canonical_trace[:150].strip()]

    @classmethod
    def extract_exception_type(cls, raw_trace: str) -> str:
        """Extract exception class name (e.g. AssertionError, TypeError, TimeoutError)."""
        if not raw_trace:
            return "UnknownError"
        # Match standard Python/JS error line at end of trace
        lines = [line.strip() for line in raw_trace.splitlines() if line.strip()]
        for line in reversed(lines):
            # Python: ValueError: invalid literal
            m_py = re.match(r"^([A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):", line)
            if m_py:
                return m_py.group(1)
            # JS: Error: expect(received).toBe(expected)
            m_js = re.match(r"^(?:[A-Za-z0-9_]+)?Error:\s*(.*)", line)
            if m_js:
                return "AssertionError" if "expect(" in line or "toBe" in line else "Error"
        return "Failure"

    @classmethod
    def extract_failed_symbol(cls, raw_trace: str, failure_item: Dict[str, Any]) -> str:
        """Extract failed test symbol, selector, or function name."""
        sym = failure_item.get("test_name") or failure_item.get("symbol") or ""
        if sym:
            return str(sym).strip()

        # Check for selector in trace: e.g. locator('button') or getByRole(...)
        sel_match = re.search(r"(?:locator|getByRole|getByTestId|getByLabel)\(['\"]([^'\"]+)['\"]\)", raw_trace)
        if sel_match:
            return sel_match.group(1)

        # Fallback to test function in trace
        for line in raw_trace.splitlines():
            if "def test_" in line or "test(" in line:
                return line.strip()[:60]
        return "unspecified_symbol"

    @classmethod
    def compute_cluster_signature(
        cls,
        raw_trace: str,
        failure_item: Dict[str, Any],
        diff_hunk: str = "",
    ) -> NormalizedFailureTrace:
        """Compute deterministic SHA-256 root-cause signature from canonicalized trace components."""
        canon_trace = cls.canonicalize_trace(raw_trace)
        exc_type = cls.extract_exception_type(canon_trace)
        top_frames = cls.extract_top_app_frames(canon_trace)
        failed_symbol = cls.extract_failed_symbol(canon_trace, failure_item)

        diff_hunk_hash = hashlib.sha256(diff_hunk.strip().encode("utf-8")).hexdigest()[:16] if diff_hunk else "nodiff"
        shard_id = failure_item.get("shard_id") or failure_item.get("runner_id") or "shard_1"

        # Construct signature preimage
        frames_repr = "|".join(top_frames)
        preimage = f"{exc_type}::{frames_repr}::{failed_symbol}::{diff_hunk_hash}"
        sig = hashlib.sha256(preimage.encode("utf-8")).hexdigest()

        return NormalizedFailureTrace(
            exception_type=exc_type,
            normalized_frames=top_frames,
            failed_symbol_or_selector=failed_symbol,
            diff_hunk_hash=diff_hunk_hash,
            cluster_sig=sig,
            raw_trace=raw_trace,
            shard_id=shard_id,
        )

    @classmethod
    def cluster_failures(
        cls,
        failures: List[Dict[str, Any]],
        diff_hunks_by_file: Optional[Dict[str, str]] = None,
    ) -> List[FailureCluster]:
        """Group a list of multi-shard failure payloads into unique root-cause clusters."""
        clusters_by_sig: Dict[str, FailureCluster] = {}

        for item in failures:
            trace_text = item.get("trace") or item.get("error") or item.get("message") or ""
            test_file = item.get("test_file") or item.get("file") or ""
            diff_hunk = ""
            if diff_hunks_by_file and test_file in diff_hunks_by_file:
                diff_hunk = diff_hunks_by_file[test_file]

            norm = cls.compute_cluster_signature(trace_text, item, diff_hunk=diff_hunk)
            sig = norm.cluster_sig

            if sig not in clusters_by_sig:
                marker = f"<!-- hermes-cluster-sig:{sig} -->"
                clusters_by_sig[sig] = FailureCluster(
                    cluster_sig=sig,
                    exception_type=norm.exception_type,
                    failed_symbol_or_selector=norm.failed_symbol_or_selector,
                    primary_failure=item,
                    all_failures=[item],
                    shards_affected=[norm.shard_id],
                    total_failures=1,
                    collapsed_count=0,
                    marker=marker,
                )
            else:
                cluster = clusters_by_sig[sig]
                cluster.all_failures.append(item)
                cluster.total_failures += 1
                cluster.collapsed_count += 1
                if norm.shard_id not in cluster.shards_affected:
                    cluster.shards_affected.append(norm.shard_id)

        # Update blast-radius summaries
        result_clusters = list(clusters_by_sig.values())
        for c in result_clusters:
            shard_cnt = len(c.shards_affected)
            if c.total_failures > 1:
                c.blast_radius_summary = (
                    f"Collapsed {c.total_failures} downstream shard failures across {shard_cnt} shard(s) into 1 root-cause fix."
                )
            else:
                c.blast_radius_summary = "Isolated single-shard failure."

        return result_clusters

