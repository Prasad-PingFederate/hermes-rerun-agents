"""
Bayesian Confidence Calibration & Cost-Aware CI Decision Model
Owner: QACriticAgent, CIDetectiveAgent & ScrumMasterOrchestrator
Phase: Phase 4 (Bayesian Calibration, Blast Radius & Zero-Waste Rerun Engine)

Enums & Contracts bridging Phases 1, 2, 3 -> Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from hermes.core.audit.tricorder_feedback import TricorderLedger


# =====================================================================
# Enums & Contracts (Bridging Phases 1, 2, 3 -> Phase 4)
# =====================================================================

class FailureCategory(str, Enum):
    PRODUCT_BUG = "PRODUCT_BUG"
    INFRA_FLAKE = "INFRA_FLAKE"
    TEST_FLAKE = "TEST_FLAKE"
    TEST_BUG = "TEST_BUG"
    CONFIG_DRIFT = "CONFIG_DRIFT"
    UNKNOWN = "UNKNOWN"


class PatchGuardStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"  # Blocked for assertion erosion or Delta-SAST violation


class RemediationAction(str, Enum):
    FAIL_FAST_ESCALATE = "FAIL_FAST_ESCALATE"
    PROPOSE_VERIFIED_PATCH = "PROPOSE_VERIFIED_PATCH"
    AUTO_RERUN_TRANSIENT = "AUTO_RERUN_TRANSIENT"
    RECOMMEND_QUARANTINE = "RECOMMEND_QUARANTINE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    OBSERVE_SILENT = "OBSERVE_SILENT"


@dataclass(frozen=True)
class LedgerFeedbackStats:
    """Closed-loop developer feedback counts from Phase 2's TricorderLedger."""
    useful_count: int = 0
    not_useful_count: int = 0


@dataclass(frozen=True)
class TriageSignalInput:
    """Consolidated input signal from Phases 1, 2, and 3."""
    test_id: str
    category: FailureCategory
    raw_llm_confidence: float

    # Phase 1: Deterministic signals (e.g., HTTP 500 -> PRODUCT_BUG, 502..504 -> INFRA_FLAKE)
    is_deterministic: bool = False
    http_status_code: Optional[int] = None
    is_network_drop: bool = False

    # Forensic corroboration signals
    has_stack_trace: bool = False
    has_network_logs: bool = False
    is_chronic_flake: bool = False

    # Phase 2: Historical feedback for this category/rule
    ledger_stats: LedgerFeedbackStats = field(default_factory=LedgerFeedbackStats)

    # Phase 3: PatchGuard verification outcome
    patch_guard_status: PatchGuardStatus = PatchGuardStatus.NOT_APPLICABLE
    candidate_patch_diff: Optional[str] = None

    # CI Suite Execution Context (for FinOps blast-radius)
    failed_tests: int = 1
    total_tests: int = 100


@dataclass(frozen=True, init=False)
class RerunPolicy:
    """FinOps Zero-Waste Rerun Guard decision."""
    allow_rerun: bool
    max_retries: int
    backoff_seconds: int
    blast_radius_ratio: float
    finops_rationale: str
    estimated_ci_minutes_saved: float

    def __init__(
        self,
        allow_rerun: bool,
        max_retries: int = 0,
        backoff_seconds: int = 0,
        blast_radius_ratio: float = 0.0,
        finops_rationale: str = "",
        estimated_ci_minutes_saved: float = 0.0,
        rationale: Optional[str] = None,
    ):
        object.__setattr__(self, "allow_rerun", allow_rerun)
        object.__setattr__(self, "max_retries", max_retries)
        object.__setattr__(self, "backoff_seconds", backoff_seconds)
        object.__setattr__(self, "blast_radius_ratio", blast_radius_ratio)
        rat = rationale if rationale is not None else finops_rationale
        object.__setattr__(self, "finops_rationale", rat)
        object.__setattr__(self, "estimated_ci_minutes_saved", estimated_ci_minutes_saved)

    @property
    def rationale(self) -> str:
        return self.finops_rationale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow_rerun": self.allow_rerun,
            "max_retries": self.max_retries,
            "backoff_seconds": self.backoff_seconds,
            "blast_radius_ratio": round(self.blast_radius_ratio, 4),
            "finops_rationale": self.finops_rationale,
            "rationale": self.finops_rationale,
            "estimated_ci_minutes_saved": round(self.estimated_ci_minutes_saved, 2),
        }


