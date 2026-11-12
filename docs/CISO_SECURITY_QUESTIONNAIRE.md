# CISO & InfoSec Security Questionnaire (SIG Lite / CAIQ Fast-Sheet)

**Product Name**: Hermes Autonomous Test Healer & Shadow Mode Agent  
**Vendor**: Hermes Platform Engineering  
**Applicability**: Enterprise InfoSec, Vendor Risk Assessment (SIG Lite, CAIQ v4, VSAQ)

---

## 1. Data Protection & Model Training Governance

### Q1.1: Is customer source code or CI telemetry used to train or fine-tune public AI models?
> **NO.** Hermes strictly adheres to a **Zero-Training and Zero-Data-Retention policy**. Customer code, test files, and CI failure logs are processed ephemerally in-memory during active execution passes. No data is stored, cached, or utilized for foundation model training by Hermes or any downstream provider.

### Q1.2: Does Hermes require customer source code to leave our corporate Virtual Private Cloud (VPC)?
> **NO.** Hermes is designed for **In-VPC and On-Premises execution**. Customers can run Hermes entirely on self-hosted GitHub Actions runners or private Kubernetes clusters, paired with internal LLM gateways (vLLM, Ollama) or enterprise VPC endpoints (AWS Bedrock, Azure OpenAI private links).

### Q1.3: How does Hermes prevent sensitive credentials or PII from leaking into LLM prompts?
> Hermes embeds a **Deterministic Pre-LLM Data Loss Prevention (DLP) Scrubber** (`core/security/dlp_scrubber.py`). Before any diagnostic log or test snippet is transmitted to an LLM provider:
> 1. PEM private keys, database connection strings, JWTs (`eyJ...`), cloud API keys (`AKIA...`, `ghp_...`), Bearer headers, and emails are scrubbed.
> 2. Secrets are mapped to referentially consistent in-memory placeholders (e.g. `<HERMES_JWT_1>`).
> 3. Raw secrets remain strictly within customer runner memory and are never transmitted over the wire.

---

## 2. Authentication, Credential Architecture & Access Control

### Q2.1: Does Hermes require long-lived static API keys to be stored in GitHub Secrets?
> **NO.** Hermes natively supports **Zero-Static-Key Cloud OIDC (Workload Identity Federation)** across AWS Bedrock, Azure OpenAI, and Google Vertex AI. Authentication is granted dynamically via short-lived GitHub Actions OIDC tokens (`permissions: id-token: write`). 
> 
> Furthermore, security teams can enforce `governance.require_oidc: true` in `.hermes.yml` to hard-block the execution of any static API keys across regulated repositories.

### Q2.2: What GitHub repository permissions are required for Hermes?
> Hermes follows the **Principle of Least Privilege**:
> - **Shadow Mode (Trials & Sensitive Repositories)**: Operates with **zero write permissions** (`contents: read`, `pull-requests: write`). Hermes only posts in-diff Markdown ` ```suggestion ```` comments.
> - **Heal Mode (Automated Remediation)**: Operates on isolated draft feature branches (`hermes/heal-*`). Hermes **never commits directly to default branches (`main`/`master`)**.

### Q2.3: Can repository owners restrict Hermes from modifying sensitive business modules?
> **YES.** Through Policy-as-Code (`.hermes.yml`), security teams define **No-Heal Zones**:
> ```yaml
> governance:
>   no_heal_zones:
>     - "src/auth/**"
>     - "src/billing/**"
>     - "src/crypto/**"
> ```
> When any CI failure touches protected zones, Hermes automatically enforces `TRIAGE_ONLY` mode, preventing any automated code modification. All paths are canonicalized (`posixpath.normpath`) to prevent path traversal (`../`) bypasses.

---

## 3. Sandboxing, Isolation & Code Execution Safety

### Q3.1: Where and how does Hermes execute test suites to verify AI patches?
> Every test run executes inside an **ephemeral Git worktree sandbox** or isolated temporary directory. Pre- and post-execution states are snapshotted using SHA-256 cryptographic hashes. Untrusted candidate patches never share memory or filesystem state with host runners.

