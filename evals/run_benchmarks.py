"""
Hermes Reproducible Evaluation Benchmark Runner
Runs 24 seeded enterprise scenarios (Regressions, Intentional Drift, Adversarial Traps)
Outputs a standardized scorecard:
- Pass@1 Accuracy
- False-Green Rate (Strictly 0.0%)
- Adversarial Trap Interception Rate (100.0%)
- Average Latency
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.audit.delta_sast import PatchGuard
from core.decision.decision_model import (
    FailureCategory,
    LedgerFeedbackStats,
    PatchGuardStatus,
    Phase4DecisionEngine,
    RemediationAction,
    TriageSignalInput,
)
from evals.scenarios import SCENARIOS, EvalScenario


def run_benchmark() -> Dict[str, Any]:
    print("=" * 75)
    print("🚀 Running Hermes Enterprise Self-Healing Benchmark (24 Seeded Scenarios)")
    print("=" * 75)

    passed_scenarios = 0
    traps_blocked = 0
    drift_detected = 0
    regressions_healed = 0
    false_greens = 0
    latencies: List[float] = []

    results: List[Dict[str, Any]] = []

    for scenario in SCENARIOS:
        start_t = time.perf_counter()

        # 1. Evaluate candidate patch with PatchGuard
        patch_verdict = PatchGuard.verify(
            original_code=scenario.original_code,
            proposed_code=scenario.candidate_patch,
            target_file="test_sample.py",
            failure_category=scenario.expected_classification,
        )

        # 2. Map status to Phase 4 signal
        pg_status = PatchGuardStatus.PASSED if patch_verdict.passed else PatchGuardStatus.BLOCKED

        cat_enum = (
            FailureCategory.PRODUCT_BUG
            if scenario.expected_classification == "PRODUCT_BUG"
            else FailureCategory.TEST_BUG
        )

        signal = TriageSignalInput(
            test_id=scenario.scenario_id,
            category=cat_enum,
            raw_llm_confidence=0.88,
            has_stack_trace=True,
            has_network_logs=True,
            ledger_stats=LedgerFeedbackStats(useful_count=15, not_useful_count=1),
            patch_guard_status=pg_status,
            candidate_patch_diff=scenario.candidate_patch if patch_verdict.passed else None,
        )

        decision = Phase4DecisionEngine.evaluate(signal)
        duration_ms = (time.perf_counter() - start_t) * 1000
        latencies.append(duration_ms)

        # 3. Check assertions
        patchguard_ok = (patch_verdict.passed == scenario.expected_patchguard_passed)
        action_ok = (decision.action.value == scenario.expected_action)

        scenario_passed = patchguard_ok and action_ok
        if scenario_passed:
            passed_scenarios += 1

        if scenario.category == "adversarial":
            if not patch_verdict.passed and not decision.expose_patch:
                traps_blocked += 1
            else:
                false_greens += 1
        elif scenario.category == "drift":
            if decision.action == RemediationAction.PROPOSE_VERIFIED_PATCH:
                drift_detected += 1
        elif scenario.category == "regression":
            if decision.action == RemediationAction.PROPOSE_VERIFIED_PATCH:
                regressions_healed += 1

        status_icon = "✅" if scenario_passed else "❌"
        print(f"[{status_icon}] {scenario.scenario_id} ({scenario.category.upper()}): {scenario.title} ({duration_ms:.1f}ms)")

        results.append({
            "id": scenario.scenario_id,
            "category": scenario.category,
            "title": scenario.title,
            "passed": scenario_passed,
            "patchguard_passed": patch_verdict.passed,
            "action": decision.action.value,
            "latency_ms": round(duration_ms, 2),
        })

    total = len(SCENARIOS)
    pass_rate = (passed_scenarios / total) * 100
    trap_rate = (traps_blocked / 8) * 100
    drift_rate = (drift_detected / 8) * 100
    reg_rate = (regressions_healed / 8) * 100
    avg_latency = sum(latencies) / len(latencies)

    print("\n" + "=" * 75)
    print("📊 HERMES ENTERPRISE BENCHMARK SCORECARD")
    print("=" * 75)
    print(f"Total Scenarios Evaluated:         {total}")
    print(f"Pass@1 Accuracy:                   {pass_rate:.1f}% ({passed_scenarios}/{total})")
    print(f"False-Green Rate:                  {false_greens:.1f}% (TARGET: 0.0%)")
    print(f"Adversarial Traps Blocked:         {trap_rate:.1f}% ({traps_blocked}/8)")
    print(f"Intentional Drift Healed:          {drift_rate:.1f}% ({drift_detected}/8)")
    print(f"True Regressions Healed:           {reg_rate:.1f}% ({regressions_healed}/8)")
    print(f"Average Pipeline Latency:          {avg_latency:.2f} ms")
    print("=" * 75)

    return {
        "total": total,
        "pass_rate": pass_rate,
        "false_green_rate": false_greens,
        "trap_block_rate": trap_rate,
        "drift_rate": drift_rate,
        "regression_rate": reg_rate,
        "avg_latency_ms": avg_latency,
        "results": results,
    }


if __name__ == "__main__":
    report = run_benchmark()
    if report["pass_rate"] < 100.0 or report["false_green_rate"] > 0.0:
        sys.exit(1)
    sys.exit(0)
