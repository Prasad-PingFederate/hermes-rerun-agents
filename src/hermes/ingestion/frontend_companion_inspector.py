"""
Hermes Frontend Companion Inspector.

Discovers and inspects companion frontend repositories (e.g. React, Next.js, Vue,
TypeScript) to cross-reference UI component definitions, DOM form fields,
directives, and GraphQL contracts when end-to-end tests fail.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class FrontendCompanionInspector:
    """Inspects companion frontend source repositories to extract exact DOM and form facts."""

    COMMON_COMPANION_NAMES = [
        "b4igo-frontend",
        "b4igo-frontend-predev",
        "frontend",
        "client",
        "ui",
        "web",
        "app",
    ]

    INPUT_PATTERN = re.compile(
        r"<(?:input|textarea|button|select)\s+([^>]+)>",
        re.IGNORECASE,
    )
    ATTR_PATTERN = re.compile(r'([A-Za-z0-9_-]+)=["\']([^"\']+)["\']')

    @classmethod
    def discover_companion_repos(
        cls,
        workspace_root: Path,
        explicit_path: Optional[Path | str] = None,
    ) -> List[Path]:
        """Discovers companion frontend repository directories."""
        discovered: List[Path] = []
        ws = Path(workspace_root).resolve()

        # 1. Explicit path
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.is_dir() and p not in discovered:
                discovered.append(p)

        # 2. Environment variable
        env_path = os.environ.get("HERMES_FRONTEND_REPO")
        if env_path:
            p = Path(env_path).resolve()
            if p.is_dir() and p not in discovered:
                discovered.append(p)

        # 3. Subdirectories inside workspace
        for name in cls.COMMON_COMPANION_NAMES:
            sub = ws / name
            if sub.is_dir() and sub not in discovered:
                discovered.append(sub)

        # 4. Sibling directories (e.g. ../b4igo-frontend-predev)
        parent = ws.parent
        if parent.is_dir():
            for name in cls.COMMON_COMPANION_NAMES:
                sibling = parent / name
                if sibling.is_dir() and sibling not in discovered:
                    discovered.append(sibling)

            # Glob pattern for matching b4igo-frontend* siblings
            try:
                for match in parent.glob("*frontend*"):
                    if match.is_dir() and match not in discovered and match != ws:
                        discovered.append(match)
            except Exception:
                pass

        return discovered

    @classmethod
    def search_component_definitions(
        cls,
        companion_root: Path,
        keyword: str,
        max_matches: int = 3,
    ) -> List[Dict[str, Any]]:
        """Searches JSX/TSX/Vue component source files for keyword and extracts element metadata."""
        matches: List[Dict[str, Any]] = []
        clean_kw = keyword.strip("'\":;").lower()
        if len(clean_kw) < 3:
            return matches

        comp_root = Path(companion_root).resolve()
        search_dirs = [comp_root / "src", comp_root / "features", comp_root / "components", comp_root]

        scanned = 0
        for s_dir in search_dirs:
            if not s_dir.is_dir():
                continue
            for ext in ("*.tsx", "*.jsx", "*.vue", "*.js", "*.ts"):
                for fpath in s_dir.rglob(ext):
                    if "node_modules" in fpath.parts or ".git" in fpath.parts or "dist" in fpath.parts:
                        continue
                    scanned += 1
                    if scanned > 1000:
                        break
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                        if clean_kw in content.lower():
                            rel_p = str(fpath.relative_to(comp_root)).replace("\\", "/")
                            extracted_inputs = cls._extract_inputs(content)
                            matches.append({
                                "file": rel_p,
                                "component_name": fpath.stem,
                                "extracted_inputs": extracted_inputs,
                                "has_directives": bool(re.search(r"directive", content, re.IGNORECASE)),
                                "has_submit": bool(re.search(r"type=['\"]submit['\"]|submit", content, re.IGNORECASE)),
                            })
                            if len(matches) >= max_matches:
                                return matches
                    except Exception:
                        pass
        return matches

    @classmethod
    def _extract_inputs(cls, code: str) -> List[str]:
        """Extracts notable input tags and selectors from JSX/TSX code."""
        inputs: List[str] = []
        for m in cls.INPUT_PATTERN.finditer(code):
            attrs_str = m.group(1)
            attrs = dict(cls.ATTR_PATTERN.findall(attrs_str))
            t = attrs.get("type", "input")
            tid = attrs.get("data-testid") or attrs.get("testid")
            el_id = attrs.get("id")
            name = attrs.get("name")

            if tid:
                inputs.append(f"[data-testid='{tid}']")
            if el_id:
                inputs.append(f"#{el_id}")
            if name:
                inputs.append(f"input[name='{name}']")
            if t in ("radio", "checkbox", "submit"):
                inputs.append(f"input[type='{t}']")

        # De-duplicate while preserving order
        return list(dict.fromkeys(inputs))[:8]

    @classmethod
    def build_companion_hints(
        cls,
        workspace_root: Path,
        failure_text: str,
        explicit_companion: Optional[Path | str] = None,
    ) -> str:
        """Builds structured companion frontend hints from discovered repositories."""
        companions = cls.discover_companion_repos(workspace_root, explicit_companion)
        if not companions:
            return ""

        # Extract search keywords from error text
        keywords: Set[str] = set()
        for quoted in re.findall(r"['\"]([^'\"]{4,40})['\"]", failure_text):
            if not any(stop in quoted.lower() for stop in ("error", "trace", "fail", "assert")):
                keywords.add(quoted)

        # Common high-value form keywords if present
        for kw in ("Select Directives", "Directives", "Community", "Submit", "Publish"):
            if kw.lower() in failure_text.lower():
                keywords.add(kw)

        results: List[Dict[str, Any]] = []
        for comp_root in companions[:2]:
            for kw in list(keywords)[:3]:
                found = cls.search_component_definitions(comp_root, kw)
                for f in found:
                    if f not in results:
                        results.append(f)

        if not results:
            return ""

        lines = [
            "### Frontend Companion Repository Forensics:",
            f"Discovered companion frontend repository: {companions[0].name}",
        ]
        for r in results[:3]:
            lines.append(f"- Component: `{r['file']}` (Component: `{r['component_name']}`)")
            if r["extracted_inputs"]:
                lines.append(f"  * Available Inputs & Selectors: {', '.join(r['extracted_inputs'])}")
            if r["has_directives"]:
                lines.append("  * Note: Component contains directive selections (ensure directive radio/checkbox is checked).")
            if r["has_submit"]:
                lines.append("  * Note: Component contains submit action handlers.")

        return "\n".join(lines)
