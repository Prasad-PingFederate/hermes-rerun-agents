"""
GAP-11: Read-Only Repository Context Slicer & Fixture Indexer
Owner: RequirementsAgent, TIER_2

Extracts lightweight, read-only interface stubs and test fixtures:
- PytestFixtureIndexer: Scans conftest.py files to index fixture names, scopes, parameters, and types.
- ContextSlicer: Extracts public AST signatures (classes, methods, type annotations) of imported neighbors.
- Token-Budget Pruner: Keeps interface payload strictly within configured max_context_tokens.
- Read-Only Boundary: Exposes interface knowledge without expanding allowed_files write scope.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class FixtureMetadata:
    name: str
    scope: str
    parameters: List[str]
    return_type: Optional[str]
    docstring: Optional[str]
    file_path: str
    line_number: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_signature_str(self) -> str:
        params_str = ", ".join(self.parameters)
        ret_str = f" -> {self.return_type}" if self.return_type else ""
        doc = f'    """{self.docstring}"""\n' if self.docstring else ""
        return f"@pytest.fixture(scope='{self.scope}')\ndef {self.name}({params_str}){ret_str}:\n{doc}    ..."


class PytestFixtureIndexer:
    """Scans repository conftest.py files and indexes fixture metadata."""

    @classmethod
    def scan_fixtures(cls, workspace_root: Path) -> List[FixtureMetadata]:
        """Discover and index all @pytest.fixture functions across workspace."""
        fixtures: List[FixtureMetadata] = []
        workspace = Path(workspace_root).resolve()

        skip_dirs = {".git", ".tm_snapshots", ".rerun_tasks", ".venv", "venv", "node_modules", "__pycache__"}

        for p in workspace.rglob("conftest.py"):
            # Check skip dirs
            if any(part in skip_dirs for part in p.parts):
                continue

            try:
                content = p.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(p))
            except Exception:
                continue

            rel_path = str(p.relative_to(workspace)).replace("\\", "/")

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_fixture = False
                    scope = "function"

                    for dec in node.decorator_list:
                        # @pytest.fixture or @fixture
                        if isinstance(dec, ast.Attribute) and dec.attr == "fixture":
                            is_fixture = True
                        elif isinstance(dec, ast.Name) and dec.id == "fixture":
                            is_fixture = True
                        elif isinstance(dec, ast.Call):
                            func = dec.func
                            if (isinstance(func, ast.Attribute) and func.attr == "fixture") or (
                                isinstance(func, ast.Name) and func.id == "fixture"
                            ):
                                is_fixture = True
                                for kw in dec.keywords:
                                    if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                                        scope = str(kw.value.value)

                    if is_fixture:
                        # Extract params
                        params = [arg.arg for arg in node.args.args]
                        # Extract return type if annotated
                        ret_type = None
                        if node.returns:
                            try:
                                ret_type = ast.unparse(node.returns)
                            except Exception:
                                ret_type = getattr(node.returns, "id", None)

                        doc = ast.get_docstring(node)
                        if doc:
                            doc = doc.strip().splitlines()[0]  # First line only

                        fixtures.append(
                            FixtureMetadata(
                                name=node.name,
                                scope=scope,
                                parameters=params,
                                return_type=ret_type,
                                docstring=doc,
                                file_path=rel_path,
                                line_number=node.lineno,
                            )
                        )

        return fixtures


class ContextSlicer:
    """Extracts read-only public AST signatures of imported modules without file modification scope."""

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Rough token estimate (~4 chars per token)."""
        return max(1, len(text) // 4)

    @classmethod
    def extract_public_signatures(cls, source_code: str, file_label: str) -> str:
        """Parse source into AST and extract public classes, functions, and type hints."""
        try:
            tree = ast.parse(source_code, filename=file_label)
        except SyntaxError:
            return f"# [SyntaxError in {file_label}]\n"

        lines: List[str] = [f"# Sliced Read-Only Interface: {file_label}"]

        for node in tree.body:
            # Classes
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue
                bases = []
                for b in node.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        pass
                base_str = f"({', '.join(bases)})" if bases else ""
                lines.append(f"class {node.name}{base_str}:")
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f'    """{doc.strip().splitlines()[0]}"""')

                methods_added = 0
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name.startswith("_") and item.name not in ("__init__", "__call__"):
                            continue
                        sig = cls._format_func_sig(item, indent="    ")
                        lines.append(sig)
                        methods_added += 1

                if methods_added == 0:
                    lines.append("    ...")
                lines.append("")

            # Top-level functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                sig = cls._format_func_sig(node, indent="")
                lines.append(sig)

        return "\n".join(lines)

    @classmethod
    def _format_func_sig(cls, node: ast.FunctionDef | ast.AsyncFunctionDef, indent: str = "") -> str:
        is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        args = []
        for a in node.args.args:
            arg_str = a.arg
            if a.annotation:
                try:
                    arg_str += f": {ast.unparse(a.annotation)}"
                except Exception:
                    pass
            args.append(arg_str)

        ret_str = ""
        if node.returns:
            try:
                ret_str = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass

        doc = ast.get_docstring(node)
        doc_str = f'\n{indent}    """{doc.strip().splitlines()[0]}"""' if doc else ""
        return f"{indent}{is_async}def {node.name}({', '.join(args)}){ret_str}:{doc_str}\n{indent}    ..."

    @classmethod
    def resolve_imports_to_files(cls, workspace_root: Path, target_file_rel: str) -> List[Path]:
        """Resolve import statements in target file to existing workspace file paths."""
        workspace = Path(workspace_root).resolve()
        target_path = workspace / target_file_rel.replace("\\", "/").lstrip("/")
        if not target_path.is_file():
            return []

        try:
            content = target_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(target_path))
        except Exception:
            return []

        resolved: List[Path] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    candidate = workspace.joinpath(*parts).with_suffix(".py")
                    if candidate.is_file() and candidate != target_path:
                        resolved.append(candidate)
                    candidate_pkg = workspace.joinpath(*parts) / "__init__.py"
                    if candidate_pkg.is_file() and candidate_pkg != target_path:
                        resolved.append(candidate_pkg)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    parts = node.module.split(".")
                    candidate = workspace.joinpath(*parts).with_suffix(".py")
                    if candidate.is_file() and candidate != target_path:
                        resolved.append(candidate)
                    candidate_pkg = workspace.joinpath(*parts) / "__init__.py"
                    if candidate_pkg.is_file() and candidate_pkg != target_path:
                        resolved.append(candidate_pkg)

                    # Also check common source roots (src, lib, app, core, pkg) and workspace rglob
                    if not candidate.is_file() and not candidate_pkg.is_file():
                        found = False
                        for sdir in ("src", "lib", "app", "core", "pkg"):
                            sub_cand = workspace / sdir / Path(*parts).with_suffix(".py")
                            if sub_cand.is_file() and sub_cand != target_path:
                                resolved.append(sub_cand)
                                found = True
                                break
                        if not found:
                            base_name = f"{parts[-1]}.py"
                            for match in workspace.rglob(base_name):
                                if match.is_file() and match != target_path and not any(part.startswith(".") for part in match.parts):
                                    resolved.append(match)
                                    break

        return list(dict.fromkeys(resolved))  # preserve order without duplicates

    @classmethod
    def build_sliced_context(
        cls,
        workspace_root: Path,
        target_files: List[str],
        max_context_tokens: int = 2000,
        dom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build read-only context slice with neighbor signatures, conftest fixtures, and DOM hints under token budget."""
        workspace = Path(workspace_root).resolve()
        fixtures = PytestFixtureIndexer.scan_fixtures(workspace)

        sections: List[str] = []

        # 0. Add UI Automation DOM & Locator Forensics if present
        if dom_context and dom_context.strip():
            sections.append(f"# UI Automation DOM & Locator Forensics:\n{dom_context.strip()}")

        # 1. Add Fixture Catalog
        if fixtures:
            fixture_lines = ["# Available Conftest Pytest Fixtures:"]
            for fix in fixtures:
                fixture_lines.append(fix.to_signature_str())
            sections.append("\n".join(fixture_lines))

        # 2. Add Neighbor Slices
        neighbor_files: Set[Path] = set()
        for tf in target_files:
            neighbors = cls.resolve_imports_to_files(workspace, tf)
            neighbor_files.update(neighbors)

        for nf in sorted(list(neighbor_files)):
            try:
                rel_label = str(nf.relative_to(workspace)).replace("\\", "/")
                content = nf.read_text(encoding="utf-8")
                stub = cls.extract_public_signatures(content, rel_label)
                if stub.strip():
                    sections.append(stub)
            except Exception:
                continue

        combined_text = "\n\n".join(sections)
        estimated_tokens = cls.estimate_tokens(combined_text)

        # 3. Token-budget pruner if exceeding max_context_tokens
        if estimated_tokens > max_context_tokens:
            # Prune docstrings first
            pruned_sections = []
            for sec in sections:
                cleaned = "\n".join(line for line in sec.splitlines() if '"""' not in line)
                pruned_sections.append(cleaned)
            combined_text = "\n\n".join(pruned_sections)
            estimated_tokens = cls.estimate_tokens(combined_text)

            # If still over, truncate
            if estimated_tokens > max_context_tokens:
                char_limit = max_context_tokens * 4
                combined_text = combined_text[:char_limit] + "\n# [Context slice truncated to token limit]"
                estimated_tokens = cls.estimate_tokens(combined_text)

        return {
            "context_str": combined_text,
            "estimated_tokens": estimated_tokens,
            "fixtures": [f.to_dict() for f in fixtures],
            "neighbor_modules": [
                str(nf.relative_to(workspace)).replace("\\", "/") for nf in sorted(list(neighbor_files))
            ],
            "dom_context": dom_context or "",
        }
