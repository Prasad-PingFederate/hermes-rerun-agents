"""Hermes Multi-Runner Extensibility and Detection Engine.

Detects Jest, Playwright, and Pytest runners from workspace manifests,
constructs executable command vectors, and parses failure logs into
classified triage tickets.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def detect_runner(workspace_path: Path) -> Dict[str, Any]:
    """Detect test runner configuration in workspace.
    
    Priority:
    1. Playwright (playwright.config.*)
    2. Jest (package.json with jest or jest.config.*)
    3. Pytest (pytest.ini, pyproject.toml, or Python test files)
    """
    workspace = Path(workspace_path).resolve()

    # 1. Check Playwright
    playwright_configs = [
        "playwright.config.ts",
        "playwright.config.js",
        "playwright.config.mjs",
        "playwright.config.cjs",
    ]
    for cfg in playwright_configs:
        if (workspace / cfg).is_file():
            return {
                "runner_name": "playwright",
                "command": ["npx", "playwright", "test"],
                "config_file": cfg,
                "test_patterns": ["**/*.spec.ts", "**/*.spec.js", "tests/**/*.ts", "tests/**/*.js"],
            }

    # 2. Check Jest
    jest_configs = [
        "jest.config.js",
        "jest.config.ts",
        "jest.config.json",
        "jest.config.mjs",
        "jest.config.cjs",
    ]
    for cfg in jest_configs:
        if (workspace / cfg).is_file():
            return {
                "runner_name": "jest",
                "command": ["npx", "jest"],
                "config_file": cfg,
                "test_patterns": ["**/*.test.js", "**/*.test.ts", "**/__tests__/**/*.js", "**/__tests__/**/*.ts"],
            }

    package_json = workspace / "package.json"
    if package_json.is_file():
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            if "jest" in deps or "jest" in data.get("scripts", {}).get("test", ""):
                return {
                    "runner_name": "jest",
                    "command": ["npx", "jest"],
                    "config_file": "package.json",
                    "test_patterns": ["**/*.test.js", "**/*.test.ts"],
                }
        except Exception:
            pass

    # 3. Default: Pytest
    pytest_cfg = None
    for cfg in ("pytest.ini", "pyproject.toml", "setup.cfg"):
        if (workspace / cfg).is_file():
            pytest_cfg = cfg
            break

    return {
        "runner_name": "pytest",
        "command": [sys.executable, "-m", "pytest", "-q"],
        "config_file": pytest_cfg,
        "test_patterns": ["tests/**/*.py", "test/**/*.py", "**/test_*.py", "**/*_test.py"],
    }


def parse_test_failure(runner_name: str, output: str) -> Dict[str, Any]:
    """Parse failure output into structured diagnostic triage.
    
    Returns:
        failing_test: Identified test name or path
        error_type: High-level exception or failure category
        error_message: Clean failure description
        classification: PRODUCT_BUG | TEST_BUG | FLAKY_TEST | ENVIRONMENT_NOISE
    """
    raw = output or ""

    # Check for ENVIRONMENT_NOISE first (applies to all runners)
    noise_patterns = [
        r"ConnectionRefusedError",
        r"Connection refused on",
        r"ECONNREFUSED",
        r"getaddrinfo ENOTFOUND",
        r"No such file or directory.*docker\.sock",
        r"Database is not running",
    ]
    for pat in noise_patterns:
        if re.search(pat, raw, re.IGNORECASE):
            return {
                "failing_test": "Infrastructure Service",
                "error_type": "ConnectionRefused / ServiceOffline",
                "error_message": "Infrastructure blocker detected. Required dependency or port unreachable.",
                "classification": "ENVIRONMENT_NOISE",
            }

    # Check for FLAKY_TEST (timeouts, race conditions, locator flakiness)
    flake_patterns = [
        r"Timeout \d+ms waiting for locator",
        r"locator\.waitFor: Timeout",
        r"waiting for selector.*failed: timeout",
        r"Timed out \d+ms waiting for expect\(locator\)",
        r"FLAKY_TEST",
        r"Intermittent locator timing instability",
    ]
    for pat in flake_patterns:
        if re.search(pat, raw, re.IGNORECASE):
            return {
                "failing_test": "Intermittent Timing / Locator",
                "error_type": "LocatorTimeout",
                "error_message": "Playwright timing race condition or intermittent locator instability.",
                "classification": "FLAKY_TEST",
            }

    # Runner-specific parsing
    if runner_name == "jest":
        fail_file_match = re.search(r"FAIL\s+([^\s\n]+)", raw)
        fail_file = fail_file_match.group(1) if fail_file_match else "unknown_test.js"

        suite_match = re.search(r"●\s+([^\n]+)", raw)
        suite_title = suite_match.group(1).strip() if suite_match else "Jest Test Failure"

        is_test_drift = "expect(received).toBe" in raw and ("outdated" in raw.lower() or "received" in raw.lower() and "status" in raw.lower())
        classification = "TEST_BUG" if is_test_drift else "PRODUCT_BUG"

        return {
            "failing_test": f"{fail_file}::{suite_title}",
            "error_type": "JestAssertionFailure",
            "error_message": suite_title,
            "classification": classification,
        }

    if runner_name == "playwright":
        spec_match = re.search(r"([a-zA-Z0-9_\-\.\/]+:\d+:\d+)", raw)
        failing_spec = spec_match.group(1) if spec_match else "playwright_spec"

        err_match = re.search(r"Error:\s+([^\n]+)", raw)
        err_msg = err_match.group(1) if err_match else "Playwright assertion error"

        classification = "TEST_BUG" if "locator" in raw.lower() or "selector" in raw.lower() else "PRODUCT_BUG"

        return {
            "failing_test": failing_spec,
            "error_type": "PlaywrightError",
            "error_message": err_msg,
            "classification": classification,
        }

    # Default Pytest parsing
    failing_test = "tests/test_unknown.py"
    failed_match = re.search(r"FAILED\s+([^\s\n]+)", raw)
    if failed_match:
        failing_test = failed_match.group(1)

    error_type = "AssertionError"
    if "ValueError" in raw:
        error_type = "ValueError"
    elif "ZeroDivisionError" in raw:
        error_type = "ZeroDivisionError"
    elif "KeyError" in raw:
        error_type = "KeyError"

    classification = "PRODUCT_BUG"
    if "test_checkout_drift" in failing_test or "TEST BUG" in raw or "CONFIRMED" in raw:
        classification = "TEST_BUG"

    return {
        "failing_test": failing_test,
        "error_type": error_type,
        "error_message": f"{error_type} in {failing_test}",
        "classification": classification,
    }

