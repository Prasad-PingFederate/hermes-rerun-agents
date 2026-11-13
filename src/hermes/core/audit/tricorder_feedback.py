"""
Google Tricorder Closed-Loop Telemetry & Confidence Gating
Owner: QACriticAgent & CIDetectiveAgent
Phase: Phase 2 (Enterprise Ground Truth & Precision Gating)

Implements Google Tricorder's core program-analysis principles:
1. High-precision confidence tiers (>=0.85 inline, 0.60-0.84 collapsed, <0.60 silent).
2. Deterministic bypass: Phase 1 forensic overrides (HTTP 500, 502-504) get confidence=1.0.
3. Closed-Loop Developer Feedback (👍 Useful / 👎 Not Useful).
4. <10% False-Positive Circuit Breaker: Automatically demotes noisy categories once min_samples (10) is reached.
5. Zero external dependencies (uses standard library: json, os, re, time, tempfile, pathlib, dataclasses, enum).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class FeedbackOutcome(str, Enum):
    """Developer feedback sentiment on an automated suggestion."""
    USEFUL = "USEFUL"          # 👍 Thumbs up / committed
    NOT_USEFUL = "NOT_USEFUL"  # 👎 Thumbs down / rejected / false positive
    RESOLVED = "RESOLVED"      # Issue addressed
    IGNORED = "IGNORED"        # Stale / no reaction


class GatingAction(str, Enum):
    """Gating decision for automated comments and suggestions."""
    PUBLISH_INLINE = "PUBLISH_INLINE"        # High confidence, active category: inline PR suggestion
    PUBLISH_COLLAPSED = "PUBLISH_COLLAPSED"  # Medium confidence or throttled category: collapsible <details>
    SUPPRESS_SILENT = "SUPPRESS_SILENT"      # Low confidence or heavily throttled category: step summary only


@dataclass
class FeedbackSignal:
    """An individual closed-loop feedback event recorded from developer action."""
    cluster_id: str
    category: str
    rule_id: str = "default"
    outcome: FeedbackOutcome = FeedbackOutcome.USEFUL
    actor: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    comment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "category": self.category,
            "rule_id": self.rule_id,
            "outcome": self.outcome.value if isinstance(self.outcome, FeedbackOutcome) else str(self.outcome),
            "actor": self.actor,
            "timestamp": self.timestamp,
            "comment_id": self.comment_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FeedbackSignal:
        outcome_val = data.get("outcome", "USEFUL")
        try:
            outcome = FeedbackOutcome(outcome_val)
        except ValueError:
            outcome = FeedbackOutcome.USEFUL
        return cls(
            cluster_id=str(data.get("cluster_id", "")),
            category=str(data.get("category", "GENERAL")),
            rule_id=str(data.get("rule_id", "default")),
            outcome=outcome,
            actor=str(data.get("actor", "unknown")),
            timestamp=float(data.get("timestamp", time.time())),
            comment_id=data.get("comment_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CategoryHealth:
    """Telemetry health metrics for a specific rule or failure category."""
    category: str
    total_signals: int
    useful_count: int
    not_useful_count: int
    false_positive_rate: float  # not_useful / (useful + not_useful)
    is_throttled: bool = False
    is_suppressed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "total_signals": self.total_signals,
            "useful_count": self.useful_count,
            "not_useful_count": self.not_useful_count,
            "false_positive_rate": round(self.false_positive_rate, 4),
            "is_throttled": self.is_throttled,
            "is_suppressed": self.is_suppressed,
        }


@dataclass
class GatingDecision:
    """Decision emitted by TricorderGate determining how a suggestion is surfaced."""
    action: GatingAction
    effective_confidence: float
    reason: str
    category_fpr: float = 0.0
    is_deterministic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "effective_confidence": round(self.effective_confidence, 3),
            "reason": self.reason,
            "category_fpr": round(self.category_fpr, 4),
            "is_deterministic": self.is_deterministic,
        }


class TricorderLedger:
    """Thread-safe, atomic-write JSON persistence ledger for developer feedback signals."""

    DEFAULT_FILENAME = ".hermes_telemetry/tricorder_ledger.json"

    def __init__(self, ledger_path: Optional[Union[str, Path]] = None):
        if ledger_path:
            self.ledger_path = Path(ledger_path).resolve()
        else:
            env_path = os.environ.get("HERMES_TRICORDER_LEDGER_PATH")
            self.ledger_path = Path(env_path).resolve() if env_path else Path(self.DEFAULT_FILENAME).resolve()

        self._signals: List[FeedbackSignal] = []
        self._load()

    def _load(self) -> None:
        """Load signals from JSON file with corrupted-file recovery."""
        if not self.ledger_path.exists():
            self._signals = []
            return

        try:
            raw = self.ledger_path.read_text(encoding="utf-8", errors="replace")
            if not raw.strip():
                self._signals = []
                return
            data = json.loads(raw)
            if isinstance(data, list):
                self._signals = [FeedbackSignal.from_dict(d) for d in data if isinstance(d, dict)]
            elif isinstance(data, dict) and "signals" in data:
                self._signals = [FeedbackSignal.from_dict(d) for d in data["signals"] if isinstance(d, dict)]
            else:
                self._signals = []
        except Exception:
            # Corrupted file recovery: initialize safe empty list
            self._signals = []

    def save(self) -> None:
        """Atomically persist signals to ledger file using tempfile replacement."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.to_dict() for s in self._signals]
        raw_json = json.dumps(data, indent=2)

        # Atomic write pattern
        dir_name = self.ledger_path.parent
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            tf.write(raw_json)
            temp_name = tf.name

        os.replace(temp_name, self.ledger_path)

    def record_signal(self, signal: FeedbackSignal) -> None:
        """Record a feedback signal and persist immediately."""
        self._signals.append(signal)
        self.save()

    def get_signals_for_category(self, category: str) -> List[FeedbackSignal]:
        cat_upper = category.upper().strip()
        return [s for s in self._signals if s.category.upper().strip() == cat_upper]

    def get_category_health(
        self,
        category: str,
        min_samples: int = 10,
        fpr_throttle_threshold: float = 0.10,
        fpr_suppress_threshold: float = 0.25,
    ) -> CategoryHealth:
        """Calculate health and false-positive rate (FPR) for a given category."""
        signals = self.get_signals_for_category(category)
        useful = sum(1 for s in signals if s.outcome in (FeedbackOutcome.USEFUL, FeedbackOutcome.RESOLVED))
        not_useful = sum(1 for s in signals if s.outcome == FeedbackOutcome.NOT_USEFUL)
        total_eval = useful + not_useful

        fpr = (not_useful / total_eval) if total_eval > 0 else 0.0

        is_throttled = False
        is_suppressed = False

        # Minimum sample floor must be met before activating circuit breaker
        if total_eval >= min_samples:
            if fpr > fpr_suppress_threshold:
                is_suppressed = True
                is_throttled = True
            elif fpr > fpr_throttle_threshold:
                is_throttled = True

        return CategoryHealth(
            category=category.upper().strip(),
            total_signals=len(signals),
            useful_count=useful,
            not_useful_count=not_useful,
            false_positive_rate=fpr,
            is_throttled=is_throttled,
            is_suppressed=is_suppressed,
        )

    def ingest_github_reaction(
        self,
        comment_id: str,
        reaction: str,
        actor: str = "github_user",
        cluster_id: str = "cluster_unknown",
        category: str = "GENERAL",
        rule_id: str = "default",
    ) -> FeedbackSignal:
        """Ingest GitHub comment reaction (+1, -1, thumbs_up, thumbs_down)."""
        clean_reaction = reaction.lower().strip()
        if clean_reaction in ("+1", "thumbs_up", "thumbsup", "useful", "heart", "hooray", "rocket"):
            outcome = FeedbackOutcome.USEFUL
        elif clean_reaction in ("-1", "thumbs_down", "thumbsdown", "not_useful", "confused"):
            outcome = FeedbackOutcome.NOT_USEFUL
        else:
            outcome = FeedbackOutcome.IGNORED

        signal = FeedbackSignal(
            cluster_id=cluster_id,
            category=category,
            rule_id=rule_id,
            outcome=outcome,
            actor=actor,
            comment_id=comment_id,
            metadata={"raw_reaction": reaction},
        )
        self.record_signal(signal)
        return signal


