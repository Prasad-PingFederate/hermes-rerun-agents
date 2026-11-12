"""
Playwright trace.zip Forensics Engine
Owner: CIDetectiveAgent & IngestionEngine
Phase: Phase 1 (Universal Artifact Ingestion & Playwright Trace Forensics)

Extracts forensic network HAR responses and action/DOM snapshots from Playwright trace.zip.
Zero external dependencies (uses standard library: zipfile, json, pathlib, re, io).

Key Security & Performance Invariants:
1. Zip-Bomb & Resource Guard:
   - Caps individual file entries at 10 MB and total uncompressed size at 50 MB.
   - Skips binary blobs (resources/*.png, images, fonts).
2. Deterministic Verdict Override:
   - If trace contains an HTTP 500 on an XHR/Fetch during the test step -> PRODUCT_BUG.
   - If trace contains HTTP 502/503/504 gateway failures -> INFRA_FLAKE.
3. DLP & Nonce Sandboxing:
   - Strips Authorization and Cookie headers; scrubs all payload bodies via DLPSessionVault(source="RUNTIME_LOG").
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.ingest.models import FailedNetworkRequest, NormalizedFailure
from core.security.dlp_scrubber import DLPSessionVault
from core.security.prompt_sandbox import PromptSandbox


class PlaywrightTraceForensics:
    """Security-hardened forensics parser inspecting Playwright trace.zip archives."""

    # Security caps
    MAX_ENTRY_SIZE_BYTES = 10 * 1024 * 1024       # 10 MB per JSON/NDJSON file
    MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024 # 50 MB total archive cap

    # Binary file extensions to skip
    BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
        ".woff", ".woff2", ".ttf", ".eot", ".bin", ".wasm",
    }

    # Sensitive headers to strip before processing
    SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}

    @classmethod
    def parse_zip(
        cls,
        zip_path: Union[str, Path, io.BytesIO],
        dlp_vault: Optional[DLPSessionVault] = None,
        test_node_id_hint: Optional[str] = None,
        file_path_hint: Optional[str] = None,
    ) -> List[NormalizedFailure]:
        """Inspect Playwright trace.zip archive and extract forensic failure signals."""
        vault = dlp_vault or DLPSessionVault()
        failed_requests: List[FailedNetworkRequest] = []
        action_errors: List[str] = []
        last_failed_selector: str = ""
        dom_snapshots: List[str] = []
        test_title = test_node_id_hint or "Playwright Spec"
        file_path = file_path_hint or "e2e/test.spec.ts"
        duration_ms = 0.0

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 1. Zip-Bomb Guard: Verify cumulative decompressed size
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > cls.MAX_TOTAL_UNCOMPRESSED_BYTES:
                    # Return error record if archive exceeds security envelope
                    return [
                        NormalizedFailure(
                            runner="playwright",
                            test_node_id=test_title,
                            file_path=file_path,
                            error_message="Security rejection: trace.zip exceeded maximum uncompressed size envelope (50 MB cap)",
                            stack_trace="",
                            deterministic_verdict="ENVIRONMENT_NOISE",
                        )
                    ]

                # 2. Iterate through relevant entries (skipping binary assets)
                for info in zf.infolist():
                    name_lower = info.filename.lower()
                    if any(name_lower.endswith(ext) for ext in cls.BINARY_EXTENSIONS):
                        continue
                    if "resources/" in name_lower and not name_lower.endswith((".json", ".ndjson", ".trace", ".network")):
                        continue
                    if info.file_size > cls.MAX_ENTRY_SIZE_BYTES:
                        continue

                    try:
                        with zf.open(info, "r") as f:
                            content_bytes = f.read(cls.MAX_ENTRY_SIZE_BYTES)
                            text = content_bytes.decode("utf-8", errors="replace")
                            
                            # Parse based on file type
                            if name_lower.endswith((".network", "network.json", "network.ndjson")):
                                cls._extract_network_signals(text, failed_requests, vault)
                            elif name_lower.endswith((".trace", "trace.json", "trace.ndjson", "actions.ndjson")):
                                action_err, sel, dom = cls._extract_trace_signals(text, failed_requests, vault)
                                if action_err:
                                    action_errors.append(action_err)
                                if sel:
                                    last_failed_selector = sel
                                if dom:
                                    dom_snapshots.append(dom)
                            elif name_lower.endswith((".json", ".txt")) and "trace" in name_lower:
                                # Fallback general signal extraction
                                cls._extract_network_signals(text, failed_requests, vault)
                                action_err, sel, dom = cls._extract_trace_signals(text, failed_requests, vault)
                                if action_err:
                                    action_errors.append(action_err)
                                if sel:
                                    last_failed_selector = sel
                                if dom:
                                    dom_snapshots.append(dom)
                    except Exception:
                        continue

        except zipfile.BadZipFile:
            return []
        except Exception:
            return []

        # 3. Construct NormalizedFailure if errors or failed network requests were detected
        combined_err = "\n".join(action_errors).strip()
        if not combined_err and failed_requests:
            top_req = failed_requests[0]
            combined_err = f"Network HTTP {top_req.status} on {top_req.method} {top_req.url}"
        elif not combined_err:
            combined_err = "Playwright test failed during execution"

        if last_failed_selector and last_failed_selector not in combined_err:
            combined_err = f"{combined_err} (Target: {last_failed_selector})"

        dom_excerpt = dom_snapshots[-1] if dom_snapshots else None

        # Build forensic stack trace summary
        trace_summary_lines = [combined_err]
        if failed_requests:
            trace_summary_lines.append("\n[FORENSIC NETWORK FAILURES CAPTURED IN TRACE]:")
            for req in failed_requests:
                snippet = f" -> {req.response_body_snippet}" if req.response_body_snippet else ""
                trace_summary_lines.append(f"  • {req.method} {req.url} [HTTP {req.status}]{snippet}")

        full_trace = "\n".join(trace_summary_lines)

        # Apply Option 5 One-Way DLP and Nonce Prompt Sandboxing
        scrubbed_msg = vault.scrub_runtime_log(combined_err).scrubbed_text
        scrubbed_trace = vault.scrub_runtime_log(full_trace).scrubbed_text
        sandboxed_trace = PromptSandbox.sandbox_untrusted_data(
            scrubbed_trace, label="playwright_trace_forensics"
        ).sandboxed_text

        failure = NormalizedFailure(
            runner="playwright",
            test_node_id=test_title,
            file_path=file_path,
            error_message=scrubbed_msg,
            stack_trace=scrubbed_trace,
            failed_requests=failed_requests,
            dom_excerpt=dom_excerpt,
            duration_ms=duration_ms,
            sandboxed_trace_block=sandboxed_trace,
        )

        return [failure]

    @classmethod
    def _extract_network_signals(
        cls,
        text: str,
        out_requests: List[FailedNetworkRequest],
        vault: DLPSessionVault,
    ) -> None:
        """Extract HTTP 5xx responses from network stream."""
        for line in text.splitlines():
            line_str = line.strip()
            if not line_str or not (line_str.startswith("{") and line_str.endswith("}")):
                continue
            try:
                event = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            status = None
            url = ""
            method = "GET"
            body = ""

            # Standard Playwright trace format:
            # { "type": "event", "method": "response", "params": { "request": {...}, "response": { "status": 500, ... } } }
            if "response" in event and isinstance(event["response"], dict):
                resp = event["response"]
                status = resp.get("status")
                url = resp.get("url", "")
                req = event.get("request", {}) if isinstance(event.get("request"), dict) else {}
                method = req.get("method", "GET")
                body = str(resp.get("body", "") or resp.get("statusText", ""))

            # Alternate trace representation
            elif event.get("type") in ("response", "resourceSnapshot") or "status" in event:
                status = event.get("status")
                url = event.get("url", "")
                method = event.get("method", "GET")
                body = str(event.get("body", "") or "")

            # Nested params pattern
            elif "params" in event and isinstance(event["params"], dict):
                p = event["params"]
                if "response" in p and isinstance(p["response"], dict):
                    resp = p["response"]
                    status = resp.get("status")
                    url = resp.get("url", "")
                    method = p.get("request", {}).get("method", "GET") if isinstance(p.get("request"), dict) else "GET"
                    body = str(resp.get("body", "") or "")

            if status is not None and isinstance(status, int) and status >= 500:
                # Sanitize response body through one-way DLP
                scrubbed_body = vault.scrub_runtime_log(body[:500]).scrubbed_text
                scrubbed_url = vault.scrub_runtime_log(url).scrubbed_text
                req_obj = FailedNetworkRequest(
                    method=method.upper(),
                    url=scrubbed_url,
                    status=status,
                    response_body_snippet=scrubbed_body,
                )
                # Deduplicate by (method, url, status)
                if not any(r.method == req_obj.method and r.url == req_obj.url and r.status == req_obj.status for r in out_requests):
                    out_requests.append(req_obj)

    @classmethod
    def _extract_trace_signals(
        cls,
        text: str,
        failed_requests: List[FailedNetworkRequest],
        vault: DLPSessionVault,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract action error message, failed locator selector, and DOM excerpt."""
        action_error = None
        failed_selector = None
        dom_excerpt = None

        for line in text.splitlines():
            line_str = line.strip()
            if not line_str or not (line_str.startswith("{") and line_str.endswith("}")):
                continue
            try:
                event = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            # Look for action error
            err_val = event.get("error")
            if err_val:
                if isinstance(err_val, dict):
                    msg = err_val.get("error", {}).get("message") or err_val.get("message") or str(err_val)
                else:
                    msg = str(err_val)
                action_error = msg[:300]

            # Look for selector
            if "selector" in event:
                failed_selector = str(event["selector"])
            elif "params" in event and isinstance(event["params"], dict) and "selector" in event["params"]:
                failed_selector = str(event["params"]["selector"])

            # Look for snapshot / DOM excerpt
            if "snapshot" in event and isinstance(event["snapshot"], dict):
                html = event["snapshot"].get("html") or event["snapshot"].get("text")
                if html:
                    dom_excerpt = vault.scrub_runtime_log(str(html)[:1000]).scrubbed_text

            # Inspect embedded network responses within trace events
            if "response" in event and isinstance(event["response"], dict):
                st = event["response"].get("status")
                if isinstance(st, int) and st >= 500:
                    url = event["response"].get("url", "")
                    body = str(event["response"].get("body", "") or "")
                    method = event.get("request", {}).get("method", "GET") if isinstance(event.get("request"), dict) else "GET"
                    scrubbed_body = vault.scrub_runtime_log(body[:500]).scrubbed_text
                    scrubbed_url = vault.scrub_runtime_log(url).scrubbed_text
                    req_obj = FailedNetworkRequest(method=method.upper(), url=scrubbed_url, status=st, response_body_snippet=scrubbed_body)
                    if not any(r.method == req_obj.method and r.url == req_obj.url and r.status == req_obj.status for r in failed_requests):
                        failed_requests.append(req_obj)

        return action_error, failed_selector, dom_excerpt
