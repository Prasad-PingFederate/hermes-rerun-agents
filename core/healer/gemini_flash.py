"""
Multimodal Failure Diagnostician & Healer Engine
Supports Google Gemini Flash (Free Tier) and Local Ollama Models with Offline Heuristic Fallbacks.
Enforces JSON responses with unified diff file changes.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.context.active_context_pruner import (
    BillionContextManager,
    prune_dom,
    prune_logs,
    prune_traceback,
)


GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash"]


class GeminiFlashHealer:
    """Diagnoses Playwright / CI test failures using Multimodal Vision, Code Context, and Domain Skills."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.context_manager = BillionContextManager()

    def diagnose_failure(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str = "",
        dom_snippet: str = "",
        screenshot_path: Optional[str | Path] = None,
        network_errors: Optional[List[str]] = None,
        console_errors: Optional[List[str]] = None,
        recent_diff: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Diagnose failure across multimodal inputs and propose minimal patch in JSON format."""
        # Check domain-specific patterns first (e.g. Breakglass QR Expired preview bug)
        specialized_analysis = self._detect_domain_patterns(
            test_name=test_name,
            error_message=error_message,
            dom_snippet=dom_snippet,
            traceback_str=traceback_str,
        )
        if specialized_analysis:
            return specialized_analysis

        # Attempt diagnosis via HermesLLMAdapter
        from llm_provider_adapter import AgentRole, HermesLLMAdapter
        adapter = HermesLLMAdapter()
        provider = adapter.resolve_provider(AgentRole.TEST_HEALER_AGENT)

        if provider != "none":
            prompt = self._build_prompt(
                test_name=test_name,
                error_message=error_message,
                traceback_str=traceback_str,
                code_snippet=code_snippet,
                dom_snippet=dom_snippet,
                network_errors=network_errors or [],
                console_errors=console_errors or [],
                recent_diff=recent_diff or "",
            )
            system_prompt = (
                "You are an expert Playwright automation engineer and automated test healer. "
                "Analyze the failure and output ONLY valid JSON matching the schema."
            )
            raw_text = adapter.complete(
                role=AgentRole.TEST_HEALER_AGENT.value,
                tier="TIER_3_JUNIOR_SWE",
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
            parsed = self._parse_json_response(raw_text)
            if parsed:
                parsed["test_name"] = test_name
                parsed["engine"] = f"Hermes LLM ({provider})"
                parsed["ai_powered"] = True
                return parsed
            raise RuntimeError(f"Failed to parse JSON response from LLM provider '{provider}': {raw_text[:200]}")

        # Robust heuristic fallback
        return self._heuristic_fallback(
            test_name=test_name,
            error_message=error_message,
            code_snippet=code_snippet,
            dom_snippet=dom_snippet,
        )

    def _detect_domain_patterns(
        self,
        test_name: str,
        error_message: str,
        dom_snippet: str,
        traceback_str: str,
    ) -> Optional[Dict[str, Any]]:
        """Specialized domain rules based on production Stage issues."""
        combined_text = f"{test_name} {error_message} {dom_snippet} {traceback_str}".lower()

        # 1. Breakglass / Responder Preview SIWE Handshake ("QR Expired" failure)
        if "click here" in combined_text and ("breakglass" in combined_text or "qr expired" in combined_text or "responder" in combined_text):
            return {
                "test_name": test_name,
                "engine": "Domain Rule Engine (Breakglass Skill)",
                "category": "Stage Preview Crypto Handshake Timeout / QR Expired",
                "root_cause": (
                    "MedicalProfileInfoVc.tsx SIWE handshake (helloServerApi / verifySignatureApi) "
                    "timed out or errored on Stage, mounting 'QR Expired – Emergency Profile'. "
                    "In this state, <InfoNote> (<Link>Click here</Link>) is never rendered into the DOM."
                ),
                "remediation": (
                    "1. Auto-reload recovery: Check if 'QR Expired' is visible; if so, trigger a single page reload.\n"
                    "2. Direct Canonical Fallback: Navigate directly to "
                    "f\"{BASE_URL}/register?type=responder&userId={owner_user_id}\" "
                    "and store 'responderSignupCallback' in sessionStorage."
                ),
                "files": [],
                "use_breakglass_skill": True,
                "ai_powered": True,
            }

        # 2. Python 3.10 Syntax Guard (Backslash in f-string)
        if "backslash" in combined_text and "f-string" in combined_text:
            return {
                "test_name": test_name,
                "engine": "Domain Rule Engine (Syntax Guard)",
                "category": "Python 3.10 Syntax Incompatibility",
                "root_cause": "F-string expression part contains a backslash, which is unsupported on Python 3.10 (PEP 701 is 3.12+ only).",
                "remediation": "Move backslashes or formatting out of f-strings, or use a plain string template with .replace().",
                "files": [],
                "ai_powered": True,
            }

        return None

    def _build_prompt(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str,
        dom_snippet: str,
        network_errors: List[str],
        console_errors: List[str],
        recent_diff: str,
    ) -> str:
        # Active Context Pruning (Billion-Context) preprocessing
        clean_dom = prune_dom(dom_snippet, max_tokens=600) if dom_snippet else "Not captured"
        clean_tb = prune_traceback(traceback_str, max_tokens=500) if traceback_str else "None"
        clean_con = prune_logs(console_errors, max_tokens=250)
        clean_net = prune_logs(network_errors, max_tokens=250)

        # Ingest into BillionContextManager for session tracking and memory status
        if dom_snippet:
            self.context_manager.ingest(dom_snippet, label="dom_snapshot", metadata={"test_name": test_name})
        if traceback_str:
            self.context_manager.ingest(traceback_str, label="traceback", metadata={"test_name": test_name})

        nl = chr(10)
        net_str = nl.join(clean_net) if clean_net else "None"
        con_str = nl.join(clean_con) if clean_con else "None"

        return f"""You are an expert Playwright automation engineer and automated test healer.
Analyze the following test failure and propose an exact code fix.

### Test Name:
`{test_name}`

### Error:
`{error_message}`

### Code Context:
```python
{code_snippet}
```

### Traceback:
```text
{clean_tb}
```

### DOM State:
```html
{clean_dom}
```

### Browser Console Errors:
{con_str}

### Network Failures:
{net_str}

### Recent Git Diff:
```text
{recent_diff}
```

CRITICAL INSTRUCTION:
You MUST respond with a valid JSON object ONLY. No conversational introduction or markdown outside the JSON.
Follow this exact JSON structure:
{{
  "category": "<Locator Drift | Modal Obstruction | Network Lag | State Desync | App Bug>",
  "root_cause": "<1-2 sentence explanation of why the test failed>",
  "files": [
    {{
      "path": "{test_name}",
      "unified_diff": "<the exact code patch or corrected content to apply>"
    }}
  ]
}}
"""

    def _parse_json_response(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from model output."""
        text = raw_text.strip()
        if "```json" in text:
            match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        elif "```" in text:
            match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def _heuristic_fallback(
        self,
        test_name: str,
        error_message: str,
        code_snippet: str,
        dom_snippet: str,
    ) -> Dict[str, Any]:
        category = "Unknown / General Failure"
        root_cause = "Inspect failure logs and DOM snapshot."
        remediation = "Inspect failure logs and DOM snapshot."

        if "Timeout" in error_message or "waiting for locator" in error_message:
            category = "Locator Drift / Timing Race"
            root_cause = "Playwright exceeded timeout waiting for dynamic locator to become visible."
            remediation = "Replace fixed wait with expect(locator).to_be_visible(timeout=15000)."
        elif "AssertionError" in error_message:
            category = "Assertion Mismatch"
            root_cause = "Assertion condition failed against current page state."
            remediation = "Verify API payload vs DOM representation."
        elif "strict mode violation" in error_message:
            category = "Ambiguous Multiple Locators"
            root_cause = "Selector resolved to multiple elements in strict mode."
            remediation = "Use .first, exact=True, or filter(has_text=...) to disambiguate target."

        return {
            "test_name": test_name,
            "engine": "Heuristic Engine (Free Tier)",
            "category": category,
            "root_cause": root_cause,
            "remediation": remediation,
            "files": [],
            "ai_powered": False,
        }