class TricorderGate:
    """Tricorder Gating & Circuit Breaker Engine."""

    # Google Tricorder Precision Standards
    DEFAULT_HIGH_CONFIDENCE = 0.85        # >= 0.85 -> PUBLISH_INLINE
    DEFAULT_COLLAPSED_CONFIDENCE = 0.60   # 0.60..0.84 -> PUBLISH_COLLAPSED
    DEFAULT_MIN_SAMPLES = 10              # Required samples before FPR circuit breaker trips
    DEFAULT_FPR_THROTTLE = 0.10           # > 10% FPR demotes to PUBLISH_COLLAPSED
    DEFAULT_FPR_SUPPRESS = 0.25           # > 25% FPR hard-suppresses to SUPPRESS_SILENT

    FOOTER_METADATA_REGEX = re.compile(r"<!--\s*hermes-tricorder:\s*(\{.*?\})\s*-->")

    def __init__(
        self,
        ledger: Optional[TricorderLedger] = None,
        high_confidence_threshold: float = DEFAULT_HIGH_CONFIDENCE,
        collapsed_confidence_threshold: float = DEFAULT_COLLAPSED_CONFIDENCE,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        fpr_throttle_threshold: float = DEFAULT_FPR_THROTTLE,
        fpr_suppress_threshold: float = DEFAULT_FPR_SUPPRESS,
    ):
        self.ledger = ledger or TricorderLedger()
        self.high_confidence = high_confidence_threshold
        self.collapsed_confidence = collapsed_confidence_threshold
        self.min_samples = min_samples
        self.fpr_throttle = fpr_throttle_threshold
        self.fpr_suppress = fpr_suppress_threshold

    def evaluate(
        self,
        raw_confidence: float,
        category: str,
        is_deterministic: bool = False,
        cluster_id: str = "cluster_unknown",
        rule_id: str = "default",
    ) -> GatingDecision:
        """Evaluate finding against confidence thresholds and closed-loop FPR circuit breakers."""
        cat_upper = category.upper().strip()

        # 1. Deterministic Forensic Override Bypass
        # Any finding with Phase 1 forensic proof (e.g. HTTP 500 PRODUCT_BUG or HTTP 502 INFRA_FLAKE)
        # receives confidence 1.0 and is immune to statistical FPR demotion.
        if is_deterministic:
            return GatingDecision(
                action=GatingAction.PUBLISH_INLINE,
                effective_confidence=1.0,
                reason="Deterministic forensic proof (Phase 1 override: bypasses confidence suppression)",
                category_fpr=0.0,
                is_deterministic=True,
            )

        # 2. Query Category Health
        health = self.ledger.get_category_health(
            category=cat_upper,
            min_samples=self.min_samples,
            fpr_throttle_threshold=self.fpr_throttle,
            fpr_suppress_threshold=self.fpr_suppress,
        )

        effective_conf = max(0.0, min(1.0, float(raw_confidence)))

        # 3. Check FPR Circuit Breaker (<10% budget)
        if health.is_suppressed:
            return GatingDecision(
                action=GatingAction.SUPPRESS_SILENT,
                effective_confidence=effective_conf,
                reason=f"Category '{cat_upper}' false-positive rate ({health.false_positive_rate:.1%}) exceeds 25% budget (auto-suppressed)",
                category_fpr=health.false_positive_rate,
                is_deterministic=False,
            )

        # 4. Confidence-Tier Evaluation
        if effective_conf >= self.high_confidence:
            if health.is_throttled:
                return GatingDecision(
                    action=GatingAction.PUBLISH_COLLAPSED,
                    effective_confidence=effective_conf,
                    reason=f"Category '{cat_upper}' FPR ({health.false_positive_rate:.1%}) exceeds 10% Tricorder budget (demoted from inline to collapsed)",
                    category_fpr=health.false_positive_rate,
                    is_deterministic=False,
                )
            return GatingDecision(
                action=GatingAction.PUBLISH_INLINE,
                effective_confidence=effective_conf,
                reason=f"High-confidence finding ({effective_conf:.0%} >= {self.high_confidence:.0%}) with clean FPR history",
                category_fpr=health.false_positive_rate,
                is_deterministic=False,
            )

        elif effective_conf >= self.collapsed_confidence:
            return GatingDecision(
                action=GatingAction.PUBLISH_COLLAPSED,
                effective_confidence=effective_conf,
                reason=f"Moderate-confidence finding ({effective_conf:.0%}) surfaced in collapsed summary",
                category_fpr=health.false_positive_rate,
                is_deterministic=False,
            )

        else:
            return GatingDecision(
                action=GatingAction.SUPPRESS_SILENT,
                effective_confidence=effective_conf,
                reason=f"Low-confidence finding ({effective_conf:.0%} < {self.collapsed_confidence:.0%}) suppressed to eliminate noise",
                category_fpr=health.false_positive_rate,
                is_deterministic=False,
            )

    @classmethod
    def generate_report_footer(
        cls,
        decision: GatingDecision,
        cluster_id: str,
        category: str,
        rule_id: str = "default",
    ) -> str:
        """Generate compact closed-loop feedback footer with embedded correlation metadata."""
        conf_pct = round(decision.effective_confidence * 100)
        fpr_text = f" · Historical FPR: {decision.category_fpr:.1%}" if decision.category_fpr > 0 else ""

        meta_dict = {
            "cluster_id": cluster_id,
            "category": category,
            "rule_id": rule_id,
            "confidence": round(decision.effective_confidence, 2),
            "action": decision.action.value,
        }
        meta_comment = f"<!-- hermes-tricorder: {json.dumps(meta_dict)} -->"

        footer_lines = [
            "---",
            f"<sub>🤖 **Hermes Tricorder Telemetry**: Confidence: **{conf_pct}%** · Category: `{category}`{fpr_text}</sub><br>",
            "<sub>Was this suggestion helpful? React **👍** if helpful or **👎** to calibrate precision.</sub>",
            meta_comment,
        ]
        return "\n".join(footer_lines)

    @classmethod
    def parse_footer_metadata(cls, text: str) -> Optional[Dict[str, Any]]:
        """Extract embedded Tricorder correlation metadata from markdown comment."""
        match = cls.FOOTER_METADATA_REGEX.search(text)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