### Q3.2: How does Hermes guarantee that an AI patch does not weaken or delete test assertions?
> Hermes enforces the **Zero Assertion Erosion Invariant** at the Abstract Syntax Tree (AST) layer:
> 1. Multi-language AST guards (Pytest, Playwright, Jest) verify that assertion counts never decrease.
> 2. Test skipping modifiers (`@pytest.mark.skip`, `test.skip`, `it.skip`, `test.todo`) are hard-blocked.
> 3. **Semantic Assertion Weakening Guard (AST v2)** blocks matcher dilution (`toBe(200)` $\to$ `toBeTruthy()`), broad exception catches (`pytest.raises(Exception)`), and artificial timeout inflation.

### Q3.3: How does Hermes prevent "False-Green" vacuous test patches?
> Hermes executes **Counterfactual Differential Verification**:
> 1. **Forward Check**: Candidate test patch must PASS against PR HEAD.
> 2. **Counterfactual Check**: Retaining the candidate test patch, the underlying source files are temporarily reverted to the broken baseline. The test **must FAIL**.
> If the test passes against known-broken baseline code, it is rejected with `COUNTERFACTUAL_FAILED: Vacuous test detected`.

---

## 4. Static Application Security Testing (SAST) & Prompt Injection

### Q4.1: Does Hermes scan AI-generated code for security vulnerabilities before opening PRs?
> **YES.** Every proposed patch must clear the **Deterministic Delta-SAST Gate** (`security_blast_radius.py`). The static analyzer audits AST diffs against high-confidence OWASP Top 10 and CWE rules:
> - **CWE-78**: OS Command Injection (`subprocess(shell=True)`, `child_process.exec`)
> - **CWE-89**: SQL Injection (Unparameterized SQL string formatting)
> - **CWE-79**: Cross-Site Scripting (`dangerouslySetInnerHTML`)
> - **CWE-798**: Hardcoded Credentials & Cryptographic Keys
> - **CWE-22**: Path Traversal (`open()`, `fs.readFile`)
> - **CWE-208**: Timing-Unsafe Comparisons (`==` on HMAC/auth tokens)

### Q4.2: How does Hermes isolate untrusted DOM fixtures and CI logs from prompt injection?
> Hermes encapsulates all failure logs and DOM snapshots within **Cryptographically Random Nonce Boundaries** (`<untrusted_ci_data_{nonce}> ... </untrusted_ci_data_{nonce}>`). Any internal closing tags are neutralized, and mandatory post-block instruction anchors remind the model that enclosed content is inert diagnostic data with zero instruction or tool authority.

---

## 5. Auditing, Compliance & FinOps

### Q5.1: Does Hermes support native integration with GitHub Code Scanning?
> **YES.** Hermes emits strict **SARIF v2.1.0** reports (`hermes-report.sarif`) compliant with GitHub Code Scanning schema requirements. Every SARIF run includes a tamper-evident **SHA-256 Cryptographic Audit Digest** over the commit SHA, policy hash, diff hash, and security findings.

### Q5.2: How are FinOps spend and runaway token consumption controlled?
> Hermes enforces multi-layered **FinOps Circuit Breakers** configured in `.hermes.yml`:
> - Maximum tokens per pull request (`max_tokens_per_pr`)
> - Maximum dollar spend per pull request (`max_usd_per_pr`)
> - Daily spend cap across all repository CI runs (`max_usd_per_day`)
> When any limit is exceeded, Hermes emits `FINOPS_CIRCUIT_OPEN` and gracefully degrades to non-LLM triage without failing CI builds.

### Q5.3: Compliance Control Mapping Summary

| Compliance Standard | Relevant Controls | Hermes Implementation |
| :--- | :--- | :--- |
| **SOC 2 Type II** | CC6.1, CC6.6, CC6.8, CC8.1 | Role-based scope gates, Delta-SAST gate, SHA-256 Time Machine rollback snapshots |
| **ISO 27001:2022** | A.8.25, A.8.28, A.8.29, A.8.31 | Secure coding verification, ephemeral worktree sandboxing, least privilege access |
| **FedRAMP Moderate** | AC-3, CM-3, SC-7 | Zero static keys via OIDC, cryptographic commit digests, VPC boundary protection |

---

*For technical security questions or to schedule a CISO-to-CISO architectural deep dive, contact the Hermes Security Council.*

