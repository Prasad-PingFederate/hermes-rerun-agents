# GitHub Marketplace Listing Copy: Hermes Autonomous Healer

**Product Name**: Hermes: Autonomous CI Self-Healing & Flake Quarantine  
**Primary Category**: Continuous Integration  
**Secondary Category**: Code Quality & Security  
**Pricing Tier**: $100 / developer / month *(14-day Zero-Write Free Trial in Shadow Mode)*

---

## ⚡ 1-Line Description (Tagline)
Autonomous, governed AI engineering: detects CI test failures, proves heals with Counterfactual Differential Verification, and posts 1-click in-diff review suggestions.

---

## 🛡️ Enterprise Feature Highlights

- **Zero-Write Shadow Mode (`SHADOW_SUGGEST`)**: Install in 60 seconds with zero write permissions. Hermes analyzes CI failures and posts 1-click multi-line Markdown ` ```suggestion ```` blocks directly in your GitHub PR review comments.
- **Zero Assertion Erosion Guarantee**: Multi-language AST invariants (Pytest, Playwright, Jest) strictly guarantee that assertions never decrease and no `.skip` / `.todo` modifiers are introduced.
- **Counterfactual Differential Verification**: Proves test heals pass on PR HEAD and **fail** against broken baseline code, proactively catching vacuous tests.
- **Deterministic Delta-SAST Gate**: Zero-dependency static analyzer checks patches against OWASP Top 10 / CWE rules (CWE-78, CWE-89, CWE-79, CWE-798) before code ever reaches human review.
- **Pre-LLM Reversible DLP Scrubber**: In-memory tokenization replaces JWTs, connection strings, emails, and cloud keys with `<HERMES_JWT_1>` before sending logs to LLMs.
- **Cross-Shard Failure Clustering**: Strips volatile runtime noise and collapses 40 parallel runner shard failures into 1 root-cause investigation.
- **Flake Lifecycle Reaper**: Isolates intermittent failures with non-erosive retry wrappers and automatically opens surgical unquarantine PRs after 50 consecutive green runs.
- **Zero-Static-Key Cloud OIDC**: Native Workload Identity federation for AWS Bedrock, Azure OpenAI, Google Vertex AI, and air-gapped private VPC gateways.
- **Native GitHub Code Scanning SARIF**: Emits strict SARIF v2.1.0 reports with cryptographic SHA-256 chain digests.

---

## 🚀 60-Second Drop-In Quickstart

Add `.github/workflows/hermes.yml` to your repository:

```yaml
name: Hermes Autonomous Healer

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  id-token: write
  security-events: write

jobs:
  hermes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 5

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Run Hermes Healer (Shadow Mode)
        id: hermes
        uses: Prasad-PingFederate/hermes-rerun-agents@v1
        with:
          mode: 'shadow'
          test-command: 'pytest tests/ -q'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          hourly-rate-usd: '125.0'

      - name: Upload SARIF Audit Report to GitHub Code Scanning
        if: always() && steps.hermes.outputs.sarif-file != ''
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: ${{ steps.hermes.outputs.sarif-file }}
```

---

## 💼 Enterprise Plans

| Tier | Price | Features |
| :--- | :--- | :--- |
| **Shadow Mode Trial** | **Free (14 Days)** | Zero-write in-diff PR review suggestions, Executive ROI telemetry, Delta-SAST scanning |
| **Team** | **$49 / dev / mo** | Autonomous Draft PR healing, Flake Quarantine Bot, Multi-Runner AST guards |
| **Enterprise SaaS** | **$100 / dev / mo** | Cloud OIDC (AWS Bedrock / Azure / Vertex), Policy-as-Code (`.hermes.yml`), Cross-Shard Clustering, SARIF & OTel audit exports, dedicated SLA |
| **Air-Gapped / VPC** | **Custom** | Self-hosted runner deployment, BYOM (vLLM / Ollama), zero external telemetry egress |

