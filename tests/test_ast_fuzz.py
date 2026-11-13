"""
Property-Based and Fuzz Testing for Multi-Language AST Guards & Patch Applier
Owner: SecurityGateAgent & QACriticAgent
Phase: Option 6 & Future-Proofing

Verifies that:
- AST guards never crash on malformed, deeply nested, or mutated syntax.
- Zero assertion erosion is strictly enforced across randomized edge cases.
- Delta-SAST never misses injected dangerous sinks even with whitespace/comment mutations.
"""

from __future__ import annotations

import random
import string
import pytest

from core.audit.delta_sast import (
    AssertionErosionChecker,
    DeltaSASTScanner,
    PatchGuard,
)
from hermes.guards.language_ast_guard import LanguageASTGuard


def generate_random_identifier(length: int = 8) -> str:
    letters = string.ascii_letters + "_"
    return "".join(random.choice(letters) for _ in range(length))


def generate_mutated_python_assertion() -> str:
    """Generate various valid and edge-case Python assertions."""
    templates = [
        "assert {lhs} == {rhs}",
        "assert {lhs} is not None, 'custom error msg'",
        "assert ({lhs} > 0 and {rhs} < 100)",
        "self.assertEqual({lhs}, {rhs})",
        "self.assertTrue({lhs})",
        "pytest.raises(ValueError)",
    ]
    lhs = generate_random_identifier()
    rhs = str(random.randint(0, 999))
    return random.choice(templates).format(lhs=lhs, rhs=rhs)


class TestASTFuzzAndRobustness:
    """Fuzz testing AST parsing and assertion erosion engines."""

    def test_randomized_python_assertions_counted_deterministically(self):
        """Random assertions should be counted without exceptions."""
        for _ in range(50):
            n_assertions = random.randint(1, 10)
            lines = [generate_mutated_python_assertion() for _ in range(n_assertions)]
            code = "\n".join(lines)

            res = LanguageASTGuard.analyze(code, language="python")
            assert res.assertion_count >= n_assertions

    def test_fuzzed_syntax_errors_handled_gracefully(self):
        """Malformed code strings must never raise unhandled exceptions."""
        malformed_snippets = [
            "def foo(::: invalid syntax",
            "assert = = = 123",
            "expect((((",
            "\"\"\" unclosed docstring",
            "class 1234: pass",
            "\x00\x01\x02 binary blob in code",
            "assert True if else",
        ]
        for snippet in malformed_snippets:
            # Must not crash
            res = LanguageASTGuard.analyze(snippet, language="python")
            assert res is not None

            verdict = PatchGuard.verify(
                original_code="assert 1 == 1",
                proposed_code=snippet,
                target_file="test_fuzz.py",
            )
            assert verdict is not None

    def test_fuzzed_assertion_erosion_detection(self):
        """Ensure assertion drops are caught even across random statement ordering."""
        for _ in range(25):
            orig_count = random.randint(3, 8)
            drop_count = random.randint(1, orig_count - 1)
            new_count = orig_count - drop_count

            orig_lines = [f"    assert x_{i} == {i}" for i in range(orig_count)]
            patched_lines = [f"    assert x_{i} == {i}" for i in range(new_count)]

            violations = AssertionErosionChecker.check_assertion_erosion(
                original_lines=orig_lines,
                patched_lines=patched_lines,
            )
            assert any(v.rule_id == "EROSION_ASSERTION_DELETED" for v in violations)

    def test_fuzzed_dangerous_sink_obfuscation(self):
        """Delta-SAST must catch dangerous sinks even when padded with whitespace."""
        sinks = [
            "  eval ( payload )  ",
            "exec ( code )",
            "os . system ( cmd )",
            "subprocess . run ( cmd , shell = True )",
            "verify = False ",
            "ignoreHTTPSErrors: true",
        ]
        for sink in sinks:
            violations = DeltaSASTScanner.scan_added_lines([sink])
            assert len(violations) > 0, f"Failed to catch padded sink: {sink}"

    def test_multi_language_fallback_resilience(self):
        """Languages with non-standard syntax should analyze cleanly."""
        languages = ["python", "typescript", "java", "go", "csharp"]
        for lang in languages:
            code = "def / func / void test() { assert(true); }"
            res = LanguageASTGuard.analyze(code, language=lang)
            assert res is not None
            assert res.language == lang
