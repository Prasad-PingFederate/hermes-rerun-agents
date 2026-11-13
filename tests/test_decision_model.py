"""
Tests for Phase 4: Bayesian Confidence Calibration & Cost-Aware CI Decision Model
Owner: QACriticAgent, CIDetectiveAgent & ScrumMasterOrchestrator
"""

from __future__ import annotations

import pytest

from core.audit.delta_sast import PatchGuardVerdict, PatchViolation
from core.audit.tricorder_feedback import (
    FeedbackOutcome,
    FeedbackSignal,
    TricorderLedger,
)
from core.decision.decision_model import (
    DecisionModel,
    DecisionVerdict,
    RemediationAction,
    RerunPolicy,
)


class TestDecisionDataModels:
    """Verify dataclasses, enums, and serialization."""

    def test_rerun_policy_to_dict(self):
        policy = RerunPolicy(
            allow_rerun=True,
            max_retries=2,
            backoff_seconds=10,
            estimated_ci_minutes_saved=0.0,
            rationale="Transient fault retry",
        )
        d = policy.to_dict()
        assert d["allow_rerun"] is True
        assert d["max_retries"] == 2
        assert d["backoff_seconds"] == 10
        assert d["estimated_ci_minutes_saved"] == 0.0
        assert "Transient fault" in d["rationale"]

    def test_decision_verdict_to_dict(self):
        policy = RerunPolicy(allow_rerun=False, max_retries=0, estimated_ci_minutes_saved=15.0)
        verdict = DecisionVerdict(
            action=RemediationAction.FAIL_FAST_ESCALATE,
            raw_confidence=0.90,
            calibrated_confidence=0.88,
            bayesian_category_precision=0.85,
            blast_radius_ratio=0.10,
            rerun_policy=policy,
            decision_trace=["Rule 1 applied", "Rule 2 applied"],
        )
        d = verdict.to_dict()
        assert d["action"] == "FAIL_FAST_ESCALATE"
        assert d["raw_confidence"] == 0.90
        assert d["calibrated_confidence"] == 0.88
        assert d["bayesian_category_precision"] == 0.85
        assert d["blast_radius_ratio"] == 0.10
        assert d["rerun_policy"]["allow_rerun"] is False
        assert len(d["decision_trace"]) == 2


