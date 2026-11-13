"""
Unified Multi-Language AST Guard with Tree-Sitter & Graceful Fallback
Owner: SecurityGateAgent & TestCaseWriterAgent, TIER_2
Phase: Option 6 & Enterprise Depth

Provides deterministic AST analysis across 5 languages:
- Python
- TypeScript / JavaScript
- Java
- Go
- C#

Uses Tree-sitter S-expression queries when tree-sitter is installed.
Gracefully falls back to standard ast (Python) and regex/lexical analyzers
if tree-sitter is not installed.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try importing tree_sitter or tree_sitter_languages
HAS_TREE_SITTER = False
_TS_PARSERS: Dict[str, Any] = {}

try:
    import tree_sitter_languages  # type: ignore
    HAS_TREE_SITTER = True
except ImportError:
    try:
        import tree_sitter  # type: ignore
        HAS_TREE_SITTER = True
    except ImportError:
        HAS_TREE_SITTER = False


@dataclass
class ASTAnalysisResult:
    language: str
    engine: str  # "tree-sitter" or "fallback-regex-ast"
    assertion_count: int = 0
    skips_detected: List[str] = field(default_factory=list)
    dangerous_sinks: List[str] = field(default_factory=list)
    has_tautologies: bool = False
    specificity_score: float = 1.0


class LanguageASTGuard:
    """Unified AST guard for Python, TypeScript, Java, Go, and C#."""

    # Language extension map
    EXT_LANG_MAP = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".cs": "csharp",
    }

    # Declarative Tree-sitter S-expression queries
    TS_QUERIES = {
        "python": {
            "assertions": "(assert_statement) @assert",
            "skips": "(decorator (dotted_name) @name (#match? @name \"(skip|skipif|xfail)\")) @skip",
            "sinks": "(call function: (identifier) @func (#match? @func \"^(eval|exec)$\")) @sink",
        },
        "typescript": {
            "assertions": """
                (call_expression
                    function: (member_expression
                        object: (call_expression function: (identifier) @fn (#match? @fn "^expect$"))
                        property: (property_identifier) @matcher)) @assert
            """,
            "skips": """
                (call_expression
                    function: (member_expression
                        object: (identifier) @obj (#match? @obj "^(test|it|describe)$")
                        property: (property_identifier) @prop (#match? @prop "^skip$"))) @skip
            """,
            "sinks": "(call_expression function: (identifier) @fn (#match? @fn \"^(eval|Function)$\")) @sink",
        },
        "java": {
            "assertions": """
                (method_invocation
                    name: (identifier) @name (#match? @name "^(assert|expect|assertThat)")) @assert
            """,
            "skips": """
                (annotation name: (identifier) @name (#match? @name "^(Ignore|Disabled)$")) @skip
            """,
            "sinks": """
                (method_invocation
                    name: (identifier) @name (#match? @name "^(exec|evaluate)$")) @sink
            """,
        },
        "go": {
            "assertions": """
                (call_expression
                    function: (selector_expression
                        field: (field_identifier) @name (#match? @name "^(Equal|True|False|NotNil|Nil|NoError)"))) @assert
            """,
            "skips": """
                (call_expression
                    function: (selector_expression
                        field: (field_identifier) @name (#match? @name "^Skip(Now|f)?$"))) @skip
            """,
            "sinks": """
                (call_expression
                    function: (selector_expression
                        operand: (identifier) @pkg (#match? @pkg "^(exec|os)$")
                        field: (field_identifier) @fn (#match? @fn "^(Command|StartProcess)$"))) @sink
            """,
        },
        "csharp": {
            "assertions": """
                (invocation_expression
                    expression: (member_access_expression
                        name: (identifier) @name (#match? @name "^(Assert|That|True|False|Equal)"))) @assert
            """,
            "skips": """
                (attribute name: (identifier) @name (#match? @name "^(Ignore|Skip)$")) @skip
            """,
            "sinks": """
                (invocation_expression
                    expression: (member_access_expression
                        name: (identifier) @name (#match? @name "^(Start|Execute)$"))) @sink
            """,
        },
    }

    # Fallback regex patterns when tree-sitter is absent
    FALLBACK_ASSERTION_PATTERNS = {
        "python": [re.compile(r"\bassert\b"), re.compile(r"\bself\.assert\w+"), re.compile(r"\bpytest\.raises\b")],
        "typescript": [re.compile(r"\bexpect\s*\(.*\)\s*\.to"), re.compile(r"\bassert\.\w+")],
        "javascript": [re.compile(r"\bexpect\s*\(.*\)\s*\.to"), re.compile(r"\bassert\.\w+")],
        "java": [re.compile(r"\bassert(Equals|True|False|Null|NotNull|That)\b")],
        "go": [re.compile(r"\bassert\.(Equal|True|False|Nil|NotNil|NoError)\b"), re.compile(r"\brequire\.\w+")],
        "csharp": [re.compile(r"\bAssert\.(That|AreEqual|IsTrue|IsFalse|NotNull)\b")],
    }

    FALLBACK_SKIP_PATTERNS = {
        "python": [re.compile(r"@pytest\.mark\.(skip|skipif|xfail)"), re.compile(r"\bunittest\.skip")],
        "typescript": [re.compile(r"\b(test|it|describe)\.skip\b"), re.compile(r"\b\.only\b")],
        "javascript": [re.compile(r"\b(test|it|describe)\.skip\b"), re.compile(r"\b\.only\b")],
        "java": [re.compile(r"@(Ignore|Disabled)\b")],
        "go": [re.compile(r"\bt\.Skip(Now|f)?\b")],
        "csharp": [re.compile(r"\[(Ignore|Fact\(Skip\s*=.*?\))\]")],
    }

    FALLBACK_SINK_PATTERNS = {
        "python": [re.compile(r"\b(eval|exec)\s*\("), re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True")],
        "typescript": [re.compile(r"\b(eval|child_process\.exec)\s*\("), re.compile(r"\bFunction\s*\(")],
        "javascript": [re.compile(r"\b(eval|child_process\.exec)\s*\("), re.compile(r"\bFunction\s*\(")],
        "java": [re.compile(r"Runtime\.getRuntime\(\)\.exec\s*\(")],
        "go": [re.compile(r"exec\.Command\s*\(")],
        "csharp": [re.compile(r"Process\.Start\s*\(")],
    }

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        """Infer programming language from file path."""
        p = Path(file_path.lower().replace("\\", "/"))
        suffix = p.suffix
        return cls.EXT_LANG_MAP.get(suffix, "unknown")

    @classmethod
    def analyze(cls, code: str, language: str) -> ASTAnalysisResult:
        """Analyze code for assertions, skips, and sinks using Tree-sitter or fallback."""
        lang = language.lower().strip()
        if lang in ("js", "jsx"):
            lang = "javascript"
        elif lang in ("ts", "tsx"):
            lang = "typescript"
        elif lang == "py":
            lang = "python"
        elif lang == "cs":
            lang = "csharp"

        # 1. Tree-sitter execution if available
        if HAS_TREE_SITTER:
            try:
                return cls._analyze_tree_sitter(code, lang)
            except Exception:
                # If tree-sitter parsing fails on grammar, gracefully fallback
                pass

        # 2. Native AST for Python
        if lang == "python":
            return cls._analyze_python_native_ast(code)

        # 3. Fallback regex analysis for non-Python languages
        return cls._analyze_fallback(code, lang)

    @classmethod
    def _analyze_tree_sitter(cls, code: str, language: str) -> ASTAnalysisResult:
        """Execute Tree-sitter queries for supported language."""
        lang_key = "typescript" if language in ("typescript", "javascript") else language
        if lang_key not in cls.TS_QUERIES:
            return cls._analyze_fallback(code, language)

        try:
            parser = tree_sitter_languages.get_parser(lang_key)
            tree = parser.parse(bytes(code, "utf8"))
            root = tree.root_node
            language_obj = tree_sitter_languages.get_language(lang_key)

            queries = cls.TS_QUERIES[lang_key]

            # Assertion query
            assert_query = language_obj.query(queries["assertions"])
            assert_captures = assert_query.captures(root)
            assertion_count = len(assert_captures)

            # Skip query
            skips = []
            if "skips" in queries:
                skip_query = language_obj.query(queries["skips"])
                skip_captures = skip_query.captures(root)
                for node, _ in skip_captures:
                    skips.append(node.text.decode("utf8"))

            # Sinks query
            sinks = []
            if "sinks" in queries:
                sink_query = language_obj.query(queries["sinks"])
                sink_captures = sink_query.captures(root)
                for node, _ in sink_captures:
                    sinks.append(node.text.decode("utf8"))

            # Check for trivial assertions
            has_tautologies = False
            for pat in [r"assert\s+True\b", r"expect\(true\)\.toBe\(true\)", r"assertEquals\(1,\s*1\)"]:
                if re.search(pat, code):
                    has_tautologies = True
                    break

            return ASTAnalysisResult(
                language=language,
                engine="tree-sitter",
                assertion_count=assertion_count,
                skips_detected=skips,
                dangerous_sinks=sinks,
                has_tautologies=has_tautologies,
            )
        except Exception:
            return cls._analyze_fallback(code, language)

    @classmethod
    def _analyze_python_native_ast(cls, code: str) -> ASTAnalysisResult:
        """Deep Python AST inspection using standard library ast module."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return cls._analyze_fallback(code, "python")

        assert_count = 0
        has_tautologies = False
        sinks = []
        skips = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                assert_count += 1
                if isinstance(node.test, ast.Constant) and node.test.value in (True, 1):
                    has_tautologies = True
                elif isinstance(node.test, ast.Compare):
                    try:
                        expr = ast.unparse(node.test).strip()
                        if expr in ("1 == 1", "True == True", "0 == 0"):
                            has_tautologies = True
                    except Exception:
                        pass
            elif isinstance(node, ast.Call):
                try:
                    name = ast.unparse(node.func)
                    if name in ("eval", "exec", "os.system", "os.popen"):
                        sinks.append(name)
                    elif "assert" in name.lower() or "raises" in name.lower():
                        assert_count += 1
                except Exception:
                    pass
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for deco in node.decorator_list:
                    try:
                        deco_name = ast.unparse(deco)
                        if any(s in deco_name for s in ("skip", "skipif", "xfail")):
                            skips.append(deco_name)
                    except Exception:
                        pass

        return ASTAnalysisResult(
            language="python",
            engine="fallback-python-ast",
            assertion_count=assert_count,
            skips_detected=skips,
            dangerous_sinks=sinks,
            has_tautologies=has_tautologies,
        )

    @classmethod
    def _analyze_fallback(cls, code: str, language: str) -> ASTAnalysisResult:
        """Regex-based fallback for all languages."""
        assert_pats = cls.FALLBACK_ASSERTION_PATTERNS.get(language, [re.compile(r"\bassert\b")])
        skip_pats = cls.FALLBACK_SKIP_PATTERNS.get(language, [])
        sink_pats = cls.FALLBACK_SINK_PATTERNS.get(language, [])

        count = 0
        for pat in assert_pats:
            count += len(pat.findall(code))

        skips = []
        for pat in skip_pats:
            skips.extend(pat.findall(code))

        sinks = []
        for pat in sink_pats:
            sinks.extend(pat.findall(code))

        has_tautologies = bool(
            re.search(r"\bassert\s+True\b", code)
            or re.search(r"\bexpect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)", code)
            or re.search(r"\bassertTrue\s*\(\s*true\s*\)", code)
            or re.search(r"\bassertEquals\s*\(\s*1\s*,\s*1\s*\)", code)
        )

        return ASTAnalysisResult(
            language=language,
            engine="fallback-regex-ast",
            assertion_count=count,
            skips_detected=skips,
            dangerous_sinks=sinks,
            has_tautologies=has_tautologies,
        )

    @classmethod
    def check_assertion_erosion(
        cls,
        original_code: str,
        patched_code: str,
        language: str = "python",
    ) -> Dict[str, Any]:
        """Perform full multi-language assertion erosion verification on patched code vs original."""
        orig_res = cls.analyze(original_code, language)
        patch_res = cls.analyze(patched_code, language)

        violations: List[str] = []

        # 1. Zero Assertion Erosion: Net assertion count drop
        if patch_res.assertion_count < orig_res.assertion_count:
            violations.append(
                f"EROSION_ASSERTION_DELETED: Assertion count dropped from {orig_res.assertion_count} to {patch_res.assertion_count}"
            )

        # 2. Tautological assertions
        if patch_res.has_tautologies:
            violations.append("EROSION_TAUTOLOGICAL_ASSERTION: Found tautological/hollow assertion (e.g. assert True, 1==1)")

        # 3. Newly added skip decorators
        new_skips = [s for s in patch_res.skips_detected if s not in orig_res.skips_detected]
        if new_skips:
            violations.append(f"EROSION_SKIP_INJECTED: Test skipping detected: {new_skips}")

        # 4. Semantic value dilution / broad exception / timeout inflation
        dilution_patterns = [
            (re.compile(r"\bexpect\s*\(.*?\)\s*\.toBeTruthy\s*\(\s*\)"), "Weakened assertion matcher toBeTruthy()"),
            (re.compile(r"\bexcept\s+(?:Exception|BaseException)\s*:\s*pass\b"), "Broad exception swallowed: except Exception: pass"),
            (re.compile(r"\bcatch\s*\(\s*(?:Exception|Throwable|any|Error)\b[^)]*\)\s*\{\s*\}"), "Broad exception swallowed in empty catch block"),
            (re.compile(r"\b(?:timeout|setTimeout)\s*[:=]\s*(?:999999|99999|600000)\b"), "Test timeout artificially inflated"),
        ]
        for pat, desc in dilution_patterns:
            if pat.search(patched_code) and not pat.search(original_code):
                violations.append(f"EROSION_SEMANTIC_DILUTION: {desc}")

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "original_assertion_count": orig_res.assertion_count,
            "patched_assertion_count": patch_res.assertion_count,
            "language": language,
            "engine": patch_res.engine,
        }
