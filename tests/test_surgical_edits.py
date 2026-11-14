import json
from pathlib import Path
from unittest import mock
from hermes.core.orchestrator.scrum_hierarchy import SubTaskTicket
from hermes.execution.llm_provider_adapter import (
    AgentRole,
    HermesLLMAdapter,
    apply_surgical_edit,
    extract_json_from_response,
)
from hermes.ingestion.context_slicer import ContextSlicer


def test_extract_json_nested():
    raw = '```json\n{"edits": [{"file": "a.py", "search": "x = {\\"a\\": 1}", "replace": "x = {\\"a\\": 2}"}]}\n```'
    assert extract_json_from_response(raw)["edits"][0]["replace"] == 'x = {"a": 2}'


def test_surgical_edits_preserves_assertions(tmp_path: Path):
    orig = "def test_1():\n    assert True\n\ndef test_2():\n    assert 'a' == 'b'\n"
    ad = HermesLLMAdapter(tmp_path)
    tk = SubTaskTicket("H1", "Fix", 2, "TIER_3_JUNIOR_SWE", ["Test_Suite3/Logout_Playwright.py"])
    resp = json.dumps({"edits": [{"file": "Logout_Playwright.py", "search": "assert 'a' == 'b'", "replace": "assert 'b' == 'b'"}]})
    with mock.patch.object(ad, "resolve_provider", return_value="ollama"), mock.patch.object(ad, "complete", return_value=resp):
        p = ad.propose_patch(AgentRole.TEST_HEALER_AGENT, tk, "TIER_3_JUNIOR_SWE", {"Test_Suite3/Logout_Playwright.py": orig})
    assert "def test_1():" in p["Test_Suite3/Logout_Playwright.py"]
    assert "assert 'b' == 'b'" in p["Test_Suite3/Logout_Playwright.py"]


def test_apply_surgical_edit_level1_exact():
    orig = "def foo():\n    return 1\n"
    res = apply_surgical_edit(orig, "return 1", "return 2")
    assert res == "def foo():\n    return 2\n"


def test_apply_surgical_edit_level2_raw_string_and_quotes():
    # Diagnostic test reproducing Logout_Playwright.py drift
    orig = (
        "def test_tc02_logout(page):\n"
        "    page.goto('http://app.local')\n"
        "    expect(page).to_have_url(re.compile(r\".*(legacy-signin-v1).*\"))\n"
    )
    # LLM emitted single quotes and no raw-string prefix and no leading indent
    search = "expect(page).to_have_url(re.compile('.*(legacy-signin-v1).*'))"
    replace = "expect(page).to_have_url(re.compile(r\".*(legacy-signin-v2).*\"))"
    res = apply_surgical_edit(orig, search, replace)
    assert res is not None
    # Must preserve the 4-space indentation
    assert "    expect(page).to_have_url(re.compile(r\".*(legacy-signin-v2).*\"))" in res
    assert "def test_tc02_logout(page):" in res


def test_apply_surgical_edit_level3_sequencematcher():
    orig = (
        "def test_calc():\n"
        "    result = compute_total_sum(a=10, b=20, tax=5)\n"
        "    assert result == 35\n"
    )
    # LLM emitted slight parameter spacing difference
    search = "result = compute_total_sum(a=10,b=20,tax=5)"
    replace = "result = compute_total_sum(a=10, b=20, tax=0)"
    res = apply_surgical_edit(orig, search, replace)
    assert res is not None
    assert "    result = compute_total_sum(a=10, b=20, tax=0)" in res


def test_context_slicer_slice_file_around_line():
    # File <= 120 lines returns full content
    small_content = "\n".join([f"line_{i}" for i in range(50)])
    assert ContextSlicer.slice_file_around_line(small_content, 25) == small_content

    # File > 120 lines
    imports = "import re\nimport pytest\nfrom playwright.sync_api import expect\n\n"
    body = "\n".join([f"def func_{i}():\n    pass" for i in range(1, 100)])
    big_content = imports + body
    assert len(big_content.splitlines()) > 120

    sliced = ContextSlicer.slice_file_around_line(big_content, target_line=150, window_size=60)
    assert "import re" in sliced
    assert "from playwright.sync_api import expect" in sliced
    assert "omitted for context brevity" in sliced
    assert len(sliced.splitlines()) < 100


def test_propose_patch_with_full_file_contents_and_slicing(tmp_path: Path):
    full_orig = (
        "import re\n\n"
        "def test_1():\n"
        "    assert True\n\n"
        "def test_2():\n"
        "    expect(page).to_have_url(re.compile(r\".*(v1).*\"))\n"
    )
    # Sliced representation passed to LLM
    sliced_view = (
        "import re\n\n"
        "# ... [omitted] ...\n"
        "def test_2():\n"
        "    expect(page).to_have_url(re.compile(r\".*(v1).*\"))\n"
    )

    ad = HermesLLMAdapter(tmp_path)
    tk = SubTaskTicket("H1", "Fix", 2, "TIER_3_JUNIOR_SWE", ["test_file.py"])
    resp = json.dumps({
        "edits": [{
            "file": "test_file.py",
            "search": "expect(page).to_have_url(re.compile('.*(v1).*'))",
            "replace": "expect(page).to_have_url(re.compile(r\".*(v2).*\"))",
        }]
    })
    with mock.patch.object(ad, "resolve_provider", return_value="ollama"), mock.patch.object(ad, "complete", return_value=resp):
        p = ad.propose_patch(
            AgentRole.TEST_HEALER_AGENT,
            tk,
            "TIER_3_JUNIOR_SWE",
            file_contents={"test_file.py": sliced_view},
            full_file_contents={"test_file.py": full_orig},
        )
    # Crucial: proposed changes must contain the FULL file with edits, NOT the slice!
    assert "test_file.py" in p
    assert "def test_1():" in p["test_file.py"]
    assert "assert True" in p["test_file.py"]
    assert ".*(v2).*" in p["test_file.py"]
    assert "# ... [omitted] ..." not in p["test_file.py"]


def test_send_openai_chat_streaming_and_num_ctx(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HERMES_LIVE_PROGRESS", "1")
    ad = HermesLLMAdapter(tmp_path)

    sse_lines = [
        b'data: {"choices": [{"delta": {"reasoning": "analyzing file"}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": "{\\"edits\\": []}"}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    class MockSSEResponse:
        def __init__(self):
            self.headers = {"Content-Type": "text/event-stream"}
            self._iter = iter(sse_lines)

        def __iter__(self):
            return self._iter

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    captured_request = {}

    def mock_urlopen(req, timeout=120):
        captured_request["body"] = json.loads(req.data.decode("utf-8"))
        return MockSSEResponse()

    with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
        out = ad._send_openai_chat(
            provider="ollama",
            model_name="qwen2.5-coder:7b",
            system_prompt="sys",
            user_prompt="usr",
            timeout=60,
        )

    assert out == '{"edits": []}'
    assert captured_request["body"]["stream"] is True
    assert captured_request["body"]["options"] == {"num_ctx": 8192}
    assert captured_request["body"]["model"] == "qwen2.5-coder:7b"

