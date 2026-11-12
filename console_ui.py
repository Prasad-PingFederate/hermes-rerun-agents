"""
Hermes Tester Console — UI Template & Client Logic (AG-7 through AG-10)
Editorial workstation interface with copper aesthetic and offline zero-dependency client.
Palette: background #14120e, text #e7e1d6, hairline borders rgba(231,225,214,0.14), copper #c9854a.
Status colors: Green and Red for status only.
Fonts: IBM Plex Sans and IBM Plex Mono.
"""

CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>Hermes // Tester Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-canvas: #14120e;
      --bg-panel: #181512;
      --bg-card: #1c1915;
      --bg-card-hover: #231f1a;
      --bg-code: #0c0b09;

      --border-hairline: rgba(231, 225, 214, 0.14);
      --border-muted: rgba(231, 225, 214, 0.22);
      --border-focus: #c9854a;

      --text-main: #e7e1d6;
      --text-muted: #a8a095;
      --text-dim: #736b61;

      --copper: #c9854a;
      --copper-hover: #db9356;
      --copper-bg: rgba(201, 133, 74, 0.14);
      --copper-border: rgba(201, 133, 74, 0.35);

      --status-red: #f87171;
      --status-red-bg: rgba(248, 113, 113, 0.12);
      --status-red-border: rgba(248, 113, 113, 0.35);

      --status-green: #4ade80;
      --status-green-bg: rgba(74, 222, 128, 0.12);
      --status-green-border: rgba(74, 222, 128, 0.35);

      --status-amber: #fbbf24;
      --status-amber-bg: rgba(251, 191, 36, 0.12);
      --status-amber-border: rgba(251, 191, 36, 0.35);

      --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --font-sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
      letter-spacing: -0.005em;
    }

    /* Top Bar */
    header.top-bar {
      height: 48px;
      background-color: var(--bg-panel);
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
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
      font-weight: 700;
      font-size: 14px;
      letter-spacing: 0.12em;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-logo .badge-tag {
      font-size: 10px;
      font-weight: 600;
      color: var(--copper);
      background: var(--copper-bg);
      border: 1px solid var(--copper-border);
      padding: 1px 6px;
      border-radius: 2px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .top-meta {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .meta-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 9px;
      border-radius: 3px;
      font-size: 11px;
      font-family: var(--font-mono);
      border: 1px solid var(--border-hairline);
      background-color: var(--bg-card);
      color: var(--text-muted);
    }

    .meta-pill .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: var(--text-dim);
    }

    .meta-pill.status-red {
      background-color: var(--status-red-bg);
      border-color: var(--status-red-border);
      color: var(--status-red);
    }
    .meta-pill.status-red .dot { background-color: var(--status-red); }

    .meta-pill.status-green {
      background-color: var(--status-green-bg);
      border-color: var(--status-green-border);
      color: var(--status-green);
    }
    .meta-pill.status-green .dot { background-color: var(--status-green); }

    .meta-pill.status-amber {
      background-color: var(--status-amber-bg);
      border-color: var(--status-amber-border);
      color: var(--status-amber);
    }
    .meta-pill.status-amber .dot { background-color: var(--status-amber); }

    .btn-top {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-main);
      padding: 4px 10px;
      font-size: 11px;
      font-family: var(--font-mono);
      border-radius: 3px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }

    .btn-top:hover {
      background: var(--bg-card-hover);
      border-color: var(--copper);
    }

    /* Executive ROI & Governance Header Bar (AG-11) */
    .roi-header-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background-color: #1a1713;
      border-bottom: 1px solid var(--border-hairline);
      padding: 6px 20px;
      font-family: var(--font-mono);
      font-size: 11px;
      flex-shrink: 0;
      gap: 16px;
    }
    .roi-metric-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .roi-metric-label {
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 10px;
    }
    .roi-metric-val {
      color: var(--text-main);
      font-weight: 600;
    }
    .roi-metric-val.highlight {
      color: var(--copper);
    }
    .roi-badge-green {
      background-color: var(--status-green-bg);
      border: 1px solid var(--status-green-border);
      color: var(--status-green);
      padding: 1px 5px;
      border-radius: 2px;
      font-size: 10px;
      font-weight: 600;
    }
    .roi-divider {
      width: 1px;
      height: 14px;
      background-color: var(--border-hairline);
    }
    .roi-clickable {
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 3px;
      transition: background 0.15s;
    }
    .roi-clickable:hover {
      background-color: rgba(201, 133, 74, 0.15);
    }

    /* Layout Body */
    .app-body {
      display: flex;
      flex: 1;
      height: calc(100vh - 84px);
      overflow: hidden;
    }

    /* Left Rail */
    aside.left-rail {
      width: 260px;
      background-color: var(--bg-panel);
      border-right: 1px solid var(--border-hairline);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      flex-shrink: 0;
    }

    .rail-section-header {
      padding: 12px 14px 6px 14px;
      font-family: var(--font-mono);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
    }

    .nav-list {
      list-style: none;
      padding: 6px 8px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      border-radius: 3px;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 500;
      margin-bottom: 2px;
      transition: all 0.12s ease;
      user-select: none;
      border-left: 3px solid transparent;
    }

    .nav-item:hover {
      background-color: var(--bg-card);
      color: var(--text-main);
    }

    .nav-item.active {
      background-color: var(--bg-card);
      color: var(--text-main);
      font-weight: 600;
      border-left: 3px solid var(--copper);
    }

    .nav-item .nav-label {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .nav-kbd {
      font-size: 10px;
      font-family: var(--font-mono);
      background-color: var(--bg-code);
      border: 1px solid var(--border-hairline);
      padding: 1px 4px;
      border-radius: 2px;
      color: var(--text-dim);
    }

    .nav-badge {
      font-size: 10px;
      font-family: var(--font-mono);
      padding: 1px 5px;
      border-radius: 2px;
      font-weight: 600;
    }
    .nav-badge.red {
      background-color: var(--status-red-bg);
      color: var(--status-red);
      border: 1px solid var(--status-red-border);
    }

    /* Inbox List on Left Rail */
    .inbox-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 4px 8px;
      overflow-y: auto;
    }

    .inbox-row {
      background-color: var(--bg-card);
      border: 1px solid var(--border-hairline);
      border-radius: 3px;
      padding: 9px 11px;
      cursor: pointer;
      transition: all 0.15s ease;
      border-left: 3px solid transparent;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .inbox-row:hover {
      border-color: var(--border-muted);
      background-color: var(--bg-card-hover);
    }

    .inbox-row.selected {
      border-left: 3px solid var(--copper);
      background-color: var(--bg-card-hover);
    }

    .inbox-row-title {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .inbox-row-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 10px;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }

    .tag-badge {
      padding: 1px 4px;
      border-radius: 2px;
      font-size: 9px;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .tag-badge.prod-bug {
      background: var(--copper-bg);
      color: var(--copper);
      border: 1px solid var(--copper-border);
    }
    .tag-badge.test-bug {
      background: var(--bg-code);
      color: var(--text-muted);
      border: 1px solid var(--border-hairline);
    }
    .tag-badge.sec-violation {
      background: var(--status-red-bg);
      color: var(--status-red);
      border: 1px solid var(--status-red-border);
    }

    .rail-footer {
      padding: 12px 14px;
      border-top: 1px solid var(--border-hairline);
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--text-dim);
      line-height: 1.6;
    }

    /* Main Content Area */
    main.main-viewport {
      flex: 1;
      overflow-y: auto;
      padding: 24px 30px;
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
      border-bottom: 1px solid var(--border-hairline);
      padding-bottom: 12px;
    }

    .view-title-group h2 {
      font-size: 17px;
      font-weight: 600;
      color: var(--text-main);
      letter-spacing: -0.01em;
    }

    .view-title-group p {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    /* Cards */
    .detail-card {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
      padding: 18px;
      margin-bottom: 16px;
    }

    .detail-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }

    .code-snippet {
      background-color: var(--bg-code);
      border: 1px solid var(--border-hairline);
      border-radius: 3px;
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: #dfd7cc;
      overflow-x: auto;
      margin-bottom: 12px;
      line-height: 1.5;
    }

    /* Action Buttons */
    .btn-action-primary {
      background: var(--copper);
      color: #14120e;
      border: none;
      padding: 7px 15px;
      border-radius: 3px;
      font-size: 12px;
      font-family: var(--font-mono);
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s ease;
    }
    .btn-action-primary:hover {
      background: var(--copper-hover);
    }
    .btn-action-primary:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }

    .btn-action-success {
      background: var(--status-green);
      color: #0c1a10;
      border: none;
      padding: 7px 15px;
      border-radius: 3px;
      font-size: 12px;
      font-family: var(--font-mono);
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: opacity 0.15s ease;
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
      color: var(--status-amber);
      border: 1px solid var(--status-amber-border);
      padding: 7px 15px;
      border-radius: 3px;
      font-size: 12px;
      font-family: var(--font-mono);
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s ease;
    }
    .btn-action-rewind:hover {
      background: var(--status-amber-bg);
    }
    .btn-action-rewind:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }

    /* Vertical Sprint Rail (7 Steps) */
    .sprint-timeline {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .agent-card {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: border-color 0.15s ease;
    }

    .agent-card.active-step {
      border-color: var(--copper);
      background-color: var(--bg-card);
    }
    .agent-card.passed-step {
      border-color: var(--border-hairline);
    }
    .agent-card.rejected-step {
      border-color: var(--status-red);
      background-color: var(--status-red-bg);
    }
    .agent-card.blocked-step {
      opacity: 0.45;
      border-color: var(--border-hairline);
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
      font-weight: 600;
      color: var(--text-main);
    }

    .agent-tier-badge {
      font-family: var(--font-mono);
      font-size: 9px;
      padding: 1px 5px;
      border-radius: 2px;
      background: var(--bg-code);
      border: 1px solid var(--border-hairline);
      color: var(--text-dim);
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
      border-top: 1px solid var(--border-hairline);
    }

    /* Diff Reviewer (Full width main stage) */
    .diff-container {
      background-color: var(--bg-code);
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
      overflow: hidden;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.45;
      margin-bottom: 20px;
    }

    .diff-header {
      background-color: var(--bg-panel);
      padding: 9px 14px;
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: var(--text-muted);
    }

    .diff-content {
      padding: 14px;
      overflow-x: auto;
      max-height: 480px;
      white-space: pre;
    }

    .diff-line-add {
      background-color: rgba(74, 222, 128, 0.1);
      color: var(--status-green);
      display: block;
      padding: 1px 4px;
    }
    .diff-line-del {
      background-color: rgba(248, 113, 113, 0.1);
      color: var(--status-red);
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
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
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
      border: 1px solid var(--border-hairline);
      color: var(--text-main);
      padding: 7px 10px;
      border-radius: 3px;
      font-family: var(--font-mono);
      font-size: 12px;
    }
    .form-input:focus {
      outline: none;
      border-color: var(--copper);
    }

    .audit-approval-line {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--copper);
      margin-top: 4px;
      min-height: 18px;
    }

    /* Audit Drawer */
    .audit-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(10, 9, 8, 0.75);
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
      border-left: 1px solid var(--border-hairline);
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
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-hairline);
    }

    .drawer-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text-main);
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
      background-color: var(--bg-code);
      border: 1px solid var(--border-hairline);
      border-radius: 3px;
      padding: 12px;
      color: #dfd7cc;
      white-space: pre-wrap;
    }

    .drawer-footer {
      margin-top: 14px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .btn-connect-sm {
      font-family: var(--font-mono);
      font-size: 10px;
      padding: 2px 7px;
      background: transparent;
      border: 1px solid var(--copper-border);
      color: var(--copper);
      border-radius: 2px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn-connect-sm:hover {
      background: var(--copper-bg);
    }

    /* Modal Overlays (Connect Repo & Story Sprint) */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(10, 8, 7, 0.78);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 120;
      backdrop-filter: blur(3px);
    }
    .modal-overlay.open {
      display: flex;
    }
    .modal-box {
      background: var(--bg-panel);
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
      width: 500px;
      max-width: 92vw;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.65);
    }

    /* Provider Switcher Drawer */
    .provider-overlay {
      position: fixed;
      inset: 0;
      background: rgba(10, 8, 7, 0.7);
      display: none;
      z-index: 90;
      backdrop-filter: blur(2px);
    }
    .provider-overlay.open {
      display: block;
    }
    .provider-drawer {
      position: fixed;
      right: 0;
      top: 0;
      bottom: 0;
      width: 540px;
      max-width: 90vw;
      background-color: var(--bg-panel);
      border-left: 1px solid var(--border-hairline);
      z-index: 95;
      display: flex;
      flex-direction: column;
      padding: 24px;
      transform: translateX(100%);
      transition: transform 0.25s ease;
    }
    .provider-overlay.open .provider-drawer {
      transform: translateX(0);
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
        border-bottom: 1px solid var(--border-hairline);
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
        HERMES <span class="badge-tag">GOVERNED</span>
      </div>
      <div class="meta-pill" id="pill-workspace" data-testid="pill-workspace">
        <span class="dot"></span>
        <span id="label-workspace">InMemoryLedger</span>
      </div>
    </div>

    <div class="top-meta">
      <button class="btn-top" id="btn-open-story" data-testid="btn-run-story" title="Launch Story Sprint DAG">
        <span>✨ New Story</span>
      </button>
      <div class="meta-pill" id="pill-provider" data-testid="pill-provider" style="cursor: pointer;" title="Configure LLM Providers">
        <span class="dot"></span>
        <span id="label-provider">LocalHeuristicEngine · MOCK</span>
      </div>
      <div class="meta-pill status-red" id="pill-status" data-testid="pill-status">
        <span class="dot"></span>
        <span id="label-status">STATUS: FAILING</span>
      </div>
      <button class="btn-top" id="btn-audit" data-testid="btn-audit" title="Open Governance Audit Trail">
        <span>📜 Audit</span>
      </button>
    </div>
  </header>

  <!-- Executive ROI & Governance Header Bar (AG-11) -->
  <section class="roi-header-bar" id="roi-header-bar" data-testid="roi-header-bar">
    <div class="roi-metric-item" id="roi-metric-hours" data-testid="roi-metric-hours">
      <span class="roi-metric-label">Engineering Hours Saved:</span>
      <span class="roi-metric-val" id="roi-val-hours">10.7 hrs</span>
    </div>
    <div class="roi-divider"></div>
    <div class="roi-metric-item" id="roi-metric-mttr" data-testid="roi-metric-mttr">
      <span class="roi-metric-label">MTTR Compression:</span>
      <span class="roi-metric-val" id="roi-val-mttr">4.2h → 1.3m <span class="roi-badge-green">-99.5%</span></span>
    </div>
    <div class="roi-divider"></div>
    <div class="roi-metric-item" id="roi-metric-governance" data-testid="roi-metric-governance">
      <span class="roi-metric-label">Quarantine & Security:</span>
      <span class="roi-metric-val" id="roi-val-governance"><span id="roi-val-flakes">1 Flake</span> • <span id="roi-val-hostiles" style="color: #ef5350;">1 Blocked</span></span>
    </div>
    <div class="roi-divider"></div>
    <div class="roi-metric-item roi-clickable" id="roi-metric-dollar" data-testid="roi-metric-dollar" title="Click to audit ROI mathematical formula breakdown">
      <span class="roi-metric-label">Estimated Value ROI:</span>
      <span class="roi-metric-val highlight" id="roi-val-dollar">$1,338 ROI ℹ️</span>
    </div>
  </section>

  <!-- Layout Body -->
  <div class="app-body">
    <!-- Left Rail -->
    <aside class="left-rail">
      <div>
        <div class="rail-section-header">Views</div>
        <ul class="nav-list">
          <li class="nav-item active" data-tab="inbox" id="nav-inbox" data-testid="nav-inbox">
            <span class="nav-label">📥 Inbox</span>
            <div>
              <span class="nav-badge red" id="badge-inbox-count">3</span>
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

        <div class="rail-section-header" style="display: flex; justify-content: space-between; align-items: center;">
          <span>Failure Queue</span>
          <button class="btn-connect-sm" id="btn-open-connect" data-testid="btn-connect-repo">+ Connect</button>
        </div>
        <div class="inbox-list" id="rail-inbox-list">
          <!-- Row 1: Ledger -->
          <div class="inbox-row selected" id="row-ledger" data-target="ledger" data-testid="inbox-row-ledger">
            <div class="inbox-row-title">InMemoryLedger</div>
            <div class="inbox-row-meta">
              <span class="tag-badge prod-bug">PRODUCT_BUG</span>
              <span>DeveloperAgent</span>
            </div>
          </div>
          <!-- Row 2: Drift -->
          <div class="inbox-row" id="row-drift" data-target="drift" data-testid="inbox-row-drift">
            <div class="inbox-row-title">PlaywrightDrift</div>
            <div class="inbox-row-meta">
              <span class="tag-badge test-bug">TEST_BUG</span>
              <span>TestHealerAgent</span>
            </div>
          </div>
          <!-- Row 3: Hostile -->
          <div class="inbox-row" id="row-hostile" data-target="hostile" data-testid="inbox-row-hostile">
            <div class="inbox-row-title">HostilePatch</div>
            <div class="inbox-row-meta">
              <span class="tag-badge sec-violation">SEC_REJECT</span>
              <span>DeveloperAgent</span>
            </div>
          </div>
          <!-- Row 4: Flake -->
          <div class="inbox-row" id="row-flake" data-target="flake" data-testid="inbox-row-flake">
            <div class="inbox-row-title">PlaywrightFlake</div>
            <div class="inbox-row-meta">
              <span class="tag-badge" style="background: rgba(201,133,74,0.18); color: #c9854a; border: 1px solid rgba(201,133,74,0.35);">FLAKY_TEST</span>
              <span>TestHealerAgent</span>
            </div>
          </div>
          <!-- Row 5: Noise -->
          <div class="inbox-row" id="row-noise" data-target="noise" data-testid="inbox-row-noise">
            <div class="inbox-row-title">EnvironmentNoise</div>
            <div class="inbox-row-meta">
              <span class="tag-badge" style="background: rgba(180,80,80,0.18); color: #df7070; border: 1px solid rgba(180,80,80,0.35);">ENV_NOISE</span>
              <span>DevOps/SRE</span>
            </div>
          </div>
          <!-- Dynamic tasks / connected repos -->
          <div id="dynamic-inbox-items"></div>
        </div>
      </div>

      <div class="rail-footer">
        <div>Python 3.10 · Zero Network</div>
        <div>8 Governed Agent Roles</div>
        <div>AST Patch Guard: ENFORCED</div>
      </div>
    </aside>

    <!-- Main Viewport -->
    <main class="main-viewport">

      <!-- PANEL 1: INBOX -->
      <section class="view-panel active" id="panel-inbox">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Deterministic Triage Queue</h2>
            <p>Governed multi-agent test failure triage and autonomous healing queue.</p>
          </div>
          <button class="btn-top" id="btn-reseed-demo">↻ Reset Queue</button>
        </div>

        <div style="display: flex; flex-direction: column; gap: 12px;">
          <!-- Item 1: InMemoryLedger -->
          <div class="detail-card" data-testid="inbox-item-ledger" id="card-ledger">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 14px; font-weight: 600; font-family: var(--font-mono);">tests/test_ledger.py::test_deposit_rejects_negative</div>
                <div style="display: flex; gap: 6px; margin-top: 6px;">
                  <span class="tag-badge sec-violation">FAILING (RED)</span>
                  <span class="tag-badge prod-bug" data-testid="badge-product-bug">PRODUCT_BUG</span>
                  <span class="tag-badge test-bug">Owner: DeveloperAgent</span>
                  <span class="tag-badge test-bug">Scope: src/InMemoryLedger.py only</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-run-heal" data-testid="btn-run-heal">
                ⚡ Run Heal Pipeline →
              </button>
            </div>

            <div class="code-snippet">def test_deposit_rejects_negative():
    ledger = InMemoryLedger(100.0)
    with pytest.raises(ValueError):
>       ledger.deposit(-25.0)
E       Failed: DID NOT RAISE &lt;class 'ValueError'&gt;</div>

            <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">
              Classification: Production code fails to validate negative amounts. Strict AST Guard prevents test file modification.
            </div>
          </div>

          <!-- Item 2: Playwright Drift -->
          <div class="detail-card" data-testid="inbox-item-drift" id="card-drift">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 14px; font-weight: 600; font-family: var(--font-mono);">tests/test_cart.py::test_checkout_drift</div>
                <div style="display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;">
                  <span class="tag-badge sec-violation">FAILING (RED)</span>
                  <span class="tag-badge prod-bug" data-testid="badge-test-bug">TEST_BUG</span>
                  <span class="tag-badge test-bug" data-testid="badge-owner-healer">Owner: TestHealerAgent</span>
                  <span class="tag-badge test-bug">Scope: tests/test_cart.py only</span>
                  <span class="tag-badge sec-violation" data-testid="badge-dev-prohibited" style="opacity: 0.85;">DeveloperAgent Visibly Unavailable</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-run-drift" data-testid="btn-run-drift">
                ⚡ Run Heal Pipeline →
              </button>
            </div>

            <div class="code-snippet">def test_checkout_drift():
    cart = ShoppingCart()
>   assert cart.checkout() == 'CONFIRMED'
E   AssertionError: assert 'ORDER_CONFIRMED' == 'CONFIRMED'</div>

            <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">
              Contract Invariant: Test assertion drifted from production contract. DeveloperAgent is disabled; TestHealerAgent routes exclusively.
            </div>
          </div>

          <!-- Item 3: HostilePatch -->
          <div class="detail-card" data-testid="inbox-item-hostile" id="card-hostile">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 14px; font-weight: 600; font-family: var(--font-mono);">tests/test_service.py::test_health_metrics</div>
                <div style="display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;">
                  <span class="tag-badge sec-violation">FAILING (RED)</span>
                  <span class="tag-badge prod-bug" data-testid="badge-hostile">PRODUCT_BUG</span>
                  <span class="tag-badge test-bug">Owner: DeveloperAgent</span>
                  <span class="tag-badge test-bug">Scope: src/service.py only</span>
                  <span class="tag-badge sec-violation">Hostile Candidate (shell=True)</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-run-hostile" data-testid="btn-run-hostile">
                ⚡ Run Heal Pipeline →
              </button>
            </div>

            <div class="code-snippet">def test_health_metrics():
    h = SystemHealth()
>   assert h.check_status() == 'HEALTHY_200'
E   AssertionError: assert 'ONLINE' == 'HEALTHY_200'</div>

            <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">
              Security Blast Radius Verification: Candidate proposal introduces subprocess shell=True. Engine must halt and refuse write gate.
            </div>
          </div>

          <!-- Item 4: PlaywrightFlake -->
          <div class="detail-card" data-testid="inbox-item-flake" id="card-flake">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 14px; font-weight: 600; font-family: var(--font-mono);">tests/test_flake.py::test_intermittent_locator</div>
                <div style="display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;">
                  <span class="tag-badge sec-violation">INTERMITTENT</span>
                  <span class="tag-badge prod-bug" data-testid="badge-flake">FLAKY_TEST</span>
                  <span class="tag-badge test-bug">Owner: TestHealerAgent</span>
                  <span class="tag-badge test-bug">Scope: tests/test_flake.py</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-view-flake" data-testid="btn-view-flake">
                ⚡ Inspect Flake Variance →
              </button>
            </div>
            <div class="code-snippet">tests/test_flake.py::test_intermittent_locator FAILED
E   AssertionError: Timeout 3000ms waiting for locator button#checkout
--- Multi-Run Execution History ---
Run 1: PASSED | Run 2: FAILED | Run 3: PASSED</div>
            <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">
              Intermittent Timing Instability: Locator race condition detected across repeat test iterations.
            </div>
          </div>

          <!-- Item 5: EnvironmentNoise -->
          <div class="detail-card" data-testid="inbox-item-noise" id="card-noise">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 14px; font-weight: 600; font-family: var(--font-mono);">tests/test_api.py::test_database_connection</div>
                <div style="display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;">
                  <span class="tag-badge sec-violation">INFRA_BLOCKER</span>
                  <span class="tag-badge sec-violation" data-testid="badge-noise">ENVIRONMENT_NOISE</span>
                  <span class="tag-badge test-bug">DevOps / SRE Escalation</span>
                  <span class="tag-badge sec-violation">DeveloperAgent Modification PROHIBITED</span>
                </div>
              </div>
              <button class="btn-action-primary" id="btn-view-noise" data-testid="btn-view-noise">
                ⚡ Triage Infrastructure →
              </button>
            </div>
            <div class="code-snippet">ConnectionRefusedError: [Errno 111] Connection refused on 127.0.0.1:5432
E   ConnectionRefusedError: address already in use or service offline</div>
            <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">
              External Dependency Outage: Database port 5432 unreachable. Automated code changes strictly prohibited.
            </div>
          </div>
        </div>
      </section>

      <!-- PANEL 2: SPRINT BOARD -->
      <section class="view-panel" id="panel-sprint">
        <div class="view-header">
          <div class="view-title-group">
            <h2>Governed Multi-Agent Sprint Execution</h2>
            <p id="sprint-subhead">Topological DAG orchestration with architectural verification gates.</p>
          </div>
          <button class="btn-action-primary" id="btn-goto-diff">Review Staged Diff →</button>
        </div>

        <div class="sprint-timeline" id="sprint-cards-container">
          <!-- Step 1: CIFailureIngestor -->
          <div class="agent-card passed-step" id="card-step-1" data-testid="board-card-classify">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>1. RequirementsAgent / CIFailureIngestor</span>
                <span class="agent-tier-badge">TIER_2_SENIOR_SWE</span>
              </div>
              <span class="tag-badge prod-bug" id="badge-step-1">CLASSIFIED: PRODUCT_BUG</span>
            </div>
            <div class="agent-body" id="body-step-1">
              Ingested failure trace from test execution. Synthesized deterministic Acceptance Criteria. High risk audit flags verified.
            </div>
            <div class="agent-scope-bar">
              Scope: Read-only symbol indexer (zero workspace mutations).
            </div>
          </div>

          <!-- Step 2: TicketRouter & Orchestrator -->
          <div class="agent-card passed-step" id="card-step-2" data-testid="board-card-route">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>2. ScrumMasterOrchestrator &amp; TicketRouter</span>
                <span class="agent-tier-badge">TIER_1_TECH_LEAD</span>
              </div>
              <span class="tag-badge test-bug" id="badge-step-2">ROUTED: HEAL-PROD-001</span>
            </div>
            <div class="agent-body" id="body-step-2">
              Constructed DAG and routed ticket to DeveloperAgent. Restricted allowed files to strictly exclude tests/*.
            </div>
            <div class="agent-scope-bar" id="scope-step-2">
              Allowed Files: ['src/InMemoryLedger.py']
            </div>
          </div>

          <!-- Step 3: WorkerAgent -->
          <div class="agent-card passed-step" id="card-step-3" data-testid="board-card-proposal">
            <div class="agent-header">
              <div class="agent-name-role">
                <span id="title-step-3">3. DeveloperAgent</span>
                <span class="agent-tier-badge" id="tier-step-3">TIER_3_JUNIOR_SWE</span>
              </div>
              <span class="tag-badge prod-bug" id="badge-step-3">PROPOSAL SYNTHESIZED</span>
            </div>
            <div class="agent-body" id="body-step-3">
              Synthesized defensive patch for src/InMemoryLedger.py using LocalHeuristicEngine. Added negative value guard.
            </div>
            <div class="agent-scope-bar" id="scope-step-3">
              Target File: src/InMemoryLedger.py • Lines modified: 4
            </div>
          </div>

          <!-- Step 4: AST Guard & QA Critic -->
          <div class="agent-card passed-step" id="card-step-4" data-testid="board-card-critic">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>4. ASTPatchGuard &amp; QACriticAgent</span>
                <span class="agent-tier-badge">TIER_4_QA_CRITIC</span>
              </div>
              <span class="tag-badge sec-violation" id="badge-step-4" style="color: var(--status-green); background: var(--status-green-bg); border-color: var(--status-green-border);">VERIFIED PASS</span>
            </div>
            <div class="agent-body" id="body-step-4">
              Line-by-line rubric evaluation completed. No syntax errors, no timing attacks, zero assertion erosion verified.
            </div>
            <div class="agent-scope-bar">
              Verdicts: 1/1 AC PASS • Zero Assertion Erosion: PASS
            </div>
          </div>

          <!-- Step 5: Security Blast Radius -->
          <div class="agent-card passed-step" id="card-step-5" data-testid="board-card-security">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>5. SecurityBlastRadiusAgent</span>
                <span class="agent-tier-badge">TIER_4_QA_CRITIC</span>
              </div>
              <span class="tag-badge test-bug" id="badge-step-5">0 CRITICAL FINDINGS</span>
            </div>
            <div class="agent-body" id="body-step-5">
              Static AST security pass verified zero SQL injection, zero shell=True invocations, zero path traversal escapes, and constant-time secrets.
            </div>
            <div class="agent-scope-bar" id="scope-step-5">
              Blast Radius: ISOLATED (src/InMemoryLedger.py only)
            </div>
          </div>

          <!-- Step 6: Sandbox Executor -->
          <div class="agent-card passed-step" id="card-step-6" data-testid="board-card-sandbox">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>6. AutomationTesterAgent &amp; Sandbox</span>
                <span class="agent-tier-badge">TIER_3_JUNIOR_SWE</span>
              </div>
              <span class="tag-badge sec-violation" id="badge-step-6" style="color: var(--status-green); background: var(--status-green-bg); border-color: var(--status-green-border);">SANDBOX PASS (3/3)</span>
            </div>
            <div class="agent-body" id="body-step-6">
              Executed test suite across 3 isolated ephemeral git worktrees (repeat=3). Clean deterministic pass with zero flakiness.
            </div>
            <div class="agent-scope-bar" id="scope-step-6">
              Runs: 3/3 Passed • Exit Code: 0
            </div>
          </div>

          <!-- Step 7: Staged in Write Gate -->
          <div class="agent-card active-step" id="card-step-7" data-testid="board-card-staged">
            <div class="agent-header">
              <div class="agent-name-role">
                <span>7. HumanWriteGateController</span>
                <span class="agent-tier-badge">GOVERNED WRITE GATE</span>
              </div>
              <span class="tag-badge sec-violation" id="badge-step-7" style="background: var(--status-amber-bg); color: var(--status-amber); border-color: var(--status-amber-border);">AWAITING APPROVAL</span>
            </div>
            <div class="agent-body" id="body-step-7">
              Safety pre-apply snapshot pinned in Time Machine. Workspace remains 100% byte-for-byte untouched until human write-gate authorization.
            </div>
            <div class="agent-scope-bar" id="scope-step-7">
              Staged Sprint: <code id="board-sprint-id">sprint_ready</code>
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
            <span id="diff-file-label">src/InMemoryLedger.py (Unified Diff vs Baseline)</span>
            <span id="diff-assertion-label">Test assertions preserved (2/2)</span>
          </div>
          <div class="diff-content" id="diff-text">--- a/src/InMemoryLedger.py (Baseline)
+++ b/src/InMemoryLedger.py (Staged Proposal)
@@ -10,6 +10,10 @@
     def deposit(self, amount: float) -> float:
+        if amount &lt;= 0:
+            raise ValueError("Deposit amount must be positive")
         self._balance += amount
         return self._balance</div>
        </div>

        <!-- Approval & Verification Bar -->
        <div class="approval-toolbar" id="toolbar-approval">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Approver Identity (QA Lead)</label>
              <input type="text" class="form-input" id="input-approver" data-testid="input-approver" value="QA Lead" placeholder="Your name or handle">
            </div>
            <div class="form-group" style="flex: 2;">
              <label class="form-label">Audit Review Comment</label>
              <input type="text" class="form-input" id="input-comment" data-testid="input-comment" value="Verified negative deposit ValueError guard; zero assertion erosion" placeholder="Reason for write authorization">
            </div>
            <div class="form-group" style="flex: 1.5;">
              <label class="form-label">Approver Guidance Note</label>
              <input type="text" class="form-input" id="input-approver-note" data-testid="input-approver-note" placeholder="Optional review note / guidance">
            </div>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <label style="display: flex; align-items: center; gap: 8px; font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); cursor: pointer;">
              <input type="checkbox" id="chk-open-pr" data-testid="chk-open-pr" checked style="accent-color: var(--copper);">
              <span>Push branch <code>hermes/heal-&lt;id&gt;</code> and open PR</span>
            </label>
            <button class="btn-top" id="btn-request-changes" data-testid="btn-request-changes" style="font-size: 11px; color: var(--status-amber); border-color: var(--status-amber-border);">
              ↩ Request Changes
            </button>
          </div>

          <div id="pr-result-banner" data-testid="pr-result-banner" style="display: none; background: rgba(201,133,74,0.12); border: 1px solid rgba(201,133,74,0.3); border-radius: 4px; padding: 10px 14px; margin-bottom: 12px; font-family: var(--font-mono); font-size: 11px;">
            <div style="font-weight: 600; color: var(--copper); margin-bottom: 4px;" id="pr-banner-title">🚀 Branch Created</div>
            <div id="pr-banner-details" style="color: var(--text-main);"></div>
          </div>

          <div style="display: flex; gap: 12px; align-items: center; justify-content: space-between; border-top: 1px solid var(--border-hairline); padding-top: 14px;">
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);">
              Pre-Apply Snapshot: <span id="snapshot-id-display" data-testid="snapshot-id-display" style="color: var(--copper);">snap_pending_approval</span>
              <div class="audit-approval-line" id="audit-approval-line" data-testid="audit-approval-line"></div>
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

        <div style="display: flex; flex-direction: column; gap: 12px;" id="tm-snapshot-list">
          <div class="detail-card">
            <div class="detail-card-header">
              <div>
                <div style="font-size: 13px; font-weight: 600; font-family: var(--font-mono);" id="tm-active-snap-id">snap_safety_pre_apply_HEAL-PROD-001</div>
                <div style="display: flex; gap: 6px; margin-top: 4px;">
                  <span class="tag-badge test-bug">Type: PRE_APPLY_SAFETY</span>
                  <span class="tag-badge test-bug" id="tm-active-target">Target: src/InMemoryLedger.py</span>
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

      <div class="drawer-footer" style="display: flex; gap: 8px; flex-wrap: wrap;">
        <button class="btn-top" id="btn-copy-markdown" data-testid="btn-copy-markdown">📋 Copy Markdown</button>
        <button class="btn-top" id="btn-export-md" data-testid="btn-export-md">📥 Download .md</button>
        <button class="btn-top" id="btn-export-json" data-testid="btn-export-json">📥 Download .json</button>
        <button class="btn-top" id="btn-export-html" data-testid="btn-export-html">🌐 View HTML</button>
      </div>
    </div>
  </div>

  <!-- Provider Drawer Overlay -->
  <div class="provider-overlay" id="provider-overlay">
    <div class="provider-drawer" id="provider-drawer" data-testid="drawer-providers">
      <div class="drawer-header">
        <div class="drawer-title">Frontier &amp; Local Provider Architecture</div>
        <button class="btn-close" id="btn-close-providers">&times;</button>
      </div>
      <div style="font-size: 12px; color: var(--text-dim); margin-bottom: 14px; font-family: var(--font-mono);">
        Configure any of 19 local and cloud inference backends. All calls route through standardized zero-SDK adapter.
      </div>
      <div style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px;" id="provider-list-container">
        <!-- Dynamically filled with 19 providers -->
      </div>
      <div style="border-top: 1px solid var(--border-hairline); padding-top: 14px; margin-top: 14px; display: flex; gap: 8px; justify-content: flex-end;">
        <button class="btn-top" id="btn-test-provider" data-testid="btn-test-provider">⚡ Test Connection</button>
        <button class="btn-action-primary" id="btn-save-provider" data-testid="btn-save-provider">Save &amp; Activate</button>
      </div>
    </div>
  </div>

  <!-- Modal: Connect Repository -->
  <div class="modal-overlay" id="modal-connect-repo">
    <div class="modal-box">
      <div class="drawer-header" style="margin-bottom: 0;">
        <div class="drawer-title">Connect Repository</div>
        <button class="btn-close" id="btn-close-connect">&times;</button>
      </div>
      <div style="font-size: 12px; color: var(--text-muted);">
        Point Hermes at a local repository or clone path to auto-discover tests and begin autonomous triage.
      </div>
      <div class="form-group">
        <label class="form-label">Repository Directory Path</label>
        <input type="text" class="form-input" id="input-connect-path" data-testid="input-repo-path" placeholder="e.g. /path/to/my-service or C:/repos/my-service">
      </div>
      <div class="form-group">
        <label class="form-label">Repository Display Name (Optional)</label>
        <input type="text" class="form-input" id="input-connect-name" data-testid="input-repo-name" placeholder="e.g. CheckoutService">
      </div>
      <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 8px;">
        <button class="btn-top" id="btn-cancel-connect">Cancel</button>
        <button class="btn-action-primary" id="btn-submit-connect" data-testid="btn-submit-connect">Connect &amp; Discover Tests</button>
      </div>
    </div>
  </div>

  <!-- Modal: Story Sprint -->
  <div class="modal-overlay" id="modal-story-sprint">
    <div class="modal-box">
      <div class="drawer-header" style="margin-bottom: 0;">
        <div class="drawer-title">✨ Run Feature Story Sprint</div>
        <button class="btn-close" id="btn-close-story">&times;</button>
      </div>
      <div style="font-size: 12px; color: var(--text-muted);">
        Executes the full 8-agent topological DAG (ProductManager &rarr; SpecWriter &rarr; Architect &rarr; Developer &rarr; QACritic &rarr; SecurityReviewer).
      </div>
      <div class="form-group">
        <label class="form-label">Feature User Story Prompt</label>
        <textarea class="form-input" id="input-story-prompt" data-testid="input-story-prompt" rows="4" style="resize: vertical; font-family: var(--font-mono); font-size: 12px;" placeholder="Describe required capability, e.g. 'Add coupon discount code validation to checkout service'"></textarea>
      </div>
      <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 8px;">
        <button class="btn-top" id="btn-cancel-story">Cancel</button>
        <button class="btn-action-primary" id="btn-submit-story" data-testid="btn-submit-story">Launch Governed DAG</button>
      </div>
    </div>
  </div>
    </div>
  </div>

  <!-- ROI Formula Drawer / Overlay (AG-11) -->
  <div class="provider-overlay" id="roi-modal-overlay">
    <div class="provider-drawer" id="roi-drawer" data-testid="roi-modal" style="width: 500px;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-hairline); padding-bottom: 12px; margin-bottom: 16px;">
        <h3 style="font-size: 14px; font-weight: 600; color: var(--copper);">Executive ROI &amp; Governance Mathematical Breakdown</h3>
        <button class="btn-top" id="btn-close-roi" style="padding: 2px 8px;">✕</button>
      </div>
      <div style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); line-height: 1.6;">
        <p style="margin-bottom: 8px; color: var(--text-main);"><strong>Transparent Formula Standard:</strong></p>
        <div style="background: var(--bg-card); padding: 12px; border-radius: 3px; border: 1px solid var(--border-hairline); margin-bottom: 16px; font-size: 11px;">
          Hours Saved = (Product Bugs × 4.2h) + (Test Drifts × 2.0h) + (Flakes × 1.5h) + (Hostiles Blocked × 3.0h)<br><br>
          Estimated ROI ($) = Total Hours Saved × Engineering Hourly Rate ($125/hr)
        </div>
        <div id="roi-breakdown-details" style="font-size: 11px;">
          <!-- Dynamically populated from /api/telemetry/roi -->
        </div>
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
      classification: "PRODUCT_BUG",
      ownerAgent: "DeveloperAgent",
      scope: ["src/InMemoryLedger.py"],
      allowedFiles: ["src/InMemoryLedger.py"],
      status: "FAILING", // FAILING, AWAITING_WRITE_GATE, APPLIED, ROLLED_BACK, FAILED
      sprintId: null,
      snapshotId: null,
      approver: "QA Lead",
      diffText: "",
      auditLog: "",
      rejectionReason: null,
    };

    // DOM Elements
    const navItems = document.querySelectorAll('.nav-item');
    const viewPanels = document.querySelectorAll('.view-panel');
    const labelStatus = document.getElementById('label-status');
    const pillStatus = document.getElementById('pill-status');
    const labelWorkspace = document.getElementById('label-workspace');
    const btnRunHeal = document.getElementById('btn-run-heal');
    const btnRunDrift = document.getElementById('btn-run-drift');
    const btnRunHostile = document.getElementById('btn-run-hostile');
    const btnApprove = document.getElementById('btn-approve');
    const btnRewind = document.getElementById('btn-rewind');
    const inputApprover = document.getElementById('input-approver');
    const inputComment = document.getElementById('input-comment');
    const auditApprovalLine = document.getElementById('audit-approval-line');
    const snapshotIdDisplay = document.getElementById('snapshot-id-display');
    const diffStatusLabel = document.getElementById('diff-status-label');
    const diffStatusPill = document.getElementById('diff-status-pill');
    const diffTextContainer = document.getElementById('diff-text');
    const diffFileLabel = document.getElementById('diff-file-label');
    const diffAssertionLabel = document.getElementById('diff-assertion-label');
    const auditOverlay = document.getElementById('audit-overlay');
    const btnAudit = document.getElementById('btn-audit');
    const btnCloseAudit = document.getElementById('btn-close-audit');
    const btnCopyMarkdown = document.getElementById('btn-copy-markdown');
    const auditContent = document.getElementById('audit-content');
    const btnGotoDiff = document.getElementById('btn-goto-diff');
    const btnReseed = document.getElementById('btn-reseed-demo');
    const btnTmRestore = document.getElementById('btn-tm-restore');
    const chkOpenPr = document.getElementById('chk-open-pr');
    const prResultBanner = document.getElementById('pr-result-banner');
    const prBannerTitle = document.getElementById('pr-banner-title');
    const prBannerDetails = document.getElementById('pr-banner-details');
    const inputApproverNote = document.getElementById('input-approver-note');
    const btnRequestChanges = document.getElementById('btn-request-changes');

    // ROI Telemetry DOM Elements (AG-11)
    const roiValHours = document.getElementById('roi-val-hours');
    const roiValMttr = document.getElementById('roi-val-mttr');
    const roiValFlakes = document.getElementById('roi-val-flakes');
    const roiValHostiles = document.getElementById('roi-val-hostiles');
    const roiValDollar = document.getElementById('roi-val-dollar');
    const roiMetricDollar = document.getElementById('roi-metric-dollar');
    const roiModalOverlay = document.getElementById('roi-modal-overlay');
    const btnCloseRoi = document.getElementById('btn-close-roi');
    const roiBreakdownDetails = document.getElementById('roi-breakdown-details');

    async function loadROITelemetry() {
      try {
        const data = await apiGet('/api/telemetry/roi');
        if (data) {
          if (roiValHours) roiValHours.innerText = `${data.engineering_hours_saved} hrs`;
          if (roiValMttr) {
            roiValMttr.innerHTML = `${data.manual_mttr_hours}h → ${data.autonomous_mttr_minutes}m <span class="roi-badge-green">-${data.mttr_reduction_percent}%</span>`;
          }
          if (roiValFlakes) roiValFlakes.innerText = `${data.quarantined_flakes} Flake${data.quarantined_flakes === 1 ? '' : 's'}`;
          if (roiValHostiles) roiValHostiles.innerText = `${data.blocked_hostile_patches} Blocked`;
          if (roiValDollar) roiValDollar.innerText = `$${Math.round(data.dollar_roi_usd).toLocaleString()} ROI ℹ️`;

          if (roiBreakdownDetails && data.formula_breakdown && data.formula_breakdown.components) {
            const c = data.formula_breakdown.components;
            roiBreakdownDetails.innerHTML = `
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <span>Product Bugs Healed (${c.product_bugs.count} × ${c.product_bugs.hours_per_unit}h):</span>
                <strong style="color:var(--text-main);">${c.product_bugs.subtotal_hours} hrs</strong>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <span>Test Drifts Healed (${c.test_drifts.count} × ${c.test_drifts.hours_per_unit}h):</span>
                <strong style="color:var(--text-main);">${c.test_drifts.subtotal_hours} hrs</strong>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <span>Flakes Quarantined (${c.quarantined_flakes.count} × ${c.quarantined_flakes.hours_per_unit}h):</span>
                <strong style="color:var(--text-main);">${c.quarantined_flakes.subtotal_hours} hrs</strong>
              </div>
              <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span>Hostile Attacks Blocked (${c.blocked_hostiles.count} × ${c.blocked_hostiles.hours_per_unit}h):</span>
                <strong style="color:var(--text-main);">${c.blocked_hostiles.subtotal_hours} hrs</strong>
              </div>
              <div style="border-top:1px solid var(--border-hairline); padding-top:8px; display:flex; justify-content:space-between; font-weight:600; color:var(--copper);">
                <span>Total Net ROI ($${data.hourly_rate_usd}/hr rate):</span>
                <span>$${Math.round(data.dollar_roi_usd).toLocaleString()} USD</span>
              </div>
            `;
          }
        }
      } catch (e) {
        console.error("ROI Telemetry error:", e);
      }
    }

    if (roiMetricDollar && roiModalOverlay) {
      roiMetricDollar.addEventListener('click', () => {
        roiModalOverlay.classList.add('open');
      });
    }
    if (btnCloseRoi && roiModalOverlay) {
      btnCloseRoi.addEventListener('click', () => {
        roiModalOverlay.classList.remove('open');
      });
    }

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

    // Selection switching in left rail
    function selectInboxRow(name) {
      document.querySelectorAll('.inbox-row').forEach(row => {
        row.classList.toggle('selected', row.dataset.target === name);
      });
    }

    document.querySelectorAll('.inbox-row').forEach(row => {
      row.addEventListener('click', () => {
        const target = row.dataset.target;
        selectInboxRow(target);
        if (target === 'ledger') loadLedgerWorkspace();
        else if (target === 'drift') loadDriftWorkspace();
        else if (target === 'hostile') loadHostileWorkspace();
        else if (target === 'flake') loadFlakeWorkspace();
        else if (target === 'noise') loadNoiseWorkspace();
      });
    });

    // Workspace Loaders
    async function loadLedgerWorkspace() {
      try {
        const data = await apiPost('/api/demo/ledger');
        setWorkspaceData(data);
      } catch (e) {
        console.error("Ledger init error:", e);
      }
    }

    async function loadDriftWorkspace() {
      try {
        const data = await apiPost('/api/demo/drift');
        setWorkspaceData(data);
      } catch (e) {
        console.error("Drift init error:", e);
      }
    }

    async function loadHostileWorkspace() {
      try {
        const data = await apiPost('/api/demo/hostile');
        setWorkspaceData(data);
      } catch (e) {
        console.error("Hostile init error:", e);
      }
    }

    async function loadFlakeWorkspace() {
      try {
        const data = await apiPost('/api/demo/flake');
        setWorkspaceData(data);
        switchTab('inbox');
      } catch (e) {
        console.error("Flake init error:", e);
      }
    }

    async function loadNoiseWorkspace() {
      try {
        const data = await apiPost('/api/demo/noise');
        setWorkspaceData(data);
        switchTab('inbox');
      } catch (e) {
        console.error("Noise init error:", e);
      }
    }

    const btnViewFlake = document.getElementById('btn-view-flake');
    if (btnViewFlake) btnViewFlake.addEventListener('click', () => loadFlakeWorkspace());
    const btnViewNoise = document.getElementById('btn-view-noise');
    if (btnViewNoise) btnViewNoise.addEventListener('click', () => loadNoiseWorkspace());

    function setWorkspaceData(data) {
      state.workspaceId = data.workspace_id;
      state.workspaceName = data.workspace_name;
      state.failingTest = data.failing_test;
      state.classification = data.classification;
      state.ownerAgent = data.owner_agent;
      state.scope = data.scope || [];
      state.allowedFiles = data.allowed_files || [];
      state.status = data.status || "FAILING";
      state.sprintId = data.active_sprint_id || null;
      state.snapshotId = data.pre_apply_snapshot_id || null;
      state.approver = data.approver || "QA Lead";
      state.rejectionReason = null;
      selectInboxRow(data.workspace_name === 'PlaywrightDrift' ? 'drift' : (data.workspace_name === 'HostilePatch' ? 'hostile' : 'ledger'));
      updateUI();
    }

    // Approver input listener (AG-7)
    function checkApproverValidity() {
      const hasName = inputApprover.value.trim().length > 0;
      if (state.status === "AWAITING_WRITE_GATE") {
        btnApprove.disabled = !hasName;
      }
    }
    inputApprover.addEventListener('input', checkApproverValidity);

    function updateUI() {
      labelWorkspace.innerText = state.workspaceName;
      const targetLabel = state.scope[0] || (state.workspaceName === 'PlaywrightDrift' ? 'tests/test_cart.py' : (state.workspaceName === 'HostilePatch' ? 'src/service.py' : 'src/InMemoryLedger.py'));
      diffFileLabel.innerText = `${targetLabel} (Unified Diff vs Baseline)`;
      document.getElementById('tm-active-target').innerText = `Target: ${targetLabel}`;

      if (state.workspaceName === 'PlaywrightDrift') {
        diffAssertionLabel.innerText = "Invariant: Test assertions preserved (1/1)";
      } else {
        diffAssertionLabel.innerText = "Invariant: Test assertions preserved (2/2)";
      }

      // Configure Step Cards for Workspace Type
      const isDrift = state.workspaceName === 'PlaywrightDrift';
      const isHostile = state.workspaceName === 'HostilePatch';

      if (isDrift) {
        document.getElementById('badge-step-1').innerText = "CLASSIFIED: TEST_BUG";
        document.getElementById('badge-step-2').innerText = "ROUTED: HEAL-TEST-001 (TestHealerAgent)";
        document.getElementById('scope-step-2').innerText = "Allowed Files: ['tests/test_cart.py'] (DeveloperAgent visibly unavailable)";
        document.getElementById('title-step-3').innerText = "3. TestHealerAgent (DeveloperAgent Prohibited)";
        document.getElementById('tier-step-3').innerText = "TIER_3_JUNIOR_SWE";
        document.getElementById('badge-step-3').innerText = "ASSERTION DRIFT HEALED";
        document.getElementById('body-step-3').innerText = "TestHealerAgent updated drifted assertion from 'CONFIRMED' to 'ORDER_CONFIRMED' in tests/test_cart.py. Product code src/cart.py remains byte-for-byte untouched.";
        document.getElementById('scope-step-3').innerText = "Target File: tests/test_cart.py • DeveloperAgent Unavailable";
        document.getElementById('scope-step-5').innerText = "Blast Radius: ISOLATED (tests/test_cart.py only)";
      } else if (isHostile) {
        document.getElementById('badge-step-1').innerText = "CLASSIFIED: PRODUCT_BUG";
        document.getElementById('badge-step-2').innerText = "ROUTED: HEAL-PROD-001";
        document.getElementById('scope-step-2').innerText = "Allowed Files: ['src/service.py']";
        document.getElementById('title-step-3').innerText = "3. DeveloperAgent";
        document.getElementById('tier-step-3').innerText = "TIER_3_JUNIOR_SWE";
        document.getElementById('badge-step-3').innerText = "HOSTILE PROPOSAL";
        document.getElementById('body-step-3').innerText = "DeveloperAgent proposed patch for src/service.py containing subprocess.run('echo HEALTHY_200', shell=True).";
        document.getElementById('scope-step-3').innerText = "Target File: src/service.py • Injected subprocess call";
        document.getElementById('scope-step-5').innerText = "Blast Radius: BLOCKED (shell=True command injection attempt)";
      } else {
        document.getElementById('badge-step-1').innerText = "CLASSIFIED: PRODUCT_BUG";
        document.getElementById('badge-step-2').innerText = "ROUTED: HEAL-PROD-001";
        document.getElementById('scope-step-2').innerText = "Allowed Files: ['src/InMemoryLedger.py']";
        document.getElementById('title-step-3').innerText = "3. DeveloperAgent";
        document.getElementById('tier-step-3').innerText = "TIER_3_JUNIOR_SWE";
        document.getElementById('badge-step-3').innerText = "PROPOSAL SYNTHESIZED";
        document.getElementById('body-step-3').innerText = "Synthesized defensive patch for src/InMemoryLedger.py using LocalHeuristicEngine. Added negative value guard.";
        document.getElementById('scope-step-3').innerText = "Target File: src/InMemoryLedger.py • Lines modified: 4";
        document.getElementById('scope-step-5').innerText = "Blast Radius: ISOLATED (src/InMemoryLedger.py only)";
      }

      // Status labels and pills
      if (state.status === "FAILING") {
        labelStatus.innerText = "STATUS: FAILING (RED)";
        pillStatus.className = "meta-pill status-red";
        diffStatusLabel.innerText = "STATUS: FAILING";
        diffStatusPill.className = "meta-pill status-red";
        btnApprove.style.display = "inline-flex";
        btnApprove.disabled = true;
        btnRewind.disabled = true;
        resetRailStyles();
        auditApprovalLine.innerText = "";
      } else if (state.status === "AWAITING_WRITE_GATE") {
        labelStatus.innerText = "STATUS: AWAITING APPROVAL";
        pillStatus.className = "meta-pill status-amber";
        diffStatusLabel.innerText = "STATUS: STAGED";
        diffStatusPill.className = "meta-pill status-amber";
        btnApprove.style.display = "inline-flex";
        checkApproverValidity();
        btnRewind.disabled = true;
        setRailPassedUpTo(7);
        document.getElementById('card-step-7').className = "agent-card active-step";
        auditApprovalLine.innerText = "";
      } else if (state.status === "APPLIED") {
        labelStatus.innerText = "STATUS: APPLIED (GREEN)";
        pillStatus.className = "meta-pill status-green";
        diffStatusLabel.innerText = "STATUS: APPLIED (100% PASSING)";
        diffStatusPill.className = "meta-pill status-green";
        btnApprove.style.display = "inline-flex";
        btnApprove.disabled = true;
        btnRewind.disabled = false;
        setRailPassedUpTo(7);
        document.getElementById('card-step-7').className = "agent-card passed-step";
        const approverName = state.approver || inputApprover.value || "QA Lead";
        auditApprovalLine.innerText = `Approved by ${approverName} · Time Machine snapshot ${state.snapshotId || 'snap_applied'}`;
      } else if (state.status === "ROLLED_BACK") {
        labelStatus.innerText = "STATUS: ROLLED_BACK (RED)";
        pillStatus.className = "meta-pill status-red";
        diffStatusLabel.innerText = "STATUS: ROLLED_BACK (BASELINE RESTORED)";
        diffStatusPill.className = "meta-pill status-red";
        btnApprove.style.display = "inline-flex";
        btnApprove.disabled = true;
        btnRewind.disabled = true;
        resetRailStyles();
        auditApprovalLine.innerText = `Rolled back to baseline snapshot ${state.snapshotId || 'snap_restored'}`;
      } else if (state.status === "FAILED") {
        // Blocked write gate (AG-9)
        labelStatus.innerText = "STATUS: REJECTED (SECURITY BLAST RADIUS)";
        pillStatus.className = "meta-pill status-red";
        diffStatusLabel.innerText = "STATUS: REJECTED BY SECURITY GATE";
        diffStatusPill.className = "meta-pill status-red";
        // Approve button is completely GONE (AG-9)
        btnApprove.style.display = "none";
        btnRewind.disabled = true;

        // Rail stops at Step 5 (Security Blast Radius)
        setRailPassedUpTo(4);
        const card5 = document.getElementById('card-step-5');
        card5.className = "agent-card rejected-step";
        document.getElementById('badge-step-5').className = "tag-badge sec-violation";
        document.getElementById('badge-step-5').innerText = "REJECTED: SEC-SUBPROCESS-001";
        const reasonText = state.rejectionReason || "SEC-SUBPROCESS-001: shell=True (subprocess execution with shell=True is dangerous and invites command injection)";
        document.getElementById('body-step-5').innerText = reasonText;

        // Steps 6 and 7 blocked
        document.getElementById('card-step-6').className = "agent-card blocked-step";
        document.getElementById('badge-step-6').innerText = "BLOCKED (NOT REACHED)";
        document.getElementById('card-step-7').className = "agent-card blocked-step";
        document.getElementById('badge-step-7').innerText = "BLOCKED (WRITE REFUSED)";
        auditApprovalLine.innerText = "Write Gate Blocked: Security violation SEC-SUBPROCESS-001. No changes staged.";
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

    function resetRailStyles() {
      for (let i = 1; i <= 6; i++) {
        document.getElementById(`card-step-${i}`).className = "agent-card passed-step";
      }
      document.getElementById('card-step-7').className = "agent-card active-step";
    }

    function setRailPassedUpTo(step) {
      for (let i = 1; i <= 7; i++) {
        const card = document.getElementById(`card-step-${i}`);
        if (i <= step) {
          card.className = "agent-card passed-step";
        } else {
          card.className = "agent-card blocked-step";
        }
      }
    }

    // Run Heal Action
    async function executeHeal(triggerBtn) {
      triggerBtn.disabled = true;
      const originalText = triggerBtn.innerText;
      triggerBtn.innerText = "⚡ Running Governed Pipeline...";

      try {
        if (!state.workspaceId) {
          await loadLedgerWorkspace();
        }

        const res = await apiPost(`/api/demo/${state.workspaceId}/heal`);
        state.status = res.status || "AWAITING_WRITE_GATE";
        state.sprintId = res.sprint_id;
        state.snapshotId = res.snapshot_id || (res.staged_proposal && res.staged_proposal.snapshot_id);

        if (state.status === "FAILED") {
          // Check for security findings
          if (res.attempts && res.attempts.length > 0) {
            const lastAttempt = res.attempts[res.attempts.length - 1];
            state.rejectionReason = lastAttempt.rejection_reason || "SEC-SUBPROCESS-001: shell=True";
          } else {
            state.rejectionReason = res.error || "SEC-SUBPROCESS-001: shell=True";
          }
        } else {
          state.rejectionReason = null;
        }

        // Fetch diff
        try {
          const diffRes = await apiGet(`/api/demo/${state.workspaceId}/diff`);
          state.diffText = diffRes.diff || "";
        } catch (e) {
          state.diffText = "";
        }

        // Fetch audit
        try {
          const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
          state.auditLog = auditRes.markdown || "";
          auditContent.innerText = state.auditLog;
        } catch (e) {}

        updateUI();
        switchTab('sprint');
        loadROITelemetry();
      } catch (e) {
        alert("Sprint heal error: " + e.message);
      } finally {
        triggerBtn.disabled = false;
        triggerBtn.innerText = originalText;
      }
    }

    btnRunHeal.addEventListener('click', async () => {
      if (state.workspaceName !== 'InMemoryLedger') {
        await loadLedgerWorkspace();
      }
      executeHeal(btnRunHeal);
    });
    if (btnRunDrift) {
      btnRunDrift.addEventListener('click', async () => {
        if (state.workspaceName !== 'PlaywrightDrift') {
          await loadDriftWorkspace();
        }
        executeHeal(btnRunDrift);
      });
    }
    if (btnRunHostile) {
      btnRunHostile.addEventListener('click', async () => {
        if (state.workspaceName !== 'HostilePatch') {
          await loadHostileWorkspace();
        }
        executeHeal(btnRunHostile);
      });
    }

    // Approve Action
    btnApprove.addEventListener('click', async () => {
      btnApprove.disabled = true;
      btnApprove.innerText = "Applying & Verifying Sandbox...";

      try {
        const approver = inputApprover.value.trim() || "QA Lead";
        const comment = inputComment.value || "";

        const res = await apiPost(`/api/demo/${state.workspaceId}/approve`, {
          approver: approver,
          comment: comment,
          verify: true,
        });

        if (res.success || res.status === "APPLIED") {
          state.status = "APPLIED";
          state.approver = approver;
          state.snapshotId = res.snapshot_id || state.snapshotId;

          // Pull Request creation if checked
          if (chkOpenPr && chkOpenPr.checked) {
            try {
              const prRes = await apiPost(`/api/demo/${state.workspaceId}/pr`, {
                branch_name: `hermes/heal-${state.workspaceId.slice(-8)}`,
                approver: approver,
                body: comment,
              });
              if (prRes.status === "success" && prResultBanner) {
                prResultBanner.style.display = "block";
                prBannerTitle.innerText = `🚀 Branch '${prRes.branch}' Created`;
                prBannerDetails.innerHTML = prRes.pr_url
                  ? `<a href="${prRes.pr_url}" target="_blank" style="color: var(--copper); text-decoration: underline;">View GitHub Pull Request →</a>`
                  : `Instructions: <code>${prRes.push_cmd}</code>`;
              }
            } catch (e) {
              console.error("PR creation error:", e);
            }
          }

          // Fetch updated audit
          try {
            const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
            state.auditLog = auditRes.markdown || "";
            auditContent.innerText = state.auditLog;
          } catch (e) {}

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

    if (btnRequestChanges) {
      btnRequestChanges.addEventListener('click', () => {
        const note = (inputApproverNote && inputApproverNote.value) || "Changes requested by QA Lead";
        auditApprovalLine.innerText = `Changes requested: "${note}". Routed back to developer.`;
        alert(`Changes requested. Guidance: "${note}"`);
      });
    }

    // Rewind Action
    btnRewind.addEventListener('click', async () => {
      btnRewind.disabled = true;
      btnRewind.innerText = "Rewinding Workspace...";

      try {
        const res = await apiPost(`/api/demo/${state.workspaceId}/rollback`);
        if (res.success || res.status === "ROLLED_BACK") {
          state.status = "ROLLED_BACK";
          if (prResultBanner) prResultBanner.style.display = "none";

          // Fetch updated audit
          try {
            const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
            state.auditLog = auditRes.markdown || "";
            auditContent.innerText = state.auditLog;
          } catch (e) {}

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

    if (btnTmRestore) {
      btnTmRestore.addEventListener('click', () => {
        btnRewind.click();
      });
    }

    // Reseed button
    if (btnReseed) {
      btnReseed.addEventListener('click', () => {
        loadLedgerWorkspace();
      });
    }

    // Connect Repo Modal
    const btnOpenConnect = document.getElementById('btn-open-connect');
    const modalConnect = document.getElementById('modal-connect-repo');
    const btnCloseConnect = document.getElementById('btn-close-connect');
    const btnCancelConnect = document.getElementById('btn-cancel-connect');
    const btnSubmitConnect = document.getElementById('btn-submit-connect');
    const inputConnectPath = document.getElementById('input-connect-path');
    const inputConnectName = document.getElementById('input-connect-name');

    if (btnOpenConnect) btnOpenConnect.addEventListener('click', () => modalConnect.classList.add('open'));
    if (btnCloseConnect) btnCloseConnect.addEventListener('click', () => modalConnect.classList.remove('open'));
    if (btnCancelConnect) btnCancelConnect.addEventListener('click', () => modalConnect.classList.remove('open'));
    if (modalConnect) modalConnect.addEventListener('click', (e) => { if (e.target === modalConnect) modalConnect.classList.remove('open'); });
    if (btnSubmitConnect) {
      btnSubmitConnect.addEventListener('click', async () => {
        const p = inputConnectPath.value.trim();
        const n = inputConnectName.value.trim();
        if (!p) { alert("Please provide a repository path on disk."); return; }
        btnSubmitConnect.disabled = true;
        btnSubmitConnect.innerText = "Scanning & Connecting...";
        try {
          const res = await apiPost('/api/repos/connect', { repo_path: p, name: n || undefined });
          modalConnect.classList.remove('open');
          setWorkspaceData(res);
          loadInboxList();
        } catch (e) {
          alert("Connect error: " + e.message);
        } finally {
          btnSubmitConnect.disabled = false;
          btnSubmitConnect.innerText = "Connect & Discover Tests";
        }
      });
    }

    // Story Sprint Modal
    const btnOpenStory = document.getElementById('btn-open-story');
    const modalStory = document.getElementById('modal-story-sprint');
    const btnCloseStory = document.getElementById('btn-close-story');
    const btnCancelStory = document.getElementById('btn-cancel-story');
    const btnSubmitStory = document.getElementById('btn-submit-story');
    const inputStoryPrompt = document.getElementById('input-story-prompt');

    if (btnOpenStory) btnOpenStory.addEventListener('click', () => modalStory.classList.add('open'));
    if (btnCloseStory) btnCloseStory.addEventListener('click', () => modalStory.classList.remove('open'));
    if (btnCancelStory) btnCancelStory.addEventListener('click', () => modalStory.classList.remove('open'));
    if (modalStory) modalStory.addEventListener('click', (e) => { if (e.target === modalStory) modalStory.classList.remove('open'); });
    if (btnSubmitStory) {
      btnSubmitStory.addEventListener('click', async () => {
        const prompt = inputStoryPrompt.value.trim();
        if (!prompt) { alert("Please describe the user story feature."); return; }
        btnSubmitStory.disabled = true;
        btnSubmitStory.innerText = "Executing Governed DAG...";
        try {
          const res = await apiPost(`/api/demo/${state.workspaceId}/story`, { story_prompt: prompt });
          modalStory.classList.remove('open');
          state.status = res.status || "AWAITING_WRITE_GATE";
          state.sprintId = res.sprint_id;
          state.snapshotId = res.snapshot_id;
          updateUI();
          switchTab('sprint');
        } catch (e) {
          alert("Story sprint error: " + e.message);
        } finally {
          btnSubmitStory.disabled = false;
          btnSubmitStory.innerText = "Launch Governed DAG";
        }
      });
    }

    // Audit Export Handlers
    const btnExportMd = document.getElementById('btn-export-md');
    const btnExportJson = document.getElementById('btn-export-json');
    const btnExportHtml = document.getElementById('btn-export-html');

    if (btnExportMd) btnExportMd.addEventListener('click', () => window.open(`/api/demo/${state.workspaceId}/audit/export?format=markdown`, '_blank'));
    if (btnExportJson) btnExportJson.addEventListener('click', () => window.open(`/api/demo/${state.workspaceId}/audit/export?format=json`, '_blank'));
    if (btnExportHtml) btnExportHtml.addEventListener('click', () => window.open(`/api/demo/${state.workspaceId}/audit/export?format=html`, '_blank'));

    // Provider Drawer Handlers
    const pillProvider = document.getElementById('pill-provider');
    const providerOverlay = document.getElementById('provider-overlay');
    const btnCloseProviders = document.getElementById('btn-close-providers');
    const providerListContainer = document.getElementById('provider-list-container');
    const btnTestProvider = document.getElementById('btn-test-provider');
    const btnSaveProvider = document.getElementById('btn-save-provider');
    let selectedProvider = "ollama";

    async function loadProviders() {
      try {
        const res = await apiGet('/api/providers/config');
        if (!providerListContainer) return;
        providerListContainer.innerHTML = "";
        selectedProvider = res.active_provider || "ollama";
        const labelP = document.getElementById('label-provider');
        if (labelP) labelP.innerText = `${selectedProvider.toUpperCase()} · ACTIVE`;
        (res.providers || []).forEach(p => {
          const item = document.createElement('div');
          item.className = "inbox-row";
          item.style.flexDirection = "row";
          item.style.alignItems = "center";
          item.style.justifyContent = "space-between";
          if (p.name === selectedProvider) item.classList.add('selected');
          item.innerHTML = `
            <div>
              <div style="font-weight: 600; font-family: var(--font-mono); font-size: 12px;">${p.name}</div>
              <div style="font-size: 10px; color: var(--text-dim);">${p.is_local ? 'Local Inference Backend' : 'Cloud Frontier API'}</div>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <span class="tag-badge ${p.is_local ? 'test-bug' : 'prod-bug'}">${p.is_local ? 'LOCAL' : 'CLOUD'}</span>
              ${p.is_active ? '<span class="tag-badge" style="background: rgba(85,158,102,0.2); color: #7ec98f;">ACTIVE</span>' : ''}
            </div>
          `;
          item.addEventListener('click', () => {
            selectedProvider = p.name;
            document.querySelectorAll('#provider-list-container .inbox-row').forEach(r => r.classList.remove('selected'));
            item.classList.add('selected');
          });
          providerListContainer.appendChild(item);
        });
      } catch (e) {}
    }

    if (pillProvider) pillProvider.addEventListener('click', () => { providerOverlay.classList.add('open'); loadProviders(); });
    if (btnCloseProviders) btnCloseProviders.addEventListener('click', () => providerOverlay.classList.remove('open'));
    if (providerOverlay) providerOverlay.addEventListener('click', (e) => { if (e.target === providerOverlay) providerOverlay.classList.remove('open'); });
    if (btnTestProvider) {
      btnTestProvider.addEventListener('click', async () => {
        btnTestProvider.innerText = "Testing...";
        try {
          const testRes = await apiPost('/api/providers/test', { provider_name: selectedProvider });
          alert(`Provider ${selectedProvider}: ${testRes.status.toUpperCase()} (${testRes.latency_ms || 20}ms)`);
        } catch (e) {
          alert(`Test failed: ${e.message}`);
        } finally {
          btnTestProvider.innerText = "⚡ Test Connection";
        }
      });
    }
    if (btnSaveProvider) {
      btnSaveProvider.addEventListener('click', async () => {
        try {
          await apiPost('/api/providers/config', { active_provider: selectedProvider });
          const labelP = document.getElementById('label-provider');
          if (labelP) labelP.innerText = `${selectedProvider.toUpperCase()} · ACTIVE`;
          providerOverlay.classList.remove('open');
        } catch (e) {
          alert(`Save error: ${e.message}`);
        }
      });
    }

    // Dynamic Inbox Sync
    async function loadInboxList() {
      try {
        const data = await apiGet('/api/demo/inbox');
        const container = document.getElementById('dynamic-inbox-items');
        if (!container) return;
        container.innerHTML = "";
        const badgeCount = document.getElementById('badge-inbox-count');
        if (badgeCount && data.workspaces) {
          badgeCount.innerText = data.workspaces.length;
        }
        (data.workspaces || []).forEach(ws => {
          if (['InMemoryLedger', 'PlaywrightDrift', 'HostilePatch', 'PlaywrightFlake', 'EnvironmentNoise'].includes(ws.workspace_name)) return;
          const row = document.createElement('div');
          row.className = "inbox-row";
          row.dataset.target = ws.workspace_id;
          row.dataset.testid = `inbox-row-${ws.workspace_id}`;
          row.innerHTML = `
            <div class="inbox-row-title">${ws.workspace_name}</div>
            <div class="inbox-row-meta">
              <span class="tag-badge ${ws.classification === 'TEST_BUG' ? 'test-bug' : 'prod-bug'}">${ws.classification}</span>
              <span>${ws.owner_agent}</span>
            </div>
          `;
          row.addEventListener('click', async () => {
            selectInboxRow(ws.workspace_id);
            state.workspaceId = ws.workspace_id;
            state.workspaceName = ws.workspace_name;
            state.failingTest = ws.failing_test;
            state.classification = ws.classification;
            state.ownerAgent = ws.owner_agent;
            state.scope = ws.scope || [];
            state.status = ws.status || "FAILING";
            updateUI();
          });
          container.appendChild(row);
        });
      } catch (e) {}
    }

    // Auto-init on page load / reload (AG-10)
    window.addEventListener('DOMContentLoaded', async () => {
      loadInboxList();
      loadROITelemetry();
      try {
        const active = await apiGet('/api/demo/active');
        if (active && active.workspace_id) {
          state.workspaceId = active.workspace_id;
          state.workspaceName = active.workspace_name;
          state.failingTest = active.failing_test;
          state.classification = active.classification;
          state.ownerAgent = active.owner_agent;
          state.scope = active.scope || [];
          state.allowedFiles = active.allowed_files || [];
          state.status = active.status || "FAILING";
          state.sprintId = active.active_sprint_id || null;
          state.snapshotId = active.pre_apply_snapshot_id || null;
          state.approver = active.approver || "QA Lead";
          if (active.approver) inputApprover.value = active.approver;

          // Fetch diff
          try {
            const diffRes = await apiGet(`/api/demo/${state.workspaceId}/diff`);
            state.diffText = diffRes.diff || "";
          } catch (e) {}

          // Fetch audit
          try {
            const auditRes = await apiGet(`/api/demo/${state.workspaceId}/audit`);
            state.auditLog = auditRes.markdown || "";
            auditContent.innerText = state.auditLog;
          } catch (e) {}

          selectInboxRow(active.workspace_name === 'PlaywrightDrift' ? 'drift' : (active.workspace_name === 'HostilePatch' ? 'hostile' : (active.workspace_name === 'PlaywrightFlake' ? 'flake' : (active.workspace_name === 'EnvironmentNoise' ? 'noise' : 'ledger'))));
          updateUI();
        } else {
          await loadLedgerWorkspace();
        }
      } catch (e) {
        await loadLedgerWorkspace();
      }
    });
  </script>
</body>
</html>
"""
