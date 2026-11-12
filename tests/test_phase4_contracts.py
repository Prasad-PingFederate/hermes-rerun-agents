"""
Contracts & Verification Suite for GAP-26 and GAP-28
- Locks single-source-of-truth invariants across orchestrator, write gate, CLI, and API.
- Verifies behavior on an unknown project (tests/fixtures/stack_project/).
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.orchestrator.scrum_hierarchy import (
    ESCALATION_CHAIN,
    ModelTier,
    SubTaskTicket,
    route_tier_by_complexity,
)
from llm_provider_adapter import ORDERED_PROVIDERS, resolve_provider
from scrum_master_orchestrator import ScrumMasterOrchestrator
import server
from sprint_state_store import SprintStateStore
from write_gate_controller import HumanWriteGateController


class FakeStackLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        fixed_stack_code = (
            "class Stack:\n"
            "    \"\"\"Simple stack collection.\"\"\"\n\n"
            "    def __init__(self):\n"
            "        self._items = []\n\n"
            "    def push(self, item):\n"
            "        self._items.append(item)\n\n"
            "    def pop(self):\n"
            "        if not self._items:\n"
            "            raise IndexError('pop from empty stack')\n"
            "        return self._items.pop()\n\n"
            "    def is_empty(self):\n"
            "        return len(self._items) == 0\n\n"
            "    def size(self):\n"
            "        return len(self._items)\n"
        )
        res = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({
                            "proposed_changes": {
                                "src/stack.py": fixed_stack_code,
                            }
                        }),
                    }
                }
            ]
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode("utf-8"))


class TestPhase4Contracts(unittest.TestCase):
    """GAP-26: Architectural invariants and API contracts locking single pipeline."""

    def test_exactly_one_scrum_master_orchestrator_class(self):
        """Contract 1: Exactly one class named ScrumMasterOrchestrator exists in the repo, in scrum_master_orchestrator.py."""
        class_locations = []
        for py_path in REPO_ROOT.rglob("*.py"):
            # Skip virtual environments or hidden dirs if any
            if ".git" in py_path.parts or ".pytest_cache" in py_path.parts or "venv" in py_path.parts or ".rerun_tasks" in py_path.parts or ".hermes_artifacts" in py_path.parts:
                continue
            try:
                tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"), filename=str(py_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == "ScrumMasterOrchestrator":
                        rel = py_path.relative_to(REPO_ROOT).as_posix()
                        class_locations.append(rel)
            except Exception:
                pass

        self.assertEqual(
            class_locations,
            ["scrum_master_orchestrator.py"],
            f"Expected exactly one ScrumMasterOrchestrator in scrum_master_orchestrator.py, found in: {class_locations}",
        )

        # Invariant on core/orchestrator/scrum_hierarchy.py
        scrum_hierarchy_path = REPO_ROOT / "core" / "orchestrator" / "scrum_hierarchy.py"
        tree = ast.parse(scrum_hierarchy_path.read_text(encoding="utf-8"), filename=str(scrum_hierarchy_path))
        top_classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        top_funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("ScrumMasterOrchestrator", top_classes)
        self.assertIn("ModelTier", top_classes)
        self.assertIn("SubTaskTicket", top_classes)
        self.assertIn("route_tier_by_complexity", top_funcs)

    def test_human_write_gate_approve_proposal_is_one_line_alias(self):
        """Contract 2: Only HumanWriteGateController.approve_and_apply writes; approve_proposal is a one-line alias."""
        source = inspect.getsource(HumanWriteGateController.approve_proposal)
        self.assertIn("approve_and_apply", source)
        self.assertIn("return self.approve_and_apply", source)
        lines = [line.strip() for line in source.splitlines() if line.strip() and not line.strip().startswith(('def ', '"""', '#', '@'))]
        # Should be just the return call to approve_and_apply
        self.assertEqual(len(lines), 1, f"Expected approve_proposal to be a one-line alias, got: {lines}")

    def test_fastapi_sprint_endpoints_require_token_and_reject_with_401(self):
        """Contract 3: POST /api/sprint/run, GET /api/sprint/{id}, and POST /api/sprint/{id}/approve require X-Hermes-Token."""
        client = TestClient(server.app)
        os.environ["HERMES_API_TOKEN"] = "test-secret-token"

        # 1. Missing token -> 401
        r1 = client.post("/api/sprint/run", json={"mode": "heal"})
        self.assertEqual(r1.status_code, 401)

        r2 = client.get("/api/sprint/sprint_nonexistent")
        self.assertEqual(r2.status_code, 401)

        r3 = client.post("/api/sprint/sprint_nonexistent/approve", json={})
        self.assertEqual(r3.status_code, 401)

        # 2. Wrong token -> 401
        bad_headers = {"X-Hermes-Token": "invalid-wrong-token"}
        r4 = client.post("/api/sprint/run", json={"mode": "heal"}, headers=bad_headers)
        self.assertEqual(r4.status_code, 401)

        r5 = client.get("/api/sprint/sprint_nonexistent", headers=bad_headers)
        self.assertEqual(r5.status_code, 401)

        r6 = client.post("/api/sprint/sprint_nonexistent/approve", json={}, headers=bad_headers)
        self.assertEqual(r6.status_code, 401)

    def test_fastapi_heal_mode_on_ledger_fixture_readable_by_sprint_state_store(self):
        """Contract 3 (continued): TestClient mode=heal on ledger failure with HERMES_LLM_PROVIDER unset returns a sprint id that load_sprint reads."""
        client = TestClient(server.app)
        old_token = os.environ.get("HERMES_API_TOKEN")
        old_provider = os.environ.get("HERMES_LLM_PROVIDER")
        os.environ["HERMES_API_TOKEN"] = "token-phase4-contract"
        os.environ.pop("HERMES_LLM_PROVIDER", None)

        try:
            resp = client.post(
                "/api/sprint/run",
                json={
                    "mode": "heal",
                    "failure_output": (
                        "FAILED tests/test_ledger.py::test_negative_deposit_raises - "
                        "Failed: DID NOT RAISE <class 'ValueError'>\n"
                        "tests/test_ledger.py:10: in test_negative_deposit_raises\n"
                        "    ledger.deposit(-50.0)\n"
                        "E   Failed: DID NOT RAISE <class 'ValueError'>\n"
                    ),
                    "scope": ["src/InMemoryLedger.py", "tests/test_ledger.py"],
                },
                headers={"X-Hermes-Token": "token-phase4-contract"},
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            res_data = resp.json()
            self.assertIn("sprint_id", res_data)
            sprint_id = res_data["sprint_id"]

            loaded = server.sprint_store.load_sprint(sprint_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["sprint_id"], sprint_id)
            self.assertIn("tickets", loaded)
            self.assertTrue(len(loaded["tickets"]) >= 1)
        finally:
            if old_token:
                os.environ["HERMES_API_TOKEN"] = old_token
            else:
                os.environ.pop("HERMES_API_TOKEN", None)
            if old_provider:
                os.environ["HERMES_LLM_PROVIDER"] = old_provider

    def test_cli_providers_prints_all_18_provider_ids(self):
        """Contract 4: python hermes_cli.py providers prints all 18 provider ids."""
        res = subprocess.run(
            [sys.executable, "hermes_cli.py", "providers"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        output = res.stdout

        expected_18 = [
            "ollama", "lmstudio", "llamacpp", "vllm", "tgi", "localai",
            "openai_compatible", "openai", "grok", "groq", "openrouter",
            "mistral", "deepseek", "together", "fireworks", "azure_openai",
            "gemini", "anthropic"
        ]
        for p in expected_18:
            self.assertIn(p, output, f"Provider '{p}' missing from hermes_cli.py providers output!")

    def test_git_grep_invariants_exit_zero_clean(self):
        """Contracts 5 & 6: git grep 'propose_patch' in cli/demo and git grep obsolete flash model print nothing."""
        # 1. propose_patch in hermes_cli.py and scripts/run_live_demo.py
        p1 = subprocess.run(
            ["git", "grep", "propose_patch", "--", "hermes_cli.py", "scripts/run_live_demo.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(p1.returncode, 0, f"propose_patch found in cli or demo: {p1.stdout}")
        self.assertEqual(p1.stdout.strip(), "")

        # 2. obsolete gemini flash model literal
        obsolete_model = "gemini" + "-1.5-" + "flash"
        p2 = subprocess.run(
            ["git", "grep", obsolete_model],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(p2.returncode, 0, f"{obsolete_model} found in repo: {p2.stdout}")
        self.assertEqual(p2.stdout.strip(), "")


class TestGAP28StackProject(unittest.TestCase):
    """GAP-28: An unknown project (tests/fixtures/stack_project/) that LocalHeuristicEngine does not know."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        # Copy stack_project fixture to temporary workspace
        fixture_dir = REPO_ROOT / "tests" / "fixtures" / "stack_project"
        shutil.copytree(fixture_dir / "src", self.workspace / "src")
        shutil.copytree(fixture_dir / "tests", self.workspace / "tests")

        # Initialize git in workspace so TimeMachine and worktrees function
        subprocess.run(["git", "init"], cwd=str(self.workspace), capture_output=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(self.workspace), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@hermes.ai"], cwd=str(self.workspace), capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial stack project"], cwd=str(self.workspace), capture_output=True)

        self.initial_stack_code = (self.workspace / "src" / "stack.py").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stack_project_no_provider_fails_and_does_not_write_workspace(self):
        """GAP-28: With no provider configured, run_sprint(mode='heal') does not invent a fix and leaves workspace untouched."""
        # Unset all provider keys
        for key in list(os.environ.keys()):
            if "LLM" in key or "API_KEY" in key or "URL" in key:
                if key not in ("PATH", "SYSTEMROOT", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
                    os.environ.pop(key, None)

        self.assertEqual(resolve_provider(), "none")
        orch = ScrumMasterOrchestrator(self.workspace)

        result = orch.run_sprint(
            mode="heal",
            pytest_cmd=[sys.executable, "-m", "pytest", "tests/test_stack.py"],
            auto_approve=False,
        )

        # Sprint fails because heuristic does not synthesize arbitrary stack repairs
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("error", result)

        # Caller workspace must NOT be modified
        current_stack_code = (self.workspace / "src" / "stack.py").read_text(encoding="utf-8")
        self.assertEqual(current_stack_code, self.initial_stack_code)

    def test_stack_project_fake_openai_provider_classifies_product_bug_and_rolls_back_on_failed_verification(self):
        """GAP-28: With fake LLM server returning IndexError fix, classifies PRODUCT_BUG, scopes src/stack.py, passes sandbox, and rolls back on verification failure."""
        server = HTTPServer(("127.0.0.1", 0), FakeStackLLMHandler)
        port = server.server_port
        t = Thread(target=server.serve_forever)
        t.daemon = True
        t.start()

        fake_url = f"http://127.0.0.1:{port}/v1"
        os.environ["HERMES_LLM_PROVIDER"] = "openai_compatible"
        os.environ["LOCAL_LLM_BASE_URL"] = fake_url
        os.environ["LOCAL_LLM_MODEL"] = "fake-stack-model"

        try:
            orch = ScrumMasterOrchestrator(self.workspace)

            # 1. Run sprint in heal mode with fake provider
            result = orch.run_sprint(
                mode="heal",
                pytest_cmd=[sys.executable, "-m", "pytest", "tests/test_stack.py"],
                auto_approve=False,
            )

            # In heal mode, classification must be PRODUCT_BUG
            self.assertEqual(result["classification"], "PRODUCT_BUG")

            # Ticket must scope src/stack.py exclusively (no tests/*)
            ticket = result["tickets"][0]
            self.assertEqual(ticket["allowed_files"], ["src/stack.py"])
            self.assertFalse(any("test" in f for f in ticket["allowed_files"]))

            # Staged in HumanWriteGate
            self.assertEqual(result["status"], "AWAITING_WRITE_GATE")
            sprint_id = result["sprint_id"]

            # 2. Approve and apply with failing verification callback -> forces rollback!
            failing_verification_fn = lambda: False
            apply_res = orch.write_gate.approve_and_apply(
                sprint_id=sprint_id,
                auto_approve=True,
                verification_fn=failing_verification_fn,
            )

            self.assertFalse(apply_res["success"])
            self.assertTrue(apply_res["rolled_back"])

            # Workspace must be safely restored to baseline
            current_stack_code = (self.workspace / "src" / "stack.py").read_text(encoding="utf-8")
            self.assertEqual(current_stack_code, self.initial_stack_code)
        finally:
            server.shutdown()
            os.environ.pop("HERMES_LLM_PROVIDER", None)
            os.environ.pop("LOCAL_LLM_BASE_URL", None)

    def test_stack_project_story_mode_ticket_ordering(self):
        """GAP-28: Story mode creates two tickets: TestCaseWriter (tests/*) and Developer (src/*, depends_on writer). Order is in saved sprint."""
        orch = ScrumMasterOrchestrator(self.workspace)
        result = orch.run_sprint(
            mode="story",
            story="Add size and clear capabilities to Stack in src/stack.py and tests/test_stack.py",
            scope=["src/stack.py", "tests/test_stack.py"],
            auto_approve=False,
        )

        sprint_id = result["sprint_id"]
        saved = orch.store.load_sprint(sprint_id)
        tickets = saved["tickets"]

        self.assertEqual(len(tickets), 2)

        # Ticket 1: TestCaseWriterAgent under tests/
        t_writer = tickets[0]
        self.assertIn("WRITER", t_writer["ticket_id"])
        self.assertTrue(all("test" in f.lower() for f in t_writer["allowed_files"]))

        # Ticket 2: DeveloperAgent under src/, depends_on writer
        t_dev = tickets[1]
        self.assertIn("DEV", t_dev["ticket_id"])
        self.assertTrue(all(not ("test" in f.lower()) for f in t_dev["allowed_files"]))
        self.assertIn(t_writer["ticket_id"], t_dev.get("depends_on", []))


if __name__ == "__main__":
    unittest.main()
