"""
Tests for GAP-19: Hermes LLM Provider Adapter & Multi-Wire Network Client.
Zero external dependencies (uses standard library http.server, unittest).
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from core.healer.gemini_flash import GeminiFlashHealer
from llm_provider_adapter import (
    AgentRole,
    HermesLLMAdapter,
    resolve_model_for_call,
    resolve_provider,
)


class FakeLLMServer(HTTPServer):
    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.received_requests = []


class FakeLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        req_record = {
            "path": self.path,
            "headers": dict(self.headers),
            "body": body.decode("utf-8", errors="replace"),
        }
        self.server.received_requests.append(req_record)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        # Wire responses
        if "generateContent" in self.path:
            # Gemini response
            res = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "proposed_changes": {"src/app.py": "print('gemini healed')"}
                                    })
                                }
                            ]
                        }
                    }
                ]
            }
        elif "messages" in self.path:
            # Anthropic response
            res = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "proposed_changes": {"src/app.py": "print('anthropic healed')"}
                        }),
                    }
                ]
            }
        else:
            # OpenAI / Ollama / Grok / Groq chat response
            res = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({
                                "proposed_changes": {"src/app.py": "print('openai healed')"},
                                "category": "App Bug",
                                "root_cause": "Fixed issue",
                                "files": [{"path": "tests/test_foo.py", "unified_diff": "--- a\n+++ b"}],
                            }),
                        }
                    }
                ]
            }
        self.wfile.write(json.dumps(res).encode("utf-8"))


class TestLLMProviders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeLLMServer(("127.0.0.1", 0), FakeLLMHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.server.received_requests.clear()
        preserved = {
            k: v for k, v in os.environ.items()
            if k.upper() in ("SYSTEMROOT", "WINDIR", "PATH", "TMP", "TEMP", "SYSTEMDRIVE", "PYTHONPATH")
        }
        self.env_patcher = mock.patch.dict(os.environ, preserved, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_ollama_base_url_sends_chat_completions_with_tier3_model(self):
        """OLLAMA_BASE_URL set and no cloud keys sends POST /chat/completions with model equal to RERUN_TIER3_MODEL."""
        os.environ["OLLAMA_BASE_URL"] = f"{self.base_url}/v1"
        os.environ["RERUN_TIER3_MODEL"] = "qwen2.5-coder:7b"

        self.assertEqual(resolve_provider(), "ollama")
        adapter = HermesLLMAdapter()
        res = adapter.complete(
            role=AgentRole.DEVELOPER_AGENT,
            tier="TIER_3_JUNIOR_SWE",
            system_prompt="system",
            user_prompt="user task",
        )
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        self.assertTrue(req["path"].endswith("/chat/completions"))
        req_body = json.loads(req["body"])
        self.assertEqual(req_body["model"], "qwen2.5-coder:7b")

    def test_grok_xai_api_key_posts_to_v1_chat_completions_with_bearer(self):
        """HERMES_LLM_PROVIDER=grok and XAI_API_KEY set posts to https://api.x.ai/v1/chat/completions with Authorization: Bearer."""
        os.environ["HERMES_LLM_PROVIDER"] = "grok"
        os.environ["XAI_BASE_URL"] = f"{self.base_url}/v1"
        os.environ["XAI_API_KEY"] = "xai-test-secret-key"
        os.environ["XAI_MODEL"] = "grok-2-latest"

        self.assertEqual(resolve_provider(), "grok")
        adapter = HermesLLMAdapter()
        adapter.complete(
            role=AgentRole.SCRUM_MASTER_ORCHESTRATOR,
            tier="TIER_1_TECH_LEAD",
            system_prompt="lead",
            user_prompt="plan",
        )
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        self.assertTrue(req["path"].endswith("/chat/completions"))
        auth = req["headers"].get("Authorization") or req["headers"].get("authorization")
        self.assertEqual(auth, "Bearer xai-test-secret-key")
        req_body = json.loads(req["body"])
        self.assertEqual(req_body["model"], "grok-2-latest")

    def test_anthropic_posts_to_messages_with_headers(self):
        """HERMES_LLM_PROVIDER=anthropic posts to /v1/messages with x-api-key and anthropic-version."""
        os.environ["HERMES_LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_BASE_URL"] = f"{self.base_url}/v1"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
        os.environ["ANTHROPIC_MODEL"] = "claude-3-5-sonnet-20241022"

        self.assertEqual(resolve_provider(), "anthropic")
        adapter = HermesLLMAdapter()
        adapter.complete(
            role=AgentRole.REQUIREMENTS_AGENT,
            tier="TIER_2_SENIOR_SWE",
            system_prompt="sys",
            user_prompt="user",
        )
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        self.assertTrue(req["path"].endswith("/messages"))
        headers = {k.lower(): v for k, v in req["headers"].items()}
        self.assertEqual(headers.get("x-api-key"), "sk-ant-test-key")
        self.assertEqual(headers.get("anthropic-version"), "2023-06-01")
        req_body = json.loads(req["body"])
        self.assertEqual(req_body["model"], "claude-3-5-sonnet-20241022")

    def test_gemini_uses_model_from_gemini_model_in_url(self):
        """HERMES_LLM_PROVIDER=gemini uses the model from GEMINI_MODEL in the URL, not a fallback model."""
        os.environ["HERMES_LLM_PROVIDER"] = "gemini"
        os.environ["GEMINI_BASE_URL"] = self.base_url
        os.environ["GEMINI_API_KEY"] = "gemini-test-key"
        os.environ["GEMINI_MODEL"] = "gemini-2.0-flash-exp"

        self.assertEqual(resolve_provider(), "gemini")
        adapter = HermesLLMAdapter()
        adapter.complete(
            role=AgentRole.DEVELOPER_AGENT,
            tier="TIER_3_JUNIOR_SWE",
            system_prompt="sys",
            user_prompt="user",
        )
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        self.assertIn("/models/gemini-2.0-flash-exp:generateContent", req["path"])
        self.assertNotIn("gemini-" + "1.5-flash", req["path"])

    def test_per_agent_override_uses_groq_even_when_global_provider_is_ollama(self):
        """HERMES_AGENT_DEVELOPER_AGENT_MODEL=groq:llama-3.3-70b-versatile on Developer call uses Groq even when global provider is ollama."""
        os.environ["HERMES_LLM_PROVIDER"] = "ollama"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434/v1"
        os.environ["HERMES_AGENT_DEVELOPER_AGENT_MODEL"] = "groq:llama-3.3-70b-versatile"
        os.environ["GROQ_BASE_URL"] = f"{self.base_url}/v1"
        os.environ["GROQ_API_KEY"] = "gsk_test_groq_key"

        adapter = HermesLLMAdapter()
        # Global is ollama
        self.assertEqual(adapter.resolve_provider(), "ollama")
        # For DeveloperAgent, provider is overridden to groq
        self.assertEqual(adapter.resolve_provider(AgentRole.DEVELOPER_AGENT), "groq")

        adapter.complete(
            role=AgentRole.DEVELOPER_AGENT,
            tier="TIER_3_JUNIOR_SWE",
            system_prompt="sys",
            user_prompt="user",
        )
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        auth = req["headers"].get("Authorization") or req["headers"].get("authorization")
        self.assertEqual(auth, "Bearer gsk_test_groq_key")
        req_body = json.loads(req["body"])
        self.assertEqual(req_body["model"], "llama-3.3-70b-versatile")

    def test_connection_error_with_configured_provider_raises(self):
        """A connection error with a provider configured raises and does not return the hardcoded InMemoryLedger patch."""
        # Point to closed port
        os.environ["HERMES_LLM_PROVIDER"] = "ollama"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:54321/v1"
        os.environ["OLLAMA_MODEL"] = "qwen2.5-coder:7b"
        os.environ["HERMES_LLM_TIMEOUT"] = "2"

        adapter = HermesLLMAdapter()

        class DummyTicket:
            ticket_id = "TICK-ERR-01"
            title = "Test Error"
            allowed_files = ["src/InMemoryLedger.py"]

        with self.assertRaises(RuntimeError):
            adapter.propose_patch(
                agent_role=AgentRole.DEVELOPER_AGENT,
                ticket=DummyTicket(),
                tier="TIER_3_JUNIOR_SWE",
                file_contents={"src/InMemoryLedger.py": "class InMemoryLedger: pass"},
            )

    def test_diagnose_failure_with_only_ollama_base_url_does_not_read_gemini_api_key(self):
        """diagnose_failure with only OLLAMA_BASE_URL does not read GEMINI_API_KEY."""
        os.environ["OLLAMA_BASE_URL"] = f"{self.base_url}/v1"
        os.environ["OLLAMA_MODEL"] = "qwen2.5-coder:7b"

        # Explicitly ensure GEMINI_API_KEY is not in os.environ
        os.environ.pop("GEMINI_API_KEY", None)

        healer = GeminiFlashHealer()
        res = healer.diagnose_failure(
            test_name="tests/test_demo.py",
            error_message="AssertionError: expected True but got False",
            traceback_str="tests/test_demo.py:10: in test_foo\nassert False",
        )
        self.assertIsNotNone(res)
        self.assertIn("Hermes LLM (ollama)", res.get("engine", ""))
        self.assertTrue(len(self.server.received_requests) >= 1)
        req = self.server.received_requests[-1]
        self.assertTrue(req["path"].endswith("/chat/completions"))

    def _setup_fake_claude(self, temp_dir: Path, fail: bool = False, bad_json: bool = False) -> Path:
        """Create a mock Claude Code CLI script and batch file on PATH."""
        info_file = temp_dir / "claude_call_info.json"
        py_script = temp_dir / "fake_claude.py"
        py_script.write_text(
            f"import sys, os, json\n"
            f"if '--version' in sys.argv:\n"
            f"    print('claude version 2.1.0')\n"
            f"    sys.exit(0)\n"
            f"info = {{'argv': sys.argv, 'cwd': os.getcwd()}}\n"
            f"with open(r'{info_file}', 'w', encoding='utf-8') as f:\n"
            f"    json.dump(info, f)\n"
            f"if {fail}:\n"
            f"    print('error_budget: budget exhausted', file=sys.stderr)\n"
            f"    sys.exit(1)\n"
            f"if {bad_json}:\n"
            f"    print('NOT VALID JSON')\n"
            f"    sys.exit(0)\n"
            f"res = {{\n"
            f"    'files': {{\n"
            f"        'src/calc.py': 'def add(a: int, b: int) -> int:\\n    return a + b\\n',\n"
            f"        'unauthorized.py': 'def hacked(): pass\\n'\n"
            f"    }},\n"
            f"    'session_id': 'sess_mock_001',\n"
            f"    'total_cost_usd': 0.04,\n"
            f"    'usage': {{'input_tokens': 100, 'output_tokens': 40}},\n"
            f"}}\n"
            f"print(json.dumps(res))\n",
            encoding="utf-8",
        )
        bat_file = temp_dir / "claude.bat"
        bat_file.write_text(f'@"{sys.executable}" "{py_script}" %*\n', encoding="utf-8")
        sh_file = temp_dir / "claude"
        sh_file.write_text(f'#!{sys.executable}\nimport sys, runpy; runpy.run_path(r"{py_script}", run_name="__main__")\n', encoding="utf-8")
        try:
            os.chmod(str(sh_file), 0o755)
        except Exception:
            pass
        return info_file

    def test_claude_code_read_only_worker_success(self):
        """GAP-29: Claude Code runs as read-only subprocess with security args and drops unauthorized files."""
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            sandbox_dir = temp_path / "sandbox"
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            (sandbox_dir / "src").mkdir(parents=True, exist_ok=True)
            (sandbox_dir / "src" / "calc.py").write_text("def add(a, b): pass\n", encoding="utf-8")

            info_file = self._setup_fake_claude(bin_dir, fail=False)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            os.environ["HERMES_LLM_PROVIDER"] = "ollama"
            os.environ["HERMES_AGENT_DEVELOPER_AGENT_MODEL"] = "claude_code:sonnet"

            try:
                self.assertEqual(resolve_provider(AgentRole.DEVELOPER_AGENT), "claude_code")
                adapter = HermesLLMAdapter(workspace_path=sandbox_dir)

                class MockTicket:
                    ticket_id = "TICK-CALC-001"
                    title = "Fix calculator addition"
                    allowed_files = ["src/calc.py"]

                dummy_ticket = MockTicket()

                raw_json = adapter.complete(
                    role=AgentRole.DEVELOPER_AGENT,
                    tier="TIER_2_SENIOR_SWE",
                    system_prompt="sys",
                    user_prompt="user",
                    cwd=sandbox_dir,
                    allowed_files=["src/calc.py"],
                    ticket=dummy_ticket,
                )
                data = json.loads(raw_json)
                files = data.get("files", {})

                # Assert only allowed files retained
                self.assertIn("src/calc.py", files)
                self.assertNotIn("unauthorized.py", files)

                # Assert session, cost, token usage stored
                self.assertEqual(data.get("session_id"), "sess_mock_001")
                self.assertEqual(data.get("total_cost_usd"), 0.04)
                self.assertIn("input_tokens", data.get("token_usage", {}))

                # Verify execution arguments and working directory
                self.assertTrue(info_file.is_file(), "Fake claude info file was not written!")
                call_info = json.loads(info_file.read_text(encoding="utf-8"))
                argv_str = " ".join(call_info["argv"])

                self.assertIn("--allowedTools", argv_str)
                self.assertIn("Read", argv_str)
                self.assertIn("--disallowedTools", argv_str)
                self.assertIn("Edit,Write,Bash", argv_str)
                self.assertNotIn("dangerously-skip-permissions", argv_str)
                self.assertNotIn("acceptEdits", argv_str)
                self.assertNotIn("bypassPermissions", argv_str)

                # Assert cwd is the sandbox
                self.assertEqual(Path(call_info["cwd"]).resolve(), sandbox_dir.resolve())
            finally:
                os.environ["PATH"] = old_path

    def test_claude_code_failing_fake_raises(self):
        """GAP-29: A failing Claude Code subprocess raises and does not fall through to heuristic."""
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            self._setup_fake_claude(bin_dir, fail=True)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
            os.environ["HERMES_AGENT_DEVELOPER_AGENT_MODEL"] = "claude_code:haiku"

            try:
                adapter = HermesLLMAdapter()
                with self.assertRaises(RuntimeError):
                    adapter.complete(
                        role=AgentRole.DEVELOPER_AGENT,
                        tier="TIER_3_JUNIOR_SWE",
                        system_prompt="sys",
                        user_prompt="user",
                    )
            finally:
                os.environ["PATH"] = old_path

    def test_claude_code_missing_binary_raises(self):
        """GAP-29: Missing claude binary raises RuntimeError immediately."""
        old_path = os.environ.get("PATH", "")
        # Empty PATH where claude cannot be found
        os.environ["PATH"] = ""
        os.environ["HERMES_AGENT_DEVELOPER_AGENT_MODEL"] = "claude_code:haiku"

        try:
            adapter = HermesLLMAdapter()
            with self.assertRaises(RuntimeError) as ctx:
                adapter.complete(
                    role=AgentRole.DEVELOPER_AGENT,
                    tier="TIER_3_JUNIOR_SWE",
                    system_prompt="sys",
                    user_prompt="user",
                )
            self.assertIn("not found on PATH", str(ctx.exception))
        finally:
            os.environ["PATH"] = old_path


if __name__ == "__main__":
    unittest.main()