@dataclass(frozen=True)
class Phase4DecisionResult:
    """Final calibrated decision emitted by Phase 4."""
    test_id: str
    category: FailureCategory
    raw_confidence: float
    posterior_precision: float
    calibrated_confidence: float
    action: RemediationAction
    rerun_policy: RerunPolicy
    expose_patch: bool
    decision_trace: Dict[str, float | str | bool]

    @property
    def bayesian_category_precision(self) -> float:
        return self.posterior_precision

    @property
    def blast_radius_ratio(self) -> float:
        return self.rerun_policy.blast_radius_ratio

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "category": self.category.value if isinstance(self.category, Enum) else str(self.category),
            "raw_confidence": round(self.raw_confidence, 4),
            "posterior_precision": round(self.posterior_precision, 4),
            "calibrated_confidence": round(self.calibrated_confidence, 4),
            "bayesian_category_precision": round(self.posterior_precision, 4),
            "blast_radius_ratio": round(self.blast_radius_ratio, 4),
            "action": self.action.value if isinstance(self.action, Enum) else str(self.action),
            "rerun_policy": self.rerun_policy.to_dict(),
            "expose_patch": self.expose_patch,
            "decision_trace": self.decision_trace,
        }


# Type alias for backward compatibility
DecisionVerdict = Phase4DecisionResult


# =====================================================================
# Phase 4 Core Engine
# =====================================================================

