# 🕰️ Hermes Time Machine + 🤖 Rerun Autonomous AI Agents

> **Production-Grade Autonomous Bug Detection, Multimodal Self-Healing & Time Machine Rollback Safety Platform**

[![Tests](https://img.shields.io/badge/tests-7%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)]()

An open-source platform uniting **[Rerun](https://rerun.build)** (agent task orchestration and supervisor UI) with **Hermes Time Machine** (transactional snapshotting, visual regression diagnosis, and zero-risk rollback engine) powered by **Google Gemini Flash (Free Tier)** and local **Ollama** models.

---

## 🎯 The Core Problem & Solution

* **The Problem with Autonomous AI Agents**: When AI agents are given freedom to write code, edit tests, or execute terminal commands, they can introduce silent regressions, syntax breakages, line-ending corruption, or infinite retry loops.
* **The Hermes + Rerun Solution**: 
  1. **Rerun** manages the AI agents, schedules tasks (CI triage, daily regression monitoring, auto-remediation), and handles human-in-the-loop approvals.
  2. **Hermes Time Machine** creates automatic git snapshots before every agent tool call. If an attempted fix fails or regresses the codebase, Hermes executes an instant, safe rollback (`/tm restore <snapshot_id>`). It also creates a "safety snapshot before rollback" so even rollbacks are reversible.
  3. **Gemini Flash (Free Tier)** provides multimodal vision to analyze failure screenshots, DOM states, and network traces at near-zero cost.

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
│   2. Execute Test in Isolated Sandbox Runner                           │
│   3. Gemini Flash / Ollama Multimodal Root Cause Diagnosis             │
│   4. Apply Agent Remediation Patch in Isolated Sandbox                 │
│   5. Re-run Verification Suite                                         │
│   6. Auto-Rollback on Regression OR Promote Verified Checkpoint T1     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
hermes-rerun-agents/
├── core/
│   ├── time_machine/
│   │   ├── engine.py              # Snapshot manager, surgical restore & rollback safety
│   ├── healer/
│   │   ├── gemini_flash.py        # Gemini Flash multimodal vision & Ollama LLM diagnostician
│   ├── rerun_bridge/
│   │   ├── orchestrator.py        # Task queue, status lifecycle & human approval gates
│   └── sandbox/
│       ├── runner.py              # Isolated subprocess execution with timeout & screenshot capture
├── agents/
│   ├── breakglass_responder_healer.py # Domain skill: Stage QR-expired preview handshake recovery
│   ├── ci_detective.py            # CI triage, log parser & parallel job isolation router
│   └── test_healer_agent.py       # Full Try → Diagnose → Verify → Rollback pipeline
├── demo/
│   └── simulate_stage_breakglass_heal.py # End-to-end simulation of Stage failure detection & heal
├── scripts/
│   └── syntax_guard.py            # Preflight Python 3.10 syntax compatibility checker
├── tests/
│   └── test_platform.py           # Unit and integration test suite
├── server.py                      # FastAPI server for GitHub Actions webhooks & manual triggers
├── requirements.txt               # Package dependencies
├── .env.example                   # Environment configuration template
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

### 2. Configure API Keys
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Set your free **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Run the Test Suite & Syntax Guard
```powershell
python -m unittest tests/test_platform.py -v
python scripts/syntax_guard.py
```

### 4. Run the End-to-End Simulation Demo
Demonstrates the agent detecting a simulated Stage preview failure, healing it, verifying it passes 100%, and demonstrating a clean safety rollback:
```powershell
python demo/simulate_stage_breakglass_heal.py
```

### 5. Start the Webhook Server
```powershell
python server.py
```
API endpoints available at `http://localhost:8000`:
* `POST /api/webhook/github-actions` - Webhook receiver for CI failure events
* `POST /api/heal` - Trigger healing on a test file
* `GET /api/tasks` - List tasks and pending human approvals
* `POST /api/tasks/{task_id}/approve` - Approve proposed code fix
* `POST /api/tasks/{task_id}/rollback` - Reject and roll back workspace
* `GET /api/time-machine/snapshots` - Query snapshots in ledger

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
3. **Autonomous Patch Applied**:
   * Auto-detects `"QR Expired"` and triggers an automatic single reload.
   * Adds direct canonical fallback:
     ```python
     elif owner_user_id:
         reg_target = f"{BASE_URL}/register?type=responder&userId={owner_user_id}"
         resp_page.evaluate("(target) => sessionStorage.setItem('responderSignupCallback', target)", resp_page.url)
         resp_page.goto(reg_target, wait_until="domcontentloaded")
     ```
4. **Verification**:
   Re-executes test in the sandbox harness $\rightarrow$ **100% Passed**.
5. **Safety**:
   If the patch had failed or introduced a syntax error, Hermes would have instantly rolled back to the pristine baseline snapshot.
