from __future__ import annotations

from pathlib import Path

from cost_governance import (
    CostGovernanceConfig,
    CostGovernanceController,
    GovernanceAction,
    ModelPricing,
)


def _make_controller(tmp_path: Path, **overrides) -> CostGovernanceController:
    cfg = CostGovernanceConfig(
        ledger_path=tmp_path / "cost_ledger.json",
        **overrides,
    )
    return CostGovernanceController(cfg)


def test_allows_within_budget_and_persists_usage(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, per_run_usd_cap=2.0)
    decision = ctrl.preflight_check(
        run_id="run-1",
        pr_id="PR-42",
        requested_model="gpt-4o",
        estimated_prompt_tokens=10_000,
        estimated_completion_tokens=2_000,
    )
    assert decision.allowed is True
    assert decision.action == GovernanceAction.ALLOW
    assert decision.selected_model == "gpt-4o"

    usage = ctrl.record_usage("run-1", "PR-42", "gpt-4o", 10_000, 2_000)
    assert usage.cost_usd == 0.045

    ctrl2 = _make_controller(tmp_path, per_run_usd_cap=2.0)
    snap = ctrl2.summary(run_id="run-1", pr_id="PR-42")
    assert snap["run"]["usd"] == 0.045
    assert snap["pr"]["calls"] == 1


def test_soft_threshold_triggers_cheaper_fallback_model(tmp_path: Path) -> None:
    ctrl = _make_controller(
        tmp_path,
        per_run_usd_cap=1.00,
        soft_threshold_ratio=0.70,
        fallback_model_chain=["gpt-4o-mini"],
    )
    ctrl.record_usage("run-2", "PR-10", "gpt-4o", 0, 75_000)

    decision = ctrl.preflight_check(
        run_id="run-2",
        pr_id="PR-10",
        requested_model="gpt-4o",
        estimated_prompt_tokens=1_000,
        estimated_completion_tokens=500,
    )
    assert decision.allowed is True
    assert decision.action == GovernanceAction.FALLBACK_MODEL
    assert decision.degraded is True
    assert decision.selected_model == "gpt-4o-mini"


def test_blocks_when_per_run_or_daily_cap_exceeded(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, per_run_usd_cap=0.10, daily_org_usd_cap=0.15)
    ctrl.record_usage("run-3", "PR-1", "gpt-4o", 30_000, 2_000)

    blocked_run = ctrl.preflight_check(
        run_id="run-3",
        pr_id="PR-1",
        requested_model="gpt-4o",
        estimated_prompt_tokens=5_000,
        estimated_completion_tokens=1_000,
    )
    assert blocked_run.allowed is False
    assert blocked_run.action == GovernanceAction.BLOCK_BUDGET

    ctrl.record_usage("run-4", "PR-2", "gpt-4o", 20_000, 1_000)
    blocked_day = ctrl.preflight_check(
        run_id="run-5",
        pr_id="PR-3",
        requested_model="gpt-4o",
        estimated_prompt_tokens=1_000,
        estimated_completion_tokens=500,
    )
    assert blocked_day.allowed is False
    assert "Daily org USD cap" in blocked_day.reason


def test_blocks_when_token_cap_exceeded(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, max_tokens_per_run=5_000)
    ctrl.record_usage("run-tok", "PR-9", "gpt-4o-mini", 4_000, 500)

    decision = ctrl.preflight_check(
        run_id="run-tok",
        pr_id="PR-9",
        requested_model="gpt-4o-mini",
        estimated_prompt_tokens=1_000,
        estimated_completion_tokens=200,
    )
    assert decision.allowed is False
    assert decision.action == GovernanceAction.BLOCK_BUDGET
    assert "token cap" in decision.reason


def test_outage_circuit_breaker_trips_and_recovers(tmp_path: Path) -> None:
    ctrl = _make_controller(
        tmp_path,
        circuit_breaker_window_seconds=600,
        circuit_breaker_unique_prs_threshold=3,
        circuit_breaker_cooldown_seconds=300,
    )
    sig = "ConnectionRefusedError:postgres:5432"
    base_ts = 1_700_000_000.0

    assert ctrl.record_failure_event("PR-1", sig, now_ts=base_ts) == (False, 1)
    assert ctrl.record_failure_event("PR-1", sig, now_ts=base_ts + 5) == (False, 1)
    assert ctrl.record_failure_event("PR-2", sig, now_ts=base_ts + 10) == (False, 2)
    assert ctrl.record_failure_event("PR-3", sig, now_ts=base_ts + 20) == (True, 3)

    blocked = ctrl.preflight_check(
        run_id="run-outage",
        pr_id="PR-4",
        requested_model="gpt-4o",
        failure_signature=sig,
        now_ts=base_ts + 100,
    )
    assert blocked.allowed is False
    assert blocked.action == GovernanceAction.BLOCK_CIRCUIT_OPEN

    recovered = ctrl.preflight_check(
        run_id="run-recovered",
        pr_id="PR-5",
        requested_model="gpt-4o",
        failure_signature=sig,
        now_ts=base_ts + 350,
    )
    assert recovered.allowed is True
    assert recovered.action == GovernanceAction.ALLOW


def test_pricing_override_config() -> None:
    cfg = CostGovernanceConfig.from_dict(
        {
            "pricing_overrides": {
                "internal-llm": {"input_per_1m": 0.10, "output_per_1m": 0.20}
            }
        }
    )
    ctrl = CostGovernanceController(cfg)
    assert ctrl.get_pricing("internal-llm") == ModelPricing(0.10, 0.20)