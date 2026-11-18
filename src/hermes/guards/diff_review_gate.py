"""
Diff Review Gate (OpenQodex-style review protocol)

Enforces review gate before any patch apply onto the caller workspace.
A patch must not land in the caller workspace while a confirmed major finding is open.

Algorithm:
1. Parse unified diff to collect changed files and line numbers.
2. Ask critic for candidate findings (or accept candidate findings).
3. Drop finding if quote is empty.
4. Drop finding if quote is not an exact line in files[file] (strip trailing newline only).
5. Drop finding whose file is not in diff.
6. A title or category about naming, style, formatting, comments, or docs is severity "observation".
7. Every surviving major and minor finding must have exactly one verdict (confirm or refute).
   If omitted, status is INCOMPLETE and apply is refused.
8. Decision:
   - any confirmed major -> BLOCKED (allow_apply False)
   - no confirmed major, and every major/minor answered -> ALLOWED (allow_apply True)
   - observations do not affect allow_apply
   - refuted major does not block
9. Write .hermes_artifacts/review/report.md relative to workspace.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import os
import re


@dataclass
class Finding:
    """A code review finding identified in a diff."""
    file: str
    line: int
    severity: str  # "major" | "minor" | "observation"
    title: str
    quote: str
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    """Critic decision on a specific review finding."""
    action: str  # "confirm" | "refute"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_file_path(p: str) -> str:
    """Normalize file path for consistent cross-platform matching."""
    norm = str(p).strip().replace("\\", "/")
    return norm.lstrip("./")


def parse_unified_diff(diff_text: str) -> Tuple[Set[str], Dict[str, Set[int]], Dict[str, List[str]]]:
    """
    Parses unified diff text.
    Returns:
      - changed_files: set of normalized relative file paths modified/added/deleted.
      - changed_lines: map from file path to set of 1-based line numbers in new file.
      - added_lines_text: map from file path to list of added/changed line texts.
    """
    changed_files: Set[str] = set()
    changed_lines: Dict[str, Set[int]] = {}
    added_lines_text: Dict[str, List[str]] = {}

    def _extract_path(header_line: str) -> str:
        s = header_line[4:].strip()
        if "\t" in s:
            s = s.split("\t")[0].strip()
        if s.startswith("a/") or s.startswith("b/"):
            s = s[2:]
        return normalize_file_path(s)

    current_file: Optional[str] = None
    new_line_num = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = _extract_path(line)
            if target and target != "dev/null" and target != "/dev/null":
                current_file = target
                changed_files.add(current_file)
                if current_file not in changed_lines:
                    changed_lines[current_file] = set()
                if current_file not in added_lines_text:
                    added_lines_text[current_file] = []
            else:
                current_file = None
            continue
        elif line.startswith("--- ") and current_file is None:
            old_target = _extract_path(line)
            if old_target and old_target != "dev/null" and old_target != "/dev/null":
                changed_files.add(old_target)
                if old_target not in changed_lines:
                    changed_lines[old_target] = set()
                if old_target not in added_lines_text:
                    added_lines_text[old_target] = []
            continue
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                p_b = parts[3]
                if p_b.startswith("b/"):
                    p_b = p_b[2:]
                target = normalize_file_path(p_b)
                if target and target != "dev/null" and target != "/dev/null":
                    changed_files.add(target)
            continue
        elif line.startswith("@@"):
            m = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                new_line_num = int(m.group(1))
            continue

        if current_file is not None and new_line_num > 0:
            if line.startswith("+"):
                changed_lines[current_file].add(new_line_num)
                added_lines_text[current_file].append(line[1:])
                new_line_num += 1
            elif line.startswith("-"):
                pass
            elif line.startswith(" "):
                new_line_num += 1
            elif line.startswith("\\"):
                pass

    return changed_files, changed_lines, added_lines_text


def _normalize_finding(f: Any) -> Finding:
    if isinstance(f, Finding):
        return f
    if isinstance(f, dict):
        return Finding(
            file=str(f.get("file", "")),
            line=int(f.get("line", 1) or 1),
            severity=str(f.get("severity", "minor")).lower(),
            title=str(f.get("title", "")),
            quote=str(f.get("quote", "")),
            category=str(f.get("category", "")),
        )
    return Finding(
        file=str(getattr(f, "file", "")),
        line=int(getattr(f, "line", 1) or 1),
        severity=str(getattr(f, "severity", "minor")).lower(),
        title=str(getattr(f, "title", "")),
        quote=str(getattr(f, "quote", "")),
        category=str(getattr(f, "category", "")),
    )


def _normalize_verdict(v: Any) -> Verdict:
    if isinstance(v, Verdict):
        return v
    if isinstance(v, dict):
        return Verdict(
            action=str(v.get("action", "")).lower(),
            reason=str(v.get("reason", "")),
        )
    return Verdict(
        action=str(getattr(v, "action", "")).lower(),
        reason=str(getattr(v, "reason", "")),
    )


class DefaultDiffCritic:
    """Production critic: Wraps QA critic checks with clean conversation history."""

    def __init__(self, workspace: Optional[Union[str, Path]] = None):
        self.workspace = Path(workspace or Path.cwd()).resolve()

    def get_findings(self, changed_lines: Dict[str, Set[int]], files: Dict[str, str]) -> List[Finding]:
        """Heuristic candidate finding detection on changed lines."""
        findings: List[Finding] = []
        for file_path, content in files.items():
            norm_p = normalize_file_path(file_path)
            lines = content.splitlines()
            c_lines = changed_lines.get(norm_p, set())
            for line_no, raw_line in enumerate(lines, 1):
                if c_lines and line_no not in c_lines:
                    continue
                # 1. Assertion erosion / removal detection
                stripped = raw_line.strip()
                if "pass  # removed assert" in stripped or "# assert" in stripped:
                    findings.append(Finding(
                        file=norm_p,
                        line=line_no,
                        severity="major",
                        title="Assertion erosion detected: assertion commented or bypassed",
                        quote=raw_line,
                        category="testing",
                    ))
                # 2. Syntax / obvious fatal crash patterns
                elif re.search(r"\b1\s*/\s*0\b", stripped):
                    findings.append(Finding(
                        file=norm_p,
                        line=line_no,
                        severity="major",
                        title="ZeroDivisionError introduced in code",
                        quote=raw_line,
                        category="logic",
                    ))
                # 3. Insecure dynamic evaluation / injection patterns
                elif "eval(" in stripped or "exec(" in stripped:
                    findings.append(Finding(
                        file=norm_p,
                        line=line_no,
                        severity="major",
                        title="Insecure dynamic code execution (eval/exec)",
                        quote=raw_line,
                        category="security",
                    ))
        return findings

    def __call__(self, findings: List[Finding], files: Dict[str, str]) -> List[Verdict]:
        """Evaluate findings and return confirm or refute."""
        verdicts: List[Verdict] = []
        for f in findings:
            norm_file = normalize_file_path(f.file)
            content = files.get(f.file) or files.get(norm_file, "")
            file_lines = [l.rstrip("\r\n") for l in content.splitlines()]
            target_quote = (f.quote or "").rstrip("\r\n")
            if target_quote in file_lines:
                # Issue confirmed present in file
                verdicts.append(Verdict(action="confirm", reason=f"Confirmed finding in {norm_file}:{f.line}"))
            else:
                verdicts.append(Verdict(action="refute", reason=f"Quote not found in {norm_file}"))
        return verdicts


def review_diff(
    diff_text: str,
    files: Dict[str, str],
    critic: Any,
    candidate_findings: Optional[List[Union[Finding, Dict[str, Any]]]] = None,
    workspace: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Executes the OpenQodex-style review gate on a unified diff.

    Parameters:
      - diff_text: Unified diff string.
      - files: Map of relative file path to full current file text.
      - critic: Callable(findings, files) -> list of verdicts.
      - candidate_findings: Optional pre-supplied candidate findings.
      - workspace: Optional workspace root for writing .hermes_artifacts/review/report.md.

    Returns dict with keys:
      - allow_apply: bool
      - status: "ALLOWED" | "BLOCKED" | "INCOMPLETE"
      - verdict: "ALLOWED" | "BLOCKED" | "INCOMPLETE"
      - report_path: str
      - findings: list[Finding] (surviving findings)
      - verdicts: list[Verdict]
      - confirmed_majors: list[str] (titles of confirmed majors)
    """
    # 1. Parse unified diff
    changed_files, changed_lines, added_lines_text = parse_unified_diff(diff_text)

    # Normalized file map for exact lookups
    norm_files: Dict[str, str] = {
        normalize_file_path(k): v for k, v in files.items()
    }

    # 2. Ask critic for candidate findings
    raw_findings: List[Any] = []
    if candidate_findings is not None:
        raw_findings = candidate_findings
    elif hasattr(critic, "get_findings") and callable(getattr(critic, "get_findings")):
        raw_findings = critic.get_findings(changed_lines, files)
    elif hasattr(critic, "candidate_findings"):
        raw_findings = getattr(critic, "candidate_findings")
    elif hasattr(critic, "findings"):
        raw_findings = getattr(critic, "findings")
    elif callable(critic):
        # Attempt calling critic to see if it supplies candidate findings
        try:
            res = critic(changed_lines, files)
            if isinstance(res, list) and res and isinstance(res[0], (Finding, dict)):
                raw_findings = res
        except Exception:
            pass

    if not raw_findings:
        try:
            default_critic = DefaultDiffCritic(workspace=workspace)
            raw_findings = default_critic.get_findings(changed_lines, files)
        except Exception:
            pass

    candidates = [_normalize_finding(item) for item in raw_findings]

    # Filter candidates according to steps 3, 4, 5, 6
    surviving_findings: List[Finding] = []
    dropped_findings: List[Dict[str, Any]] = []

    style_keywords = r"\b(naming|rename|name|style|formatting|format|comments?|docs?|documentation|docstrings?)\b"

    for cand in candidates:
        # 3. Drop a finding when quote is empty
        raw_quote = cand.quote if cand.quote is not None else ""
        if not raw_quote.strip():
            dropped_findings.append({"finding": cand, "reason": "empty quote"})
            continue

        # 5. Drop a finding whose file is not in the diff
        norm_file = normalize_file_path(cand.file)
        if norm_file not in changed_files:
            dropped_findings.append({"finding": cand, "reason": "file not in diff"})
            continue

        # 4. Drop a finding when quote is not an exact line in files[file].
        # Strip only trailing newline before comparing. Do not fuzzy-match.
        file_content = norm_files.get(norm_file)
        if file_content is None:
            dropped_findings.append({"finding": cand, "reason": "file not in files dictionary"})
            continue

        file_lines = [l.rstrip("\r\n") for l in file_content.splitlines()]
        target_quote = raw_quote.rstrip("\r\n")

        if target_quote not in file_lines:
            dropped_findings.append({"finding": cand, "reason": "quote not exact line in file"})
            continue

        # 6. A title or category about naming, style, formatting, comments, or docs
        # is severity "observation" even if the model said major.
        sev = cand.severity.lower()
        title_cat_text = f"{cand.title} {cand.category}".lower()
        if re.search(style_keywords, title_cat_text):
            sev = "observation"

        surviving = Finding(
            file=norm_file,
            line=cand.line,
            severity=sev,
            title=cand.title,
            quote=cand.quote,
            category=cand.category,
        )
        surviving_findings.append(surviving)

    # 7. Collect verdicts from critic for surviving findings
    verdicts: List[Verdict] = []
    if callable(critic):
        try:
            raw_v = critic(surviving_findings, files)
            if isinstance(raw_v, list):
                verdicts = [_normalize_verdict(v) for v in raw_v]
        except Exception:
            pass

    if not raw_findings:
        try:
            default_critic = DefaultDiffCritic(workspace=workspace)
            raw_findings = default_critic.get_findings(changed_lines, files)
        except Exception:
            pass

    actionable_findings = [f for f in surviving_findings if f.severity in ("major", "minor")]

    # Pair findings with verdicts
    finding_verdict_pairs: List[Tuple[Finding, Optional[Verdict]]] = []
    if len(verdicts) == len(surviving_findings):
        for f, v in zip(surviving_findings, verdicts):
            finding_verdict_pairs.append((f, v))
    elif len(verdicts) == len(actionable_findings):
        act_idx = 0
        for f in surviving_findings:
            if f.severity in ("major", "minor"):
                finding_verdict_pairs.append((f, verdicts[act_idx]))
                act_idx += 1
            else:
                finding_verdict_pairs.append((f, None))
    else:
        for i, f in enumerate(surviving_findings):
            v = verdicts[i] if i < len(verdicts) else None
            finding_verdict_pairs.append((f, v))

    # 8. Decision:
    # - any confirmed major -> allow_apply false, status "BLOCKED"
    # - no confirmed major, and every major/minor was answered -> allow_apply true, status "ALLOWED"
    # - observations do not affect allow_apply
    # - a refuted major does not block
    has_incomplete = False
    confirmed_majors: List[Finding] = []

    for f, v in finding_verdict_pairs:
        sev = f.severity.lower()
        if sev in ("major", "minor"):
            if v is None or v.action not in ("confirm", "refute"):
                has_incomplete = True
            elif sev == "major" and v.action == "confirm":
                confirmed_majors.append(f)

    if confirmed_majors:
        status = "BLOCKED"
        allow_apply = False
    elif has_incomplete:
        status = "INCOMPLETE"
        allow_apply = False
    else:
        status = "ALLOWED"
        allow_apply = True

    # 9. Write .hermes_artifacts/review/report.md relative to the workspace:
    # first line: verdict ALLOWED, BLOCKED, or INCOMPLETE
    # then one line per surviving finding: severity, action, file:line, title
    # then one line: apply_allowed true/false
    ws = Path(workspace or Path.cwd()).resolve()
    report_dir = ws / ".hermes_artifacts" / "review"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "report.md"

    report_lines: List[str] = [status]
    for f, v in finding_verdict_pairs:
        act = v.action if (v and v.action) else "none"
        report_lines.append(f"{f.severity}, {act}, {f.file}:{f.line}, {f.title}")

    apply_str = "true" if allow_apply else "false"
    report_lines.append(f"apply_allowed {apply_str}")

    report_content = "\n".join(report_lines) + "\n"
    report_file.write_text(report_content, encoding="utf-8")

    clean_report_path = str(report_file).replace("\\", "/")

    return {
        "status": status,
        "verdict": status,
        "allow_apply": allow_apply,
        "report_path": clean_report_path,
        "findings": surviving_findings,
        "surviving_findings": surviving_findings,
        "verdicts": [v for _, v in finding_verdict_pairs if v is not None],
        "confirmed_majors": [f.title for f in confirmed_majors],
        "dropped_findings": dropped_findings,
    }
