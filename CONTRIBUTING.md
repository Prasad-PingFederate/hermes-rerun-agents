# Contributing to Hermes

Thank you for your interest in contributing to **Hermes**! We welcome contributions to our autonomous self-healing and governed software engineering platform.

To maintain enterprise-grade reliability, safety, and deterministic behavior, please review the following guidelines before submitting issues or pull requests.

---

## 🏛️ Architecture & Package Layout

Hermes follows a strict **Single Source of Truth** architecture:

```
hermes-rerun-agents/
├── src/hermes/                     # Canonical Package Source (Single Source of Truth)
│   ├── agents/                     # Specialized reasoning agents (CIDetective, TestHealerAgent, etc.)
│   ├── core/                       # Core engine (TimeMachine, events, LLM, verification)
│   ├── console/                    # Tester Console FastAPI backend, WebSocket/SSE & HTML UI
│   ├── execution/                  # Execution harnesses (SandboxExecutor, DockerSandbox, patch applier)
│   ├── guards/                     # Security & safety guards (diff review gate, AST, SAST, write gate)
│   ├── ingestion/                  # Artifact ingestion (JUnit, CTRF, Playwright traces, context slicer)
│   └── orchestration/              # Sprint scheduling, AutofixThread, DAG & state persistence
├── core/                           # Backwards-compatibility import shim -> src/hermes/core/
├── agents/                         # Backwards-compatibility import shim -> src/hermes/agents/
├── *.py (19 root modules)          # Root compatibility import shims (hermes_cli.py, server.py, etc.)
├── tests/                          # 361 unit tests covering all gates, shims, and pipelines
├── console_tests/                  # 7 Playwright browser E2E test specifications
├── evals/                          # 24 enterprise benchmark evaluation scenarios
└── scripts/                        # Automated CI validation utilities (syntax_guard.py, etc.)
```

> [!IMPORTANT]
> **Single Source of Truth Invariant**:
> - All new features, bug fixes, and logic **must be placed exclusively under `src/hermes/`**.
> - Files in the root directory (such as `hermes_cli.py`, `scrum_master_orchestrator.py`, `write_gate_controller.py`) and root directories `core/` and `agents/` are **pure backwards-compatibility import shims**. Never add business logic, new class definitions, or standalone functions to root shims.
> - This rule is continuously checked by `tests/test_packaging_integrity.py` and `scripts/syntax_guard.py`.

---

## 🛠️ Development Setup

### Prerequisites
- Python **3.10** or higher (tested across 3.10, 3.11, 3.12, 3.13)
- Git CLI
- (Optional for Playwright console tests) Node.js >= 18 and Playwright

### Installation
Clone the repository and install dependencies in editable mode:

```bash
git clone https://github.com/Prasad-PingFederate/hermes-rerun-agents.git
cd hermes-rerun-agents

# Create and activate virtual environment
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies and dev packages
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
```

---

## 🔒 Safety & Governance Invariants

All contributions must strictly adhere to Hermes's core safety invariants:

1. **Zero Assertion Erosion**:
   - Test fixes must never "heal" a failure by deleting an assertion, weakening strict comparison (`===` -> `!= null`), or wrapping assertions in dead branches (`if False:`).
   - Never inject `@pytest.mark.skip`, `pytest.xfail`, `test.skip()`, or timeout inflation.
   - The AST patch guard (`src/hermes/guards/ast_patch_guard.py`) will automatically block non-compliant patches.

2. **OpenQodex-Style Diff Review Gate**:
   - Patches are evaluated by the diff review gate (`src/hermes/guards/diff_review_gate.py`) before write application.
   - Any confirmed major finding results in a `BLOCKED` status and halts the apply.

3. **Deterministic Verification (No Network in Unit Tests)**:
   - Unit tests under `tests/` must be 100% deterministic and make **zero live network calls** (no live Ollama, OpenAI, Gemini, or Claude API calls).
   - Use mock adapters (`LocalHeuristicEngine` or `MagicMock`) for all LLM tests.

4. **Python 3.10 Compatibility**:
   - Ensure complete Python 3.10 backwards compatibility.
   - **Never put backslashes inside f-string expressions `{...}`** (which syntax-errors on Python 3.10/3.11). Use `.replace()` or string concatenation outside the expression.

---

## 🧪 Verification & Test Suite

Before opening a pull request, run the full verification suite locally:

```bash
# 1. Run the Python 3.10 Syntax Guard & Shim Validator
python scripts/syntax_guard.py

# 2. Run the Full Unit Test Suite (361 tests)
python -m pytest tests/ -q

# 3. Verify Packaging Integrity
python -m pytest tests/test_packaging_integrity.py -v

# 4. Verify Hermes Doctor CLI
python -m hermes.cli doctor

# 5. (Optional) Run Playwright Console E2E Tests
python -m pytest console_tests/ -v

# 6. (Optional) Run Enterprise Benchmark Evals
python evals/run_benchmarks.py
```

All 361 unit tests and 214 syntax files must pass cleanly.

---

## 📬 Pull Request Workflow

1. **Create a Topic Branch**:
   ```bash
   git checkout -b feat/your-feature-name
   # or for bug fixes:
   git checkout -b fix/issue-description
   ```

2. **Commit with Conventional Commit Format**:
   - `feat(scope): ...` for new capabilities
   - `fix(scope): ...` for bug fixes
   - `docs(scope): ...` for documentation updates
   - `test(scope): ...` for testing enhancements

3. **Verify CI Workflows**:
   - Ensure the `CI Suite` (matrix across Python 3.10, 3.11, 3.12, 3.13 and OSes) passes.
   - Ensure `Hermes Autonomous Healer` passes.

---

## 📄 License

By contributing to Hermes, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
