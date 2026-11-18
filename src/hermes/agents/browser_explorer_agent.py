"""
Hermes Live Browser Explorer Agent.

Inspired by OpenHands / BrowserGym multimodal agents, drives a live Playwright
Chromium browser instance to explore pages, interact with DOM elements,
capture network mutations, and generate resilient locator hints.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DOMElementInfo:
    tag: str
    text: str
    element_id: Optional[str] = None
    test_id: Optional[str] = None
    name: Optional[str] = None
    input_type: Optional[str] = None
    role: Optional[str] = None
    suggested_locator: str = ""


@dataclass
class BrowserExplorationReport:
    url: str
    title: str
    status: str
    elements: List[DOMElementInfo] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    network_errors: List[str] = field(default_factory=list)
    toasts: List[str] = field(default_factory=list)
    screenshot_base64: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_summary_str(self) -> str:
        lines = [
            f"=== Live Browser Exploration: {self.title} ({self.url}) ===",
            f"Status: {self.status}",
            f"Interactive Elements Discovered: {len(self.elements)}",
        ]
        if self.elements:
            lines.append("Key Discovered Locators:")
            for el in self.elements[:10]:
                lines.append(f"  * [{el.tag.upper()}] '{el.text[:30]}' -> {el.suggested_locator}")
        if self.toasts:
            lines.append(f"Captured UI Toasts: {', '.join(self.toasts)}")
        if self.console_errors:
            lines.append(f"Console Errors: {len(self.console_errors)}")
        if self.network_errors:
            lines.append(f"Network Failures: {len(self.network_errors)}")
        return "\n".join(lines)


class LiveBrowserExplorerAgent:
    """Multimodal browser exploration agent driving headless Chromium sessions."""

    def __init__(self, workspace_path: Optional[Path | str] = None):
        self.workspace_path = Path(workspace_path or Path.cwd()).resolve()

    def explore_url(
        self,
        url: str,
        headless: bool = True,
        timeout_ms: int = 15000,
    ) -> BrowserExplorationReport:
        """Navigates to URL, extracts interactive elements, and captures live DOM telemetry."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return BrowserExplorationReport(
                url=url,
                title="Playwright Unavailable",
                status="PLAYWRIGHT_NOT_INSTALLED",
            )

        console_errors: List[str] = []
        network_errors: List[str] = []
        elements: List[DOMElementInfo] = []
        toasts: List[str] = []
        title = ""
        screenshot_b64 = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()

                # Event listeners
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("requestfailed", lambda req: network_errors.append(f"{req.method} {req.url}: {req.failure}"))

                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                title = page.title()

                # Extract interactive elements via JS evaluation
                raw_elements = page.evaluate("""() => {
                    const nodes = Array.from(document.querySelectorAll('button, input, textarea, select, a, [role="button"]'));
                    return nodes.slice(0, 50).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || '').trim(),
                        element_id: el.id || null,
                        test_id: el.getAttribute('data-testid') || el.getAttribute('data-test-id') || null,
                        name: el.getAttribute('name') || null,
                        input_type: el.getAttribute('type') || null,
                        role: el.getAttribute('role') || null,
                    }));
                }""")

                for item in raw_elements:
                    loc = self._compute_suggested_locator(item)
                    elements.append(DOMElementInfo(**item, suggested_locator=loc))

                # Extract toasts if present
                raw_toasts = page.locator(".toast, .toast-body, [role='alert'], .alert").all_inner_texts()
                toasts = [t.strip() for t in raw_toasts if t.strip()]

                # Capture screenshot
                shot_bytes = page.screenshot()
                screenshot_b64 = base64.b64encode(shot_bytes).decode("utf-8")

                browser.close()

            return BrowserExplorationReport(
                url=url,
                title=title,
                status="SUCCESS",
                elements=elements,
                console_errors=console_errors,
                network_errors=network_errors,
                toasts=toasts,
                screenshot_base64=screenshot_b64,
            )
        except Exception as exc:
            return BrowserExplorationReport(
                url=url,
                title=title or "Error",
                status=f"FAILED: {exc}",
                console_errors=console_errors,
                network_errors=network_errors,
            )

    @staticmethod
    def _compute_suggested_locator(info: Dict[str, Any]) -> str:
        """Determines the most resilient locator strategy based on element attributes."""
        if info.get("test_id"):
            return f"page.get_by_test_id('{info['test_id']}')"
        if info.get("element_id"):
            return f"page.locator('#{info['element_id']}')"
        if info.get("name"):
            return f"page.locator(\"input[name='{info['name']}']\")"
        if info.get("text") and info.get("tag") in ("button", "a"):
            clean_text = info["text"][:30]
            return f"page.get_by_role('{info.get('role') or info['tag']}', name='{clean_text}')"
        if info.get("input_type") in ("radio", "checkbox", "submit"):
            return f"page.locator(\"input[type='{info['input_type']}']\").first"
        return f"page.locator('{info.get('tag', 'div')}').first"
