"""
Tests for E2E Healing Playbook Enhancements in Hermes Multi-Agent Orchestrator.

Validates:
1. DOMLocatorForensicsExtractor:
   - Backend Error ID extraction ([Error ID: 9405-XK0R])
   - Toast message capture (Toasts seen after submit: ['...'])
   - GraphQL operation detection (AssignSubscriber, UpdateCommunitySharedModules)
   - Playwright strict mode violation extraction
2. FrontendCompanionInspector:
   - Companion repo discovery (subdirectories and sibling repos)
   - Component form input extraction
   - Formatting of companion forensic hints for LLM prompt
3. CIDetectiveAgent.sync_upstream_repository and CLI --sync-git argument parsing
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes.agents.ci_detective import CIDetectiveAgent
from hermes.cli import build_parser
from hermes.ingestion.ci_failure_ingestor import CIFailureIngestor, DOMLocatorForensicsExtractor
from hermes.ingestion.frontend_companion_inspector import FrontendCompanionInspector


class TestPlaybookEnhancements(unittest.TestCase):
    """Verifies that Hermes incorporates the E2E healing playbook features."""

    def test_dom_locator_forensics_backend_error_ids_and_toasts(self):
        """Verifies extraction of Error IDs, toasts, GraphQL mutations, and strict-mode violations."""
        failure_log = (
            "AssertionError: Expected the community access wizard to confirm publication for "
            "'PublishComm_1794807841', but no success toast appeared. "
            "Toasts seen after submit: ['ErrorSomething went wrong [Error ID: 9405-XK0R]', 'Something went wrong [Error ID: 9405-XK0R]']. "
            "GraphQL operation: mutation AssignSubscriber { id }\n"
            "strict mode violation: locator('.dashboard-cards') resolved to 8 elements"
        )
        hints = DOMLocatorForensicsExtractor.extract(failure_log)

        # Check backend Error IDs
        self.assertIn("9405-XK0R", hints.backend_error_ids)

        # Check toast capture
        self.assertTrue(any("ErrorSomething went wrong" in t for t in hints.toast_messages))

        # Check GraphQL operation
        self.assertIn("AssignSubscriber", hints.graphql_operations)

        # Check strict mode violation
        self.assertIsNotNone(hints.strict_mode_violations)
        self.assertIn("resolved to 8 elements", hints.strict_mode_violations)

        prompt_str = hints.to_prompt_str()
        self.assertIn("Backend Rejection Error IDs: 9405-XK0R", prompt_str)
        self.assertIn("Domain Guidance:", prompt_str)
        self.assertIn("Playwright Strict-Mode Violation:", prompt_str)

    def test_ci_failure_ingestor_generates_playbook_acceptance_criteria(self):
        """Verifies CIFailureIngestor creates domain-specific ACs for Error IDs and strict mode."""
        failure_text = (
            "def test_foo():\n"
            "    E   AssertionError: Error [Error ID: 1670-NKVP]\n"
            "    strict mode violation: locator('button') resolved to 3 elements\n"
        )
        with tempfile.TemporaryDirectory() as td:
            ingestor = CIFailureIngestor(workspace_root=Path(td))
            res = ingestor.ingest_failure_output(failure_text)

            acs = res.get("acceptance_criteria", [])
            # Must generate AC for backend Error ID
            self.assertTrue(any("1670-NKVP" in ac and "directive" in ac.lower() for ac in acs))
            # Must generate AC for strict-mode violation
            self.assertTrue(any("strict-mode" in ac.lower() and ".first" in ac for ac in acs))

    def test_frontend_companion_inspector_input_extraction(self):
        """Verifies extracting JSX/TSX form inputs and directives from component code."""
        component_code = """
        import React from 'react';
        export const CommunityStepThree = () => {
            return (
                <div>
                    <h5>Select Directives</h5>
                    <input type="radio" name="directiveOption" id="directive-alive" />
                    <input type="checkbox" data-testid="member-agree-checkbox" />
                    <textarea id="notes" placeholder="Notes" />
                    <button type="submit" className="custom-btn">Submit</button>
                </div>
            );
        };
        """
        inputs = FrontendCompanionInspector._extract_inputs(component_code)
        self.assertIn("[data-testid='member-agree-checkbox']", inputs)
        self.assertIn("#directive-alive", inputs)
        self.assertIn("input[name='directiveOption']", inputs)

    def test_frontend_companion_inspector_discovery_and_hints(self):
        """Verifies companion repo discovery and hint formatting."""
        with tempfile.TemporaryDirectory() as parent_dir:
            p_dir = Path(parent_dir)
            ws = p_dir / "automation_suite"
            ws.mkdir()

            companion = p_dir / "b4igo-frontend-predev"
            src_dir = companion / "src" / "features"
            src_dir.mkdir(parents=True)
            (src_dir / "CommunityStepThree.tsx").write_text(
                "export const CommunityStepThree = () => <div><h5>Select Directives</h5><input type='radio' id='opt1' /></div>;",
                encoding="utf-8",
            )

            discovered = FrontendCompanionInspector.discover_companion_repos(ws)
            self.assertIn(companion.resolve(), [d.resolve() for d in discovered])

            hints = FrontendCompanionInspector.build_companion_hints(ws, "Error in Select Directives wizard")
            self.assertIn("Frontend Companion Repository Forensics", hints)
            self.assertIn("CommunityStepThree.tsx", hints)
            self.assertIn("directive", hints.lower())

    def test_ci_detective_sync_upstream_repository(self):
        """Verifies sync_upstream_repository detects non-git or git workspace gracefully."""
        with tempfile.TemporaryDirectory() as td:
            res = CIDetectiveAgent.sync_upstream_repository(Path(td))
            self.assertFalse(res["synced"])
            self.assertEqual(res["branch"], "unknown")

    def test_cli_sync_git_parser_argument(self):
        """Verifies --sync-git flag is accepted by both run and heal CLI subcommands."""
        parser = build_parser()

        args_heal = parser.parse_args(["heal", "--sync-git"])
        self.assertTrue(getattr(args_heal, "sync_git", False))

        args_run = parser.parse_args(["run", "--story", "Feature", "--sync-git"])
        self.assertTrue(getattr(args_run, "sync_git", False))


if __name__ == "__main__":
    unittest.main()