class Phase4DecisionEngine:
    """
    Bayesian Confidence Calibration, FinOps Blast-Radius Guard,
    and Optimal Remediation Action Selector.
    """

    # Laplace-smoothed Beta prior: Beta(alpha=2.0, beta=1.0) -> E[p] = 2/3 (~0.667)
    PRIOR_ALPHA: float = 2.0
    PRIOR_BETA: float = 1.0

    # Calibration modifiers
    FORENSIC_CORROBORATION_BONUS: float = 0.10
    PATCHGUARD_PASS_BONUS: float = 0.05
    PATCHGUARD_BLOCK_PENALTY: float = -0.15

    # Action thresholds
    SILENT_THRESHOLD: float = 0.45
    HIGH_CONFIDENCE_THRESHOLD: float = 0.75
    QUARANTINE_THRESHOLD: float = 0.65

    @classmethod
    def compute_beta_posterior_mean(cls, stats: LedgerFeedbackStats) -> float:
        """
        Computes the Beta-Binomial posterior expectation:
        E[p | useful, not_useful] = (alpha + useful) / (alpha + beta + useful + not_useful)
        """
        u = max(0, stats.useful_count)
        nu = max(0, stats.not_useful_count)
        numerator = cls.PRIOR_ALPHA + u
        denominator = cls.PRIOR_ALPHA + cls.PRIOR_BETA + u + nu
        return numerator / denominator

    @classmethod
    def calibrate_confidence(
        cls, signal: TriageSignalInput
    ) -> tuple[float, float, Dict[str, float | str | bool]]:
        """
        Calibrates raw LLM confidence using the Beta-Binomial posterior,
        forensic telemetry corroboration, and PatchGuard verification status.
        """
        posterior_precision = cls.compute_beta_posterior_mean(signal.ledger_stats)

        # Phase 1 deterministic findings remain locked at 1.0
        if signal.is_deterministic or signal.http_status_code in (500, 502, 503, 504):
            return 1.0, 1.0, {
                "deterministic_lock": True,
                "posterior_precision": 1.0,
                "forensic_bonus": 0.0,
                "patch_guard_modifier": 0.0,
            }

        raw = max(0.0, min(1.0, signal.raw_llm_confidence))

        # Down-weight raw LLM overconfidence by historical posterior precision
        base_calibrated = raw * posterior_precision

        # Forensic telemetry bonus (+0.10 when both stack trace + network logs corroborate)
        forensic_bonus = (
            cls.FORENSIC_CORROBORATION_BONUS
            if (signal.has_stack_trace and signal.has_network_logs)
            else 0.0
        )

        # PatchGuard modifier (+0.05 on pass, -0.15 on block for assertion erosion / SAST)
        if signal.patch_guard_status == PatchGuardStatus.PASSED:
            patch_modifier = cls.PATCHGUARD_PASS_BONUS
        elif signal.patch_guard_status == PatchGuardStatus.BLOCKED:
            patch_modifier = cls.PATCHGUARD_BLOCK_PENALTY
        else:
            patch_modifier = 0.0

        calibrated = base_calibrated + forensic_bonus + patch_modifier
        calibrated = max(0.0, min(1.0, calibrated))

        trace = {
            "deterministic_lock": False,
            "raw_confidence": round(raw, 4),
            "posterior_precision": round(posterior_precision, 4),
            "base_calibrated": round(base_calibrated, 4),
            "forensic_bonus": forensic_bonus,
            "patch_guard_modifier": patch_modifier,
            "final_calibrated": round(calibrated, 4),
        }
        return round(calibrated, 4), round(posterior_precision, 4), trace

    @classmethod
    def evaluate_finops_rerun_guard(
        cls, signal: TriageSignalInput, calibrated_confidence: float
    ) -> RerunPolicy:
        """
        Computes blast_radius_ratio and enforces zero-waste retry rules.
        """
        total = max(1, signal.total_tests)
        failed = max(0, min(signal.failed_tests, total))
        blast_radius = round(failed / total, 4)

        # Strictly block retries on confirmed PRODUCT_BUGs to save CI runner minutes
        if signal.category == FailureCategory.PRODUCT_BUG:
            return RerunPolicy(
                allow_rerun=False,
                max_retries=0,
                backoff_seconds=0,
                blast_radius_ratio=blast_radius,
                finops_rationale=(
                    "Zero-Waste Guard: Confirmed PRODUCT_BUG. Retries strictly disabled "
                    "to prevent burning CI runner minutes on deterministic backend defects."
                ),
                estimated_ci_minutes_saved=20.0,
            )

        # Authorize bounded retries for transient INFRA_FLAKEs or network drops
        is_transient_infra = (
            signal.category == FailureCategory.INFRA_FLAKE
            or signal.is_network_drop
            or signal.http_status_code in (502, 503, 504)
        )
        if is_transient_infra:
            return RerunPolicy(
                allow_rerun=True,
                max_retries=2,
                backoff_seconds=10,  # 10s exponential backoff base
                blast_radius_ratio=blast_radius,
                finops_rationale=(
                    "Transient INFRA_FLAKE / gateway drop detected. Authorized bounded "
                    "retries (max_retries=2, 10s exponential backoff)."
                ),
                estimated_ci_minutes_saved=0.0,
            )

        # For chronic test flakes, allow a single retry only if confidence is high
        if signal.category == FailureCategory.TEST_FLAKE and calibrated_confidence >= cls.QUARANTINE_THRESHOLD:
            return RerunPolicy(
                allow_rerun=True,
                max_retries=1,
                backoff_seconds=5,
                blast_radius_ratio=blast_radius,
                finops_rationale="Non-deterministic TEST_FLAKE: single verification retry permitted.",
                estimated_ci_minutes_saved=10.0,
            )

        # Default fallback: no automatic retries
        return RerunPolicy(
            allow_rerun=False,
            max_retries=0,
            backoff_seconds=0,
            blast_radius_ratio=blast_radius,
            finops_rationale="Default FinOps policy: retries disabled for unverified failure mode.",
            estimated_ci_minutes_saved=0.0,
        )

    @classmethod
    def select_remediation_action(
        cls, signal: TriageSignalInput, calibrated_confidence: float
    ) -> tuple[RemediationAction, bool]:
        """
        Selects the optimal remediation action and determines whether a candidate patch
        is safe to expose to developers.
        """
        # 1. Noise gate: suppress low-confidence classifications
        if calibrated_confidence < cls.SILENT_THRESHOLD:
            return RemediationAction.OBSERVE_SILENT, False

        # 2. Transient infrastructure / gateway failures (502..504 or network drop)
        if (
            signal.category == FailureCategory.INFRA_FLAKE
            or signal.is_network_drop
            or signal.http_status_code in (502, 503, 504)
        ):
            return RemediationAction.AUTO_RERUN_TRANSIENT, False

        # 3. High-confidence finding with a PatchGuard-verified fix
        if (
            signal.patch_guard_status == PatchGuardStatus.PASSED
            and signal.candidate_patch_diff
            and calibrated_confidence >= cls.HIGH_CONFIDENCE_THRESHOLD
        ):
            return RemediationAction.PROPOSE_VERIFIED_PATCH, True

        # 4. If PatchGuard stripped an unsafe patch, downgrade to DIAGNOSTIC_ONLY
        #    (unless it's a deterministic HTTP 500 product bug that must escalate)
        if signal.patch_guard_status == PatchGuardStatus.BLOCKED:
            if signal.category == FailureCategory.PRODUCT_BUG and calibrated_confidence >= cls.HIGH_CONFIDENCE_THRESHOLD:
                return RemediationAction.FAIL_FAST_ESCALATE, False
            return RemediationAction.DIAGNOSTIC_ONLY, False

        # 5. Confirmed PRODUCT_BUG without a safe patch -> FAIL_FAST_ESCALATE
        if (
            signal.category == FailureCategory.PRODUCT_BUG
            and calibrated_confidence >= cls.HIGH_CONFIDENCE_THRESHOLD
        ):
            return RemediationAction.FAIL_FAST_ESCALATE, False

        # 6. Chronic TEST_FLAKE with non-deterministic drift -> RECOMMEND_QUARANTINE
        if (
            signal.category == FailureCategory.TEST_FLAKE
            and (signal.is_chronic_flake or calibrated_confidence >= cls.QUARANTINE_THRESHOLD)
        ):
            return RemediationAction.RECOMMEND_QUARANTINE, False

        # 7. Moderate confidence fallback -> DIAGNOSTIC_ONLY
        return RemediationAction.DIAGNOSTIC_ONLY, False

    @classmethod
    def evaluate(cls, signal: TriageSignalInput) -> Phase4DecisionResult:
        """End-to-end Phase 4 evaluation pipeline."""
        calibrated_conf, posterior_prec, trace = cls.calibrate_confidence(signal)
        rerun_policy = cls.evaluate_finops_rerun_guard(signal, calibrated_conf)
        action, expose_patch = cls.select_remediation_action(signal, calibrated_conf)
        trace["action"] = action.value
        trace["allow_rerun"] = rerun_policy.allow_rerun

        return Phase4DecisionResult(
            test_id=signal.test_id,
            category=signal.category,
            raw_confidence=signal.raw_llm_confidence,
            posterior_precision=posterior_prec,
            calibrated_confidence=calibrated_conf,
            action=action,
            rerun_policy=rerun_policy,
            expose_patch=expose_patch,
            decision_trace=trace,
        )


