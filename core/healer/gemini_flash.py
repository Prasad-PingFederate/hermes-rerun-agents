"""
Multimodal Failure Diagnostician & Healer Engine
Supports Google Gemini Flash (Free Tier) and Local Ollama Models with Offline Heuristic Fallbacks.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        """Diagnose failure across multimodal inputs and propose minimal patch."""
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
        if "click here" in combined_text and ("breakglass" in combined_text or "qr expired" in combined_text or "infonote" in combined_text):
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
                "proposed_patch": (
                    "# Auto-detect QR Expired\n"
                    "if _is_visible(resp_page.locator(\"text='QR Expired'\").first, 3000):\n"
                    "    resp_page.reload(wait_until='domcontentloaded')\n\n"
                    "# Direct Canonical Fallback\n"
                    "elif owner_user_id:\n"
                    "    reg_target = f\"{BASE_URL}/register?type=responder&userId={owner_user_id}\"\n"
                    "    resp_page.evaluate('(target) => sessionStorage.setItem(\"responderSignupCallback\", target)', resp_page.url)\n"
                    "    resp_page.goto(reg_target, wait_until='domcontentloaded')\n"
                ),
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
                "proposed_patch": "template = '...\\n...'.replace('{placeholder}', value)",
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
        nl = chr(10)
        net_str = nl.join(network_errors[:5]) if network_errors else "None"
        con_str = nl.join(console_errors[:5]) if console_errors else "None"

        return f"""You are an expert Playwright automation engineer and test self-healer.
Analyze the following test failure and provide a root cause diagnosis and resilient fix.

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
{traceback_str[-1200:]}
```

### DOM State:
```html
{dom_snippet[-800:] if dom_snippet else "Not captured"}
```

### Browser Console Errors:
{con_str}

### Network Failures:
{net_str}

### Recent Git Diff:
```text
{recent_diff}
```

Return:
1. Root Cause Summary
2. Category: [Locator Drift, Modal Obstruction, Network/Handshake Lag, State Desync, App Bug, Syntax Error]
3. Resilient Playwright Remediation
4. Replacement Code Patch
"""

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
                        if text:
                            return {
                                "test_name": test_name,
                                "engine": f"Google {model} (Multimodal)",
                                "analysis": text,
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
                {"role": "system", "content": "You are an automated Playwright testing diagnostician."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 200:
                res_data = resp.json()
                content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return {
                        "test_name": test_name,
                        "engine": f"Local Ollama ({self.ollama_model})",
                        "analysis": content,
                        "ai_powered": True,
                    }
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
        remediation = "Inspect failure logs and DOM snapshot."

        if "Timeout" in error_message or "waiting for locator" in error_message:
            category = "Locator Drift / Timing Race"
            remediation = "Replace fixed wait with expect(locator).to_be_visible(timeout=15000)."
        elif "AssertionError" in error_message:
            category = "Assertion Mismatch"
            remediation = "Verify API payload vs DOM representation."
        elif "strict mode violation" in error_message:
            category = "Ambiguous Multiple Locators"
            remediation = "Use .first, exact=True, or filter(has_text=...) to disambiguate target."

        return {
            "test_name": test_name,
            "engine": "Heuristic Engine (Free Tier)",
            "category": category,
            "remediation": remediation,
            "ai_powered": False,
        }
