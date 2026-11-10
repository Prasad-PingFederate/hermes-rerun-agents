# 🕰️ Hermes Time Machine + 🤖 Rerun Autonomous AI Agents

> **Production-Grade Autonomous Bug Detection, Multimodal Self-Healing & Time Machine Rollback Safety Platform**

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)

An open-source platform uniting **[Rerun](https://rerun.build)** task coordination patterns with **Hermes Time Machine** (deterministic snapshotting, visual regression diagnosis, and zero-risk rollback engine) powered by **Google Gemini Flash (Free Tier)** and local **Ollama** models.

> **Note on Rerun Orchestration**: By default, task state and human approval gates are managed locally via a lightweight, deterministic JSON-backed orchestrator stored in `.rerun_tasks/tasks.json`. External Rerun servers are only queried if `RERUN_SERVER_URL` is explicitly configured.

---

## 🎯 The Core Problem & Solution

* **The Problem with Autonomous AI Agents**: When AI agents are given freedom to write code, edit tests, or execute terminal commands, they can introduce silent regressions, syntax breakages, line-ending corruption, or infinite retry loops.
* **The Hermes + Rerun Solution**: 
  1. **Orchestrator & Human Write Gate**: Tasks advance through explicit states (`PENDING -> RUNNING -> AWAITING_APPROVAL -> COMPLETED / ROLLED_BACK`). **Patches are never written to the caller's working tree while a fix is only proposed.** Changes are tested strictly inside an isolated sandbox copy, holding for human approval before promotion.
  2. **Hermes Time Machine**: Deterministic, non-destructive file tree snapshots before every mutating action. Does not execute destructive `git reset --hard` or `git clean`. If an attempted fix fails or regresses the codebase, Hermes executes an instant, safe rollback (`/tm restore <snapshot_id>`), including an automated "rollback-of-a-rollback" safety snapshot.
  3. **Multimodal Failure Diagnosis**: Accepts screenshots, DOM state, traceback logs, and code context to diagnose root causes and propose minimal unified diffs via Google Gemini Flash (using direct REST API calls) or local Ollama models.

---

## 🏗️ System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Rerun Supervisor & Web UI                       │
│    (Task Scheduling, Webhook Triggers, Human Approval Review Card)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Dispatches Task
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Hermes Sandbox Controller                         │
│   1. Snapshot Baseline T0 (.tm_snapshots/ledger.json)                  │
│   2. Execute Test in Isolated Workspace Copy                           │
│   3. Gemini Flash / Ollama Multimodal Root Cause Diagnosis             │
│   4. Apply Agent Remediation Patch strictly in Isolated Sandbox        │
│   5. Re-run Verification Suite in Sandbox Copy                         │
│   6. On Success: Task -> AWAITING_APPROVAL (Caller Workspace Untouched)│
│   7. On Approval: Promote Verified Fix -> COMPLETED                   │
│   8. On Rejection: Rollback to Baseline T0 -> ROLLED_BACK              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
hermes-rerun-agents/
├── core/
│   ├── time_machine/
│   │   ├── engine.py              # Safe tree snapshots, surgical restore & rollback safety
│   ├── healer/
│   │   ├── gemini_flash.py        # Gemini Flash multimodal vision & Ollama diagnostician
│   ├── rerun_bridge/
│   │   ├── orchestrator.py        # Task queue, status lifecycle & human approval gates
│   └── sandbox/
│       ├── runner.py              # Isolated subprocess execution & temporary copy isolation
├── agents/
│   ├── breakglass_responder_healer.py # Domain skill: Stage QR-expired preview handshake recovery
│   ├── ci_detective.py            # CI triage, log parser & parallel job isolation router
│   └── test_healer_agent.py       # Full Try → Diagnose → Verify → Approval Write-Gate pipeline
├── demo/
│   └── simulate_stage_breakglass_heal.py # End-to-end simulation of Stage failure detection & heal
├── scripts/
│   └── syntax_guard.py            # Preflight Python 3.10 syntax compatibility checker
├── tests/
│   ├── fixtures/
│   │   ├── bad_py310_fstring.py.txt          # Fixture with illegal Py3.10 f-string backslash
│   │   └── gha_workflow_job_failure.json     # GitHub Actions workflow_job failure payload
│   └── test_platform.py           # Comprehensive unit and integration test suite
├── server.py                      # FastAPI server for GitHub Actions webhooks & manual triggers
├── requirements.txt               # Package dependencies (FastAPI, Uvicorn, Pydantic, Requests, Pytest)
├── .env.example                   # Environment configuration template
├── LICENSE                        # AGPL-3.0 License
└── README.md
```

---

## 🚀 Quickstart

### 1. Set Up Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure API Keys & Tokens
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Key configuration settings:
```env
# 1. AI Diagnostician
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash

# 2. Server & Security Gate
RERUN_SERVER_HOST=127.0.0.1
RERUN_SERVER_PORT=8000
HERMES_API_TOKEN=your_secure_token_here
WEBHOOK_SECRET=your_github_webhook_secret_here

# 3. Target Workspace (defaults to current working directory)
TARGET_WORKSPACE_PATH=.
```

### 3. Run the Test Suite & Syntax Guard
```powershell
python -m unittest tests/test_platform.py -v
python scripts/syntax_guard.py
```

### 4. Run the End-to-End Simulation Demo
Demonstrates the agent detecting a simulated Stage preview failure, healing it inside a sandbox copy, verifying the write-gate keeps caller code untouched until approval, promoting the fix on approval, and demonstrating a clean safety rollback:
```powershell
python demo/simulate_stage_breakglass_heal.py
```

### 5. Start the Webhook Server
```powershell
python server.py
```
API endpoints available at `http://127.0.0.1:8000`:
* `POST /api/webhook/github-actions` - Webhook receiver (verifies `X-Hub-Signature-256` HMAC SHA256)
* `POST /api/heal` - Trigger healing on a test file (requires `X-Hermes-Token`)
* `GET /api/tasks` - List tasks and pending human approvals (requires `X-Hermes-Token`)
* `POST /api/tasks/{task_id}/approve` - Human write gate: Promotes verified fix to workspace (requires `X-Hermes-Token`)
* `POST /api/tasks/{task_id}/rollback` - Human rejection: Restores workspace to baseline snapshot (requires `X-Hermes-Token`)
* `GET /api/time-machine/snapshots` - Query snapshots in ledger (requires `X-Hermes-Token`)

---

## 💡 Worked Example: Breakglass Responder Stage Healing

When a Playwright test encounters the Stage preview crypto handshake failure (`MedicalProfileInfoVc.tsx` timing out and displaying `"QR Expired – Emergency Profile"`, skipping the `<InfoNote>` component):

1. **Detection**:
   The agent detects the signature error:
   ```text
   AssertionError: Could not find the 'Click here' link on the Breakglass preview page...
   ```
2. **Analysis**:
   The agent identifies that the crypto verification timed out, preventing `<InfoNote>` from mounting.
3. **Autonomous Patch Applied in Sandbox Copy**:
   * Auto-detects `"QR Expired"` and triggers an automatic single reload.
   * Adds direct canonical fallback:
     ```python
     elif owner_user_id:
         reg_target = f"{BASE_URL}/register?type=responder&userId={owner_user_id}"
         resp_page.evaluate("(target) => sessionStorage.setItem('responderSignupCallback', target)", resp_page.url)
         resp_page.goto(reg_target, wait_until="domcontentloaded")
     ```
4. **Verification in Sandbox Copy**:
   Re-executes test in the isolated sandbox harness $\rightarrow$ **100% Passed**. Caller workspace is **untouched**.
5. **Approval Write Gate**:
   Human reviews the diff card in Rerun/API. Calling `approve_task` promotes the verified fix to the working tree.
6. **Safety Rollback**:
   If rejected, `rollback_task` guarantees the workspace reverts to the pristine baseline snapshot with zero damage.
