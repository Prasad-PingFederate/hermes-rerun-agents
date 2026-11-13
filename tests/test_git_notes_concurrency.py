"""
Optimistic Concurrency & CRDT Deep Merge Tests for GitNotesStateBackend
Owner: ScrumMasterOrchestrator & SprintStateStore
Phase: Phase 2 (v1.1.0) Deliverable 2
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hermes.orchestration.sprint_state_store import GitNotesStateBackend


class TestGitNotesConcurrency(unittest.TestCase):
    """Verifies CRDT-style deep merge and optimistic retry for GitNotesStateBackend."""

    def test_deep_merge_consecutive_green_runs_max_rule(self):
        """Matrix shards with differing streak counts must merge to max()."""
        base_state = {
            "version": "1.0",
            "timestamp": 1000.0,
            "consecutive_green_runs": 14,
        }
        incoming_state = {
            "version": "1.0",
            "timestamp": 1010.0,
            "consecutive_green_runs": 28,
        }
        merged = GitNotesStateBackend.deep_merge_states(base_state, incoming_state)
        self.assertEqual(merged["consecutive_green_runs"], 28)
        self.assertEqual(merged["timestamp"], 1010.0)

    def test_deep_merge_per_test_green_run_streaks(self):
        """Per-test green run streak dictionaries must merge taking max per test ID."""
        base_state = {
            "consecutive_green_runs": {
                "tests/test_auth.py::test_login": 45,
                "tests/test_cart.py::test_checkout": 12,
            }
        }
        incoming_state = {
            "consecutive_green_runs": {
                "tests/test_auth.py::test_login": 48,
                "tests/test_billing.py::test_invoice": 3,
            }
        }
        merged = GitNotesStateBackend.deep_merge_states(base_state, incoming_state)
        self.assertEqual(merged["consecutive_green_runs"]["tests/test_auth.py::test_login"], 48)
        self.assertEqual(merged["consecutive_green_runs"]["tests/test_cart.py::test_checkout"], 12)
        self.assertEqual(merged["consecutive_green_runs"]["tests/test_billing.py::test_invoice"], 3)

    def test_deep_merge_quarantined_tests_union(self):
        """Quarantine records across matrix shards must be unioned without dropping any."""
        base_state = {
            "quarantined_tests": [
                {"test_id": "test_flaky_a", "ttl_days": 14, "owner": "@dev1"},
            ]
        }
        incoming_state = {
            "quarantined_tests": [
                {"test_id": "test_flaky_b", "ttl_days": 14, "owner": "@dev2"},
            ]
        }
        merged = GitNotesStateBackend.deep_merge_states(base_state, incoming_state)
        test_ids = {q["test_id"] for q in merged["quarantined_tests"]}
        self.assertEqual(test_ids, {"test_flaky_a", "test_flaky_b"})

    def test_deep_merge_finops_ledger_run_aggregation(self):
        """FinOps token/cost entries must combine by run_id without duplicate counting."""
        base_state = {
            "finops_ledger": {
                "run_shard_1": {"tokens": 1200, "cost_usd": 0.04},
                "run_shared": {"tokens": 500, "cost_usd": 0.01},
            }
        }
        incoming_state = {
            "finops_ledger": {
                "run_shard_2": {"tokens": 1800, "cost_usd": 0.06},
                "run_shared": {"tokens": 300, "cost_usd": 0.01},
            }
        }
        merged = GitNotesStateBackend.deep_merge_states(base_state, incoming_state)
        self.assertEqual(merged["finops_ledger"]["run_shard_1"]["tokens"], 1200)
        self.assertEqual(merged["finops_ledger"]["run_shard_2"]["tokens"], 1800)
        # Shared run aggregates tokens & cost
        self.assertEqual(merged["finops_ledger"]["run_shared"]["tokens"], 800)
        self.assertAlmostEqual(merged["finops_ledger"]["run_shared"]["cost_usd"], 0.02)

    def test_deep_merge_snapshots_and_attempts_append_only(self):
        """Snapshots and attempt records must be deduplicated append-only collections."""
        base_state = {
            "snapshots": [{"snapshot_id": "snap_1", "sha": "aaa"}],
            "attempts": [{"attempt_id": "att_1", "status": "REJECTED"}],
        }
        incoming_state = {
            "snapshots": [
                {"snapshot_id": "snap_1", "sha": "aaa"},
                {"snapshot_id": "snap_2", "sha": "bbb"},
            ],
            "attempts": [
                {"attempt_id": "att_2", "status": "APPROVED"},
            ],
        }
        merged = GitNotesStateBackend.deep_merge_states(base_state, incoming_state)
        self.assertEqual(len(merged["snapshots"]), 2)
        self.assertEqual(len(merged["attempts"]), 2)
        self.assertEqual({s["snapshot_id"] for s in merged["snapshots"]}, {"snap_1", "snap_2"})
        self.assertEqual({a["attempt_id"] for a in merged["attempts"]}, {"att_1", "att_2"})

    @patch("subprocess.run")
    def test_push_state_with_retry_conflict_and_merge(self, mock_run):
        """Simulate push conflict (exit code 1), successful fetch & merge, then successful retry push."""
        # 1. export_state_to_git_notes -> returncode 0
        # 2. git push -> returncode 1 (conflict)
        # 3. git fetch -> returncode 0
        # 4. import_state_from_git_notes -> returncode 0 (shows remote note)
        # 5. export_state_to_git_notes -> returncode 0
        # 6. git push -> returncode 0 (success)

        import json

        remote_json = json.dumps({
            "version": "1.0",
            "consecutive_green_runs": 10,
            "quarantined_tests": [{"test_id": "test_remote"}],
        })

        mock_results = [
            MagicMock(returncode=0),                                   # notes add
            MagicMock(returncode=1, stderr="non-fast-forward"),        # push fail
            MagicMock(returncode=0),                                   # fetch ok
            MagicMock(returncode=0, stdout=remote_json),               # notes show remote
            MagicMock(returncode=0),                                   # notes add merged
            MagicMock(returncode=0),                                   # retry push ok
        ]
        mock_run.side_effect = mock_results

        local_state = {
            "version": "1.0",
            "consecutive_green_runs": 15,
            "quarantined_tests": [{"test_id": "test_local"}],
        }

        success = GitNotesStateBackend.push_state_with_retry(
            repo_root="/dummy/repo",
            state_data=local_state,
            max_retries=3,
            base_backoff=0.001,
        )
        self.assertTrue(success)
