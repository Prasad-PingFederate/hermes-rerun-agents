# Hermes 14-Day Enterprise Proof-of-Value (POV) Playbook

**Objective**: Guide prospective enterprise engineering organizations from initial Zero-Write trial to verified CISO procurement and production deployment within 14 business days.

---

## 📅 The 14-Day Milestone Timeline

```
Day 1 ──────────► Day 3 ──────────► Day 7 ──────────► Day 10 ─────────► Day 14
Zero-Write        Baseline MTTR     Flake Quarantine  CISO Policy      Executive ROI
Shadow Deploy     Calibration       Audit & FinOps    Hardening        Readout & Deal
```

---

### Phase 1: Days 1–3 — Zero-Write Shadow Deployment & Baseline Calibration

#### Objectives:
- Install Hermes in under 60 seconds with **zero write permissions** to production code branches.
- Ingest live CI failures across test suites (Pytest, Playwright, Jest).

#### Step-by-Step Actions:
1. **Add Hermes Shadow Workflow**:
   Add `.github/workflows/hermes-shadow.yml` configured in `mode: 'shadow'`.
2. **Configure Zero-Write GitHub Permissions**:
   ```yaml
   permissions:
     contents: read         # Zero write access to repository source
     pull-requests: write   # Allows posting in-diff 1-click review suggestions
   ```
3. **Audit First 10 CI Failures**:
   - Verify that `CIDetectiveAgent` correctly categorizes `TEST_BUG` vs `PRODUCT_BUG`.
   - Inspect the in-diff Markdown ` ```suggestion ```` blocks posted on active PRs.

---

### Phase 2: Days 4–7 — Flake Quarantine Audit & FinOps Validation

#### Objectives:
- Identify intermittent and flaky tests without human investigation time.
- Verify that LLM spend stays strictly capped under FinOps limits.

#### Step-by-Step Actions:
1. **Review Flake Quarantine PRs**:
   - Inspect draft PRs staged by `FlakeQuarantineAgent` with structured Flake Evidence tables.
   - Verify the presence of `# hermes:quarantine(date=..., ttl=14d)` metadata stamps.
2. **Verify FinOps Circuit Breaker**:
   - Add `.hermes.yml` with conservative budget caps:
     ```yaml
     finops:
       max_tokens_per_pr: 25000
       max_usd_per_pr: 5.00
       max_usd_per_day: 25.00
     ```
   - Verify that runaway multi-test failures trip `FINOPS_CIRCUIT_OPEN` and degrade cleanly to deterministic triage without failing CI builds.

---

### Phase 3: Days 8–10 — CISO Policy Hardening & Workload Identity Federation

#### Objectives:
- Clear InfoSec review by demonstrating zero static API key storage and zero customer code retention.

#### Step-by-Step Actions:
1. **Enable Workload Identity Federation (Cloud OIDC)**:
   - Configure AWS Bedrock, Azure OpenAI, or Google Vertex AI via GitHub Actions OIDC:
     ```yaml
     permissions:
       id-token: write  # Enables ambient OIDC without long-lived secrets
     ```
2. **Enforce Protected No-Heal Zones**:
   - Update `.hermes.yml` to seal sensitive modules:
     ```yaml
     governance:
       no_heal_zones:
         - "src/auth/**"
         - "src/billing/**"
         - "src/crypto/**"
       require_oidc: true
     ```
   - Verify that test failures touching `src/auth/` automatically force `TRIAGE_ONLY`.

---

### Phase 4: Days 11–14 — Executive ROI Readout & Procurement Closing

#### Objectives:
- Present mathematical ROI proof to the VP of Engineering, Head of QA, and CISO.

#### Deliverables for Closing Meeting:
1. **Executive ROI Header Readout**:
   - **Engineering Hours Saved**: Total developer hours reclaimed across healed bugs, test drift, and triaged flakes.
   - **MTTR Compression**: Documented reduction in Mean-Time-To-Resolution (e.g. 4.2 hours manual triage $\to$ 1.3 minutes autonomous heal, **-99.5% MTTR**).
   - **Flaky Tests Quarantined**: High-frequency flaky tests isolated from master CI runs.
   - **Verified Dollar ROI**: Calculated based on customer hourly cost (default: \$125/hour).
2. **SARIF Code Scanning Compliance Report**:
   - Exported `hermes-report.sarif` uploaded to GitHub Security tab proving zero new CWE/OWASP vulnerabilities introduced.
3. **Flake Reaper Burn-Down**:
   - Stabilized tests auto-unquarantined after reaching 50 consecutive green runs on attempt #1.

---

*For POV support or tailored CISO security documentation, contact the Hermes Enterprise Solutions Team.*

