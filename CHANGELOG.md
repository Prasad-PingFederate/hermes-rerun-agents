# Changelog

All notable changes to the Hermes Autonomous Test Healer & Shadow Mode platform are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-11-13

### 🛡️ Architectural Hardening, Dual-Tree Drift Elimination & Platform Audit Release

#### Architectural Hardening (Phase 2 Deliverables)
- **Single Source of Truth in `src/hermes/` & Zero-Drift Root Shims**: Migrated canonical logic exclusively under `src/hermes/`, replacing all 19 root `.py` modules with thin backwards-compatibility re-export shims. Backed by `tests/test_packaging_integrity.py` enforcing 0 duplicate `ast.ClassDef` nodes and verified module identity.
- **Git Notes Optimistic Concurrency Control (`src/hermes/orchestration/sprint_state_store.py`)**: Implemented CRDT deep state merging (`deep_merge_states`) resolving concurrent matrix runner write conflicts, paired with jittered exponential backoff retry (`push_state_with_retry`) ensuring zero state overwrites.
- **Sub-Second Virtualenv Caching in `action.yml`**: Integrated GitHub Action caching (`actions/cache@v4`) keyed by OS and dependency hashes (`requirements.txt`, `pyproject.toml`), reducing GitHub Action bootstrap overhead from ~25s to sub-second cache restoration.
- **Untrusted Fork PR Security Guardrails (`src/hermes/guards/write_gate_controller.py`, `src/hermes/execution/sandbox_executor.py`)**: Automatic untrusted fork detection down-scoping permissions to read-only `SHADOW_SUGGEST` and hard-blocking any privileged subprocess or command execution on external PRs.
- **Rootless Containerization & SLSA Provenance**: Multi-stage minimal rootless `Dockerfile` running as unprivileged UID 10001 with pre-cached wheels, plus automated SLSA build provenance attestation in `.github/workflows/ci.yml`.

#### Truth-in-Engineering Platform Capability Verification
- **Multi-Format Ingestion**: Ingests JUnit XML, CTRF JSON, and Playwright `trace.zip` archives with deterministic 5xx forensic overrides (`core/ingest/artifact_loader.py`).
- **Cross-Shard Failure Clustering**: Collapses 40 duplicate runner matrix shard failures into 1 atomic root cause ticket via regex noise stripping and SHA-256 cluster signatures (`core/scale/shard_clusterer.py`).
- **Commit & PR Intent Differentiation**: Inspects `git log -n 5` and webhook intent to classify intentional contract drift vs application regressions (`src/hermes/ingestion/ci_failure_ingestor.py`).
- **Multi-Language Zero Assertion Erosion**: AST guard enforcing zero net assertion deletions, blocking tautological replacements, skip injections, and semantic dilutions across Python, TypeScript, Java, Go (`t.Skip()`, error checks), and C# (`[Ignore]`, `Assert.AreEqual`).
- **Comprehensive Verification Suite**: 310 unit/integration tests passing (100%), 24/24 enterprise benchmark scenarios passing, 7/7 Playwright console E2E tests passing, and 198/198 Python 3.10 syntax-clean files.

---

## [1.0.0] - 2026-11-12

### 🚀 Enterprise B2B SaaS Release ("The Autonomous Scrum & Governance Engine")

#### Phase 1: Core Accuracy Upgrades (Commit & PR Intent Classification)
- **Commit & PR Intent Classifier (`agents/ci_detective.py`)**: Ingests `git log -n 5` headers and PR webhook payloads (with graceful fallback for shallow `fetch-depth: 1` clones) to deterministically classify failures into `PRODUCT_BUG`, `TEST_BUG`, `FLAKY_TEST`, or `ENVIRONMENT_NOISE`.
- **Deterministic Delta-SAST Gate (`security_blast_radius.py`)**: Zero-dependency static analyzer mapping AST checks against high-confidence OWASP/CWE antipatterns across Python and JS/TS (CWE-78, CWE-89, CWE-79, CWE-798, CWE-22, CWE-208). Scans AST deltas to prevent legacy false-positive blocking.
- **Multi-Runner Zero Assertion Erosion Guard (`core/governance/assertion_erosion_guard.py`)**: Multi-language AST validator enforcing that test assertions never decrease and strictly forbidding `.skip` / `.todo` modifiers across Pytest, Playwright, and Jest.

