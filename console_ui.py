"""
Hermes Tester Console — UI Template & Client Logic (AG-1 through AG-6)
Dark editorial workstation interface served directly at GET /
Zero external CDN dependencies (100% offline, deterministic, pure HTML5/CSS/ES6).
"""

CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>Hermes // Tester Console</title>
  <style>
    :root {
      --bg-canvas: #090a0c;
      --bg-panel: #111316;
      --bg-card: #171a1e;
      --bg-card-hover: #1c2025;
      --border-subtle: #22262c;
      --border-muted: #2f353d;
      --border-focus: #4a5568;
      
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      
      --accent-red: #f43f5e;
      --accent-red-bg: rgba(244, 63, 94, 0.12);
      --accent-green: #10b981;
      --accent-green-bg: rgba(16, 185, 129, 0.12);
      --accent-amber: #f59e0b;
      --accent-amber-bg: rgba(245, 158, 11, 0.12);
      --accent-indigo: #6366f1;
      --accent-indigo-bg: rgba(99, 102, 241, 0.12);
      --accent-cyan: #06b6d4;
      --accent-cyan-bg: rgba(6, 182, 212, 0.12);

      --font-mono: ui-monospace, "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-canvas);
      color: var(--text-main);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      overflow-x: hidden;
      display: flex;
      flex-direction: column;
      height: 100vh;
      width: 100vw;
    }

    /* Top Bar */
    header.top-bar {
      height: 50px;
      background-color: var(--bg-panel);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      flex-shrink: 0;
      z-index: 10;
    }

    .brand-section {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-logo {
      font-family: var(--font-mono);
      font-weight: 800;
      font-size: 14px;
      letter-spacing: 0.1em;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .brand-logo span.badge-tag {
      font-size: 10px;
      font-weight: 600;
      background: var(--border-subtle);
      color: var(--text-muted);
      padding: 2px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .top-meta {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .meta-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 11px;
      font-family: var(--font-mono);
      border: 1px solid var(--border-subtle);
      background-color: var(--bg-card);
      color: var(--text-muted);
    }

    .meta-pill .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: var(--accent-green);
    }

    .meta-pill.status-red .dot { background-color: var(--accent-red); }
    .meta-pill.status-amber .dot { background-color: var(--accent-amber); }
    .meta-pill.status-green .dot { background-color: var(--accent-green); }

    .btn-top {
      background: var(--bg-card);
      border: 1px solid var(--border-muted);
      color: var(--text-main);
      padding: 5px 11px;
      font-size: 11px;
      font-family: var(--font-mono);
      border-radius: 4px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }

    .btn-top:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-focus);
    }

    /* Layout Body */
    .app-body {
      display: flex;
      flex: 1;
      height: calc(100vh - 50px);
      overflow: hidden;
    }

    /* Left Rail */
    aside.left-rail {
      width: 220px;
      background-color: var(--bg-panel);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      flex-shrink: 0;
    }

    .nav-list {
      list-style: none;
      padding: 12px 8px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 12px;
      border-radius: 4px;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 500;
      margin-bottom: 2px;
      transition: all 0.15s ease;
      user-select: none;
    }

    .nav-item:hover {
      background-color: var(--bg-card);
      color: var(--text-main);
    }

    .nav-item.active {
      background-color: var(--bg-card);
      color: #fff;
      font-weight: 600;
      border-left: 2px solid var(--accent-indigo);
    }

    .nav-item .nav-label {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .nav-kbd {
      font-size: 10px;
      font-family: var(--font-mono);
      background-color: var(--bg-canvas);
      border: 1px solid var(--border-subtle);
      padding: 1px 5px;
      border-radius: 3px;
      color: var(--text-dim);
    }

    .nav-badge {
      font-size: 10px;
      font-family: var(--font-mono);
      padding: 2px 6px;
      border-radius: 10px;
      font-weight: 700;
    }
    .nav-badge.red {
      background-color: var(--accent-red-bg);
      color: var(--accent-red);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }

    .rail-footer {
      padding: 14px;
      border-top: 1px solid var(--border-subtle);
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--text-dim);
      line-height: 1.6;
    }

    /* Main Content Area */
    main.main-viewport {
      flex: 1;
      overflow-y: auto;
      padding: 24px 32px;
      background-color: var(--bg-canvas);
    }

    .view-panel {
      display: none;
    }
    .view-panel.active {
      display: block;
    }

    /* Section Headers */
    .view-header {
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 12px;
    }

    .view-title-group h2 {
      font-size: 18px;
      font-weight: 700;
      color: #fff;
      letter-spacing: -0.01em;
    }

    .view-title-group p {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    /* Cards & Components */
    .inbox-grid {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .failure-card {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 18px;
      transition: border-color 0.15s;
    }

    .failure-card:hover {
      border-color: var(--border-muted);
    }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }

    .card-title-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .card-title {
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .card-badges {
      display: flex;
      gap: 6px;
      margin-top: 4px;
    }

    .tag {
      font-family: var(--font-mono);
      font-size: 10px;
      padding: 2px 7px;
      border-radius: 3px;
      font-weight: 600;
      letter-spacing: 0.03em;
    }
    .tag-product-bug {
      background-color: var(--accent-indigo-bg);
      color: #818cf8;
      border: 1px solid rgba(99, 102, 241, 0.4);
    }
    .tag-test-bug {
      background-color: var(--accent-cyan-bg);
      color: #22d3ee;
      border: 1px solid rgba(6, 182, 212, 0.4);
    }
    .tag-scope {
      background-color: var(--bg-card);
      color: var(--text-muted);
      border: 1px solid var(--border-muted);
    }
    .tag-status-red {
      background-color: var(--accent-red-bg);
      color: var(--accent-red);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }

    .code-snippet {
      background-color: #050607;
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 10px 12px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: #e2e8f0;
      overflow-x: auto;
      margin-bottom: 14px;
      line-height: 1.45;
    }

    .btn-action-primary {
      background: var(--accent-indigo);
      color: #fff;
      border: none;
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: opacity 0.15s;
    }
    .btn-action-primary:hover {
      opacity: 0.9;
    }
    .btn-action-primary:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .btn-action-success {
      background: var(--accent-green);
      color: #064e3b;
      font-weight: 700;
      border: none;
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: opacity 0.15s;
    }
    .btn-action-success:hover {
      opacity: 0.9;
    }
    .btn-action-success:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }

    .btn-action-rewind {
      background: var(--bg-card);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.4);
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }
    .btn-action-rewind:hover {
      background: rgba(245, 158, 11, 0.1);
    }
    .btn-action-rewind:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }

    /* Sprint Flow Timeline */
    .sprint-timeline {
      display: flex;
      flex-direction: column;
      gap: 12px;
      position: relative;
    }

    .agent-card {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .agent-card.active-step {
      border-color: var(--accent-indigo);
    }
    .agent-card.passed-step {
      border-color: var(--border-muted);
    }

    .agent-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .agent-name-role {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 700;
      color: #fff;
    }

    .agent-tier-badge {
      font-family: var(--font-mono);
      font-size: 9px;
      padding: 2px 6px;
      border-radius: 3px;
      background: var(--bg-card);
      border: 1px solid var(--border-muted);
      color: var(--text-muted);
    }

    .agent-body {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
    }

    .agent-scope-bar {
      display: flex;
      align-items: center;
      gap: 6px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-dim);
      padding-top: 6px;
      border-top: 1px solid var(--border-subtle);
    }

    /* Diff Reviewer */
    .diff-container {
      background-color: #07080a;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      overflow: hidden;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.45;
      margin-bottom: 20px;
    }

    .diff-header {
      background-color: var(--bg-panel);
      padding: 8px 14px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: var(--text-muted);
    }

    .diff-content {
      padding: 12px;
      overflow-x: auto;
      max-height: 480px;
      white-space: pre;
    }

    .diff-line-add {
      background-color: rgba(16, 185, 129, 0.12);
      color: #34d399;
      display: block;
      padding: 1px 4px;
    }
    .diff-line-del {
      background-color: rgba(244, 63, 94, 0.12);
      color: #fb7185;
      display: block;
      padding: 1px 4px;
    }
    .diff-line-info {
      color: var(--text-dim);
      display: block;
      padding: 1px 4px;
    }

    .approval-toolbar {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .form-row {
      display: flex;
      gap: 12px;
      align-items: center;
    }

    .form-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .form-label {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }

    .form-input {
      background-color: var(--bg-card);
      border: 1px solid var(--border-muted);
      color: var(--text-main);
      padding: 7px 10px;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 12px;
    }
    .form-input:focus {
      outline: none;
      border-color: var(--accent-indigo);
    }

    /* Audit Drawer */
    .audit-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(2px);
      z-index: 50;
    }
    .audit-overlay.open {
      display: block;
    }

    .audit-drawer {
      position: fixed;
      right: 0;
      top: 0;
      bottom: 0;
      width: 520px;
      max-width: 90vw;
      background-color: var(--bg-panel);
      border-left: 1px solid var(--border-muted);
      z-index: 60;
      display: flex;
      flex-direction: column;
      padding: 24px;
      transform: translateX(100%);
      transition: transform 0.25s ease;
    }
    .audit-overlay.open .audit-drawer {
      transform: translateX(0);
    }

    .drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .drawer-title {
      font-size: 16px;
      font-weight: 700;
      color: #fff;
    }

    .btn-close {
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 18px;
    }

    .audit-content {
      flex: 1;
      overflow-y: auto;
      font-family: var(--font-mono);
      font-size: 11px;
      line-height: 1.6;
      background-color: #050607;
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 12px;
      color: #cbd5e1;
      white-space: pre-wrap;
    }

    .drawer-footer {
      margin-top: 16px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    /* Empty states */
    .empty-state {
      background-color: var(--bg-panel);
      border: 1px dashed var(--border-muted);
      border-radius: 6px;
      padding: 40px;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
    }
    .empty-state h3 {
      font-size: 15px;
      color: #fff;
    }
    .empty-state p {
      font-size: 12px;
      color: var(--text-dim);
      max-width: 360px;
    }

    /* Mobile 390px responsive */
    @media (max-width: 640px) {
      .app-body {
        flex-direction: column;
      }
      aside.left-rail {
        width: 100%;
        height: auto;
        border-right: none;
        border-bottom: 1px solid var(--border-subtle);
      }
      .nav-list {
        display: flex;
        padding: 6px;
        overflow-x: auto;
      }
      .nav-item {
        padding: 6px 10px;
        font-size: 11px;
        margin-bottom: 0;
      }
      .rail-footer {
        display: none;
      }
      main.main-viewport {
        padding: 16px;
      }
      .form-row {
        flex-direction: column;
      }
    }
  </style>
</head>
<body>

  <!-- Top Bar -->
  <header class="top-bar">
    <div class="brand-section">
      <div class="brand-logo">
        HERMES <span class="badge-tag">CONSOLE</span>
      </div>
      <div class="meta-pill" id="pill-workspace" data-testid="pill-workspace">
        <span class="dot"></span>
        <span id="label-workspace">InMemoryLedger (Seeded Demo)</span>
      </div>
    </div>

    <div class="top-meta">
      <div class="meta-pill" id="pill-provider">
        <span class="dot"></span>
        <span>LocalHeuristicEngine • offline</span>
      </div>
      <div class="meta-pill status-red" id="pill-status" data-testid="pill-status">
        <span class="dot"></span>
        <span id="label-status">STATUS: FAILING</span>
      </div>
      <button class="btn-top" id="btn-audit" data-testid="btn-audit" title="Open Audit Trail">
        <span>📜 Audit</span>
      </button>
    </div>
  </header>

  <!-- Layout Body -->
  <div class="app-body">
    <!-- Left Rail -->
    <aside class="left-rail">
      <ul class="nav-list">
        <li class="nav-item active" data-tab="inbox" id="nav-inbox" data-testid="nav-inbox">
          <span class="nav-label">📥 Inbox</span>
          <div>
            <span class="nav-badge red" id="badge-inbox-count">1</span>
            <span class="nav-kbd">g i</span>
          </div>
        </li>
        <li class="nav-item" data-tab="sprint" id="nav-sprint" data-testid="nav-sprint">
          <span class="nav-label">⚡ Sprint Board</span>
          <span class="nav-kbd">g s</span>
        </li>
        <li class="nav-item" data-tab="diff" id="nav-diff" data-testid="nav-diff">
          <span class="nav-label">📑 Staged Diff</span>
          <span class="nav-kbd">g d</span>
        </li>
        <li class="nav-item" data-tab="timemachine" id="nav-timemachine" data-testid="nav-timemachine">
          <span class="nav-label">🕰 Time Machine</span>
          <span class="nav-kbd">g t</span>
        </li>
      </ul>

      <div class="rail-footer">
        <div>Python 3.10 • urllib.request</div>
        <div>8 Governed Agents Active</div>
        <div>AST Patch Guard: ENFORCED</div>
      </div>
    </aside>

    <!-- Main Viewport -->
    <main class="main-viewport">

      <!-- PANEL 1: INBOX -->
      <section class="view-panel active" id="panel-inbox">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Deterministic Failure Inbox</h2>
            <p>Governed multi-agent test failure triage and autonomous healing queue.</p>
          </div>
          <button class="btn-top" id="btn-reseed-demo">↻ Refresh Seed</button>
        </div>

        <div class="inbox-grid">
          <!-- Seed 1: InMemoryLedger (Product Bug) -->
          <div class="failure-card" data-testid="inbox-item-ledger" id="card-ledger">
            <div class="card-top">
              <div class="card-title-group">
                <div class="card-title">
                  <span>tests/test_ledger.py::test_deposit_rejects_negative</span>
                </div>
                <div class="card-badges">
                  <span class="tag tag-status-red">FAILING (RED)</span>
                  <span class="tag tag-product-bug" data-testid="badge-product-bug">PRODUCT_BUG</span>
                  <span class="tag tag-scope">Owner: DeveloperAgent</span>
                  <span class="tag tag-scope">Allowed Scope: src/InMemoryLedger.py only</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-run-heal" data-testid="btn-run-heal">
                ⚡ Run Heal Pipeline →
              </button>
            </div>

            <div class="code-snippet">
def test_deposit_rejects_negative():
    ledger = InMemoryLedger(100.0)
    with pytest.raises(ValueError):
&gt;       ledger.deposit(-25.0)
E       Failed: DID NOT RAISE &lt;class 'ValueError'&gt;
            </div>

            <div style="font-size: 11px; color: var(--text-dim);">
              Classification: Production code fails to validate negative amounts. Strict AST Guard prevents test file modification.
            </div>
          </div>

          <!-- Seed 2: Playwright Drift (Test Bug) -->
          <div class="failure-card" data-testid="inbox-item-drift" id="card-drift">
            <div class="card-top">
              <div class="card-title-group">
                <div class="card-title">
                  <span>tests/test_cart.py::test_checkout_drift</span>
                </div>
                <div class="card-badges">
                  <span class="tag tag-status-red">FAILING (RED)</span>
                  <span class="tag tag-test-bug" data-testid="badge-test-bug">TEST_BUG</span>
                  <span class="tag tag-scope">Owner: TestHealerAgent</span>
                  <span class="tag tag-scope">Allowed Scope: tests/test_cart.py only</span>
                </div>
              </div>
              <button class="btn-top" id="btn-inspect-drift" disabled style="opacity: 0.6;">
                DeveloperAgent Prohibited (Test Bug Only)
              </button>
            </div>

            <div class="code-snippet">
def test_checkout_drift():
    cart = ShoppingCart()
&gt;   assert cart.checkout() == 'CONFIRMED'
E   AssertionError: assert 'ORDER_CONFIRMED' == 'CONFIRMED'
            </div>

            <div style="font-size: 11px; color: var(--text-dim);">
              Contract Invariant: Test assertion drifted from production contract. DeveloperAgent is disabled; TestHealerAgent routes exclusively.
            </div>
          </div>
        </div>
      </section>

      <!-- PANEL 2: SPRINT BOARD -->
      <section class="view-panel" id="panel-sprint">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Governed Multi-Agent Sprint Execution</h2>
            <p id="sprint-subhead">Sprint DAG orchestration with architectural verification gates.</p>
          </div>
          <button class="btn-action-primary" id="btn-goto-diff">Review Staged Diff →</button>
        </div>

        <div class="sprint-timeline" id="sprint-cards-container">
          <!-- Step 1: CIFailureIngestor -->
          <div class="agent-card passed-step" data-testid="board-card-classify">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>1. RequirementsAgent / CIFailureIngestor</span>
                <span class="agent-tier-badge">TIER_2_SENIOR_SWE</span>
              </div>
              <span class="tag tag-product-bug">CLASSIFIED: PRODUCT_BUG</span>
            </div>
            <div class="agent-body">
              Ingested failure trace from <code>tests/test_ledger.py</code>. Synthesized deterministic Acceptance Criteria (AC-1: Deposit must validate amount &gt; 0 and raise ValueError). Tagged high_risk=False.
            </div>
            <div class="agent-scope-bar">
              Scope: Read-only symbol indexer (no workspace mutations).
            </div>
          </div>

          <!-- Step 2: TicketRouter & Orchestrator -->
          <div class="agent-card passed-step" data-testid="board-card-route">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>2. ScrumMasterOrchestrator &amp; TicketRouter</span>
                <span class="agent-tier-badge">TIER_1_TECH_LEAD</span>
              </div>
              <span class="tag tag-scope">ROUTED: HEAL-PROD-001</span>
            </div>
            <div class="agent-body">
              Constructed DAG and routed ticket <code>HEAL-PROD-001</code> to <code>DeveloperAgent</code>. Complexity score: 2. Restricted allowed files to strictly exclude <code>tests/*</code>.
            </div>
            <div class="agent-scope-bar">
              Allowed Files: <code>['src/InMemoryLedger.py']</code>
            </div>
          </div>

          <!-- Step 3: DeveloperAgent -->
          <div class="agent-card passed-step" data-testid="board-card-proposal">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>3. DeveloperAgent</span>
                <span class="agent-tier-badge">TIER_3_JUNIOR_SWE</span>
              </div>
              <span class="tag tag-product-bug">PROPOSAL SYNTHESIZED</span>
            </div>
            <div class="agent-body">
              Synthesized defensive patch for <code>src/InMemoryLedger.py</code> using <code>LocalHeuristicEngine</code>. Added guard raising <code>ValueError("Deposit amount must be positive")</code>.
            </div>
            <div class="agent-scope-bar">
              Target File: <code>src/InMemoryLedger.py</code> • Lines modified: 4
            </div>
          </div>

          <!-- Step 4: AST Guard & QA Critic -->
          <div class="agent-card passed-step" data-testid="board-card-critic">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>4. ASTPatchGuard &amp; QACriticAgent</span>
                <span class="agent-tier-badge">TIER_4_QA_CRITIC</span>
              </div>
              <span class="tag tag-status-red" style="color: #34d399; background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.3);">VERIFIED PASS</span>
            </div>
            <div class="agent-body">
              Line-by-line rubric evaluation completed. No syntax errors, no timing attacks, zero assertion erosion. Verified AC-1 addressed at <code>src/InMemoryLedger.py:7</code>.
            </div>
            <div class="agent-scope-bar">
              Verdicts: 1/1 AC PASS • Citations: <code>src/InMemoryLedger.py:7</code>
            </div>
          </div>

          <!-- Step 5: Security Blast Radius -->
          <div class="agent-card passed-step" data-testid="board-card-security">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>5. SecurityBlastRadiusAgent</span>
                <span class="agent-tier-badge">TIER_4_QA_CRITIC</span>
              </div>
              <span class="tag tag-scope">0 HIGH / CRITICAL FINDINGS</span>
            </div>
            <div class="agent-body">
              Static AST security pass verified zero SQL injection, zero shell=True invocations, zero path traversal escapes, and clean constant-time compliance.
            </div>
            <div class="agent-scope-bar">
              Blast Radius: ISOLATED (src/InMemoryLedger.py only)
            </div>
          </div>

          <!-- Step 6: Sandbox Executor -->
          <div class="agent-card passed-step" data-testid="board-card-sandbox">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>6. AutomationTesterAgent &amp; Sandbox</span>
                <span class="agent-tier-badge">TIER_3_JUNIOR_SWE</span>
              </div>
              <span class="tag tag-status-red" style="color: #34d399; background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.3);">SANDBOX PASS (3/3)</span>
            </div>
            <div class="agent-body">
              Executed test suite across 3 isolated ephemeral git worktrees (repeat=3). Clean deterministic pass with zero flakiness. Worktrees purged from disk.
            </div>
            <div class="agent-scope-bar">
              Runs: 3/3 Passed • Exit Code: 0
            </div>
          </div>

          <!-- Step 7: Staged in Write Gate -->
          <div class="agent-card active-step" data-testid="board-card-staged">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>7. HumanWriteGateController</span>
                <span class="agent-tier-badge">GOVERNED WRITE GATE</span>
              </div>
              <span class="tag" style="background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4);">AWAITING APPROVAL</span>
            </div>
            <div class="agent-body">
              Safety pre-apply snapshot pinned in Time Machine. Workspace remains 100% byte-for-byte untouched until human write-gate authorization.
            </div>
            <div class="agent-scope-bar">
              Staged Sprint: <code id="board-sprint-id">sprint_ready</code> • Staged Files: <code>['src/InMemoryLedger.py']</code>
            </div>
          </div>
        </div>
      </section>

      <!-- PANEL 3: DIFF & WRITE GATE -->
      <section class="view-panel" id="panel-diff">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Write Gate Review &amp; Time Machine Control</h2>
            <p>Unified diff computed via difflib against baseline snapshot. Zero live workspace writes until verification succeeds.</p>
          </div>
          <div id="diff-status-pill" class="meta-pill status-amber">
            <span class="dot"></span>
            <span id="diff-status-label">STATUS: STAGED</span>
          </div>
        </div>

        <div class="diff-container" data-testid="diff-container">
          <div class="diff-header">
            <span>src/InMemoryLedger.py (Unified Diff vs Baseline)</span>
            <span>Invariant: Test assertions preserved (2/2)</span>
          </div>
          <div class="diff-content" id="diff-text">
--- a/src/InMemoryLedger.py (Baseline)
+++ b/src/InMemoryLedger.py (Staged Proposal)
@@ -10,6 +10,10 @@
     def deposit(self, amount: float) -> float:
+        if amount &lt;= 0:
+            raise ValueError("Deposit amount must be positive")
         self._balance += amount
         return self._balance
          </div>
        </div>

        <!-- Approval & Verification Bar -->
        <div class="approval-toolbar" id="toolbar-approval">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Approver Identity (QA Lead)</label>
              <input type="text" class="form-input" id="input-approver" data-testid="input-approver" value="QA Lead" placeholder="Name or email">
            </div>
            <div class="form-group" style="flex: 2;">
              <label class="form-label">Audit Review Comment</label>
              <input type="text" class="form-input" id="input-comment" data-testid="input-comment" value="Verified negative deposit ValueError guard; zero assertion erosion" placeholder="Reason for write authorization">
            </div>
          </div>

          <div style="display: flex; gap: 12px; align-items: center; justify-content: space-between; border-top: 1px solid var(--border-subtle); padding-top: 14px;">
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);">
              Pre-Apply Snapshot: <span id="snapshot-id-display" data-testid="snapshot-id-display" style="color: var(--accent-cyan);">snap_pending_approval</span>
            </div>

            <div style="display: flex; gap: 10px;">
              <button class="btn-action-success" id="btn-approve" data-testid="btn-approve">
                ✓ Approve &amp; Verify (Sandbox)
              </button>
              <button class="btn-action-rewind" id="btn-rewind" data-testid="btn-rewind">
                ↺ Rewind Workspace (TimeMachine)
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- PANEL 4: TIME MACHINE -->
      <section class="view-panel" id="panel-timemachine">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Time Machine Snapshot Ledger</h2>
            <p>Cryptographic workspace state ledger with microsecond rollback capability.</p>
          </div>
        </div>

        <div class="inbox-grid" id="tm-snapshot-list">
          <div class="failure-card">
            <div class="card-top">
              <div class="card-title-group">
                <div class="card-title">
                  <span id="tm-active-snap-id">snap_safety_pre_apply_HEAL-PROD-001</span>
                </div>
                <div class="card-badges">
                  <span class="tag tag-scope">Type: PRE_APPLY_SAFETY</span>
                  <span class="tag tag-scope">Target: src/InMemoryLedger.py</span>
                </div>
              </div>
              <button class="btn-action-rewind" id="btn-tm-restore">
                Restore Baseline
              </button>
            </div>
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);">
              Protects against regressions. Restores workspace byte-for-byte to the exact pre-patch baseline.
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <!-- Audit Drawer Overlay -->
  <div class="audit-overlay" id="audit-overlay">
    <div class="audit-drawer" id="audit-drawer" data-testid="audit-drawer">
      <div class="drawer-header">
        <div class="drawer-title">Sprint Governance Audit Ledger</div>
        <button class="btn-close" id="btn-close-audit">&times;</button>
      </div>

      <div class="audit-content" id="audit-content">
# HERMES SPRINT AUDIT REPORT
Sprint ID: sprint_demo_ledger
Mode: heal
Status: ACTIVE

## 1. INGESTION & CLASSIFICATION
- Agent: RequirementsAgent / CIFailureIngestor (TIER_2_SENIOR_SWE)
- Classification: PRODUCT_BUG
- Source: tests/test_ledger.py::test_deposit_rejects_negative
- Acceptance Criteria: AC-1 (Enforce deposit &gt; 0 guard)

## 2. ORCHESTRATION & ROUTING
- Orchestrator: ScrumMasterOrchestrator (TIER_1_TECH_LEAD)
- Ticket ID: HEAL-PROD-001
- Assigned Worker: DeveloperAgent (TIER_3_JUNIOR_SWE)
- Allowed Files: ['src/InMemoryLedger.py'] (tests/* strictly excluded)

## 3. QA CRITIC & AST GUARD
- Agent: QACriticAgent (TIER_4_QA_CRITIC)
- AST Patch Guard: PASS (0 syntax errors, 0 prohibited calls)
- Zero Assertion Erosion: PASS (assertions preserved: 2/2)
- Line Citations: src/InMemoryLedger.py:7

## 4. SECURITY BLAST RADIUS
- Agent: SecurityBlastRadiusAgent (TIER_4_QA_CRITIC)
- Finding Count: 0 HIGH / CRITICAL
- Constant-Time Secret Audit: PASS
      </div>

      <div class="drawer-footer">
        <button class="btn-top" id="btn-copy-markdown" data-testid="btn-copy-markdown">📋 Copy as Markdown</button>
      </div>
    </div>
  </div>

  <!-- Client JavaScript -->
  <script>
    // State management
    const state = {
      workspaceId: null,
      workspaceName: "InMemoryLedger",
      failingTest: "test_deposit_rejects_negative",
      status: "FAILING", // FAILING, AWAITING_WRITE_GATE, APPLIED, ROLLED_BACK
      sprintId: null,
      snapshotId: null,
      diffText: "",
      auditLog: "",
    };

    // DOM Elements
    const navItems = document.querySelectorAll('.nav-item');
    const viewPanels = document.querySelectorAll('.view-panel');
    const labelStatus = document.getElementById('label-status');
    const pillStatus = document.getElementById('pill-status');
    const btnRunHeal = document.getElementById('btn-run-heal');
    const btnApprove = document.getElementById('btn-approve');
    const btnRewind = document.getElementById('btn-rewind');
    const snapshotIdDisplay = document.getElementById('snapshot-id-display');
    const diffStatusLabel = document.getElementById('diff-status-label');
    const diffStatusPill = document.getElementById('diff-status-pill');
    const diffTextContainer = document.getElementById('diff-text');
    const auditOverlay = document.getElementById('audit-overlay');
    const btnAudit = document.getElementById('btn-audit');
    const btnCloseAudit = document.getElementById('btn-close-audit');
    const btnCopyMarkdown = document.getElementById('btn-copy-markdown');
    const auditContent = document.getElementById('audit-content');
    const btnGotoDiff = document.getElementById('btn-goto-diff');
    const btnReseed = document.getElementById('btn-reseed-demo');

    // Navigation Switcher
    function switchTab(tabName) {
      navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.tab === tabName);
      });
      viewPanels.forEach(panel => {
        panel.classList.toggle('active', panel.id === `panel-${tabName}`);
      });
    }

    navItems.forEach(item => {
      item.addEventListener('click', () => switchTab(item.dataset.tab));
    });

    if (btnGotoDiff) {
      btnGotoDiff.addEventListener('click', () => switchTab('diff'));
    }

    // Keyboard Shortcuts: g i -> inbox, g d -> diff, g s -> sprint, g t -> timemachine
    let keySeq = '';
    let keyTimer = null;
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      if (e.key === 'Escape') {
        auditOverlay.classList.remove('open');
        return;
      }

      const key = e.key.toLowerCase();
      keySeq += key;
      clearTimeout(keyTimer);
      keyTimer = setTimeout(() => { keySeq = ''; }, 600);

      if (keySeq === 'gi') { switchTab('inbox'); keySeq = ''; }
      else if (keySeq === 'gd') { switchTab('diff'); keySeq = ''; }
      else if (keySeq === 'gs') { switchTab('sprint'); keySeq = ''; }
      else if (keySeq === 'gt') { switchTab('timemachine'); keySeq = ''; }
    });

    // Audit Drawer Handlers
    btnAudit.addEventListener('click', () => auditOverlay.classList.add('open'));
    btnCloseAudit.addEventListener('click', () => auditOverlay.classList.remove('open'));
    auditOverlay.addEventListener('click', (e) => {
      if (e.target === auditOverlay) auditOverlay.classList.remove('open');
    });

    btnCopyMarkdown.addEventListener('click', () => {
      navigator.clipboard.writeText(auditContent.innerText).then(() => {
        const orig = btnCopyMarkdown.innerText;
        btnCopyMarkdown.innerText = "✓ Copied!";
        setTimeout(() => { btnCopyMarkdown.innerText = orig; }, 1800);
      });
    });

    // API Helpers
    async function apiPost(endpoint, data = {}) {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`API error ${resp.status}: ${err}`);
      }
      return await resp.json();
    }

    async function apiGet(endpoint) {
      const resp = await fetch(endpoint);
      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`API error ${resp.status}: ${err}`);
      }
      return await resp.json();
    }

    // Initial Seed: Create demo workspace
    async function initializeDemoWorkspace() {
      try {
        const data = await apiPost('/api/demo/ledger');
        state.workspaceId = data.workspace_id;
        state.workspaceName = data.workspace_name;
        state.failingTest = data.failing_test;
        state.status = "FAILING";
        updateUI();
      } catch (e) {
        console.error("Demo init error:", e);
      }
    }

    function updateUI() {
      // Status labels and pills
      if (state.status === "FAILING") {
        labelStatus.innerText = "STATUS: FAILING (RED)";
        pillStatus.className = "meta-pill status-red";
        diffStatusLabel.innerText = "STATUS: FAILING";
        diffStatusPill.className = "meta-pill status-red";
        btnApprove.disabled = true;
        btnRewind.disabled = true;
      } else if (state.status === "AWAITING_WRITE_GATE") {
        labelStatus.innerText = "STATUS: AWAITING APPROVAL";
        pillStatus.className = "meta-pill status-amber";
        diffStatusLabel.innerText = "STATUS: STAGED";
        diffStatusPill.className = "meta-pill status-amber";
        btnApprove.disabled = false;
        btnRewind.disabled = true;
      } else if (state.status === "APPLIED") {
        labelStatus.innerText = "STATUS: APPLIED (GREEN)";
        pillStatus.className = "meta-pill status-green";
        diffStatusLabel.innerText = "STATUS: APPLIED (100% PASSING)";
        diffStatusPill.className = "meta-pill status-green";
        btnApprove.disabled = true;
        btnRewind.disabled = false;
      } else if (state.status === "ROLLED_BACK") {
        labelStatus.innerText = "STATUS: ROLLED_BACK (RED)";
        pillStatus.className = "meta-pill status-red";
        diffStatusLabel.innerText = "STATUS: ROLLED_BACK (BASELINE RESTORED)";
        diffStatusPill.className = "meta-pill status-red";
        btnApprove.disabled = true;
        btnRewind.disabled = true;
      }

      if (state.snapshotId) {
        snapshotIdDisplay.innerText = state.snapshotId;
        const snapEl = document.getElementById('tm-active-snap-id');
        if (snapEl) snapEl.innerText = state.snapshotId;
      }

      if (state.sprintId) {
        const sprintEl = document.getElementById('board-sprint-id');
        if (sprintEl) sprintEl.innerText = state.sprintId;
      }

      if (state.diffText) {
        diffTextContainer.innerText = state.diffText;
      }
    }

    // [1] Run Heal Action
    btnRunHeal.addEventListener('click', async () => {
      btnRunHeal.disabled = true;
      btnRunHeal.innerText = "⚡ Running Governed Pipeline...";

      try {
        if (!state.workspaceId) {
          await initializeDemoWorkspace();
        }

        const res = await apiPost(`/api/demo/${state.workspaceId}/heal`);
        state.status = res.status || "AWAITING_WRITE_GATE";
        state.sprintId = res.sprint_id;
        state.snapshotId = res.snapshot_id || (res.staged_proposal && res.staged_proposal.snapshot_id);
        
        // Fetch diff
        const diffRes = await apiGet(`/api/demo/${state.workspaceId}/diff`);
        state.diffText = diffRes.diff || "";

        // Fetch audit
        const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
        state.auditLog = auditRes.markdown || "";
        auditContent.innerText = state.auditLog;

        updateUI();
        switchTab('sprint');
      } catch (e) {
        alert("Sprint heal error: " + e.message);
      } finally {
        btnRunHeal.disabled = false;
        btnRunHeal.innerText = "⚡ Run Heal Pipeline →";
      }
    });

    // [2] Approve Action
    btnApprove.addEventListener('click', async () => {
      btnApprove.disabled = true;
      btnApprove.innerText = "Applying & Verifying Sandbox...";

      try {
        const approver = document.getElementById('input-approver').value || "QA Lead";
        const comment = document.getElementById('input-comment').value || "";

        const res = await apiPost(`/api/demo/${state.workspaceId}/approve`, {
          approver: approver,
          comment: comment,
          verify: true,
        });

        if (res.success || res.status === "APPLIED") {
          state.status = "APPLIED";
          state.snapshotId = res.snapshot_id || state.snapshotId;

          // Fetch updated audit
          const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
          state.auditLog = auditRes.markdown || "";
          auditContent.innerText = state.auditLog;

          updateUI();
        } else {
          state.status = "ROLLED_BACK";
          updateUI();
          alert("Approval failed: " + (res.error || "Verification failed, rolled back"));
        }
      } catch (e) {
        alert("Approve error: " + e.message);
      } finally {
        btnApprove.innerText = "✓ Approve & Verify (Sandbox)";
      }
    });

    // [3] Rewind Action
    btnRewind.addEventListener('click', async () => {
      btnRewind.disabled = true;
      btnRewind.innerText = "Rewinding Workspace...";

      try {
        const res = await apiPost(`/api/demo/${state.workspaceId}/rollback`);
        if (res.success || res.status === "ROLLED_BACK") {
          state.status = "ROLLED_BACK";

          // Fetch updated audit
          const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
          state.auditLog = auditRes.markdown || "";
          auditContent.innerText = state.auditLog;

          updateUI();
        } else {
          alert("Rollback failed: " + (res.error || "unknown error"));
        }
      } catch (e) {
        alert("Rewind error: " + e.message);
      } finally {
        btnRewind.innerText = "↺ Rewind Workspace (TimeMachine)";
      }
    });

    // Reseed button
    if (btnReseed) {
      btnReseed.addEventListener('click', () => {
        initializeDemoWorkspace();
      });
    }

    // Auto-init on page load
    window.addEventListener('DOMContentLoaded', () => {
      initializeDemoWorkspace();
    });
  </script>
</body>
</html>
"""
