"""Unit tests for AST Surgical Patcher (AST-Healer Engine)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from core.healer.ast_surgical_patcher import ASTSurgicalPatcher, FunctionSpan


SAMPLE_CLASS_SOURCE = '''"""Sample module."""

class FinancialAccount:
    """Account implementation."""

    def __init__(self, initial: float = 0.0):
        self.balance = initial
        self.history = []

    def deposit(self, amount: float) -> float:
        self.balance += amount
        return self.balance

    def withdraw(self, amount: float) -> float:
        self.balance -= amount
        return self.balance
'''


class TestASTSurgicalPatcher(unittest.TestCase):
    def test_parse_traceback_location(self):
        tb = (
            'Traceback (most recent call last):\n'
            '  File "/workspace/tests/test_account.py", line 10, in test_negative_deposit\n'
            '    acc.deposit(-50.0)\n'
            '  File "/workspace/src/account.py", line 11, in deposit\n'
            '    self.balance += amount\n'
            'AssertionError: Expected ValueError\n'
        )
        loc = ASTSurgicalPatcher.parse_traceback_location(tb)
        self.assertIsNotNone(loc)
        self.assertEqual(loc["file"], "/workspace/src/account.py")
        self.assertEqual(loc["line"], 11)
        self.assertEqual(loc["function"], "deposit")

    def test_locate_function_span(self):
        span = ASTSurgicalPatcher.locate_function_span(
            SAMPLE_CLASS_SOURCE,
            function_name="deposit",
            line_number=11,
        )
        self.assertIsNotNone(span)
        self.assertEqual(span.name, "deposit")
        self.assertEqual(span.indentation, "    ")
        self.assertEqual(span.start_line, 10)
        self.assertEqual(span.end_line, 12)

    def test_splice_function_patch_preserves_surrounding_code(self):
        span = ASTSurgicalPatcher.locate_function_span(
            SAMPLE_CLASS_SOURCE,
            function_name="deposit",
        )
        self.assertIsNotNone(span)

        replacement = (
            "def deposit(self, amount: float) -> float:\n"
            "    if amount <= 0:\n"
            "        raise ValueError('Deposit must be positive')\n"
            "    self.balance += amount\n"
            "    return self.balance\n"
        )

        patched = ASTSurgicalPatcher.splice_function_patch(
            SAMPLE_CLASS_SOURCE,
            span,
            replacement,
        )

        # Check surrounding methods are untouched
        self.assertIn("class FinancialAccount:", patched)
        self.assertIn("def __init__(self, initial: float = 0.0):", patched)
        self.assertIn("def withdraw(self, amount: float) -> float:", patched)
        # Check new guard is present
        self.assertIn("if amount <= 0:", patched)
        self.assertIn("raise ValueError('Deposit must be positive')", patched)

        # Syntax check
        tree = ast.parse(patched)
        self.assertIsNotNone(tree)


if __name__ == "__main__":
    unittest.main()

