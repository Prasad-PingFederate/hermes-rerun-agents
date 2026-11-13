"""
Bayesian Confidence Calibration & Cost-Aware CI Decision Model
Owner: QACriticAgent, CIDetectiveAgent & ScrumMasterOrchestrator
Phase: Phase 4 (Bayesian Calibration, Blast Radius & Zero-Waste Rerun Engine)

Implements:
1. Bayesian Confidence Calibration (Beta-Binomial posterior smoothing using Tricorder precision).
2. Blast-Radius & Zero-Waste Rerun Policy (stops wasteful CI reruns on confirmed PRODUCT_BUGs).
3. Optimal Remediation Action Selection (FAIL_FAST_ESCALATE, PROPOSE_VERIFIED_PATCH, AUTO_RERUN_TRANSIENT, etc.).
4. Fully explainable decision audit trace.
5. Zero external dependencies (Python 3.10 standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from core.audit.delta_sast import PatchGuardVerdict
from core.audit.tricorder_feedback import CategoryHealth, TricorderLedger


class RemediationAction(str, Enum):
    """Optimal remediation action chosen by the decision model."""
    FAIL_FAST_ESCALATE = "FAIL_FAST_ESCALATE"        # Confirmed PRODUCT_BUG; abort wasteful retries, alert team
    PROPOSE_VERIFIED_PATCH = "PROPOSE_VERIFIED_PATCH"# High calibrated confidence + PatchGuard approved
    AUTO_RERUN_TRANSIENT = "AUTO_RERUN_TRANSIENT"    # INFRA_FLAKE / transient 502-504; bounded exponential retry
    RECOMMEND_QUARANTINE = "RECOMMEND_QUARANTINE"    # Chronic TEST_FLAKE without verified patch
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"              # Moderate confidence or PatchGuard stripped patch
    OBSERVE_SILENT = "OBSERVE_SILENT"                # Low calibrated confidence (<0.60); suppress PR noise


@dataclass
class RerunPolicy:
    """FinOps cost-aware rerun decision policy."""
    allow_rerun: bool
    max_retries: int = 0
    backoff_seconds: int = 0
    estimated_ci_minutes_saved: float = 0.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow_rerun": self.allow_rerun,
            "max_retries": self.max_retries,
            "backoff_seconds": self.backoff_seconds,
            "estimated_ci_minutes_saved": round(self.estimated_ci_minutes_saved, 2),
            "rationale": self.rationale,
        }


@dataclass
class DecisionVerdict:
    """Consolidated decision verdict with Bayesian calibration and explainable trace."""
    action: RemediationAction
    raw_confidence: float
    calibrated_confidence: float
    bayesian_category_precision: float
    blast_radius_ratio: float
    rerun_policy: RerunPolicy
    decision_trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "raw_confidence": round(self.raw_confidence, 3),
            "calibrated_confidence": round(self.calibrated_confidence, 3),
            "bayesian_category_precision": round(self.bayesian_category_precision, 3),
            "blast_radius_ratio": round(self.blast_radius_ratio, 4),
            "rerun_policy": self.rerun_policy.to_dict(),
            "decision_trace": list(self.decision_trace),
        }


class DecisionModel:
    """Bayesian calibration and cost-aware CI decision engine."""

    # Laplace-smoothed Beta prior parameters
    DEFAULT_ALPHA_PRIOR: float = 2.0  # Equivalent to 2 pseudo-useful signals
    DEFAULT_BETA_PRIOR: float = 1.0   # Equivalent to 1 pseudo-not-useful signal
    DEFAULT_SUITE_MINUTES: float = 10.0

    def __init__(
        self,
        ledger: Optional[TricorderLedger] = None,
        alpha_prior: float = DEFAULT_ALPHA_PRIOR,
        beta_prior: float = DEFAULT_BETA_PRIOR,
        default_suite_minutes: float = DEFAULT_SUITE_MINUTES,
    ):
        self.ledger = ledger or TricorderLedger()
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        self.default_suite_minutes = default_suite_minutes

    def calculate_posterior_precision(self, category: str) -> float:
        """Calculate Bayesian Beta-Binomial posterior precision: (useful + alpha) / (total + alpha + beta)."""
        health: CategoryHealth = self.ledger.get_category_health(category)
        useful = float(health.useful_count)
        not_useful = float(health.not_useful_count)

        numerator = useful + self.alpha_prior
        denominator = useful + not_useful + self.alpha_prior + self.beta_prior
        posterior = numerator / denominator if denominator > 0 else 0.5
        return float(posterior)

    def calibrate_confidence(
        self,
        raw_confidence: float,
        category: str,
        is_deterministic: bool = False,
        has_forensic_evidence: bool = False,
        patch_guard_verdict: Optional[PatchGuardVerdict] = None,
        trace: Optional[List[str]] = None,
    ) -> tuple[float, float]:
        """Calibrate raw confidence using Bayesian category precision and forensic evidence.

        Returns: (calibrated_confidence, posterior_precision)
        """
        trace_list = trace if trace is not None else []
        cat_upper = category.upper().strip()

        # 1. Deterministic Override Lock (Phase 1)
        if is_deterministic:
            trace_list.append("⚡ [DETERMINISTIC LOCK] Phase 1 forensic override: locked calibrated_confidence = 1.000")
            return 1.0, 1.0

        # 2. Bayesian Beta-Binomial Posterior Precision
        posterior_precision = self.calculate_posterior_precision(cat_upper)
        trace_list.append(
            f"📊 [BAYESIAN POSTERIOR] Category '{cat_upper}' Beta({self.alpha_prior:.1f}, {self.beta_prior:.1f}) "
            f"posterior precision = {posterior_precision:.3f}"
        )

        # 3. Base Calibration: Blend raw confidence with historical precision
        clamped_raw = max(0.0, min(1.0, float(raw_confidence)))
        base_calibrated = (clamped_raw * 0.60) + (posterior_precision * 0.40)
        trace_list.append(
            f"⚖️ [BLENDED CONFIDENCE] Raw ({clamped_raw:.3f} * 0.60) + Precision ({posterior_precision:.3f} * 0.40) = {base_calibrated:.3f}"
        )

        # 4. Forensic Evidence Bonus (+0.10)
        calibrated = base_calibrated
        if has_forensic_evidence:
            calibrated += 0.10
            trace_list.append("🔍 [FORENSIC BONUS] +0.10 applied (stack trace / network telemetry corroborated)")

        # 5. PatchGuard Penalty / Bonus
        if patch_guard_verdict is not None:
            if patch_guard_verdict.passed:
                calibrated += 0.05
                trace_list.append("🛡️ [PATCHGUARD BONUS] +0.05 applied (patch passed Delta-SAST & Assertion Erosion guards)")
            else:
                calibrated -= 0.15
                trace_list.append(
                    f"⛔ [PATCHGUARD PENALTY] -0.15 applied (patch blocked: {patch_guard_verdict.status})"
                )

        calibrated = max(0.0, min(1.0, calibrated))
        trace_list.append(f"🎯 [FINAL CALIBRATED CONFIDENCE] {calibrated:.3f}")
        return calibrated, posterior_precision

    def calculate_rerun_policy(
        self,
        category: str,
        blast_radius_ratio: float,
        is_transient_error: bool = False,
        estimated_suite_runtime: Optional[float] = None,
        trace: Optional[List[str]] = None,
    ) -> RerunPolicy:
        """Compute FinOps blast-radius and cost-aware rerun policy."""
        trace_list = trace if trace is not None else []
        cat_upper = category.upper().strip()
        suite_time = estimated_suite_runtime if estimated_suite_runtime is not None else self.default_suite_minutes

        # Zero-Waste Guard: NEVER retry confirmed PRODUCT_BUG
        if cat_upper == "PRODUCT_BUG":
            saved_minutes = suite_time * 2.0  # Assumes 2 wasted retries prevented
            trace_list.append(
                f"🛑 [ZERO-WASTE GUARD] PRODUCT_BUG confirmed: reruns forbidden (saved ~{saved_minutes:.1f} CI minutes)"
            )
            return RerunPolicy(
                allow_rerun=False,
                max_retries=0,
                backoff_seconds=0,
                estimated_ci_minutes_saved=saved_minutes,
                rationale="Zero-Waste Rerun Guard: Confirmed PRODUCT_BUG; retrying would burn CI minutes without fixing root cause.",
            )

        # Transient Network / Infrastructure Retry
        if cat_upper == "INFRA_FLAKE" or is_transient_error or (blast_radius_ratio >= 0.50 and is_transient_error):
            trace_list.append(
                f"🔄 [TRANSIENT RERUN] {cat_upper} detected: authorizing 2 bounded retries with 10s exponential backoff"
            )
            return RerunPolicy(
                allow_rerun=True,
                max_retries=2,
                backoff_seconds=10,
                estimated_ci_minutes_saved=0.0,
                rationale="Transient infrastructure or network fault detected; bounded retry with exponential backoff authorized.",
            )

        # Chronic Flake
        if cat_upper in ("TEST_FLAKE", "FLAKY_TEST"):
            saved_minutes = suite_time * 1.0
            trace_list.append(
                f"⚠️ [FLAKE MITIGATION] {cat_upper} detected: suppression/quarantine preferred over CI rerun loops"
            )
            return RerunPolicy(
                allow_rerun=False,
                max_retries=0,
                backoff_seconds=0,
                estimated_ci_minutes_saved=saved_minutes,
                rationale="Test flakiness detected; blind reruns mask non-determinism. Quarantining or patching recommended.",
            )

        # Default / Environment Noise
        return RerunPolicy(
            allow_rerun=False,
            max_retries=0,
            backoff_seconds=0,
            estimated_ci_minutes_saved=0.0,
            rationale="Non-transient test failure; immediate rerun not recommended.",
        )

    def evaluate(
        self,
        raw_confidence: float,
        category: str,
        is_deterministic: bool = False,
        has_forensic_evidence: bool = False,
        patch_guard_verdict: Optional[PatchGuardVerdict] = None,
        failed_tests_count: int = 1,
        total_tests_run: int = 100,
        is_transient_error: bool = False,
        estimated_suite_runtime: Optional[float] = None,
        blast_radius_ratio: Optional[float] = None,
    ) -> DecisionVerdict:
        """Evaluate failure to produce calibrated confidence, blast radius, and optimal remediation action."""
        trace: List[str] = []
        cat_upper = category.upper().strip()

        # 1. Compute Blast Radius Ratio
        safe_total = max(1, total_tests_run)
        if blast_radius_ratio is not None:
            blast_radius = min(1.0, max(0.0, float(blast_radius_ratio)))
        else:
            blast_radius = min(1.0, max(0.0, float(failed_tests_count) / float(safe_total)))
        trace.append(f"💥 [BLAST RADIUS] {failed_tests_count}/{safe_total} failed tests = {blast_radius:.1%}")

        # 2. Bayesian Confidence Calibration
        calibrated_conf, posterior_prec = self.calibrate_confidence(
            raw_confidence=raw_confidence,
            category=cat_upper,
            is_deterministic=is_deterministic,
            has_forensic_evidence=has_forensic_evidence,
            patch_guard_verdict=patch_guard_verdict,
            trace=trace,
        )

        # 3. Cost-Aware Rerun Policy
        rerun_policy = self.calculate_rerun_policy(
            category=cat_upper,
            blast_radius_ratio=blast_radius,
            is_transient_error=is_transient_error,
            estimated_suite_runtime=estimated_suite_runtime,
            trace=trace,
        )

        # 4. Remediation Action Selection
        action = self._select_remediation_action(
            category=cat_upper,
            calibrated_confidence=calibrated_conf,
            patch_guard_verdict=patch_guard_verdict,
            trace=trace,
        )

        return DecisionVerdict(
            action=action,
            raw_confidence=raw_confidence,
            calibrated_confidence=calibrated_conf,
            bayesian_category_precision=posterior_prec,
            blast_radius_ratio=blast_radius,
            rerun_policy=rerun_policy,
            decision_trace=trace,
        )

    def _select_remediation_action(
        self,
        category: str,
        calibrated_confidence: float,
        patch_guard_verdict: Optional[PatchGuardVerdict],
        trace: List[str],
    ) -> RemediationAction:
        """Determine optimal remediation action based on category, confidence, and patch status."""
        cat_upper = category.upper().strip()

        # Low confidence -> Observe silently (no noise)
        if calibrated_confidence < 0.60:
            trace.append(f"🤫 [ACTION] Calibrated confidence ({calibrated_confidence:.2f}) < 0.60 -> OBSERVE_SILENT")
            return RemediationAction.OBSERVE_SILENT

        # Infra / Network Flake -> Auto rerun transient
        if cat_upper == "INFRA_FLAKE":
            trace.append("🔄 [ACTION] Infrastructure flake with transient fault -> AUTO_RERUN_TRANSIENT")
            return RemediationAction.AUTO_RERUN_TRANSIENT

        # Product Bug
        if cat_upper == "PRODUCT_BUG":
            if patch_guard_verdict is not None and patch_guard_verdict.passed and calibrated_confidence >= 0.80:
                trace.append("✨ [ACTION] Confirmed PRODUCT_BUG with PatchGuard-approved fix -> PROPOSE_VERIFIED_PATCH")
                return RemediationAction.PROPOSE_VERIFIED_PATCH
            trace.append("🛑 [ACTION] Confirmed PRODUCT_BUG without verified patch -> FAIL_FAST_ESCALATE")
            return RemediationAction.FAIL_FAST_ESCALATE

        # Flaky Test
        if cat_upper in ("TEST_FLAKE", "FLAKY_TEST"):
            if patch_guard_verdict is not None and patch_guard_verdict.passed and calibrated_confidence >= 0.80:
                trace.append("✨ [ACTION] Flaky test with verified patch -> PROPOSE_VERIFIED_PATCH")
                return RemediationAction.PROPOSE_VERIFIED_PATCH
            trace.append("🚧 [ACTION] Flaky test without safe patch -> RECOMMEND_QUARANTINE")
            return RemediationAction.RECOMMEND_QUARANTINE

        # If a patch was proposed but BLOCKED by PatchGuard
        if patch_guard_verdict is not None and not patch_guard_verdict.passed:
            trace.append("📋 [ACTION] Patch blocked by PatchGuard -> DIAGNOSTIC_ONLY")
            return RemediationAction.DIAGNOSTIC_ONLY

        # High confidence with approved patch
        if calibrated_confidence >= 0.80 and patch_guard_verdict is not None and patch_guard_verdict.passed:
            trace.append("✨ [ACTION] High confidence with PatchGuard-approved fix -> PROPOSE_VERIFIED_PATCH")
            return RemediationAction.PROPOSE_VERIFIED_PATCH

        # Moderate confidence / general diagnosis
        trace.append(f"📋 [ACTION] Calibrated confidence ({calibrated_confidence:.2f}) -> DIAGNOSTIC_ONLY")
        return RemediationAction.DIAGNOSTIC_ONLY
