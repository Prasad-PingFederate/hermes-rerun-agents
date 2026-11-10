# 🕰️ Hermes Time Machine + 🤖 Rerun Autonomous AI Agents

> **Autonomous AI Coworkers with Deterministic Time-Travel Safety & Self-Healing**

An open-source platform uniting **[Rerun](https://rerun.build)** (agent task orchestration and supervisor UI) with **Hermes Time Machine** (transactional snapshotting, visual regression diagnosis, and zero-risk rollback engine) powered by **Google Gemini Flash (Free Tier)**.

---

## 🎯 The Core Problem & Solution

* **The Problem with Autonomous AI Agents**: When AI agents are given freedom to write code, edit tests, or execute terminal commands, they can introduce silent regressions, syntax breakages, line-ending corruption, or infinite retry loops.
* **The Hermes + Rerun Solution**: 
  1. **Rerun** manages the AI agents, schedules tasks (CI triage, daily regression monitoring, auto-remediation), and handles human-in-the-loop approvals.
  2. **Hermes Time Machine** creates automatic git snapshots before every agent tool call. If an attempted fix fails or regresses the codebase, Hermes executes an instant, safe rollback (`/tm restore <snapshot_id>`).
  3. **Gemini Flash (Free Tier)** provides multimodal vision to analyze failure screenshots, DOM states, and network traces at near-zero cost.

---

## 🏗️ System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                 Rerun Supervisor & Web UI                   │
│   (Task Scheduling, Webhook Triggers, Human Approval Card)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Dispatches Task
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Hermes Sandbox Controller                   │
│   1. Snapshot Baseline T0 (.tm_snapshots)                   │
│   2. Execute Test / Capture Failure Context                 │
│   3. Gemini Flash Multimodal Root Cause Diagnosis           │
│   4. Apply Agent Remediation Patch in Isolated Sandbox      │
│   5. Re-run Verification Suite                              │
│   6. Auto-Rollback on Regression OR Promote Checkpoint      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
hermes-rerun-agents/
├── core/
│   ├── time_machine/       # Snapshotting, rollback engine, git ledger
│   ├── healer/             # Gemini Flash multimodal diagnosis & diff healer
│   ├── rerun_bridge/       # Rerun agent supervisor, task queue, webhook listener
│   └── sandbox/            # Isolated test execution harness
├── agents/                 # Specialized agent definitions (CI Detective, Playwright Healer)
├── tests/                  # Unit and integration test suite
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variables template
└── README.md               # Project guide and architecture documentation
```

---

## 🚀 Quickstart

### 1. Set Up Python Environment
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
Add your free **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Run the Unit Tests
```powershell
python -m unittest tests/test_platform.py -v
```

---

## 🗺️ Building Roadmap

1. [x] **Repository & Architecture Foundation**: Dedicated repository, directory structure, requirements, and environment templates.
2. [x] **Core Time Machine Engine**: Snapshot manager, patch store, and rollback engine with zero risk.
3. [x] **Gemini Flash Failure Healer**: Multimodal screenshot + code diff failure diagnosis engine.
4. [x] **Rerun Agent Bridge**: Task queue, status transitions, and human approval gates.
5. [x] **Autonomous Test Healer Agent**: Try $\rightarrow$ verify $\rightarrow$ rollback on regression pipeline.
6. [ ] **FastAPI Webhook Server**: GitHub Actions webhook receiver for real-time CI triaging.