# =====================================================================
# DecisionModel: Bridge between Phase 2 Tricorder & Phase 4 Engine
# =====================================================================

class DecisionModel:
    """Convenience wrapper integrating TricorderLedger with Phase4DecisionEngine."""

    def __init__(
        self,
        ledger: Optional[TricorderLedger] = None,
        alpha_prior: float = Phase4DecisionEngine.PRIOR_ALPHA,
        beta_prior: float = Phase4DecisionEngine.PRIOR_BETA,
        default_suite_minutes: float = 10.0,
    ):
        self.ledger = ledger or TricorderLedger()
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        self.default_suite_minutes = default_suite_minutes

    def calculate_posterior_precision(self, category: str) -> float:
        health = self.ledger.get_category_health(category)
        stats = LedgerFeedbackStats(useful_count=health.useful_count, not_useful_count=health.not_useful_count)
        return Phase4DecisionEngine.compute_beta_posterior_mean(stats)

    def calibrate_confidence(
        self,
        raw_confidence: float,
        category: str,
        is_deterministic: bool = False,
        has_forensic_evidence: bool = False,
        patch_guard_verdict: Optional[Any] = None,
        trace: Optional[List[str]] = None,
    ) -> tuple[float, float]:
        cat_enum = self._to_category_enum(category)
        health = self.ledger.get_category_health(category)
        stats = LedgerFeedbackStats(useful_count=health.useful_count, not_useful_count=health.not_useful_count)
        pg_status = self._to_patch_guard_status(patch_guard_verdict)
        signal = TriageSignalInput(
            test_id="eval",
            category=cat_enum,
            raw_llm_confidence=raw_confidence,
            is_deterministic=is_deterministic,
            http_status_code=500 if (is_deterministic and cat_enum == FailureCategory.PRODUCT_BUG) else None,
            has_stack_trace=has_forensic_evidence,
            has_network_logs=has_forensic_evidence,
            ledger_stats=stats,
            patch_guard_status=pg_status,
        )
        calibrated, precision, trace_dict = Phase4DecisionEngine.calibrate_confidence(signal)
        if trace is not None:
            for k, v in trace_dict.items():
                trace.append(f"{k}: {v}")
        return calibrated, precision

    def evaluate(
        self,
        raw_confidence: float,
        category: Union[FailureCategory, str],
        is_deterministic: bool = False,
        has_forensic_evidence: bool = False,
        patch_guard_verdict: Optional[Any] = None,
        failed_tests_count: int = 1,
        total_tests_run: int = 100,
        is_transient_error: bool = False,
        estimated_suite_runtime: Optional[float] = None,
        blast_radius_ratio: Optional[float] = None,
        candidate_patch_diff: Optional[str] = None,
    ) -> Phase4DecisionResult:
        cat_enum = self._to_category_enum(category)
        health = self.ledger.get_category_health(str(category))
        stats = LedgerFeedbackStats(useful_count=health.useful_count, not_useful_count=health.not_useful_count)
        pg_status = self._to_patch_guard_status(patch_guard_verdict)

        diff = candidate_patch_diff
        if diff is None and patch_guard_verdict and getattr(patch_guard_verdict, "passed", False):
            diff = "--- a/file\n+++ b/file\n"

        status_code = None
        if is_deterministic:
            if cat_enum == FailureCategory.PRODUCT_BUG:
                status_code = 500
            elif cat_enum == FailureCategory.INFRA_FLAKE:
                status_code = 503

        signal = TriageSignalInput(
            test_id="ci_run",
            category=cat_enum,
            raw_llm_confidence=raw_confidence,
            is_deterministic=is_deterministic,
            http_status_code=status_code,
            is_network_drop=is_transient_error,
            has_stack_trace=has_forensic_evidence,
            has_network_logs=has_forensic_evidence,
            is_chronic_flake=(cat_enum == FailureCategory.TEST_FLAKE),
            ledger_stats=stats,
            patch_guard_status=pg_status,
            candidate_patch_diff=diff,
            failed_tests=failed_tests_count,
            total_tests=total_tests_run,
        )
        return Phase4DecisionEngine.evaluate(signal)

    @staticmethod
    def _to_category_enum(category: Union[FailureCategory, str]) -> FailureCategory:
        if isinstance(category, FailureCategory):
            return category
        raw = str(category).upper().strip()
        if raw in FailureCategory.__members__:
            return FailureCategory[raw]
        if raw in ("FLAKY_TEST", "TEST_FLAKE"):
            return FailureCategory.TEST_FLAKE
        return FailureCategory.UNKNOWN

    @staticmethod
    def _to_patch_guard_status(patch_guard_verdict: Optional[Any]) -> PatchGuardStatus:
        if patch_guard_verdict is None:
            return PatchGuardStatus.NOT_APPLICABLE
        if getattr(patch_guard_verdict, "passed", False):
            return PatchGuardStatus.PASSED
        return PatchGuardStatus.BLOCKED
