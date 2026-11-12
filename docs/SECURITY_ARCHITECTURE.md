# 🛡️ Hermes Autonomous Software Engineering Platform: CISO Security Architecture & Compliance Specification

**Document Version**: 2.4.0  
**Target Audience**: Chief Information Security Officers (CISOs), Application Security (AppSec) Teams, Compliance Auditors (SOC 2, ISO 27001, FedRAMP).  
**Platform Owner**: ScrumMasterOrchestrator & SecurityBlastRadiusAgent, TIER_1 / TIER_4  
**Classification**: Public Enterprise Technical Specification  

---

## 1. Executive Summary & Security Model

Hermes is an enterprise-grade autonomous software engineering and self-healing engine. Unlike naive LLM code-generation scripts that execute unconstrained bash commands or indiscriminately rewrite codebases, Hermes is engineered around **Deterministic Zero-Trust Governance**:

1. **Strict Bidirectional Scope Isolation**: Developer agents cannot modify test suites to "fake" green builds; test healer agents cannot modify application logic.
2. **Deterministic Delta-SAST Gate**: Static AST analysis evaluates every code modification before write-staging—blocking OWASP Top 10 and CWE antipatterns at the syntax layer with zero false-positive blocking of legacy code.
3. **Multi-Runner Zero Assertion Erosion**: Mathematical proof ($assertions_{post} \ge assertions_{pre}$) ensuring tests are never weakened, skipped, or deleted.
4. **Ephemeral Sandboxing**: Autonomous execution and multi-pass testing run strictly inside isolated Git worktrees—never in-place on the primary branch or deployment workspace.
5. **SHA-256 Time Machine Invariant**: Atomic, reversible tarball snapshots generated before every mutation, enabling instantaneous deterministic rollback via `/hermes rewind`.
6. **Air-Gapped & Local-First LLM Architecture**: Operates via standard library HTTP with zero vendor SDKs, full support for on-premise local inference (Ollama, vLLM, LMStudio), and **zero telemetry or code-training egress**.

---

