"""Ensure unit tests run deterministically without leaking host LLM env vars."""
import pytest

_LLM_ENV_VARS = [
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_MODEL",
    "XAI_API_KEY", "GROQ_API_KEY", "FIREWORKS_API_KEY",
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL", "AZURE_OPENAI_DEPLOYMENT",
    "OLLAMA_BASE_URL", "OLLAMA_MODEL",
    "LMSTUDIO_BASE_URL", "LLAMACPP_BASE_URL",
    "LOCAL_LLM_BASE_URL", "LOCALAI_BASE_URL", "LOCAL_LLM_MODEL",
    "HERMES_LLM_PROVIDER", "LLM_PROVIDER", "CLAUDE_CODE_USE",
]


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    for key in _LLM_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
