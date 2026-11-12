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

try:
    import requests
except ImportError:
    requests = None

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash"]


class GeminiFlashHealer:
    """Diagnoses Playwright / CI test failures using Multimodal Vision, Code Context, and Domain Skills."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.ollama_base_url = ollama_base_url or os.environ.get("OLLAMA_BASE_URL")
        self.ollama_model = ollama_model or os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:latest")
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

        # Attempt Gemini Flash multimodal query
        if self.api_key and requests:
            res = self._diagnose_with_gemini(
                test_name=test_name,
                error_message=error_message,
                traceback_str=traceback_str,
                code_snippet=code_snippet,
                dom_snippet=dom_snippet,
                screenshot_path=screenshot_path,
                network_errors=network_errors or [],
                console_errors=console_errors or [],
                recent_diff=recent_diff or "",
            )
            if res:
                return res

        # Attempt Ollama local model query
        if self.ollama_base_url and requests:
            res = self._diagnose_with_ollama(
                test_name=test_name,
                error_message=error_message,
                traceback_str=traceback_str,
                code_snippet=code_snippet,
                dom_snippet=dom_snippet,
                network_errors=network_errors or [],
                console_errors=console_errors or [],
                recent_diff=recent_diff or "",
            )
            if res:
                return res

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

    def _diagnose_with_gemini(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str,
        dom_snippet: str,
        screenshot_path: Optional[str | Path],
        network_errors: List[str],
        console_errors: List[str],
        recent_diff: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(
            test_name=test_name,
            error_message=error_message,
            traceback_str=traceback_str,
            code_snippet=code_snippet,
            dom_snippet=dom_snippet,
            network_errors=network_errors,
            console_errors=console_errors,
            recent_diff=recent_diff,
        )

        screenshot_bytes = None
        if screenshot_path and Path(screenshot_path).is_file():
            try:
                screenshot_bytes = Path(screenshot_path).read_bytes()
            except Exception:
                pass

        parts: List[Dict[str, Any]] = []
        if screenshot_bytes:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(screenshot_bytes).decode("utf-8"),
                }
            })
        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
        }

        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = self._parse_json_response(text)
                        if parsed:
                            parsed["test_name"] = test_name
                            parsed["engine"] = f"Google {model} (Multimodal)"
                            parsed["ai_powered"] = True
                            return parsed
                        elif text:
                            return {
                                "test_name": test_name,
                                "engine": f"Google {model} (Multimodal)",
                                "category": "AI Diagnosed",
                                "root_cause": text[:300],
                                "files": [],
                                "ai_powered": True,
                            }
            except Exception:
                continue
        return None

    def _diagnose_with_ollama(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str,
        dom_snippet: str,
        network_errors: List[str],
        console_errors: List[str],
        recent_diff: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(
            test_name=test_name,
            error_message=error_message,
            traceback_str=traceback_str,
            code_snippet=code_snippet,
            dom_snippet=dom_snippet,
            network_errors=network_errors,
            console_errors=console_errors,
            recent_diff=recent_diff,
        )

        url = f"{self.ollama_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": "You are an automated Playwright testing diagnostician. Always reply with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 200:
                res_data = resp.json()
                content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                parsed = self._parse_json_response(content)
                if parsed:
                    parsed["test_name"] = test_name
                    parsed["engine"] = f"Local Ollama ({self.ollama_model})"
                    parsed["ai_powered"] = True
                    return parsed
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
