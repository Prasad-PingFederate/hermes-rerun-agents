from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class GovernanceAction(str, Enum):
    ALLOW = "allow"
    FALLBACK_MODEL = "fallback_model"
    BLOCK_BUDGET = "block_budget"
    BLOCK_CIRCUIT_OPEN = "block_circuit_open"


class BudgetExceededError(RuntimeError):
    """Raised when a run, PR, or daily organization spend/token cap is reached."""


class CircuitBreakerOpenError(RuntimeError):
    """Raised when an org-wide CI outage circuit breaker pauses LLM healing."""


@dataclass(frozen=True)
class ModelPricing:
    """USD cost per 1,000,000 tokens."""
    input_per_1m: float
    output_per_1m: float

    def estimate_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        in_cost = (max(0, prompt_tokens) / 1_000_000.0) * self.input_per_1m
        out_cost = (max(0, completion_tokens) / 1_000_000.0) * self.output_per_1m
        return round(in_cost + out_cost, 6)


DEFAULT_MODEL_PRICING: Dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(input_per_1m=2.50, output_per_1m=10.00),
    "gpt-4o-mini": ModelPricing(input_per_1m=0.15, output_per_1m=0.60),
    "claude-3-5-sonnet": ModelPricing(input_per_1m=3.00, output_per_1m=15.00),
    "claude-3-5-haiku": ModelPricing(input_per_1m=0.80, output_per_1m=4.00),
    "gemini-2.5-pro": ModelPricing(input_per_1m=1.25, output_per_1m=10.00),
    "gemini-2.5-flash": ModelPricing(input_per_1m=0.15, output_per_1m=0.60),
    "local": ModelPricing(input_per_1m=0.0, output_per_1m=0.0),
}


@dataclass
class CostGovernanceConfig:
    enabled: bool = True
    per_run_usd_cap: float = 1.50
    per_pr_usd_cap: float = 5.00
    daily_org_usd_cap: float = 50.00
    max_tokens_per_run: int = 120_000
    soft_threshold_ratio: float = 0.70
    fallback_model_chain: List[str] = field(
        default_factory=lambda: ["gpt-4o-mini", "gemini-2.5-flash"]
    )
    circuit_breaker_window_seconds: int = 900
    circuit_breaker_unique_prs_threshold: int = 5
    circuit_breaker_cooldown_seconds: int = 1800
    ledger_path: Path = field(default_factory=lambda: Path(".rerun_tasks/cost_ledger.json"))
    pricing_overrides: Dict[str, ModelPricing] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CostGovernanceConfig":
        if not data:
            return cls()
        overrides: Dict[str, ModelPricing] = {}
        for model_name, rates in (data.get("pricing_overrides") or {}).items():
            overrides[model_name] = ModelPricing(
                input_per_1m=float(rates["input_per_1m"]),
                output_per_1m=float(rates["output_per_1m"]),
            )
        return cls(
            enabled=bool(data.get("enabled", True)),
            per_run_usd_cap=float(data.get("per_run_usd_cap", 1.50)),
            per_pr_usd_cap=float(data.get("per_pr_usd_cap", 5.00)),
            daily_org_usd_cap=float(data.get("daily_org_usd_cap", 50.00)),
            max_tokens_per_run=int(data.get("max_tokens_per_run", 120_000)),
            soft_threshold_ratio=float(data.get("soft_threshold_ratio", 0.70)),
            fallback_model_chain=list(
                data.get("fallback_model_chain", ["gpt-4o-mini", "gemini-2.5-flash"])
            ),
            circuit_breaker_window_seconds=int(
                data.get("circuit_breaker_window_seconds", 900)
            ),
            circuit_breaker_unique_prs_threshold=int(
                data.get("circuit_breaker_unique_prs_threshold", 5)
            ),
            circuit_breaker_cooldown_seconds=int(
                data.get("circuit_breaker_cooldown_seconds", 1800)
            ),
            ledger_path=Path(data.get("ledger_path", ".rerun_tasks/cost_ledger.json")),
            pricing_overrides=overrides,
        )


@dataclass
class GovernanceDecision:
    allowed: bool
    action: GovernanceAction
    selected_model: str
    reason: str
    degraded: bool = False
    remaining_run_usd: float = 0.0
    remaining_pr_usd: float = 0.0
    remaining_daily_usd: float = 0.0

    def to_event_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        return payload


@dataclass
class UsageRecord:
    timestamp_utc: str
    run_id: str
    pr_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    def to_event_payload(self) -> Dict[str, Any]:
        return asdict(self)


