"""
Tests for Phase 2: Google Tricorder Closed-Loop Telemetry & Confidence Gating
Owner: QACriticAgent & CIDetectiveAgent
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.audit.tricorder_feedback import (
    CategoryHealth,
    FeedbackOutcome,
    FeedbackSignal,
    GatingAction,
    GatingDecision,
    TricorderGate,
    TricorderLedger,
)
from core.shadow_mode.suggestion_engine import (
    ShadowSuggestionClient,
    ShadowSuggestionFormatter,
)


class TestTricorderDataModels:
    """Verify dataclasses and enums."""

    def test_feedback_signal_serialization(self):
        signal = FeedbackSignal(
            cluster_id="cluster_123",
            category="PRODUCT_BUG",
            rule_id="RULE-500",
            outcome=FeedbackOutcome.USEFUL,
            actor="octocat",
            comment_id="comment_999",
            metadata={"source": "pr_review"},
        )
        d = signal.to_dict()
        assert d["cluster_id"] == "cluster_123"
        assert d["category"] == "PRODUCT_BUG"
        assert d["outcome"] == "USEFUL"
        assert d["actor"] == "octocat"
        assert d["comment_id"] == "comment_999"

        restored = FeedbackSignal.from_dict(d)
        assert restored.cluster_id == signal.cluster_id
        assert restored.category == signal.category
        assert restored.outcome == FeedbackOutcome.USEFUL
        assert restored.metadata == {"source": "pr_review"}

    def test_category_health_to_dict(self):
        health = CategoryHealth(
            category="INFRA_FLAKE",
            total_signals=15,
            useful_count=12,
            not_useful_count=3,
            false_positive_rate=0.20,
            is_throttled=True,
            is_suppressed=False,
        )
        d = health.to_dict()
        assert d["category"] == "INFRA_FLAKE"
        assert d["total_signals"] == 15
        assert d["false_positive_rate"] == 0.2
        assert d["is_throttled"] is True
        assert d["is_suppressed"] is False


class TestTricorderLedger:
    """Verify thread-safe atomic ledger and corrupted-file resilience."""

    def test_ledger_save_and_reload(self, tmp_path):
        ledger_file = tmp_path / "ledger.json"
        ledger = TricorderLedger(ledger_path=ledger_file)

        signal1 = FeedbackSignal(cluster_id="c1", category="PRODUCT_BUG", outcome=FeedbackOutcome.USEFUL)
        signal2 = FeedbackSignal(cluster_id="c2", category="PRODUCT_BUG", outcome=FeedbackOutcome.NOT_USEFUL)
        ledger.record_signal(signal1)
        ledger.record_signal(signal2)

        assert ledger_file.exists()
        reloaded = TricorderLedger(ledger_path=ledger_file)
        signals = reloaded.get_signals_for_category("PRODUCT_BUG")
        assert len(signals) == 2

    def test_ledger_corrupted_file_recovery(self, tmp_path):
        ledger_file = tmp_path / "corrupted_ledger.json"
        ledger_file.write_text("{ this is not valid json !!!", encoding="utf-8")

        ledger = TricorderLedger(ledger_path=ledger_file)
        # Should gracefully recover to empty signals without crashing
        assert len(ledger.get_signals_for_category("ANY")) == 0

        # Can write new signals safely over the corrupted file
        sig = FeedbackSignal(cluster_id="c1", category="TEST_FLAKE", outcome=FeedbackOutcome.USEFUL)
        ledger.record_signal(sig)
        assert len(ledger.get_signals_for_category("TEST_FLAKE")) == 1

    def test_ledger_github_reaction_ingestion(self, tmp_path):
        ledger_file = tmp_path / "reaction_ledger.json"
        ledger = TricorderLedger(ledger_path=ledger_file)

        # Positive reactions
        s1 = ledger.ingest_github_reaction("101", "+1", actor="alice", category="PRODUCT_BUG")
        assert s1.outcome == FeedbackOutcome.USEFUL

        s2 = ledger.ingest_github_reaction("102", "thumbs_up", actor="bob", category="PRODUCT_BUG")
        assert s2.outcome == FeedbackOutcome.USEFUL

        # Negative reactions
        s3 = ledger.ingest_github_reaction("103", "-1", actor="charlie", category="PRODUCT_BUG")
        assert s3.outcome == FeedbackOutcome.NOT_USEFUL

        s4 = ledger.ingest_github_reaction("104", "thumbs_down", actor="dave", category="PRODUCT_BUG")
        assert s4.outcome == FeedbackOutcome.NOT_USEFUL

        # Neutral / unknown reactions
        s5 = ledger.ingest_github_reaction("105", "eyes", actor="eve", category="PRODUCT_BUG")
        assert s5.outcome == FeedbackOutcome.IGNORED

        health = ledger.get_category_health("PRODUCT_BUG", min_samples=4)
        assert health.useful_count == 2
        assert health.not_useful_count == 2
        assert health.false_positive_rate == 0.50


class TestTricorderConfidenceGating:
    """Verify confidence gating, deterministic overrides, and FPR circuit breakers."""

    def test_deterministic_forensic_override_bypass(self, tmp_path):
        ledger_file = tmp_path / "ledger.json"
        ledger = TricorderLedger(ledger_path=ledger_file)

        # Populate high FPR history to ensure it would normally be suppressed
        for i in range(12):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"c_{i}", category="PRODUCT_BUG", outcome=FeedbackOutcome.NOT_USEFUL)
            )

        health = ledger.get_category_health("PRODUCT_BUG", min_samples=10)
        assert health.is_suppressed is True  # 100% FPR

        gate = TricorderGate(ledger=ledger)

        # Deterministic override (e.g. HTTP 500 ground-truth from Phase 1)
        decision = gate.evaluate(
            raw_confidence=0.40,
            category="PRODUCT_BUG",
            is_deterministic=True,
            cluster_id="sprint_det_1",
        )

        # Must bypass statistical FPR demotion/suppression with 1.0 confidence!
        assert decision.action == GatingAction.PUBLISH_INLINE
        assert decision.effective_confidence == 1.0
        assert decision.is_deterministic is True
        assert "Deterministic forensic proof" in decision.reason

    def test_multi_tier_confidence_clean_history(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        gate = TricorderGate(ledger=ledger)

        # Tier 1: High confidence (>= 0.85) -> PUBLISH_INLINE
        d1 = gate.evaluate(raw_confidence=0.92, category="PRODUCT_BUG")
        assert d1.action == GatingAction.PUBLISH_INLINE
        assert d1.effective_confidence == 0.92

        # Tier 2: Moderate confidence (0.60..0.84) -> PUBLISH_COLLAPSED
        d2 = gate.evaluate(raw_confidence=0.75, category="PRODUCT_BUG")
        assert d2.action == GatingAction.PUBLISH_COLLAPSED
        assert d2.effective_confidence == 0.75

        # Tier 3: Low confidence (< 0.60) -> SUPPRESS_SILENT
        d3 = gate.evaluate(raw_confidence=0.45, category="PRODUCT_BUG")
        assert d3.action == GatingAction.SUPPRESS_SILENT
        assert d3.effective_confidence == 0.45

    def test_minimum_sample_floor_prevents_premature_throttling(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        # 3 negative feedback signals (100% FPR), but below min_samples (10)
        for i in range(3):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"c_{i}", category="FLAKY_TEST", outcome=FeedbackOutcome.NOT_USEFUL)
            )

        gate = TricorderGate(ledger=ledger, min_samples=10)
        decision = gate.evaluate(raw_confidence=0.90, category="FLAKY_TEST")

        # Below sample floor: remains inline
        assert decision.action == GatingAction.PUBLISH_INLINE

    def test_fpr_over_10_percent_auto_demotes_to_collapsed(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        # 8 useful, 2 not useful -> 20% FPR (exceeds 10% budget, under 25% suppress limit)
        for i in range(8):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"u_{i}", category="CONFIG_ERROR", outcome=FeedbackOutcome.USEFUL)
            )
        for i in range(2):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"n_{i}", category="CONFIG_ERROR", outcome=FeedbackOutcome.NOT_USEFUL)
            )

        gate = TricorderGate(ledger=ledger, min_samples=10)
        # Even with high raw confidence (0.95), circuit breaker demotes to PUBLISH_COLLAPSED
        decision = gate.evaluate(raw_confidence=0.95, category="CONFIG_ERROR")
        assert decision.action == GatingAction.PUBLISH_COLLAPSED
        assert "exceeds 10% Tricorder budget" in decision.reason

    def test_fpr_over_25_percent_hard_suppresses(self, tmp_path):
        ledger = TricorderLedger(ledger_path=tmp_path / "ledger.json")
        # 7 useful, 3 not useful -> 30% FPR (exceeds 25% budget)
        for i in range(7):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"u_{i}", category="NETWORK_NOISE", outcome=FeedbackOutcome.USEFUL)
            )
        for i in range(3):
            ledger.record_signal(
                FeedbackSignal(cluster_id=f"n_{i}", category="NETWORK_NOISE", outcome=FeedbackOutcome.NOT_USEFUL)
            )

        gate = TricorderGate(ledger=ledger, min_samples=10)
        decision = gate.evaluate(raw_confidence=0.95, category="NETWORK_NOISE")
        assert decision.action == GatingAction.SUPPRESS_SILENT
        assert "exceeds 25% budget" in decision.reason


class TestTricorderReportFooter:
    """Verify report footer generation and metadata recovery."""

    def test_footer_generation_and_metadata_parsing(self):
        decision = GatingDecision(
            action=GatingAction.PUBLISH_INLINE,
            effective_confidence=0.94,
            reason="High confidence",
            category_fpr=0.04,
            is_deterministic=False,
        )
        footer = TricorderGate.generate_report_footer(
            decision=decision,
            cluster_id="sprint_alpha_01",
            category="PRODUCT_BUG",
            rule_id="RULE-PROD-01",
        )

        assert "🤖 **Hermes Tricorder Telemetry**" in footer
        assert "Confidence: **94%**" in footer
        assert "Category: `PRODUCT_BUG`" in footer
        assert "Historical FPR: 4.0%" in footer
        assert "<!-- hermes-tricorder:" in footer

        # Metadata recovery
        meta = TricorderGate.parse_footer_metadata(footer)
        assert meta is not None
        assert meta["cluster_id"] == "sprint_alpha_01"
        assert meta["category"] == "PRODUCT_BUG"
        assert meta["rule_id"] == "RULE-PROD-01"
        assert meta["confidence"] == 0.94
        assert meta["action"] == "PUBLISH_INLINE"


class TestShadowClientWithTricorderIntegration:
    """Verify ShadowSuggestionClient embeds Tricorder footers properly."""

    def test_shadow_client_simulated_in_diff_with_footer(self):
        client = ShadowSuggestionClient(token=None)
        footer = "---\n<sub>🤖 Hermes Tricorder</sub>"
        res = client.post_or_update_suggestion(
            owner="org",
            repo="repo",
            pr_number=1,
            commit_sha="abc1234",
            file_path="src/calc.py",
            start_line=1,
            end_line=2,
            replacement_code="return a + b",
            sprint_id="sprint_test",
            is_in_diff=True,
            tricorder_footer=footer,
        )
        assert res["status"] == "simulated"
        assert res["mode"] == "in_diff"
        assert footer in res["payload"]["body"]

    def test_shadow_client_simulated_out_of_diff_with_footer(self):
        client = ShadowSuggestionClient(token=None)
        footer = "---\n<sub>🤖 Hermes Tricorder Collapsed</sub>"
        res = client.post_or_update_suggestion(
            owner="org",
            repo="repo",
            pr_number=1,
            commit_sha="abc1234",
            file_path="src/calc.py",
            start_line=1,
            end_line=2,
            replacement_code="return a + b",
            sprint_id="sprint_test",
            is_in_diff=False,
            unified_diff="--- a\n+++ b\n",
            tricorder_footer=footer,
        )
        assert res["status"] == "simulated"
        assert res["mode"] == "out_of_diff"
        assert footer in res["body"]

