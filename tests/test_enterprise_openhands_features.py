"""
Unit and Integration Tests for Hermes Enterprise OpenHands-Inspired Architecture.

Validates:
1. DockerSandboxExecutor:
   - Command assembly with memory, CPU, and volume isolation
   - Docker availability probe
   - Graceful fallback when Docker is unavailable
2. LiveBrowserExplorerAgent:
   - Resilient locator derivation (test_id, id, role, input types)
   - Playwright availability handling
   - Exploration summary string generation
3. EventStreamBus:
   - Append-only event emission
   - Subscriber callback notification
   - Disk persistence and replay from event_stream.jsonl
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes.agents.browser_explorer_agent import (
    BrowserExplorationReport,
    DOMElementInfo,
    LiveBrowserExplorerAgent,
)
from hermes.core.events.event_stream import EventStreamBus, HermesEvent
from hermes.execution.docker_sandbox import DockerSandboxExecutor
from hermes.execution.sandbox_executor import SandboxExecutor


class TestEnterpriseOpenHandsFeatures(unittest.TestCase):
    """Verifies the enterprise container sandboxing, browser exploration, and event stream."""

    def test_docker_sandbox_command_generation(self):
        """Verifies assembling safe Docker run parameters with memory and CPU constraints."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            executor = DockerSandboxExecutor(
                workspace_path=ws,
                image="mcr.microsoft.com/playwright/python:v1.49.0-noble",
                memory_limit="2g",
                cpu_limit="1.5",
            )
            cmd = executor.build_docker_command(
                command=["pytest", "-q"],
                container_name="test-sandbox-001",
                env_vars={"CI": "true", "HERMES_ENV": "sandbox"},
                read_only_root=True,
            )

            # Assert flags
            self.assertIn("docker", cmd)
            self.assertIn("run", cmd)
            self.assertIn("--rm", cmd)
            self.assertIn("--name", cmd)
            self.assertIn("test-sandbox-001", cmd)
            self.assertIn("--memory", cmd)
            self.assertIn("2g", cmd)
            self.assertIn("--cpus", cmd)
            self.assertIn("1.5", cmd)
            self.assertIn(f"{executor.workspace_path}:/workspace:ro", cmd)
            self.assertIn("CI=true", cmd)
            self.assertIn("HERMES_ENV=sandbox", cmd)
            self.assertIn("mcr.microsoft.com/playwright/python:v1.49.0-noble", cmd)
            self.assertEqual(cmd[-2:], ["pytest", "-q"])

    def test_docker_sandbox_availability_check(self):
        """Verifies is_docker_available returns a boolean without throwing exceptions."""
        avail = DockerSandboxExecutor.is_docker_available()
        self.assertIsInstance(avail, bool)

    def test_sandbox_executor_docker_helper(self):
        """Verifies SandboxExecutor provides run_in_docker_sandbox helper."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            sb = SandboxExecutor(workspace_path=ws)
            if not DockerSandboxExecutor.is_docker_available():
                with self.assertRaises(RuntimeError):
                    sb.run_in_docker_sandbox(["echo", "hi"])

    def test_live_browser_explorer_locator_generation(self):
        """Verifies computing resilient Playwright locators across diverse elements."""
        cases = [
            ({"test_id": "submit-btn", "tag": "button"}, "page.get_by_test_id('submit-btn')"),
            ({"element_id": "username-input", "tag": "input"}, "page.locator('#username-input')"),
            ({"name": "email", "tag": "input"}, "page.locator(\"input[name='email']\")"),
            ({"tag": "button", "text": "Save Changes"}, "page.get_by_role('button', name='Save Changes')"),
            ({"tag": "input", "input_type": "radio"}, "page.locator(\"input[type='radio']\").first"),
            ({"tag": "input", "input_type": "checkbox"}, "page.locator(\"input[type='checkbox']\").first"),
        ]
        for info, expected in cases:
            loc = LiveBrowserExplorerAgent._compute_suggested_locator(info)
            self.assertEqual(loc, expected)

    def test_browser_exploration_report_summary(self):
        """Verifies report summary formatting with elements, toasts, and errors."""
        report = BrowserExplorationReport(
            url="https://app.test/login",
            title="Login Page",
            status="SUCCESS",
            elements=[
                DOMElementInfo(tag="button", text="Sign In", suggested_locator="page.get_by_role('button', name='Sign In')"),
                DOMElementInfo(tag="input", text="", input_type="checkbox", suggested_locator="page.locator(\"input[type='checkbox']\").first"),
            ],
            toasts=["Welcome back!"],
            console_errors=["Failed to load favicon"],
        )
        summary = report.to_summary_str()
        self.assertIn("Login Page", summary)
        self.assertIn("Sign In", summary)
        self.assertIn("Welcome back!", summary)
        self.assertIn("Console Errors: 1", summary)

    def test_event_stream_bus_emission_and_subscription(self):
        """Verifies EventStreamBus records, notifies subscribers, and persists to disk."""
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            bus = EventStreamBus(workspace_path=ws)

            received: list[HermesEvent] = []
            bus.subscribe(lambda ev: received.append(ev))

            ev1 = bus.emit(
                event_type="ActionTriggered",
                source_agent="AutomationTesterAgent",
                payload={"command": "pytest -q"},
            )
            ev2 = bus.emit(
                event_type="PatchSynthesized",
                source_agent="TestHealerAgent",
                payload={"file": "test_auth.py", "edits": 1},
            )

            # Assert in-memory events
            self.assertEqual(len(bus.get_events()), 2)
            self.assertEqual(len(received), 2)
            self.assertEqual(received[0].event_type, "ActionTriggered")
            self.assertEqual(received[1].event_type, "PatchSynthesized")

            # Assert disk persistence and replay
            self.assertTrue(bus.log_file.is_file())
            replayed = bus.replay_from_disk()
            self.assertEqual(len(replayed), 2)
            self.assertEqual(replayed[0].event_id, ev1.event_id)
            self.assertEqual(replayed[1].event_id, ev2.event_id)


if __name__ == "__main__":
    unittest.main()
