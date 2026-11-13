"""
Strict SARIF v2.1.0 Exporter & Cryptographic Audit Digest
Owner: SecurityBlastRadiusAgent & QACriticAgent
Phase: Option 6 (Monorepo Scale & Ecosystem Depth)

Emits schema-compliant SARIF v2.1.0 reports for GitHub Code Scanning:
1. Strict GitHub Code Scanning Compliance:
   - Valid $schema and version 2.1.0
   - Relative POSIX artifactLocation.uri paths
   - 1-indexed region.startLine (clamped >= 1)
   - Deduplicated tool.driver.rules matching every emitted result.ruleId
   - Deterministic partialFingerprints for stable alert tracking.
2. Cryptographic Audit Digest:
   Stamps run.properties with SHA-256 chain digest over (commit_sha, policy_hash, diff_hash, verdict).

Zero external dependencies (uses standard library: hashlib, json, posixpath, typing).
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class SARIFExportResult:
    """Outcome of SARIF report generation."""
    report_path: Optional[Path]
    report_dict: Dict[str, Any]
    audit_digest: str
    total_findings: int
    rule_ids: List[str] = field(default_factory=list)

    @property
    def digest(self) -> str:
        return self.audit_digest

    @property
    def sarif_json(self) -> str:
        return json.dumps(self.report_dict, indent=2)


class SARIFExporter:
    """Generates GitHub Code Scanning compliant SARIF v2.1.0 reports with cryptographic audit digests."""

    SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
    SARIF_VERSION = "2.1.0"
    TOOL_NAME = "Hermes-Governance"
    TOOL_VERSION = "2.0.0"

    DEFAULT_RULE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
        "HERMES-CWE-78": {
            "name": "CommandInjection",
            "shortDescription": {"text": "Deterministic Delta-SAST: OS Command Injection"},
            "helpUri": "https://cwe.mitre.org/data/definitions/78.html",
            "defaultConfiguration": {"level": "error"},
        },
        "HERMES-CWE-89": {
            "name": "SQLInjection",
            "shortDescription": {"text": "Deterministic Delta-SAST: SQL String Interpolation"},
            "helpUri": "https://cwe.mitre.org/data/definitions/89.html",
            "defaultConfiguration": {"level": "error"},
        },
        "HERMES-CWE-79": {
            "name": "CrossSiteScripting",
            "shortDescription": {"text": "Deterministic Delta-SAST: dangerouslySetInnerHTML / XSS"},
            "helpUri": "https://cwe.mitre.org/data/definitions/79.html",
            "defaultConfiguration": {"level": "error"},
        },
        "HERMES-CWE-798": {
            "name": "HardcodedSecrets",
            "shortDescription": {"text": "Deterministic Delta-SAST: Hardcoded API Credentials"},
            "helpUri": "https://cwe.mitre.org/data/definitions/798.html",
            "defaultConfiguration": {"level": "error"},
        },
        "HERMES-PRODUCT-BUG": {
            "name": "ProductRegressionDetected",
            "shortDescription": {"text": "CI Detective: Confirmed Product Logic Regression"},
            "helpUri": "https://hermes.agent/rules/product-bug",
            "defaultConfiguration": {"level": "error"},
        },
        "HERMES-EROSION-BLOCKED": {
            "name": "ZeroAssertionErosionBlocked",
            "shortDescription": {"text": "Zero Assertion Erosion Guard: Weakened or Deleted Assertions"},
            "helpUri": "https://hermes.agent/rules/assertion-erosion",
            "defaultConfiguration": {"level": "error"},
        },
    }

    @classmethod
    def normalize_artifact_uri(cls, file_path: str) -> str:
        """Ensure file path is relative and POSIX normalized (no leading slashes or .\\)."""
        clean = file_path.replace("\\", "/").strip()
        norm = posixpath.normpath(clean)
        return norm.lstrip("/")

    @classmethod
    def compute_audit_digest(
        cls,
        commit_sha: str,
        policy_hash: str,
        diff_hash: str,
        verdict: str,
        findings_count: int,
    ) -> str:
        """Generate tamper-evident SHA-256 chain digest for enterprise compliance auditing."""
        preimage = f"{commit_sha}:{policy_hash}:{diff_hash}:{verdict}:{findings_count}"
        return hashlib.sha256(preimage.encode("utf-8")).hexdigest()

    @classmethod
    def export_report(
        cls,
        findings: List[Dict[str, Any]],
        commit_sha: str = "HEAD",
        policy_hash: str = "default_policy",
        diff_hash: str = "nodiff",
        verdict: str = "AUDITED",
        output_path: Optional[Path | str] = None,
        run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SARIFExportResult:
        """Construct SARIF v2.1.0 document conforming strictly to GitHub Code Scanning schema."""
        if run_id and commit_sha == "HEAD":
            commit_sha = run_id
        active_rules: Dict[str, Dict[str, Any]] = {}
        sarif_results: List[Dict[str, Any]] = []

        for f in findings:
            rule_id = f.get("rule_id") or f.get("cwe") or "HERMES-GOVERNANCE-ALERT"
            if not rule_id.startswith("HERMES-"):
                rule_id = f"HERMES-{rule_id}"

            # Register rule definition if not present
            if rule_id not in active_rules:
                base_def = cls.DEFAULT_RULE_DEFINITIONS.get(rule_id)
                if base_def:
                    active_rules[rule_id] = {"id": rule_id, **base_def}
                else:
                    active_rules[rule_id] = {
                        "id": rule_id,
                        "name": rule_id.replace("HERMES-", ""),
                        "shortDescription": {"text": f.get("message", "Hermes Governance finding")},
                        "defaultConfiguration": {"level": "error" if f.get("severity") == "HIGH" else "warning"},
                    }

            # Normalize file URI and clamp startLine >= 1
            raw_path = f.get("file_path") or f.get("file") or "workspace"
            norm_uri = cls.normalize_artifact_uri(raw_path)
            start_line = max(1, int(f.get("line_number") or f.get("line") or 1))

            # Deterministic partial fingerprint
            fp_raw = f"{rule_id}:{norm_uri}:{start_line}"
            line_hash = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()[:32]

            level = "error" if f.get("severity") in ("HIGH", "CRITICAL") else "warning"
            sarif_results.append({
                "ruleId": rule_id,
                "level": level,
                "message": {"text": f.get("message") or f.get("description") or f"Finding {rule_id}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": norm_uri,
                                "uriBaseId": "%SRCROOT%",
                            },
                            "region": {
                                "startLine": start_line,
                                "startColumn": 1,
                            },
                        }
                    }
                ],
                "partialFingerprints": {
                    "primaryLocationLineHash": line_hash,
                },
            })

        # Cryptographic Audit Digest
        digest = cls.compute_audit_digest(
            commit_sha=commit_sha,
            policy_hash=policy_hash,
            diff_hash=diff_hash,
            verdict=verdict,
            findings_count=len(sarif_results),
        )

        # Full SARIF v2.1.0 Document
        doc: Dict[str, Any] = {
            "$schema": cls.SARIF_SCHEMA,
            "version": cls.SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": cls.TOOL_NAME,
                            "semanticVersion": cls.TOOL_VERSION,
                            "rules": list(active_rules.values()),
                        }
                    },
                    "results": sarif_results,
                    "properties": {
                        "hermesAuditDigest": digest,
                        "commitSha": commit_sha,
                        "verdict": verdict,
                    },
                }
            ],
        }

        # Write to disk if path specified
        out_p = Path(output_path).resolve() if output_path else None
        if out_p:
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        return SARIFExportResult(
            report_path=out_p,
            report_dict=doc,
            audit_digest=digest,
            total_findings=len(sarif_results),
            rule_ids=list(active_rules.keys()),
        )