class TestDeterministicOverridesAndZeroWasteGuard:
    """Verify Phase 1 deterministic overrides and zero-waste rerun guard."""

    def test_deterministic_product_bug_locks_confidence_and_blocks_rerun(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger, default_suite_minutes=10.0)

        # HTTP 500 deterministic override -> PRODUCT_BUG without patch
        verdict = model.evaluate(
            raw_confidence=0.35,  # Raw LLM was confused
            category="PRODUCT_BUG",
            is_deterministic=True,
            has_forensic_evidence=True,
            patch_guard_verdict=None,
            failed_tests_count=2,
            total_tests_run=20,
        )

        # 1. Calibrated confidence is locked at 1.0
        assert verdict.calibrated_confidence == 1.0
        assert verdict.bayesian_category_precision == 1.0

        # 2. Zero-Waste Rerun Guard strictly forbids retrying
        assert verdict.rerun_policy.allow_rerun is False
        assert verdict.rerun_policy.max_retries == 0
        assert verdict.rerun_policy.estimated_ci_minutes_saved == 20.0  # 10m * 2 retries saved
        assert "Zero-Waste Rerun Guard" in verdict.rerun_policy.rationale

        # 3. Action is FAIL_FAST_ESCALATE (no patch available)
        assert verdict.action == RemediationAction.FAIL_FAST_ESCALATE
        assert any("DETERMINISTIC LOCK" in t for t in verdict.decision_trace)

    def test_deterministic_product_bug_with_approved_patch_proposes_fix(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        patch_verdict = PatchGuardVerdict(passed=True, status="APPROVED", violations=[])
        verdict = model.evaluate(
            raw_confidence=0.95,
            category="PRODUCT_BUG",
            is_deterministic=True,
            has_forensic_evidence=True,
            patch_guard_verdict=patch_verdict,
        )

        assert verdict.calibrated_confidence == 1.0
        assert verdict.rerun_policy.allow_rerun is False
        assert verdict.action == RemediationAction.PROPOSE_VERIFIED_PATCH


class TestTransientInfraRetryPolicy:
    """Verify transient 502-504 / INFRA_FLAKE authorizes bounded retries."""

    def test_infra_flake_authorizes_bounded_exponential_retry(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        verdict = model.evaluate(
            raw_confidence=0.90,
            category="INFRA_FLAKE",
            is_deterministic=True,
            has_forensic_evidence=True,
            failed_tests_count=5,
            total_tests_run=5,  # 100% blast radius
            is_transient_error=True,
        )

        assert verdict.action == RemediationAction.AUTO_RERUN_TRANSIENT
        assert verdict.rerun_policy.allow_rerun is True
        assert verdict.rerun_policy.max_retries == 2
        assert verdict.rerun_policy.backoff_seconds == 10
        assert "Transient" in verdict.rerun_policy.rationale

    def test_high_blast_radius_transient_authorizes_retry(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        # 8 out of 10 tests failed due to connection reset / timeout
        verdict = model.evaluate(
            raw_confidence=0.85,
            category="ENVIRONMENT_NOISE",
            blast_radius_ratio=0.80,
            is_transient_error=True,
            failed_tests_count=8,
            total_tests_run=10,
        )

        assert verdict.rerun_policy.allow_rerun is True
        assert verdict.rerun_policy.max_retries == 2
        assert verdict.blast_radius_ratio == 0.80


class TestBayesianConfidenceCalibration:
    """Verify Laplace-smoothed Beta-Binomial posterior updates."""

    def test_beta_prior_smoothing_with_zero_signals(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger, alpha_prior=2.0, beta_prior=1.0)

        # Prior (alpha=2, beta=1) with 0 signals -> 2 / (2+1) = 2/3 = ~0.667
        precision = model.calculate_posterior_precision("PRODUCT_BUG")
        assert pytest.approx(precision, 0.01) == 0.667

    def test_calibrates_down_on_noisy_historical_category(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        # Record 1 useful and 9 not useful signals (poor category precision)
        ledger.record_signal(FeedbackSignal(cluster_id="c1", category="HEURISTIC_GUESS", outcome=FeedbackOutcome.USEFUL))
        for i in range(9):
            ledger.record_signal(FeedbackSignal(cluster_id=f"c{i+2}", category="HEURISTIC_GUESS", outcome=FeedbackOutcome.NOT_USEFUL))

        model = DecisionModel(ledger=ledger, alpha_prior=2.0, beta_prior=1.0)
        # Posterior: (1 + 2) / (1 + 9 + 2 + 1) = 3 / 13 = ~0.231
        precision = model.calculate_posterior_precision("HEURISTIC_GUESS")
        assert pytest.approx(precision, 0.01) == 0.231

        # Even if raw LLM confidence is 0.95 (overconfident)
        calibrated, _ = model.calibrate_confidence(
            raw_confidence=0.95,
            category="HEURISTIC_GUESS",
            is_deterministic=False,
            has_forensic_evidence=False,
            patch_guard_verdict=None,
        )

        # (0.95 * 0.60) + (0.231 * 0.40) = 0.57 + 0.0924 = ~0.662
        assert calibrated < 0.75
        assert calibrated < 0.95

    def test_penalizes_patchguard_blocked_suggestion(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        blocked_patch = PatchGuardVerdict(
            passed=False,
            status="BLOCKED_ASSERTION_EROSION",
            violations=[PatchViolation(rule_id="EROSION_ASSERTION_DELETED", severity="ERROR", message="Deleted assert")],
        )

        calibrated, _ = model.calibrate_confidence(
            raw_confidence=0.70,
            category="TEST_BUG",
            is_deterministic=False,
            patch_guard_verdict=blocked_patch,
        )

        # Blended base is ~0.68; minus 0.15 penalty -> ~0.53
        assert calibrated < 0.60  # Pushed below 0.60 threshold due to hallucinated unsafe patch

    def test_forensic_bonus_boosts_confidence(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        conf_with_forensics, _ = model.calibrate_confidence(
            raw_confidence=0.75,
            category="PRODUCT_BUG",
            has_forensic_evidence=True,
        )
        conf_without_forensics, _ = model.calibrate_confidence(
            raw_confidence=0.75,
            category="PRODUCT_BUG",
            has_forensic_evidence=False,
        )

        assert pytest.approx(conf_with_forensics - conf_without_forensics, 0.01) == 0.10


class TestFlakyTestQuarantineAndLowConfidenceGating:
    """Verify quarantine recommendation for chronic flakes and silent observation for low confidence."""

    def test_flaky_test_recommends_quarantine_without_patch(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        verdict = model.evaluate(
            raw_confidence=0.85,
            category="TEST_FLAKE",
            patch_guard_verdict=None,
        )

        assert verdict.action == RemediationAction.RECOMMEND_QUARANTINE
        assert verdict.rerun_policy.allow_rerun is False
        assert "non-determinism" in verdict.rerun_policy.rationale

    def test_low_calibrated_confidence_selects_observe_silent(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        # Raw confidence is low (0.40)
        verdict = model.evaluate(
            raw_confidence=0.40,
            category="UNKNOWN_ANOMALY",
            has_forensic_evidence=False,
        )

        assert verdict.calibrated_confidence < 0.60
        assert verdict.action == RemediationAction.OBSERVE_SILENT
        assert any("OBSERVE_SILENT" in t for t in verdict.decision_trace)

    def test_moderate_confidence_with_blocked_patch_is_diagnostic_only(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        model = DecisionModel(ledger=ledger)

        blocked_patch = PatchGuardVerdict(
            passed=False,
            status="BLOCKED_DELTA_SAST",
            violations=[PatchViolation(rule_id="SAST_EXEC_INJECTION", severity="ERROR", message="eval injected")],
        )

        verdict = model.evaluate(
            raw_confidence=0.90,
            category="TEST_BUG",
            has_forensic_evidence=True,
            patch_guard_verdict=blocked_patch,
        )

        # Patch is blocked, so cannot propose verified patch
        assert verdict.action == RemediationAction.DIAGNOSTIC_ONLY
        assert any("DIAGNOSTIC_ONLY" in t for t in verdict.decision_trace)


class TestBlastRadiusCalculation:
    """Verify blast radius ratio computations."""

    def test_blast_radius_bounds(self, tmp_path):
        model = DecisionModel(ledger=TricorderLedger(ledger_path=tmp_path / "l.json"))

        v1 = model.evaluate(raw_confidence=0.8, category="GENERAL", failed_tests_count=0, total_tests_run=50)
        assert v1.blast_radius_ratio == 0.0

        v2 = model.evaluate(raw_confidence=0.8, category="GENERAL", failed_tests_count=25, total_tests_run=50)
        assert v2.blast_radius_ratio == 0.50

        v3 = model.evaluate(raw_confidence=0.8, category="GENERAL", failed_tests_count=100, total_tests_run=50)
        assert v3.blast_radius_ratio == 1.0  # Clamped at 1.0

        v4 = model.evaluate(raw_confidence=0.8, category="GENERAL", failed_tests_count=5, total_tests_run=0)
        assert v4.blast_radius_ratio == 1.0  # Safe division