class CostGovernanceController:
    """Thread-safe, file-backed budget enforcer, model fallback router, and outage circuit breaker."""

    def __init__(self, config: Optional[CostGovernanceConfig] = None) -> None:
        self.config = config or CostGovernanceConfig()
        self._lock = threading.RLock()
        self._pricing: Dict[str, ModelPricing] = {
            **DEFAULT_MODEL_PRICING,
            **self.config.pricing_overrides,
        }

    def _today_key(self, now_ts: Optional[float] = None) -> str:
        ts = now_ts if now_ts is not None else time.time()
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    def _empty_ledger(self) -> Dict[str, Any]:
        return {
            "runs": {},
            "prs": {},
            "daily": {},
            "failure_events": {},
            "circuit_open_until": {},
        }

    def _load_ledger(self) -> Dict[str, Any]:
        path = self.config.ledger_path
        if not path.exists():
            return self._empty_ledger()
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            base = self._empty_ledger()
            base.update(data)
            return base
        except (OSError, json.JSONDecodeError):
            return self._empty_ledger()

    def _save_ledger(self, ledger: Dict[str, Any]) -> None:
        path = self.config.ledger_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".cost_ledger_", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_fh:
                json.dump(ledger, tmp_fh, indent=2, sort_keys=True)
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def get_pricing(self, model: str) -> ModelPricing:
        if model in self._pricing:
            return self._pricing[model]
        lowered = model.lower()
        for key, pricing in self._pricing.items():
            if key in lowered:
                return pricing
        return ModelPricing(input_per_1m=3.00, output_per_1m=15.00)

    def _select_cheaper_model(self, requested_model: str) -> Optional[str]:
        current_rate = self.get_pricing(requested_model).output_per_1m
        for candidate in self.config.fallback_model_chain:
            if candidate == requested_model:
                continue
            if self.get_pricing(candidate).output_per_1m < current_rate:
                return candidate
        return None

    def record_failure_event(
        self,
        pr_id: str,
        failure_signature: str,
        now_ts: Optional[float] = None,
    ) -> Tuple[bool, int]:
        ts = now_ts if now_ts is not None else time.time()
        cutoff = ts - self.config.circuit_breaker_window_seconds

        with self._lock:
            ledger = self._load_ledger()
            events = [
                ev
                for ev in ledger["failure_events"].get(failure_signature, [])
                if float(ev.get("ts", 0.0)) >= cutoff
            ]
            events.append({"pr_id": str(pr_id), "ts": ts})
            ledger["failure_events"][failure_signature] = events

            distinct_prs = {str(ev["pr_id"]) for ev in events}
            tripped = False
            if len(distinct_prs) >= self.config.circuit_breaker_unique_prs_threshold:
                ledger["circuit_open_until"][failure_signature] = (
                    ts + self.config.circuit_breaker_cooldown_seconds
                )
                tripped = True

            self._save_ledger(ledger)
            return tripped, len(distinct_prs)

    def preflight_check(
        self,
        run_id: str,
        pr_id: str,
        requested_model: str,
        estimated_prompt_tokens: int = 0,
        estimated_completion_tokens: int = 2000,
        failure_signature: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> GovernanceDecision:
        if not self.config.enabled:
            return GovernanceDecision(
                allowed=True,
                action=GovernanceAction.ALLOW,
                selected_model=requested_model,
                reason="cost_governance_disabled",
            )

        ts = now_ts if now_ts is not None else time.time()
        day_key = self._today_key(ts)

        with self._lock:
            ledger = self._load_ledger()

            if failure_signature:
                open_until = float(ledger["circuit_open_until"].get(failure_signature, 0.0))
                if open_until > ts:
                    remaining_sec = int(open_until - ts)
                    return GovernanceDecision(
                        allowed=False,
                        action=GovernanceAction.BLOCK_CIRCUIT_OPEN,
                        selected_model=requested_model,
                        reason=(
                            f"Outage circuit breaker OPEN for signature '{failure_signature}' "
                            f"({remaining_sec}s cooldown remaining)."
                        ),
                    )

            run_stats = ledger["runs"].get(str(run_id), {"usd": 0.0, "tokens": 0})
            pr_stats = ledger["prs"].get(str(pr_id), {"usd": 0.0, "tokens": 0})
            day_stats = ledger["daily"].get(day_key, {"usd": 0.0, "tokens": 0})

            est_cost = self.get_pricing(requested_model).estimate_usd(
                estimated_prompt_tokens, estimated_completion_tokens
            )
            est_tokens = max(0, estimated_prompt_tokens) + max(0, estimated_completion_tokens)

            rem_run = max(0.0, round(self.config.per_run_usd_cap - run_stats["usd"], 6))
            rem_pr = max(0.0, round(self.config.per_pr_usd_cap - pr_stats["usd"], 6))
            rem_day = max(0.0, round(self.config.daily_org_usd_cap - day_stats["usd"], 6))

            if run_stats["tokens"] + est_tokens > self.config.max_tokens_per_run:
                return GovernanceDecision(
                    allowed=False,
                    action=GovernanceAction.BLOCK_BUDGET,
                    selected_model=requested_model,
                    reason=(
                        f"Per-run token cap exceeded ({run_stats['tokens'] + est_tokens} > "
                        f"{self.config.max_tokens_per_run})."
                    ),
                    remaining_run_usd=rem_run,
                    remaining_pr_usd=rem_pr,
                    remaining_daily_usd=rem_day,
                )

            if run_stats["usd"] + est_cost > self.config.per_run_usd_cap:
                return GovernanceDecision(
                    allowed=False,
                    action=GovernanceAction.BLOCK_BUDGET,
                    selected_model=requested_model,
                    reason=(
                        f"Per-run USD cap exceeded (${run_stats['usd'] + est_cost:.4f} > "
                        f"${self.config.per_run_usd_cap:.2f})."
                    ),
                    remaining_run_usd=rem_run,
                    remaining_pr_usd=rem_pr,
                    remaining_daily_usd=rem_day,
                )

            if pr_stats["usd"] + est_cost > self.config.per_pr_usd_cap:
                return GovernanceDecision(
                    allowed=False,
                    action=GovernanceAction.BLOCK_BUDGET,
                    selected_model=requested_model,
                    reason=(
                        f"Per-PR USD cap exceeded (${pr_stats['usd'] + est_cost:.4f} > "
                        f"${self.config.per_pr_usd_cap:.2f})."
                    ),
                    remaining_run_usd=rem_run,
                    remaining_pr_usd=rem_pr,
                    remaining_daily_usd=rem_day,
                )

            if day_stats["usd"] + est_cost > self.config.daily_org_usd_cap:
                return GovernanceDecision(
                    allowed=False,
                    action=GovernanceAction.BLOCK_BUDGET,
                    selected_model=requested_model,
                    reason=(
                        f"Daily org USD cap exceeded (${day_stats['usd'] + est_cost:.4f} > "
                        f"${self.config.daily_org_usd_cap:.2f})."
                    ),
                    remaining_run_usd=rem_run,
                    remaining_pr_usd=rem_pr,
                    remaining_daily_usd=rem_day,
                )

            run_ratio = run_stats["usd"] / max(self.config.per_run_usd_cap, 1e-9)
            day_ratio = day_stats["usd"] / max(self.config.daily_org_usd_cap, 1e-9)
            if max(run_ratio, day_ratio) >= self.config.soft_threshold_ratio:
                fallback = self._select_cheaper_model(requested_model)
                if fallback:
                    return GovernanceDecision(
                        allowed=True,
                        action=GovernanceAction.FALLBACK_MODEL,
                        selected_model=fallback,
                        degraded=True,
                        reason=(
                            f"Soft budget threshold ({self.config.soft_threshold_ratio:.0%}) "
                            f"reached; downgrading {requested_model} -> {fallback}."
                        ),
                        remaining_run_usd=rem_run,
                        remaining_pr_usd=rem_pr,
                        remaining_daily_usd=rem_day,
                    )

            return GovernanceDecision(
                allowed=True,
                action=GovernanceAction.ALLOW,
                selected_model=requested_model,
                reason="within_budget",
                remaining_run_usd=rem_run,
                remaining_pr_usd=rem_pr,
                remaining_daily_usd=rem_day,
            )

    def record_usage(
        self,
        run_id: str,
        pr_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        now_ts: Optional[float] = None,
    ) -> UsageRecord:
        ts = now_ts if now_ts is not None else time.time()
        day_key = self._today_key(ts)
        cost_usd = self.get_pricing(model).estimate_usd(prompt_tokens, completion_tokens)
        total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)

        with self._lock:
            ledger = self._load_ledger()

            for bucket, key in (
                (ledger["runs"], str(run_id)),
                (ledger["prs"], str(pr_id)),
                (ledger["daily"], day_key),
            ):
                entry = bucket.get(key, {"usd": 0.0, "tokens": 0, "calls": 0})
                entry["usd"] = round(float(entry["usd"]) + cost_usd, 6)
                entry["tokens"] = int(entry["tokens"]) + total_tokens
                entry["calls"] = int(entry.get("calls", 0)) + 1
                bucket[key] = entry

            self._save_ledger(ledger)

        return UsageRecord(
            timestamp_utc=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            run_id=str(run_id),
            pr_id=str(pr_id),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )

    def summary(
        self,
        run_id: Optional[str] = None,
        pr_id: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        day_key = self._today_key(now_ts)
        with self._lock:
            ledger = self._load_ledger()
            return {
                "date_utc": day_key,
                "daily": ledger["daily"].get(day_key, {"usd": 0.0, "tokens": 0, "calls": 0}),
                "run": ledger["runs"].get(str(run_id), {"usd": 0.0, "tokens": 0, "calls": 0})
                if run_id is not None
                else None,
                "pr": ledger["prs"].get(str(pr_id), {"usd": 0.0, "tokens": 0, "calls": 0})
                if pr_id is not None
                else None,
                "active_circuit_breakers": {
                    sig: exp
                    for sig, exp in ledger["circuit_open_until"].items()
                    if float(exp) > (now_ts if now_ts is not None else time.time())
                },
            }