## 2. Threat Model & Defense-in-Depth Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │      Untrusted Incoming CI Test Failure      │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │  CIDetectiveAgent (Intent & Shallow Fallback)│
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
             [ Intentional API Change ]              [ Unintended Regression ]
                        │                                     │
                        ▼                                     ▼
                TEST_BUG Route                        PRODUCT_BUG Route
              (Scope: tests/* only)               (Scope: src/*, lib/* only)
                        │                                     │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │     Ephemeral Git Worktree Sandbox (3x)      │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │   Deterministic Delta-SAST Security Gate     │
                    │   (Python AST + JS/TS Scanner: SEC-001..005) │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │        Zero Assertion Erosion Guard          │
                    │  (Comment-Aware Non-Decreasing Assertions)   │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │        Human Write Gate + Time Machine       │
                    │    (SHA-256 Tarball Pre-Apply Snapshot)      │
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
              SHADOW_SUGGEST Mode                      DRAFT_PR Mode
           (In-Diff / Out-of-Diff)              (Gated Human Approval)
```

---

## 3. Sandboxing & Workspace Isolation

### 3.1 Ephemeral Git Worktrees
All exploratory execution, candidate patching, and multi-pass regression testing (`repeat=3`) take place in ephemeral Git worktrees created under temporary directories (`tempfile.mkdtemp`):
* The primary repository checkout is mounted **read-only** to worker agents.
* If a candidate patch produces crashes, hanging infinite loops, or disk writes, the ephemeral worktree is wiped instantly (`rmtree`) without affecting the working directory.
* Workers run under non-root operating context with strict subprocess timeouts (`timeout=30s`).

### 3.2 Path Traversal & Symlink Defense (`SEC-PATH-001`)
All file reads, AST slices, and proposal submissions pass through `TimeMachineEngine._validate_safe_workspace_path`:
* Rejects path arguments starting with `-`, `..`, or leading slashes.
* Resolves canonical filesystem paths and strictly enforces `resolved_path.is_relative_to(workspace_root)`.
* Prohibits access to sensitive directories: `.git`, `.tm_snapshots`, `.rerun_tasks`, `.env*`.
* Prohibits symlink creation or traversal across workspace boundaries.

---

## 4. Deterministic Delta-SAST Security Gate

Enterprise codebases contain legacy technical debt and pre-existing linting warnings. Scanning entire files blocks critical fixes due to unrelated pre-existing issues. Hermes solves this with **Deterministic Delta-SAST**:

### 4.1 Delta Computation Algorithm
1. The scanner parses the AST of the pre-patch file and catalogs all existing security rules:
   $$\text{Findings}_{pre} = \{ (rule\_id, code\_snippet) \}$$
2. The scanner parses the proposed post-patch file:
   $$\text{Findings}_{post} = \{ (rule\_id, code\_snippet) \}$$
3. The delta is mathematically isolated:
   $$\Delta_{findings} = \text{Findings}_{post} \setminus \text{Findings}_{pre}$$
4. **Enforcement Policy**:
   * Legacy findings ($\text{Findings}_{pre}$) are preserved in `report.legacy_findings` for audit reporting and do **not** block the heal.
   * Any newly introduced finding ($\Delta_{findings}$) with severity `CRITICAL` or `HIGH` **hard-blocks the write gate**.

### 4.2 Security Ruleset Across Python & JavaScript / TypeScript

| Rule ID | Severity | Category | Antipattern Detected |
| :--- | :---: | :--- | :--- |
| `SEC-SUBPROCESS-001` | **CRITICAL** | CWE-78: Command Injection | `subprocess.run(..., shell=True)`, `os.system()`, `os.popen()` |
| `SEC-EVAL-001` | **CRITICAL** | CWE-95: Code Injection | `eval()`, `exec()`, `new Function(...)` |
| `SEC-SQLI-001` | **CRITICAL** | CWE-89: SQL Injection | Raw SQL query formatted via f-strings or string concatenation |
| `SEC-XSS-001` | **HIGH** | CWE-79: Cross-Site Scripting | React/JSX `dangerouslySetInnerHTML`, innerHTML assignment |
| `SEC-TIMING-001` | **HIGH** | CWE-208: Timing Side-Channel | Variable-time secret comparison (`==`) instead of `hmac.compare_digest` |
| `SEC-SECRET-001` | **HIGH** | CWE-798: Hardcoded Secrets | High-entropy string literals matching API key, AWS, or JWT token patterns |
| `SEC-PATH-001` | **HIGH** | CWE-22: Path Traversal | Directory traversal (`../`) or absolute path injection |

---

## 5. Zero Assertion Erosion & Test Integrity

A common failure mode of autonomous coding bots is "cheating": modifying a test assertion (`assert True`), commenting out assertions, or adding skip decorators (`@pytest.mark.skip`) so tests appear green.

Hermes eliminates this via `ZeroAssertionErosionGuard` & `PlaywrightASTGuard`:

### 5.1 Invariants Enforced
1. **Non-Decreasing Assertion Counts**:
   $$N_{assertions}(Proposed) \ge N_{assertions}(Original)$$
2. **Comment-Aware Token Parsing**:
   Single-line (`//`, `#`) and multi-line (`/* */`) comments are stripped prior to AST counting, catching attempts where agents comment out failing assertions (`// expect(res).toBe(200)`).
3. **URL & String Literal Preservation**:
   Regex comment strippers are string-literal aware; URLs like `"https://api.example.com"` inside quotes are never truncated.
4. **Prohibition of Test Suppression Modifiers**:
   Any patch adding the following tokens is rejected with an immediate write-gate block:
   * `@pytest.mark.skip`, `@pytest.mark.skipif`, `pytest.xfail`
   * `@unittest.skip`
   * `test.skip()`, `it.skip()`, `describe.skip()`, `test.fixme()`
   * `xit()`, `xtest()`, `xdescribe()`
   * `test.todo()`, `it.todo()`
   * `page.pause()` (CI hang trigger)
5. **Tautological Assertion Rejection**:
   Rejects dummy assertions designed to artificially inflate assertion counts:
   * `assert True`, `assert 1 == 1`, `assert 1`
   * `expect(true).toBe(true)`, `expect(1).toBe(1)`

---

## 6. Bidirectional Scope Gates (Role-Based Access Control)

Every agent ticket enforces strict filesystem read/write boundaries:

```text
┌─────────────────────────────────┬─────────────────────────────────┐
│     Product Code (src/, lib/)   │       Test Code (tests/*)       │
├─────────────────────────────────┼─────────────────────────────────┤
│ DeveloperAgent: WRITE           │ DeveloperAgent: STRICTLY BLOCKED│
│ TestHealerAgent: STRICTLY BLOCKED│ TestHealerAgent: WRITE         │
│ TestCaseWriterAgent: READ-ONLY  │ TestCaseWriterAgent: WRITE      │
│ RequirementsAgent: READ-ONLY    │ RequirementsAgent: READ-ONLY    │
└─────────────────────────────────┴─────────────────────────────────┘
```

If `DeveloperAgent` attempts to modify even a single character in `tests/`, or if `TestHealerAgent` attempts to modify production code, the proposal is rejected at the orchestrator boundary before sandbox staging.

---

## 7. SHA-256 Time Machine & Rollback Guarantees

Before any proposal is applied to the workspace, Hermes generates an immutable, reversible snapshot:
* **Snapshot Artifact**: Compressed `.tar.gz` archive stored under `.tm_snapshots/snap_<timestamp>_<sha256>`.
* **Manifest Verification**: The snapshot records SHA-256 hashes of all files, Git commit HEAD, and active branch state.
* **Deterministic Rollback**:
  * Can be triggered via Webhook command (`/hermes rewind`), Console button, or API (`POST /api/demo/{workspace_id}/rollback`).
  * Rollback completely restores the pre-apply file state, resets Git HEAD, and purges all untracked files generated during the sprint.

---

## 8. Data Privacy & Zero Cloud Egress

### 8.1 Zero External SDK Dependencies
Hermes is implemented entirely with Python standard library networking (`urllib.request`). It does not bundle proprietary SDKs, tracking pixels, or third-party analytics telemetry.

### 8.2 Air-Gapped & On-Premise Operation
* **Local Inference**: Hermes fully supports locally hosted open-source weights via Ollama, vLLM, LMStudio, and TGI (`HERMES_LLM_PROVIDER=ollama`).
* **Zero Egress Compliance**: In local mode, zero bytes of source code or failure context leave the organization's perimeter network.
* **Air-Gapped CI**: Operates inside disconnected CI/CD runner environments using `LocalHeuristicEngine` or local endpoints.

---

## 9. Compliance Mapping: SOC 2, ISO 27001 & FedRAMP

| Compliance Standard | Control Reference | Hermes Implementation Mechanism |
| :--- | :--- | :--- |
| **SOC 2 Type II** | CC6.1 (Logical Access) | Role-Based Scope Gates prevent agents from modifying out-of-scope modules. |
| **SOC 2 Type II** | CC6.8 (Malicious Code Prevention) | Deterministic Delta-SAST Gate stops injection of OWASP Top 10 vulnerabilities. |
| **SOC 2 Type II** | CC7.2 (Infrastructure Monitoring) | Immutable append-only audit trail (`sprint_audit.jsonl`) records all actions. |
| **SOC 2 Type II** | CC8.1 (Change Management) | Human Write Gate and SHA-256 Time Machine ensure changes are approved & reversible. |
| **ISO 27001:2022** | A.8.28 (Secure Coding) | Delta-SAST verifies constant-time crypto, SQL parameterization, safe subprocesses. |
| **ISO 27001:2022** | A.8.31 (Separation of Environments) | Ephemeral Git worktree sandboxing guarantees multi-pass test isolation. |
| **FedRAMP Low/Mod** | CM-3 (Configuration Change Control) | Reversible snapshots and cryptographic commit verification. |

---

*For technical security questions or to schedule an architectural review, contact the Hermes Security Council.*
