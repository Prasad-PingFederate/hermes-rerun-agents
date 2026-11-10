"""
Gemini Flash Multimodal Failure Diagnostician
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash"]


class GeminiFlashHealer:
    """Diagnoses test failures using Gemini Flash multimodal capabilities."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def diagnose_failure(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str,
        screenshot_path: Optional[str | Path] = None,
        network_errors: Optional[List[str]] = None,
        console_errors: Optional[List[str]] = None,
        recent_diff: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send complete failure context to Gemini Flash for diagnosis and remediation."""
        if not self.api_key:
            return self._heuristic_fallback(error_message, code_snippet)

        screenshot_bytes = None
        if screenshot_path and Path(screenshot_path).is_file():
            try:
                screenshot_bytes = Path(screenshot_path).read_bytes()
            except Exception:
                pass

        prompt = self._build_prompt(
            test_name=test_name,
            error_message=error_message,
            traceback_str=traceback_str,
            code_snippet=code_snippet,
            network_errors=network_errors or [],
            console_errors=console_errors or [],
            recent_diff=recent_diff or "",
        )

        response_text = self._call_gemini(prompt, screenshot_bytes)
        if not response_text:
            return self._heuristic_fallback(error_message, code_snippet)

        return {
            "test_name": test_name,
            "engine": "Gemini Flash (Multimodal)",
            "analysis": response_text,
            "ai_powered": True,
        }

    def _build_prompt(
        self,
        test_name: str,
        error_message: str,
        traceback_str: str,
        code_snippet: str,
        network_errors: List[str],
        console_errors: List[str],
        recent_diff: str,
    ) -> str:
        nl = chr(10)
        net_str = nl.join(network_errors[:5]) if network_errors else "None"
        con_str = nl.join(console_errors[:5]) if console_errors else "None"

        return f"""You are an expert Playwright automation engineer and test failure healer.
Analyze the following test failure and determine the root cause, category, and resilient fix.

### Test Metadata:
- Test: `{test_name}`
- Error Message: `{error_message}`

### Code Context:
```python
{code_snippet}
```

### Traceback:
```text
{traceback_str[-1200:]}
```

### Console Errors:
{con_str}

### Network Errors:
{net_str}

### Recent Git Diff:
```text
{recent_diff}
```

A screenshot of the exact failure state is attached.

Provide:
1. Root Cause Summary
2. Failure Category (Locator Drift, Modal Obstruction, Network/Handshake Lag, State Desync, or App Bug)
3. Recommended Resilient Playwright Fix (replace fixed sleeps or fragile locators)
4. Exact Replacement Code Patch
"""

    def _call_gemini(self, prompt: str, screenshot_bytes: Optional[bytes] = None) -> Optional[str]:
        if not requests:
            return None

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
                        if text:
                            return text
            except Exception:
                continue
        return None

    def _heuristic_fallback(self, error_message: str, code_snippet: str) -> Dict[str, Any]:
        category = "Unknown"
        remediation = "Inspect the failure logs and verify selector."

        if "Timeout" in error_message or "waiting for locator" in error_message:
            category = "Timeout / Locator Drift"
            remediation = "Use expect(locator).to_be_visible(timeout=...) or inspect if dynamic DOM ID changed."
        elif "AssertionError" in error_message:
            category = "Assertion Mismatch"
            remediation = "Verify expected test data vs actual backend response state."

        return {
            "engine": "Heuristic Fallback (Set GEMINI_API_KEY for Multimodal Vision)",
            "category": category,
            "remediation": remediation,
            "ai_powered": False,
        }