#### Phase 2: The Enterprise Wedge (Shadow Mode & Flake Quarantine)
- **Zero-Write Shadow Mode (`core/shadow_mode/`)**: 14-day zero-write enterprise trial mode. Posts 1-click in-diff `suggestion` comments when failing spans overlap modified PR hunks; gracefully falls back to collapsible out-of-diff unified diff comments to prevent GitHub HTTP 422 errors. Idempotent tracking marker (`<!-- hermes-shadow-heal -->`).
- **Executive ROI & MTTR Telemetry (`core/telemetry/`)**: Real-time engineering cost savings and MTTR compression calculator backed by historical sprint ledgers. Integrated into the Tester Console with interactive formula audit drawers.
- **Flake Quarantine PR Bot (`core/quarantine/`)**: Automatically synthesizes non-erosive retry quarantine patches (`@pytest.mark.flaky`, `test.describe.configure({ retries: 2 })`, `jest.retryTimes(2)`) and opens structured draft PRs with Flake Diagnostic Evidence tables.

#### Phase 3: Commercial Architecture & 60-Second Packaging
- **CISO Security Architecture Whitepaper (`docs/SECURITY_ARCHITECTURE.md`)**: Comprehensive 11-section enterprise security specification detailing ephemeral git worktree isolation, SHA-256 state snapshots, BYOK zero-retention topologies, and SOC 2 / ISO 27001 / FedRAMP compliance mappings.
- **60-Second GitHub Action Packaging (`action.yml`, `scripts/hermes_action_runner.py`)**: Composite action for GitHub Marketplace supporting `mode: 'shadow'` and `mode: 'heal'`, with step outputs for `sarif-file`, `hours_saved`, and `dollar_roi`.

#### Phase 4: Zero False-Green Verification
- **Counterfactual Differential Verification (`core/verification/counterfactual_verifier.py`)**: Dual-step ephemeral sandbox runner that verifies candidate test heals pass on PR HEAD and **fail** against broken baseline code, proactively catching vacuous tests.
- **Semantic Assertion Weakening Guard AST v2 (`core/verification/semantic_assertion_guard.py`)**: Assertion specificity scoring blocking value dilution (`assert x == 200` $\to$ `assert x is not None`), exception broadening (`pytest.raises(PermissionError)` $\to$ `pytest.raises(Exception)`), and test timeout inflation.
- **Accessibility-First Locator Guard (`core/verification/accessibility_locator_guard.py`)**: Rejects brittle structural pseudo-classes (`:nth-child`, deep tag combinators, XPath, hashed CSS) in favor of semantic accessible locators (`getByRole`, `getByLabel`, `getByTestId`).

#### Phase 5: InfoSec, DLP & FinOps Controls
- **Deterministic DLP Scrubber (`core/security/dlp_scrubber.py`)**: Specificity-ordered in-memory tokenization of PEM blocks, connection URIs, JWTs, cloud keys, Bearer headers, and emails. Enforces referential consistency (`<HERMES_JWT_1>`) and rejects hallucinated placeholders.
- **Policy-as-Code & FinOps Engine (`core/governance/policy_engine.py`)**: Canonicalizes paths to prevent traversal bypasses (`../`), enforces `no_heal_zones` (`src/auth/**` $\to$ `TRIAGE_ONLY`), resolves multi-file touches via Most-Restrictive-Wins, and enforces FinOps circuit breakers (`FINOPS_CIRCUIT_OPEN`).
- **Prompt-Injection Isolation (`core/security/prompt_sandbox.py`)**: Cryptographic nonce boundaries (`<untrusted_ci_data_{nonce}>`) with tag collision neutralization and exfiltration diff checks.
- **Cloud OIDC Provider (`core/llm/oidc_provider.py`)**: Discovers ambient Workload Identity tokens across AWS Bedrock, Azure OpenAI, Google Vertex AI, and air-gapped VPCs; forbids static API keys when `require_oidc: true`.

#### Phase 6: Monorepo Scale & Ecosystem Depth
- **Cross-Shard Failure Clustering (`core/scale/shard_clusterer.py`)**: Strips volatile runtime noise (ephemeral ports, hex addresses, timestamps, PIDs, runner paths) and computes SHA-256 cluster signatures to collapse 40 duplicate matrix shard failures into 1 atomic suggestion.
- **Issue-Tracker Context Hydration (`core/context/ticket_hydrator.py`)**: Extracts Jira/Linear/GitHub issue keys while denylisting technical standards (`UTF-8`, `SHA-256`, `CVE-2026-1111`), piping external ticket summaries through DLP and nonce sandboxing with GHES URL support.
- **Flake Lifecycle Reaper (`core/hygiene/flake_reaper.py`)**: Structured cross-runner quarantine stamps, 14-day TTL escalation alerts, and automated surgical unquarantine PR generation after 50 consecutive green runs on attempt #1.
- **Strict SARIF v2.1.0 & OpenTelemetry (`core/audit/`)**: Schema-compliant GitHub Code Scanning reports with cryptographic SHA-256 audit digests, and zero-dependency OTLP/HTTP JSON exporter for Datadog / Grafana Cloud.

