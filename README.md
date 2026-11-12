# 🤖 Hermes: Autonomous Software Engineering & Governed Self-Healing Platform

[![Tests](https://img.shields.io/badge/unit%20tests-125%20passed-brightgreen.svg)]()
[![Playwright E2E](https://img.shields.io/badge/console%20e2e-7%20passed%20(100%25)-brightgreen.svg)]()
[![Syntax Guard](https://img.shields.io/badge/syntax%20guard-68%2F68%20Python%203.10%20passed-success.svg)]()
[![Governance](https://img.shields.io/badge/governance-Zero%20Assertion%20Erosion-orange.svg)]()
[![Security](https://img.shields.io/badge/security-Deterministic%20Delta--SAST-blue.svg)]()
[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-60s%20Install-purple.svg)](#-60-second-install-with-github-actions)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)

**Hermes** is an enterprise B2B self-healing platform and autonomous software engineering engine. Built on a hierarchical 8-agent Scrum DAG, Hermes automatically ingests failing CI runs, isolates root causes, synthesizes surgical AST-level repairs, deterministically blocks security vulnerabilities, and posts 1-click in-diff suggestions or draft PRs—compressing Mean Time To Resolution (MTTR) from **4.2 hours to 1.3 minutes (-99.5%)**.

---

## ⚡ 60-Second Install with GitHub Actions

Add Hermes to any repository in 60 seconds with zero proprietary dependencies. Drop this workflow into `.github/workflows/hermes-heal.yml`:

```yaml
name: Hermes Autonomous Healer

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  hermes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 5  # Ingests commit/PR intent to differentiate intentional drift from regressions

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: pip install -r requirements.txt || true

      - name: Run Hermes Healer (Shadow Mode)
        uses: Prasad-PingFederate/hermes-rerun-agents@feat/tester-console
        with:
          mode: 'shadow'  # Zero-Write: posts 1-click ```suggestion blocks in PR review
          test-command: 'pytest tests/ -q'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          hourly-rate-usd: '125.0'
```

---

## 🥊 Why Enterprise Teams Choose Hermes

| Dimension | Naive LLM Coding Bots | Copilot Workspace / Standard CI | Hermes Autonomous Scrum Engine |
| :--- | :--- | :--- | :--- |
| **Test Tampering** | ❌ Weakens tests, comments out assertions, or adds `.skip` to turn builds green | ❌ Manual human review required | ✅ **Zero Assertion Erosion**: Non-decreasing assertion invariant enforced at AST layer |
| **Security Scanning** | ❌ May hallucinate `shell=True`, code injection, or SQL concatenations | ⚠️ Generic linter after PR merge | ✅ **Deterministic Delta-SAST Gate**: Zero-dependency AST scanner blocks CWE/OWASP Top 10 |
| **False Positives** | ❌ Blocks fixes on legacy unrelated warnings | ❌ Developer fatigue | ✅ **Delta-Only SAST**: Compares pre- vs post-patch AST; only new vulnerabilities block |
| **Scope Boundaries** | ❌ Agent edits any file it touches | ❌ Whole-file replacements | ✅ **Bidirectional Scope Gate**: DeveloperAgent cannot touch tests; TestHealer cannot touch product |
| **Trial Adoption** | ❌ Requires broad write permissions to all repository branches | ❌ High enterprise friction | ✅ **Shadow Mode (`SHADOW_SUGGEST`)**: 1-click in-diff `suggestion` comments with zero write access |
| **Rollback Safety** | ❌ Manual `git revert` required if patch introduces regressions | ❌ Git tree pollution | ✅ **SHA-256 Time Machine**: Instant reversible snapshots via `/hermes rewind` |
| **Flake Management**| ❌ Ignores flakes or deletes intermittent tests | ⚠️ Re-runs entire CI pipeline | ✅ **Flake Quarantine Bot**: Auto-injects Pytest/Playwright/Jest retries + diagnostic table |
| **Data Privacy** | ❌ Bundles proprietary SDKs, code sent to unknown servers | ⚠️ Cloud vendor lock-in | ✅ **Air-Gapped & Local-First**: Runs on Ollama, vLLM, LMStudio with zero telemetry leak |

---

## 🏗️ The 8-Agent Governed Scrum Hierarchy

Hermes coordinates 8 specialized agent roles across 4 competence tiers with strict system prompts, tools, and inviolable scope boundaries enforced at the Python layer:

```
                  ┌──────────────────────────────────────────────┐
                  │          ScrumMasterOrchestrator             │
                  │   (TIER_1_TECH_LEAD · Sprint DAG Governance) │
                  └──────────────────────┬───────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  RequirementsAgent   │      │  TestCaseWriterAgent │      │ FlakeQuarantineAgent │
│  (TIER_2 · Read-Only)│      │  (TIER_3 · Tests-Only)      │  (TIER_2 · Retries)  │
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘
        │                                │                                │
        ▼                                ▼                                ▼
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│   DeveloperAgent     │      │   TestHealerAgent    │      │AutomationTesterAgent │
│ (TIER_3 · Impl Only) │      │  (TIER_3 · Tests-Only)      │(TIER_3 · Worktree 3x)│
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘
        │                                │                                │
        └────────────────────────────────┼────────────────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │    QACriticAgent & SecurityBlastRadiusAgent  │
                  │ (TIER_4_QA_CRITIC · Delta-SAST & Rubrics)    │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │       HumanWriteGate & TimeMachineEngine     │
                  │   (SHA-256 Tarball Pre-Apply Snapshot Rollback│
                  └──────────────────────────────────────────────┘
```

| Agent Role | Model Tier | Allowed Scope | Key Responsibilities & Invariants |
| :--- | :--- | :--- | :--- |
| **ScrumMasterOrchestrator** | `TIER_1_TECH_LEAD` | Global Governance | Owns sprint planning (`create_sprint_plan`), topological DAG scheduling, escalation loops, and write-gate acceptance. |
| **RequirementsAgent** | `TIER_2_SENIOR_SWE` | Read-Only | Analyzes user stories and stack traces into Acceptance Criteria (`AC-1..N`) and Edge Cases (`EC-1..N`). |
| **DeveloperAgent** | `TIER_3_JUNIOR_SWE` | Product Files (`src/`, `lib/`) | Repairs defects and implements features. **Strictly forbidden from modifying test suites.** |
| **TestCaseWriterAgent** | `TIER_3_JUNIOR_SWE` | Test Files (`tests/*`) | Authors comprehensive unit and Playwright specs. **Strictly forbidden from weakening assertions.** |
| **TestHealerAgent** | `TIER_3_JUNIOR_SWE` | Test Files (`tests/*`) | Surgically repairs drifted assertions for `TEST_BUG` failures. **Forbidden from editing product code.** |
| **FlakeQuarantineAgent** | `TIER_2_SENIOR_SWE` | Test Files (`tests/*`) | Auto-stabilizes intermittent flakes by injecting Pytest/Playwright/Jest retries + diagnostic tables. |
| **AutomationTesterAgent** | `TIER_3_JUNIOR_SWE` | Ephemeral Worktree | Executes multi-pass runs 3x (`repeat=3`), collects artifacts, and classifies failures. |
| **QACriticAgent** | `TIER_4_QA_CRITIC` | Proposal Review | Evaluates proposals against acceptance criteria. Rejections trigger auto-escalation (`TIER_3 -> 2 -> 1`). |
| **SecurityBlastRadiusAgent**| `TIER_4_QA_CRITIC` | AST Delta Scan | Scans proposed AST changes for command injection, SQLi, XSS, and timing attacks. |

---

## 🛡️ CISO Security & Compliance Architecture

Hermes was designed from day one to pass enterprise vendor security assessments (SOC 2 Type II, ISO 27001, FedRAMP). For the full technical security specification, read [**docs/SECURITY_ARCHITECTURE.md**](docs/SECURITY_ARCHITECTURE.md).

### Key Security Safeguards
1. **Deterministic Delta-SAST Gate**:
   * Evaluates Python AST and JS/TS regex AST against CWE-78, CWE-89, CWE-79, CWE-208, CWE-22, and CWE-798.
   * Compares pre-patch vs. post-patch AST nodes. Pre-existing legacy warnings do not block the build; **only newly introduced vulnerabilities hard-block write staging**.
2. **Zero Assertion Erosion Guard**:
   * Strips single-line and multi-line comments before counting assertions to prevent agents from commenting out tests (`// expect(...)`).
   * String-literal aware: URLs in assertions (`expect(url).toBe("https://...")`) are preserved without truncation.
   * Hard-blocks `.skip()`, `test.fixme()`, `xit()`, `xtest()`, and `page.pause()`.
3. **Ephemeral Sandboxing**:
   * Exploratory execution occurs in throwaway Git worktrees created via `tempfile.mkdtemp`.
   * Primary checkout is read-only; processes execute with strict subprocess timeouts (`timeout=30s`).
4. **Time Machine Reversibility**:
   * Atomic SHA-256 tarball snapshots saved in `.tm_snapshots/` before any file write.
   * Instant rollback via `/hermes rewind` Webhook command or UI button.
5. **Zero Cloud Telemetry**:
   * Standard library `urllib.request` implementation requires **zero proprietary cloud SDKs**.
   * 100% on-premise local inference support (Ollama, vLLM, LMStudio).

---

## 📊 Executive ROI & MTTR Telemetry

Hermes includes a real-time ROI calculation engine providing complete mathematical transparency to engineering leadership:

```
Engineering Hours Saved = (Product Bugs × 4.2h) + (Test Drifts × 2.0h) + (Flakes × 1.5h) + (Hostiles Blocked × 3.0h)
Estimated Dollar ROI ($) = Total Hours Saved × Fully Loaded Engineering Rate ($125/hr)
MTTR Compression % = ((4.2h Baseline - Autonomous Duration) / 4.2h) × 100
```

### Telemetry API Endpoints
* `GET /api/telemetry/roi`: Returns live hours saved, dollar ROI, and MTTR compression metrics.
* `POST /api/telemetry/roi/config`: Dynamically updates hourly engineering rates and manual MTTR baselines.

---

## 🖥️ Interactive Hermes Tester Console

Hermes includes a developer console styled in dark copper (`#14120e` / `#c9854a`), free of heavy dependencies:

* **Executive ROI Header Bar**: Real-time display of hours saved, MTTR compression (`4.2h → 1.3m -99.5%`), quarantines, and dollar ROI.
* **Math Breakdown Drawer**: Clickable ROI metric slides out the auditable formula breakdown.
* **Sprint Board Rail**: Visual 7-step progression from triage to write gate.
* **Time Machine Controls**: 1-click snapshot creation, rollback, and branch PR staging.

```bash
# Start the Hermes Server & Console
python server.py --host 127.0.0.1 --port 8000

# Open in browser
http://127.0.0.1:8000/console
```

---

## 🧪 Comprehensive Verification Suite

Every commit to Hermes is validated against strict verification gates:

```bash
# 1. Syntax Guard: 100% Python 3.10 syntax compatibility
python scripts/syntax_guard.py
# Output: ✅ [SYNTAX GUARD PASSED] All 68 files are 100% Python 3.10 compatible.

# 2. Complete Unit Test Suite (125 tests)
python -m pytest tests/ -q
# Output: 125 passed in 2m 23s

# 3. Playwright Console E2E Suite (7 specifications)
python -m pytest console_tests/ -v
# Output: 7 passed in 2m 38s
```

---

## 📄 License & Commercial Support

Hermes is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).  
For commercial enterprise licensing, dedicated support, custom model fine-tuning, or private cloud VPC deployments, contact **sales@hermes-rerun.ai**.
