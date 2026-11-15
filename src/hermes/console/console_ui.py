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
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
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
      height: 52px;
      background-color: var(--bg-panel);
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      flex-shrink: 0;
      z-index: 10;
      gap: 12px;
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
      width: 270px;
      background-color: var(--bg-panel);
      border-right: 1px solid var(--border-hairline);
      display: flex;
      flex-direction: column;
      height: 100%;
      flex-shrink: 0;
      min-height: 0;
      overflow: hidden;
    }

    .rail-top-group {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow: hidden;
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
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 4px 8px;
      overflow-y: auto;
      min-height: 0;
    }

    .inbox-list::-webkit-scrollbar, .view-panel::-webkit-scrollbar, .terminal-body::-webkit-scrollbar {
      width: 5px;
      height: 5px;
    }
    .inbox-list::-webkit-scrollbar-track, .view-panel::-webkit-scrollbar-track, .terminal-body::-webkit-scrollbar-track {
      background: transparent;
    }
    .inbox-list::-webkit-scrollbar-thumb, .view-panel::-webkit-scrollbar-thumb, .terminal-body::-webkit-scrollbar-thumb {
      background: rgba(231, 225, 214, 0.18);
      border-radius: 3px;
    }
    .inbox-list::-webkit-scrollbar-thumb:hover, .view-panel::-webkit-scrollbar-thumb:hover, .terminal-body::-webkit-scrollbar-thumb:hover {
      background: var(--copper);
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

    /* Phase 2: Drag & Drop Ingestion */
    .dropzone {
      border: 2px dashed rgba(201, 133, 74, 0.4);
      border-radius: 6px;
      padding: 18px 24px;
      text-align: center;
      background: rgba(201, 133, 74, 0.04);
      margin-bottom: 16px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: var(--copper);
      background: rgba(201, 133, 74, 0.12);
    }
    .dropzone-icon {
      font-size: 22px;
      margin-bottom: 4px;
    }
    .dropzone-text {
      font-size: 13px;
      color: var(--text-main);
    }
    .dropzone-browse {
      color: var(--copper);
      text-decoration: underline;
      cursor: pointer;
    }
    .dropzone-subtext {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 4px;
      font-family: var(--font-mono);
    }

    /* Phase 2: Collapsible LLM Thinking Process (chat-demo style) */
    .thinking-box {
      margin-bottom: 16px;
      border-radius: 6px;
      background: rgba(20, 24, 33, 0.85);
      border: 1px solid rgba(59, 130, 246, 0.3);
      backdrop-filter: blur(10px);
      overflow: hidden;
    }
    .thinking-details {
      padding: 12px 16px;
    }
    .thinking-summary {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #93c5fd;
      font-weight: 600;
    }
    .thinking-summary::-webkit-details-marker {
      display: none;
    }
    .thinking-badge {
      margin-left: auto;
      font-size: 10px;
      padding: 2px 6px;
      background: rgba(59, 130, 246, 0.2);
      border: 1px solid rgba(59, 130, 246, 0.4);
      border-radius: 3px;
      color: #60a5fa;
    }
    .thinking-content {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-family: var(--font-mono);
      font-size: 11px;
      color: #cbd5e1;
      line-height: 1.6;
      max-height: 220px;
      overflow-y: auto;
      white-space: pre-wrap;
    }

    /* Phase 2: SprintDAGScheduler Mermaid Container */
    .dag-box {
      margin-bottom: 16px;
      border: 1px solid var(--border-hairline);
      border-radius: 6px;
      background: var(--bg-panel);
      padding: 14px 18px;
    }
    .dag-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      color: var(--copper);
      margin-bottom: 10px;
    }
    .mermaid {
      overflow-x: auto;
      padding: 10px 0;
    }

    /* Phase 2: Tier Switcher & Cancel Button */
    .tier-switcher-bar {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      padding: 8px 12px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-hairline);
      border-radius: 4px;
    }
    .tier-tab {
      background: transparent;
      border: 1px solid var(--border-hairline);
      color: var(--text-dim);
      padding: 4px 10px;
      font-size: 11px;
      font-family: var(--font-mono);
      border-radius: 3px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .tier-tab:hover {
      color: var(--text-main);
      border-color: var(--border-mid);
    }
    .tier-tab.active {
      background: rgba(201, 133, 74, 0.15);
      border-color: var(--copper);
      color: var(--copper);
      font-weight: 600;
    }
    .btn-cancel {
      background: rgba(239, 83, 80, 0.12);
      border: 1px solid rgba(239, 83, 80, 0.4);
      color: #ef5350;
      padding: 6px 12px;
      font-size: 11px;
      font-family: var(--font-mono);
      border-radius: 3px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.15s ease;
    }
    .btn-cancel:hover {
      background: rgba(239, 83, 80, 0.25);
      border-color: #ef5350;
    }

    /* Split Side-by-Side Diff View */
    .diff-split-container {
      display: flex;
      width: 100%;
      background: #0f0d0b;
      min-height: 180px;
    }
    .diff-split-col {
      flex: 1;
      min-width: 0;
    }
    .diff-split-body {
      font-family: var(--font-mono);
      font-size: 11px;
    }
    .diff-line-row {
      display: flex;
      min-height: 20px;
      line-height: 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.02);
    }
    .diff-line-num {
      width: 38px;
      padding-right: 8px;
      text-align: right;
      color: var(--text-dim);
      background: rgba(0, 0, 0, 0.25);
      border-right: 1px solid var(--border-hairline);
      user-select: none;
      flex-shrink: 0;
      font-size: 10px;
    }
    .diff-line-del {
      background: rgba(248, 113, 113, 0.12);
      color: #fca5a5;
    }
    .diff-line-add {
      background: rgba(74, 222, 128, 0.12);
      color: #86efac;
    }

    /* Playwright Locator Studio */
    .locator-studio-card {
      transition: border-color 0.15s ease;
    }
    .locator-alt-tag {
      background: var(--bg-code);
      padding: 2px 6px;
      border-radius: 3px;
      border: 1px solid var(--border-hairline);
      font-size: 10px;
      transition: all 0.15s ease;
    }
    .locator-alt-tag:hover {
      border-color: var(--copper);
      color: var(--copper);
    }

    /* Filter pills */
    .filter-type-pill {
      transition: all 0.15s ease;
    }
    .filter-type-pill.active {
      background: var(--bg-card) !important;
      color: var(--text-main) !important;
      border-color: var(--border-hairline) !important;
    }

    .diff-mode-btn.active {
      background: var(--bg-card) !important;
      color: var(--text-main) !important;
      border-color: var(--border-hairline) !important;
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
      <div class="workspace-selector" style="display: inline-flex; align-items: center; gap: 6px; margin-left: 8px;">
        <input type="text" id="input-real-workspace" list="recent-workspaces-list" placeholder="Target workspace path..." style="background: #1c1815; border: 1px solid #42382f; color: #f0e6df; padding: 5px 10px; border-radius: 4px; font-size: 11px; font-family: var(--font-mono); width: 280px;" title="Target project workspace path (Double-click or type to view recent)" autocomplete="off" />
        <datalist id="recent-workspaces-list"></datalist>
        <button id="btn-load-workspace" class="btn-top" style="padding: 5px 10px; font-size: 11px;" title="Load local repository workspace">📂 Load</button>
      </div>
    </div>

    <div class="top-meta">
      <div class="meta-pill status-green" id="pill-doctor" data-testid="pill-doctor" style="cursor: pointer;" title="Hermes Pre-Flight Doctor: OS, Runners, and LLM Status (Click to re-ping)">
        <span class="dot"></span>
        <span id="label-doctor">🩺 Doctor: Ready</span>
      </div>
      <button class="btn-top" id="btn-open-story" data-testid="btn-run-story" title="Launch Story Sprint DAG">
        <span>✨ New Story</span>
      </button>
      <div class="meta-pill" id="pill-provider" data-testid="pill-provider" style="cursor: pointer;" title="Configure LLM Providers">
        <span class="dot"></span>
        <span id="label-provider">🤖 OLLAMA · qwen2.5-coder:7b</span>
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
      <div class="rail-top-group">
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

        <!-- Dual Mode Switcher: Failures vs Discovered Tests -->
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px 6px; border-top: 1px solid var(--border-hairline);">
          <div style="display: flex; gap: 4px;">
            <button class="rail-tab-btn active" id="btn-tab-failures" style="background: var(--bg-card); border: 1px solid var(--border-hairline); color: var(--text-main); font-family: var(--font-mono); font-size: 10px; padding: 3px 8px; border-radius: 3px; cursor: pointer;">🔥 Failures</button>
            <button class="rail-tab-btn" id="btn-tab-tests" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); font-family: var(--font-mono); font-size: 10px; padding: 3px 8px; border-radius: 3px; cursor: pointer;">📂 Tests (<span id="count-discovered-tests">0</span>)</button>
          </div>
          <button class="btn-connect-sm" id="btn-open-connect" data-testid="btn-connect-repo" title="Connect another repo">+ Connect</button>
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

        <!-- Discovered Tests Container (shown when 'Tests' tab is active) -->
        <div id="rail-tests-container" style="display: none; flex: 1; flex-direction: column; min-height: 0; overflow: hidden;">
          <div style="padding: 6px 8px; border-bottom: 1px solid var(--border-hairline); display: flex; flex-direction: column; gap: 6px; background: rgba(0,0,0,0.15);">
            <input type="text" id="filter-tests-input" placeholder="🔍 Filter tests..." style="width: 100%; background: #1c1815; border: 1px solid #42382f; color: #f0e6df; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-family: var(--font-mono);" />
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; gap: 4px; font-size: 9px; font-family: var(--font-mono); flex-wrap: wrap;">
                <button id="filter-pill-all" class="filter-type-pill active" style="background: var(--bg-card); border: 1px solid var(--border-hairline); color: var(--text-main); padding: 2px 5px; border-radius: 3px; cursor: pointer;">All (<span id="count-all-tests">0</span>)</button>
                <button id="filter-pill-py" class="filter-type-pill" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); padding: 2px 5px; border-radius: 3px; cursor: pointer;">🐍 Py</button>
                <button id="filter-pill-pw" class="filter-type-pill" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); padding: 2px 5px; border-radius: 3px; cursor: pointer;">🎭 PW</button>
                <button id="filter-pill-art" class="filter-type-pill" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); padding: 2px 5px; border-radius: 3px; cursor: pointer;">🖼️ Artifacts (<span id="count-artifacts">0</span>)</button>
              </div>
              <button id="btn-run-all-tests" class="btn-top" style="padding: 2px 6px; font-size: 9px;" title="Execute entire test suite in workspace">▶ Run All</button>
            </div>
          </div>
          <div class="inbox-list" id="rail-tests-list" style="flex: 1; overflow-y: auto;">
            <!-- Dynamically populated with discovered test files -->
          </div>
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

        <!-- Drag & Drop Artifact Ingestion Zone -->
        <div class="dropzone" id="artifact-dropzone" data-testid="artifact-dropzone">
          <div class="dropzone-icon">📥</div>
          <div class="dropzone-text"><strong>Drag &amp; drop CI failure artifacts here</strong> or <span class="dropzone-browse" id="dropzone-browse">browse files</span></div>
          <div class="dropzone-subtext">Drop JUnit XML, CTRF JSON, Playwright trace.zip, or failure screenshots (.png, .jpg) to trigger autonomous triage &amp; healing</div>
          <input type="file" id="file-artifact-input" style="display:none;" accept=".xml,.json,.zip,.png,.jpg,.jpeg" />
        </div>

        <!-- Real Workspace Scope & Action Bar -->
        <div class="real-workspace-controls" id="real-workspace-controls" style="display: flex; gap: 10px; align-items: flex-end; background: #1a1613; padding: 10px 14px; border-radius: 6px; border: 1px solid #362e26; font-size: 12px; margin-bottom: 12px;">
          <div style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
            <label style="color: var(--text-dim); font-size: 11px;">Target Scope (Optional):</label>
            <input type="text" id="input-heal-scope" placeholder="e.g. src/app.py, src/service.py" style="background: #14120e; border: 1px solid #42382f; color: #f0e6df; padding: 6px 10px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px;" />
          </div>
          <div style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
            <label style="color: var(--text-dim); font-size: 11px;">Verification Command (Optional):</label>
            <input type="text" id="input-heal-cmd" placeholder="e.g. pytest tests/test_checkout.py" style="background: #14120e; border: 1px solid #42382f; color: #f0e6df; padding: 6px 10px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px;" />
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn-top" id="btn-run-shadow" style="background: #25201b; border-color: #5c4d3c; color: #e6a76e; padding: 7px 12px; font-size: 12px;" title="Preview proposed patch in shadow mode without modifying files on disk">🛡️ Shadow Preview</button>
            <button class="btn-action-primary" id="btn-run-real-heal" style="padding: 7px 14px; font-size: 12px;" title="Apply patch, verify in sandbox, and auto-rollback on failure">⚡ Apply &amp; Verify</button>
          </div>
        </div>

        <!-- Playwright Locator Resilience Studio (UI Automation Self-Healing) -->
        <div class="locator-studio-card" id="locator-studio-card" style="background: #171411; border: 1px solid #4a3828; border-radius: 6px; padding: 14px 16px; margin-bottom: 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 15px;">🎭</span>
              <span style="font-size: 13px; font-weight: 600; font-family: var(--font-mono); color: var(--copper);">PLAYWRIGHT LOCATOR RESILIENCE STUDIO</span>
              <span class="tag-badge" id="locator-studio-badge" style="background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3);">BRITTLE DETECTED</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 11px; font-family: var(--font-mono); color: var(--text-dim);">
              <span>Resilience Score:</span>
              <strong id="locator-score-label" style="color: #f87171; font-size: 13px;">35%</strong>
            </div>
          </div>

          <!-- Selector Audit Live Input Bar -->
          <div style="display: flex; gap: 8px; margin-bottom: 12px;">
            <input type="text" id="input-audit-selector" placeholder="Inspect or paste any selector (e.g., button#checkout, //div[2]/button, .submit-btn)..." value="button#checkout" style="flex: 1; background: #0f0d0b; border: 1px solid #42382f; color: #f0e6df; padding: 6px 12px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px;" />
            <button id="btn-audit-selector" class="btn-top" style="padding: 6px 12px; font-size: 11px; white-space: nowrap;">⚡ Audit Resilience</button>
          </div>

          <!-- Comparison Grid: Brittle vs Healed -->
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 10px;">
            <div style="background: rgba(248,113,113,0.05); border: 1px solid rgba(248,113,113,0.25); border-radius: 4px; padding: 10px 12px;">
              <div style="font-size: 10px; font-weight: 600; font-family: var(--font-mono); color: #f87171; margin-bottom: 4px;">⚠️ BRITTLE FAILING LOCATOR (CLASS/CSS ID)</div>
              <code id="locator-brittle-text" style="font-size: 12px; color: #fca5a5; word-break: break-all;">button#checkout</code>
              <div id="locator-brittle-reason" style="font-size: 10px; color: var(--text-dim); margin-top: 6px; line-height: 1.4;">
                Tightly coupled to CSS ID. Breaks on dynamic hydration, re-renders, and ID hashing.
              </div>
            </div>
            <div style="background: rgba(74,222,128,0.06); border: 1px solid rgba(74,222,128,0.25); border-radius: 4px; padding: 10px 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div style="font-size: 10px; font-weight: 600; font-family: var(--font-mono); color: #4ade80;">🛡️ HEALED ACCESSIBLE LOCATOR (RECOMMENDED)</div>
                <div style="display: flex; gap: 4px;">
                  <button id="btn-copy-py-locator" class="btn-top" style="padding: 1px 6px; font-size: 9px;" title="Copy Python Playwright locator">📋 Python</button>
                  <button id="btn-copy-ts-locator" class="btn-top" style="padding: 1px 6px; font-size: 9px;" title="Copy TypeScript Playwright locator">📋 TS</button>
                </div>
              </div>
              <code id="locator-healed-text" style="font-size: 12px; color: #86efac; word-break: break-all;">page.get_by_role("button", name="Checkout")</code>
              <div id="locator-healed-reason" style="font-size: 10px; color: var(--text-dim); margin-top: 6px; line-height: 1.4;">
                User-facing semantic accessibility role. Resilient across frontend refactors and responsive UI changes.
              </div>
            </div>
          </div>

          <!-- Alternative Strategies & Trace Trigger Bar -->
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-family: var(--font-mono); color: var(--text-dim); border-top: 1px solid var(--border-hairline); padding-top: 8px;">
            <div id="locator-alt-list" style="display: flex; gap: 8px; flex-wrap: wrap;">
              <span>Alternatives:</span>
              <span class="locator-alt-tag" style="color: var(--copper); cursor: pointer;" title="Click to use test ID">data-testid="checkout-btn"</span>
              <span>&middot;</span>
              <span class="locator-alt-tag" style="color: var(--copper); cursor: pointer;" title="Click to use text match">has-text('Checkout')</span>
            </div>
            <button id="btn-open-trace-viewer" class="btn-top" style="display: none; padding: 3px 8px; font-size: 10px; color: #60a5fa; border-color: rgba(96,165,250,0.3);" title="Open Playwright Trace Viewer">🎭 Open in Trace Viewer</button>
          </div>

          <!-- Interactive DOM & Strict-Mode Playground -->
          <div style="margin-top: 10px; border-top: 1px dashed var(--border-hairline); padding-top: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="font-size: 11px; font-weight: 600; font-family: var(--font-mono); color: var(--text-dim); display: flex; align-items: center; gap: 6px;">
                <span>🧪 SELECTOR PLAYGROUND &amp; STRICT-MODE VALIDATOR</span>
                <span id="playground-status-badge" style="font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(74,222,128,0.1); color: #4ade80;">READY</span>
              </div>
              <div style="display: flex; gap: 6px;">
                <button id="btn-playground-load-sample" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Load sample e-commerce checkout DOM snippet">Sample DOM</button>
                <button id="btn-playground-toggle" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Toggle DOM playground view">↕ Toggle</button>
              </div>
            </div>

            <div id="playground-container" style="display: none; flex-direction: column; gap: 8px; margin-top: 8px;">
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div>
                  <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-dim); margin-bottom: 3px;">Page DOM / Aria Snapshot:</div>
                  <textarea id="playground-dom" rows="5" style="width: 100%; box-sizing: border-box; background: #0f0d0b; border: 1px solid #42382f; color: #f0e6df; font-family: var(--font-mono); font-size: 11px; padding: 6px; border-radius: 4px; resize: vertical;" placeholder="Paste HTML DOM or Aria snapshot here..."></textarea>
                </div>
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
                    <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-dim);">Live Matched Elements:</div>
                    <span id="playground-match-count" style="font-size: 10px; font-family: var(--font-mono); color: var(--copper); font-weight: 600;">0 matched</span>
                  </div>
                  <div id="playground-preview" style="height: 95px; overflow-y: auto; background: #0f0d0b; border: 1px solid #42382f; border-radius: 4px; padding: 6px; font-family: var(--font-mono); font-size: 11px; color: #f0e6df;">
                    <div style="color: var(--text-dim); font-size: 10px;">Matched elements will appear here in real-time...</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
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
          <div style="display: flex; gap: 8px;">
            <button class="btn-cancel" id="btn-cancel-sprint" data-testid="btn-cancel-sprint">⏹ Stop Sprint</button>
            <button class="btn-action-primary" id="btn-goto-diff">Review Staged Diff →</button>
          </div>
        </div>

        <!-- Collapsible LLM Thinking Process (chat-demo style) -->
        <div class="thinking-box" id="thinking-box" style="display: none;">
          <details class="thinking-details" id="thinking-details" open>
            <summary class="thinking-summary">
              <span class="thinking-icon">🧠</span>
              <span id="thinking-title">Thinking Process (~0 tokens, 0s)</span>
              <span class="thinking-badge" id="thinking-badge">LIVE STREAM</span>
            </summary>
            <div class="thinking-content" id="thinking-content">
              <em>Streaming agent reasoning &amp; token telemetry...</em>
            </div>
          </details>
        </div>

        <!-- Mermaid SprintDAGScheduler Topological Dependency Graph -->
        <div class="dag-box" id="dag-box">
          <div class="dag-header">
            <span>⚡ SPRINT DAG SCHEDULER DEPENDENCY GRAPH</span>
            <span style="font-size: 10px; color: var(--text-dim);">Topologically Sorted Execution Pipeline</span>
          </div>
          <div class="mermaid" id="sprint-mermaid-graph" data-testid="sprint-mermaid-graph">
graph LR
  S1["1. CIFailureIngestor"] --> S2["2. Requirements &amp; AC"]
  S2 --> S3["3. SprintDAGScheduler"]
  S3 --> S4["4. Multi-Tier Worker"]
  S4 --> S5["5. AST &amp; Security Guards"]
  S5 --> S6["6. Sandbox Verification"]
  S6 --> S7["7. Human Write Gate"]
  style S1 fill:#1e293b,stroke:#3b82f6,stroke-width:1.5px,color:#f8fafc
  style S2 fill:#1e293b,stroke:#3b82f6,stroke-width:1.5px,color:#f8fafc
  style S3 fill:#1e293b,stroke:#3b82f6,stroke-width:1.5px,color:#f8fafc
  style S4 fill:#1e293b,stroke:#f59e0b,stroke-width:1.5px,color:#f8fafc
  style S5 fill:#1e293b,stroke:#10b981,stroke-width:1.5px,color:#f8fafc
  style S6 fill:#1e293b,stroke:#10b981,stroke-width:1.5px,color:#f8fafc
  style S7 fill:#1e293b,stroke:#6366f1,stroke-width:1.5px,color:#f8fafc
          </div>
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

        <!-- Tier Switcher Bar -->
        <div class="tier-switcher-bar">
          <span style="font-size: 11px; font-weight: 600; font-family: var(--font-mono); color: var(--text-dim); letter-spacing: 0.05em;">PROPOSAL TIER:</span>
          <div class="tier-switcher-tabs" data-testid="tier-switcher-tabs" style="display: inline-flex; gap: 6px;">
            <button class="tier-tab active" data-tier="TIER_3_JUNIOR_SWE" data-testid="tab-tier-3">Tier 3 (Junior SWE)</button>
            <button class="tier-tab" data-tier="TIER_2_SENIOR_SWE" data-testid="tab-tier-2">Tier 2 (Senior SWE)</button>
            <button class="tier-tab" data-tier="TIER_1_TECH_LEAD" data-testid="tab-tier-1">Tier 1 (Tech Lead)</button>
          </div>
          <button class="btn-action-secondary" id="btn-export-zip" data-testid="btn-export-zip" style="margin-left: auto; padding: 4px 10px; font-size: 11px;">
            📦 Download .zip Audit Bundle
          </button>
        </div>

        <div class="diff-container" data-testid="diff-container">
          <div class="diff-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span id="diff-file-label">src/InMemoryLedger.py (Unified Diff vs Baseline)</span>
              <div class="diff-view-mode-tabs" style="display: inline-flex; gap: 4px; background: rgba(0,0,0,0.3); padding: 2px 4px; border-radius: 4px; border: 1px solid var(--border-hairline);">
                <button id="btn-diff-mode-unified" class="diff-mode-btn active" style="background: var(--bg-card); border: 1px solid var(--border-hairline); color: var(--text-main); font-family: var(--font-mono); font-size: 10px; padding: 2px 8px; border-radius: 3px; cursor: pointer;">📄 Unified</button>
                <button id="btn-diff-mode-split" class="diff-mode-btn" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); font-family: var(--font-mono); font-size: 10px; padding: 2px 8px; border-radius: 3px; cursor: pointer;">📑 Split Side-by-Side</button>
                <button id="btn-diff-mode-edit" class="diff-mode-btn" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); font-family: var(--font-mono); font-size: 10px; padding: 2px 8px; border-radius: 3px; cursor: pointer;">✏️ Manual Tweak</button>
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span id="diff-assertion-label">Test assertions preserved (2/2)</span>
              <button id="btn-copy-diff" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Copy Unified Diff to Clipboard">📋 Copy Diff</button>
              <button id="btn-download-patch" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Download .patch file">📥 Download .patch</button>
            </div>
          </div>
          <!-- Unified Diff View (Default) -->
          <div class="diff-content" id="diff-text">--- a/src/InMemoryLedger.py (Baseline)
+++ b/src/InMemoryLedger.py (Staged Proposal)
@@ -10,6 +10,10 @@
     def deposit(self, amount: float) -> float:
+        if amount &lt;= 0:
+            raise ValueError("Deposit amount must be positive")
         self._balance += amount
         return self._balance</div>

          <!-- Split Side-by-Side Diff View -->
          <div id="diff-split-view" class="diff-split-container" style="display: none; width: 100%; border-top: 1px solid var(--border-hairline); font-family: var(--font-mono); font-size: 11px;">
            <div class="diff-split-col baseline" style="flex: 1; border-right: 1px solid var(--border-hairline); overflow-x: auto;">
              <div class="diff-split-header" style="padding: 6px 10px; background: rgba(248,113,113,0.08); color: #f87171; font-weight: 600; border-bottom: 1px solid var(--border-hairline);">BASELINE (ORIGINAL)</div>
              <div id="diff-split-left" class="diff-split-body" style="padding: 4px 0; line-height: 1.5;"></div>
            </div>
            <div class="diff-split-col proposal" style="flex: 1; overflow-x: auto;">
              <div class="diff-split-header" style="padding: 6px 10px; background: rgba(74,222,128,0.08); color: #4ade80; font-weight: 600; border-bottom: 1px solid var(--border-hairline);">PROPOSED HEALED (NEW)</div>
              <div id="diff-split-right" class="diff-split-body" style="padding: 4px 0; line-height: 1.5;"></div>
            </div>
          </div>

          <!-- Manual Code Tweaker & AST Validation View -->
          <div id="diff-manual-view" style="display: none; width: 100%; padding: 10px; border-top: 1px solid var(--border-hairline); background: #0c0a08;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div style="font-family: var(--font-mono); font-size: 11px; color: var(--copper); font-weight: 600;">
                ✏️ IN-PLACE CODE TWEAKER &middot; AST PATCH GUARD
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span id="diff-ast-badge" class="tag-badge" style="background: rgba(74,222,128,0.12); color: #4ade80; display: none;">✓ AST VERIFIED</span>
                <button id="btn-validate-manual-ast" class="btn-action-primary" style="padding: 4px 10px; font-size: 11px;">✓ Validate AST &amp; Apply</button>
              </div>
            </div>
            <textarea id="diff-manual-editor" class="form-input" style="width: 100%; height: 260px; font-family: var(--font-mono); font-size: 11px; line-height: 1.5; background: #12100d; color: #f0e6df; border: 1px solid #362e26; border-radius: 4px; padding: 10px; resize: vertical; tab-size: 4;" spellcheck="false"></textarea>
            <div id="diff-ast-feedback" style="margin-top: 6px; font-family: var(--font-mono); font-size: 11px; display: none;"></div>
          </div>
        </div>

        <!-- Instruction Edit & Regenerate -->
        <div class="instruction-box" id="instruction-box" style="margin-top: 12px; margin-bottom: 12px; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-hairline); border-radius: 6px;">
          <label for="input-custom-instruction" style="display: flex; justify-content: space-between; font-weight: 600; font-size: 11px; font-family: var(--font-mono); color: var(--copper); margin-bottom: 6px;">
            <span>✍️ STEERING INSTRUCTION (RE-SYNTHESIZE PROPOSAL)</span>
            <span style="color: var(--text-dim);">Tier guidance &amp; constraints</span>
          </label>
          <div style="display: flex; gap: 8px;">
            <input type="text" id="input-custom-instruction" data-testid="input-custom-instruction" class="form-input" style="flex: 1;" placeholder="E.g., 'Add explicit type validation and structured logging', 'Use resilient Playwright locator'..." />
            <button class="btn-action-primary" id="btn-regenerate-proposal" data-testid="btn-regenerate-proposal" style="white-space: nowrap; padding: 6px 14px; font-size: 12px;">
              🔄 Re-synthesize
            </button>
          </div>
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

            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
              <button class="btn-action-success" id="btn-approve" data-testid="btn-approve">
                ✓ Approve &amp; Verify (Sandbox)
              </button>
              <button class="btn-action-rewind" id="btn-rewind" data-testid="btn-rewind">
                ↺ Rewind Workspace (TimeMachine)
              </button>
              <button class="btn-top" id="btn-create-branch" data-testid="btn-create-branch" style="background: rgba(96,165,250,0.12); color: #60a5fa; border: 1px solid rgba(96,165,250,0.3); padding: 8px 14px; font-size: 12px; font-weight: 600; border-radius: 4px; display: inline-flex; align-items: center; gap: 6px;" title="Commit verified patch to new Git branch">
                🌿 Commit to Branch / PR
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
        <button class="btn-action-primary" id="btn-export-zip-audit" data-testid="btn-export-zip-audit" style="padding: 4px 10px; font-size: 11px;">📦 Download .zip Bundle</button>
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
      <div class="form-group" style="margin-top: 8px;">
        <label class="form-label">Target Test File Scope (Optional)</label>
        <input type="text" class="form-input" id="input-story-scope" placeholder="e.g. tests/test_coupon.py" style="font-family: var(--font-mono); font-size: 12px;" />
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

  <!-- Modal: Failure Screenshot Lightbox -->
  <div class="modal-overlay" id="modal-screenshot-lightbox" style="display: none; z-index: 9999;">
    <div class="modal-box" style="max-width: 900px; width: 90%;">
      <div class="drawer-header" style="margin-bottom: 8px;">
        <div class="drawer-title" id="lightbox-title" style="word-break: break-all;">🖼️ Failure Screenshot Preview</div>
        <button class="btn-top" id="btn-close-lightbox">✕ Close</button>
      </div>
      <div style="max-height: 70vh; overflow: auto; text-align: center; background: #000; border-radius: 4px; padding: 10px;">
        <img id="lightbox-img" src="" alt="Failure Screenshot" style="max-width: 100%; height: auto; border-radius: 4px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);" />
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
        <span id="lightbox-path" style="font-size: 11px; font-family: var(--font-mono); color: var(--text-dim);"></span>
        <a id="lightbox-download-link" href="#" target="_blank" class="btn-top" style="padding: 4px 10px; font-size: 11px; text-decoration: none;">💾 Open in Tab</a>
      </div>
    </div>
  </div>

  <!-- Modal: Agent Step Inspector -->
  <div class="modal-overlay" id="modal-agent-inspector" style="display: none;">
    <div class="modal-box" style="width: 640px; max-width: 90vw;">
      <div class="drawer-header" style="margin-bottom: 0;">
        <div class="drawer-title" id="inspector-agent-title">Agent Inspection Details</div>
        <button class="btn-close" id="btn-close-inspector">&times;</button>
      </div>
      <div style="display: flex; gap: 8px; border-bottom: 1px solid var(--border-hairline); padding: 8px 0; margin-bottom: 12px;">
        <button class="inspector-tab active" id="tab-insp-overview" style="background: var(--bg-card); border: 1px solid var(--border-hairline); color: var(--text-main); font-family: var(--font-mono); font-size: 11px; padding: 3px 10px; border-radius: 3px; cursor: pointer;">Overview</button>
        <button class="inspector-tab" id="tab-insp-prompt" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 3px 10px; border-radius: 3px; cursor: pointer;">System Directive</button>
        <button class="inspector-tab" id="tab-insp-ast" style="background: transparent; border: 1px solid transparent; color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 3px 10px; border-radius: 3px; cursor: pointer;">AST &amp; Safety Rubric</button>
      </div>
      <div id="inspector-tab-overview" class="inspector-tab-content">
        <div id="inspector-overview-body" style="font-family: var(--font-mono); font-size: 12px; line-height: 1.6; color: var(--text-main);"></div>
      </div>
      <div id="inspector-tab-prompt" class="inspector-tab-content" style="display: none;">
        <pre id="inspector-prompt-body" style="font-family: var(--font-mono); font-size: 11px; line-height: 1.5; color: #dcd6cd; background: var(--bg-code); padding: 12px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; max-height: 300px;"></pre>
      </div>
      <div id="inspector-tab-ast" class="inspector-tab-content" style="display: none;">
        <pre id="inspector-ast-body" style="font-family: var(--font-mono); font-size: 11px; line-height: 1.5; color: #86efac; background: #0c0a08; padding: 12px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; max-height: 300px;"></pre>
      </div>
      <div style="display: flex; justify-content: flex-end; margin-top: 14px;">
        <button class="btn-top" id="btn-close-inspector-footer">Close</button>
      </div>
    </div>
  </div>

  <!-- Modal: Failure Screenshot Previewer -->
  <div class="modal-overlay" id="modal-screenshot-preview" style="display: none;">
    <div class="modal-box" style="width: 800px; max-width: 95vw; background: #0a0806;">
      <div class="drawer-header" style="margin-bottom: 8px;">
        <div class="drawer-title" id="screenshot-preview-title">🖼️ CI Failure Screenshot</div>
        <button class="btn-close" id="btn-close-screenshot">&times;</button>
      </div>
      <div style="display: flex; justify-content: center; align-items: center; background: #000; border-radius: 4px; padding: 10px; max-height: 70vh; overflow: auto;">
        <img id="screenshot-preview-img" src="" alt="Failure Screenshot" style="max-width: 100%; max-height: 65vh; border-radius: 3px; box-shadow: 0 4px 20px rgba(0,0,0,0.6);" />
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
        <span id="screenshot-preview-caption" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);"></span>
        <button class="btn-top" id="btn-close-screenshot-footer">Close</button>
      </div>
    </div>
  </div>

  <!-- Live Terminal / Test Runner Drawer -->
  <div id="terminal-drawer" style="position: fixed; bottom: 0; left: 270px; right: 0; height: 230px; background: #0c0a08; border-top: 1px solid var(--border-hairline); z-index: 50; display: none; flex-direction: column; box-shadow: 0 -8px 24px rgba(0,0,0,0.5);">
    <div style="height: 34px; background: #16130f; border-bottom: 1px solid var(--border-hairline); display: flex; align-items: center; justify-content: space-between; padding: 0 14px; font-family: var(--font-mono); font-size: 11px;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="color: var(--copper); font-weight: 600;">&gt;_ Execution Terminal</span>
        <span id="term-status-badge" class="tag-badge" style="background: rgba(74,222,128,0.12); color: #4ade80;">IDLE</span>
        <span id="term-cmd-label" style="color: var(--text-dim);"></span>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <span id="term-elapsed" style="color: var(--text-dim); margin-right: 6px;">0.0s</span>
        <button id="btn-term-heal" class="btn-top" style="display: none; padding: 2px 8px; font-size: 10px; background: var(--copper-bg); border-color: var(--copper-border); color: var(--copper);" title="Feed output directly into Autonomous Healer">⚡ Triage &amp; Heal</button>
        <button id="btn-term-copy" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Copy terminal log">📋 Copy</button>
        <button id="btn-term-clear" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Clear terminal">🗑️ Clear</button>
        <button id="btn-term-expand" class="btn-top" style="padding: 2px 8px; font-size: 10px;" title="Toggle Expand/Compact Terminal">↕ Expand</button>
        <button id="btn-term-close" class="btn-close" style="padding: 0 6px; font-size: 14px;" title="Close terminal">&times;</button>
      </div>
    </div>
    <pre id="term-output" class="terminal-body" style="flex: 1; margin: 0; padding: 10px 14px; font-family: var(--font-mono); font-size: 11px; line-height: 1.45; color: #dcd6cd; overflow-y: auto; white-space: pre-wrap; word-break: break-all;"></pre>
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
    window.state = state;

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
      if (data.workspace_name === 'PlaywrightDrift') selectInboxRow('drift');
      else if (data.workspace_name === 'HostilePatch') selectInboxRow('hostile');
      else if (data.workspace_name === 'PlaywrightFlake') selectInboxRow('flake');
      else if (data.workspace_name === 'EnvironmentNoise') selectInboxRow('noise');
      else selectInboxRow('ledger');
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
      const targetLabel = state.scope[0] || (state.workspaceName === 'PlaywrightDrift' ? 'tests/test_cart.py' : (state.workspaceName === 'HostilePatch' ? 'src/service.py' : (state.workspaceName === 'PlaywrightFlake' ? 'tests/test_flake.py' : (state.workspaceName === 'EnvironmentNoise' ? 'tests/test_api.py' : 'src/InMemoryLedger.py'))));
      diffFileLabel.innerText = `${targetLabel} (Unified Diff vs Baseline)`;
      document.getElementById('tm-active-target').innerText = `Target: ${targetLabel}`;

      if (state.workspaceName === 'PlaywrightDrift') {
        diffAssertionLabel.innerText = "Invariant: Test assertions preserved (1/1)";
      } else if (state.workspaceName === 'PlaywrightFlake') {
        diffAssertionLabel.innerText = "Invariant: Flake timing stabilized (1/1)";
      } else if (state.workspaceName === 'EnvironmentNoise') {
        diffAssertionLabel.innerText = "Invariant: Infrastructure outage; 0 files modified";
      } else {
        diffAssertionLabel.innerText = "Invariant: Test assertions preserved (2/2)";
      }

      // Configure Step Cards for Workspace Type
      const isDrift = state.workspaceName === 'PlaywrightDrift';
      const isHostile = state.workspaceName === 'HostilePatch';
      const isFlake = state.workspaceName === 'PlaywrightFlake';
      const isNoise = state.workspaceName === 'EnvironmentNoise';

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
      } else if (isFlake) {
        document.getElementById('badge-step-1').innerText = "CLASSIFIED: FLAKY_TEST (INTERMITTENT)";
        document.getElementById('badge-step-2').innerText = "ROUTED: HEAL-FLAKE-001 (TestHealerAgent)";
        document.getElementById('scope-step-2').innerText = "Allowed Files: ['tests/test_flake.py'] (Quarantine & Variance Shield)";
        document.getElementById('title-step-3').innerText = "3. TestHealerAgent (Playwright Locator Shield)";
        document.getElementById('tier-step-3').innerText = "TIER_3_JUNIOR_SWE";
        document.getElementById('badge-step-3').innerText = "LOCATOR FLAKE HEALED";
        document.getElementById('body-step-3').innerText = "TestHealerAgent replaced brittle timing locator 'button#checkout' with auto-waiting semantic locator page.get_by_role('button', name='Checkout').";
        document.getElementById('scope-step-3').innerText = "Target File: tests/test_flake.py • Timing Instability Eliminated";
        document.getElementById('scope-step-5').innerText = "Blast Radius: ISOLATED (tests/test_flake.py only)";
      } else if (isNoise) {
        document.getElementById('badge-step-1').innerText = "CLASSIFIED: ENVIRONMENT_NOISE";
        document.getElementById('badge-step-2').innerText = "ROUTED: SRE / Infrastructure Escalation";
        document.getElementById('scope-step-2').innerText = "Allowed Files: [] (Automated Changes PROHIBITED)";
        document.getElementById('title-step-3').innerText = "3. SRE / DevOps Escalation Sentinel";
        document.getElementById('tier-step-3').innerText = "TIER_1_TECH_LEAD";
        document.getElementById('badge-step-3').innerText = "INFRA BLOCKER DETECTED";
        document.getElementById('body-step-3').innerText = "External Dependency Outage: Database port 5432 unreachable. Automated changes strictly prohibited to protect repository integrity.";
        document.getElementById('scope-step-3').innerText = "Target: Zero Files Modified • Incident Dispatched";
        document.getElementById('scope-step-5').innerText = "Blast Radius: PROTECTED (0 workspace changes)";
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

      const thinkingBox = document.getElementById('thinking-box');
      const thinkingContent = document.getElementById('thinking-content');
      const thinkingTitle = document.getElementById('thinking-title');
      if (thinkingBox) {
        thinkingBox.style.display = "block";
        if (thinkingContent) thinkingContent.innerText = "Analyzing failure trace and ingesting DOM/locator context...";
      }

      let sse = null;
      try {
        if (!state.workspaceId) {
          await loadLedgerWorkspace();
        }

        try {
          sse = new EventSource(`/api/demo/${state.workspaceId}/stream`);
          sse.addEventListener('milestone', (ev) => {
            try {
              const m = JSON.parse(ev.data);
              if (m.stage && typeof setRailPassedUpTo === 'function') {
                setRailPassedUpTo(m.stage);
              }
            } catch (err) {}
          });
          sse.addEventListener('thinking', (ev) => {
            try {
              const t = JSON.parse(ev.data);
              if (thinkingTitle) {
                thinkingTitle.innerText = `Thinking Process (~${t.token_count || 48} tokens, ${t.elapsed_s || 1}s)`;
              }
              if (t.reasoning && thinkingContent) {
                thinkingContent.innerText = t.reasoning;
              }
            } catch (err) {}
          });
        } catch (err) {}

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

        await loadTierProposals();
        await loadMermaidDAG();

        updateUI();
        switchTab('sprint');
        loadROITelemetry();
      } catch (e) {
        alert("Sprint heal error: " + e.message);
      } finally {
        if (sse) {
          try { sse.close(); } catch (err) {}
        }
        triggerBtn.disabled = false;
        triggerBtn.innerText = originalText;
      }
    }

    // Phase 2: Tier Proposals & Mermaid DAG
    async function loadTierProposals() {
      try {
        const res = await apiGet(`/api/demo/${state.workspaceId}/proposals`);
        if (res && res.proposals) {
          const activeTier = state.activeTier || res.active_tier || "TIER_3_JUNIOR_SWE";
          if (res.proposals[activeTier]) {
            state.diffText = res.proposals[activeTier].diff || state.diffText;
            if (diffTextContainer) diffTextContainer.innerText = state.diffText;
          }
        }
      } catch (err) {}
    }

    async function loadMermaidDAG() {
      try {
        const res = await apiGet(`/api/demo/${state.workspaceId}/dag`);
        const el = document.getElementById('sprint-mermaid-graph');
        if (el && res && res.mermaid) {
          el.removeAttribute('data-processed');
          el.innerHTML = res.mermaid;
          if (window.mermaid) {
            window.mermaid.run({ nodes: [el] });
          }
        }
      } catch (err) {}
    }

    // Phase 2: Drag & Drop CI Failure Artifact Ingestion
    const artifactDropzone = document.getElementById('artifact-dropzone');
    const fileArtifactInput = document.getElementById('file-artifact-input');
    const dropzoneBrowse = document.getElementById('dropzone-browse');

    if (dropzoneBrowse && fileArtifactInput) {
      dropzoneBrowse.addEventListener('click', (e) => {
        e.stopPropagation();
        fileArtifactInput.click();
      });
    }

    if (artifactDropzone && fileArtifactInput) {
      artifactDropzone.addEventListener('click', () => {
        fileArtifactInput.click();
      });
      artifactDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        artifactDropzone.classList.add('dragover');
      });
      artifactDropzone.addEventListener('dragleave', () => {
        artifactDropzone.classList.remove('dragover');
      });
      artifactDropzone.addEventListener('drop', async (e) => {
        e.preventDefault();
        artifactDropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          await handleArtifactUpload(e.dataTransfer.files[0]);
        }
      });
      fileArtifactInput.addEventListener('change', async () => {
        if (fileArtifactInput.files && fileArtifactInput.files.length > 0) {
          await handleArtifactUpload(fileArtifactInput.files[0]);
        }
      });
    }

    async function handleArtifactUpload(file) {
      const formData = new FormData();
      formData.append('file', file);
      const textEl = artifactDropzone.querySelector('.dropzone-text');
      const origHtml = textEl.innerHTML;
      try {
        textEl.innerHTML = `<strong>⚡ Uploading and decomposing ${file.name}...</strong>`;
        const res = await fetch('/api/demo/upload', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data && data.workspace_id) {
          state.workspaceId = data.workspace_id;
          state.workspaceName = data.workspace_name;
          state.status = data.workspace_status || "FAILING";
          if (labelWorkspace) labelWorkspace.innerText = data.workspace_name;
          updateUI();
          alert(`Successfully ingested ${file.name}! New autonomous healing workspace created.`);
        }
      } catch (err) {
        alert("Artifact upload failed: " + err.message);
      } finally {
        textEl.innerHTML = origHtml;
      }
    }

    // Phase 2: Stop/Cancel Sprint Button
    const btnCancelSprint = document.getElementById('btn-cancel-sprint');
    if (btnCancelSprint) {
      btnCancelSprint.addEventListener('click', async () => {
        if (!state.workspaceId) return;
        try {
          btnCancelSprint.disabled = true;
          btnCancelSprint.innerText = "Stopping...";
          await apiPost(`/api/demo/${state.workspaceId}/cancel`);
          state.status = "CANCELLED";
          updateUI();
          alert("Sprint execution halted by user.");
        } catch (err) {
          alert("Cancel failed: " + err.message);
        } finally {
          btnCancelSprint.disabled = false;
          btnCancelSprint.innerText = "⏹ Stop Sprint";
        }
      });
    }

    // Phase 2: Switchable Tier Tabs
    const tierTabs = document.querySelectorAll('.tier-tab');
    tierTabs.forEach(tab => {
      tab.addEventListener('click', async () => {
        tierTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const tier = tab.getAttribute('data-tier');
        state.activeTier = tier;
        try {
          const res = await apiGet(`/api/demo/${state.workspaceId}/proposals`);
          if (res && res.proposals && res.proposals[tier]) {
            const prop = res.proposals[tier];
            state.diffText = prop.diff || "";
            if (diffTextContainer) diffTextContainer.innerText = state.diffText;
            if (diffAssertionLabel) {
              diffAssertionLabel.innerText = `Proposal: ${prop.title} (${prop.model || ''})`;
            }
          }
        } catch (err) {}
      });
    });

    // Phase 2: Instruction Edit & Regenerate
    const btnRegenerate = document.getElementById('btn-regenerate-proposal');
    const inputInstruction = document.getElementById('input-custom-instruction');
    if (btnRegenerate) {
      btnRegenerate.addEventListener('click', async () => {
        if (!state.workspaceId) return;
        const tier = state.activeTier || "TIER_3_JUNIOR_SWE";
        const instruction = inputInstruction ? inputInstruction.value.trim() : "";
        btnRegenerate.disabled = true;
        btnRegenerate.innerText = "🔄 Re-synthesizing...";
        try {
          const res = await apiPost(`/api/demo/${state.workspaceId}/regenerate`, {
            tier: tier,
            instruction: instruction,
          });
          if (res && res.diff) {
            state.diffText = res.diff;
            if (diffTextContainer) diffTextContainer.innerText = state.diffText;
            alert(`Re-synthesized proposal for ${tier} with custom steering instruction!`);
          }
        } catch (err) {
          alert("Regeneration failed: " + err.message);
        } finally {
          btnRegenerate.disabled = false;
          btnRegenerate.innerText = "🔄 Re-synthesize";
        }
      });
    }

    // Phase 2: 1-Click .zip Sprint Audit Bundle Download
    function triggerZipDownload() {
      if (state.workspaceId && state.workspaceId.startsWith("real_")) {
        window.location.href = `/api/real/audit/export-zip`;
      } else if (state.workspaceId) {
        window.location.href = `/api/demo/${state.workspaceId}/audit/export-zip`;
      } else {
        window.location.href = `/api/real/audit/export-zip`;
      }
    }

    const btnExportZip = document.getElementById('btn-export-zip');
    if (btnExportZip) {
      btnExportZip.addEventListener('click', triggerZipDownload);
    }
    const btnExportZipAudit = document.getElementById('btn-export-zip-audit');
    if (btnExportZipAudit) {
      btnExportZipAudit.addEventListener('click', triggerZipDownload);
    }

    btnRunHeal.addEventListener('click', async () => {
      if (!state.workspaceId || state.workspaceName !== 'InMemoryLedger') {
        await loadLedgerWorkspace();
      }
      executeHeal(btnRunHeal);
    });
    if (btnRunDrift) {
      btnRunDrift.addEventListener('click', async () => {
        if (!state.workspaceId || state.workspaceName !== 'PlaywrightDrift') {
          await loadDriftWorkspace();
        }
        executeHeal(btnRunDrift);
      });
    }
    if (btnRunHostile) {
      btnRunHostile.addEventListener('click', async () => {
        if (!state.workspaceId || state.workspaceName !== 'HostilePatch') {
          await loadHostileWorkspace();
        }
        executeHeal(btnRunHostile);
      });
    }

    // Approve Action
    btnApprove.addEventListener('click', async () => {
      if (!state.workspaceId) {
        console.warn("No active workspace to approve");
        return;
      }
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
          updateUI();

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
        const inputStoryScope = document.getElementById('input-story-scope');
        const scopeVal = inputStoryScope ? inputStoryScope.value.trim() : "";
        const scope = scopeVal ? [scopeVal] : undefined;
        btnSubmitStory.disabled = true;
        btnSubmitStory.innerText = "Executing Governed DAG...";
        try {
          let res;
          if (state.workspaceId && state.workspaceId.startsWith("real_")) {
            res = await apiPost('/api/real/story', { story: prompt, story_prompt: prompt, scope: scope });
          } else {
            res = await apiPost(`/api/demo/${state.workspaceId}/story`, { story_prompt: prompt, scope: scope });
          }
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

    // =========================================================================
    // Real Workspace & Pre-Flight Doctor Workstation (v1.3.0)
    // =========================================================================
    const pillDoctor = document.getElementById('pill-doctor');
    const labelDoctor = document.getElementById('label-doctor');
    const inputRealWorkspace = document.getElementById('input-real-workspace');
    const btnLoadWorkspace = document.getElementById('btn-load-workspace');
    const btnRunShadow = document.getElementById('btn-run-shadow');
    const btnRunRealHeal = document.getElementById('btn-run-real-heal');
    const inputHealScope = document.getElementById('input-heal-scope');
    const inputHealCmd = document.getElementById('input-heal-cmd');

    async function fetchDoctorStatus(ping = false) {
      if (labelDoctor) labelDoctor.innerText = ping ? "🔄 Pinging..." : "🩺 Doctor: Checking...";
      try {
        const res = await apiGet(`/api/real/doctor?ping=${ping}`);
        if (res && res.status === "success") {
          if (inputRealWorkspace && (!inputRealWorkspace.value || inputRealWorkspace.value === ".")) {
            inputRealWorkspace.value = res.workspace_path;
          }
          const osShort = res.os_family || (res.os_name ? res.os_name.substring(0, 3) : "OS");
          const pyShort = res.python_version ? res.python_version.split('.').slice(0, 2).join('.') : "3.10";
          const pwVer = res.playwright_version ? res.playwright_version.replace(/^(Version|python-playwright|Version\\s+)/i, '').trim().split(' ')[0] : (res.has_playwright ? 'Ready' : 'None');
          if (labelDoctor) {
            labelDoctor.innerText = `🩺 ${osShort} · Py ${pyShort} · PW ${pwVer}`;
          }
          if (pillDoctor) {
            pillDoctor.className = res.is_live_llm ? "meta-pill status-green" : "meta-pill";
            pillDoctor.title = `Hermes Pre-Flight Doctor:\n• OS: ${res.os_name} ${res.os_release || ''}\n• Python: ${res.python_version}\n• Git: ${res.git_version}\n• Playwright: ${res.playwright_version || (res.has_playwright ? 'Ready' : 'Not installed')}\n• Node: ${res.node_version || 'Not installed'}\n• LLM: ${res.llm_provider} (${res.llm_status})${res.ping_ms !== null ? ' • ' + res.ping_ms + 'ms' : ''}\n• AST Guard: ${res.tree_sitter || 'Active'}\n\nClick to ping live LLM`;
          }
          // Dynamic sync of provider pill
          const labelP = document.getElementById('label-provider');
          if (labelP && res.llm_provider) {
            const modelName = res.llm_model || (res.llm_provider === 'OLLAMA' ? 'qwen2.5-coder:7b' : 'heuristic');
            labelP.innerText = `🤖 ${res.llm_provider} · ${modelName}`;
          }
        }
      } catch (e) {
        if (labelDoctor) labelDoctor.innerText = "⚠️ Doctor Error";
      }
    }

    if (pillDoctor) {
      pillDoctor.addEventListener('click', () => fetchDoctorStatus(true));
    }

    // Left Rail Dual Mode (Failures vs Discovered Tests)
    const btnTabFailures = document.getElementById('btn-tab-failures');
    const btnTabTests = document.getElementById('btn-tab-tests');
    const listFailures = document.getElementById('rail-inbox-list');
    const listTests = document.getElementById('rail-tests-list');

    function switchRailTab(tab) {
      if (tab === 'tests') {
        if (btnTabTests) {
          btnTabTests.style.background = 'var(--bg-card)';
          btnTabTests.style.color = 'var(--text-main)';
          btnTabTests.style.borderColor = 'var(--border-hairline)';
        }
        if (btnTabFailures) {
          btnTabFailures.style.background = 'transparent';
          btnTabFailures.style.color = 'var(--text-dim)';
          btnTabFailures.style.borderColor = 'transparent';
        }
        const containerTests = document.getElementById('rail-tests-container');
        if (listFailures) listFailures.style.display = 'none';
        if (containerTests) containerTests.style.display = 'flex';
      } else {
        if (btnTabFailures) {
          btnTabFailures.style.background = 'var(--bg-card)';
          btnTabFailures.style.color = 'var(--text-main)';
          btnTabFailures.style.borderColor = 'var(--border-hairline)';
        }
        if (btnTabTests) {
          btnTabTests.style.background = 'transparent';
          btnTabTests.style.color = 'var(--text-dim)';
          btnTabTests.style.borderColor = 'transparent';
        }
        const containerTests = document.getElementById('rail-tests-container');
        if (listFailures) listFailures.style.display = 'flex';
        if (containerTests) containerTests.style.display = 'none';
      }
    }

    if (btnTabFailures) btnTabFailures.addEventListener('click', () => switchRailTab('failures'));
    if (btnTabTests) btnTabTests.addEventListener('click', () => switchRailTab('tests'));

    // Test Discovery & Terminal Execution
    async function discoverRealWorkspace() {
      try {
        const res = await apiGet('/api/real/discover');
        if (res) {
          discoveredTestsList = res.tests || [];
          discoveredArtifactsList = res.artifacts || [];
          const countArt = document.getElementById('count-artifacts');
          if (countArt) countArt.innerText = discoveredArtifactsList.length;
          renderFilteredDiscoveredTests();

          // Check for trace files in artifacts
          if (res.artifacts && btnOpenTraceViewer) {
            const traceArt = res.artifacts.find(a => a.type === 'PLAYWRIGHT_TRACE' || (a.file_name && a.file_name.endsWith('.zip')));
            if (traceArt) {
              btnOpenTraceViewer.style.display = 'inline-block';
              btnOpenTraceViewer.setAttribute('data-trace-path', traceArt.rel_path);
            }
          }
        }
      } catch (e) {
        console.error("Discovery error:", e);
      }
    }

    async function runTestInTerminal(testPath, cmd) {
      const drawer = document.getElementById('terminal-drawer');
      const termOutput = document.getElementById('term-output');
      const statusBadge = document.getElementById('term-status-badge');
      const cmdLabel = document.getElementById('term-cmd-label');
      const elapsedLabel = document.getElementById('term-elapsed');
      const btnHeal = document.getElementById('btn-term-heal');

      if (drawer) drawer.style.display = 'flex';
      if (statusBadge) {
        statusBadge.innerText = 'RUNNING';
        statusBadge.style.color = '#fbbf24';
        statusBadge.style.background = 'rgba(251,191,36,0.12)';
      }
      if (cmdLabel) cmdLabel.innerText = testPath ? `[${testPath}]` : '';
      if (termOutput) termOutput.innerText = `🚀 Running: ${testPath} ...\n\n`;
      if (btnHeal) btnHeal.style.display = 'none';

      const t0 = Date.now();
      const timer = setInterval(() => {
        if (elapsedLabel) elapsedLabel.innerText = ((Date.now() - t0) / 1000).toFixed(1) + 's';
      }, 100);

      let accumulated = "";
      let sseFinished = false;

      // Try Live Streaming via SSE first
      if (window.EventSource) {
        const streamUrl = `/api/real/run-test-stream?test_path=${encodeURIComponent(testPath)}${cmd ? '&cmd=' + encodeURIComponent(cmd) : ''}`;
        const es = new EventSource(streamUrl);

        es.addEventListener('line', (e) => {
          try {
            const data = JSON.parse(e.data);
            accumulated += data.text;
            if (termOutput) {
              termOutput.innerHTML = ansiToHtml(accumulated);
              termOutput.scrollTop = termOutput.scrollHeight;
            }
          } catch (_) {}
        });

        es.addEventListener('exit', (e) => {
          sseFinished = true;
          clearInterval(timer);
          es.close();
          try {
            const res = JSON.parse(e.data);
            if (elapsedLabel) elapsedLabel.innerText = (res.elapsed_s || 0) + 's';
            if (res.passed) {
              if (statusBadge) {
                statusBadge.innerText = 'PASSED';
                statusBadge.style.color = '#4ade80';
                statusBadge.style.background = 'rgba(74,222,128,0.12)';
              }
            } else {
              if (statusBadge) {
                statusBadge.innerText = 'FAILED';
                statusBadge.style.color = '#f87171';
                statusBadge.style.background = 'rgba(248,113,113,0.12)';
              }
              if (btnHeal) {
                btnHeal.style.display = 'inline-block';
                btnHeal.onclick = () => {
                  const inputScope = document.getElementById('input-heal-scope');
                  const inputFailure = document.getElementById('input-heal-failure');
                  if (inputScope) inputScope.value = testPath;
                  if (inputFailure) inputFailure.value = res.output || accumulated;
                  switchTab('inbox');
                  const controls = document.getElementById('real-workspace-controls');
                  if (controls) controls.scrollIntoView({ behavior: 'smooth' });
                };
              }
            }
          } catch (_) {}
        });

        es.onerror = async () => {
          es.close();
          if (sseFinished) return;
          // Clean fallback to standard POST endpoint
          try {
            const res = await apiPost('/api/real/run-test', { test_path: testPath, cmd: cmd });
            clearInterval(timer);
            if (elapsedLabel) elapsedLabel.innerText = (res.elapsed_s || 0) + 's';
            if (termOutput) termOutput.innerHTML = ansiToHtml(res.output || "No output returned.");

            if (res.passed) {
              if (statusBadge) {
                statusBadge.innerText = 'PASSED';
                statusBadge.style.color = '#4ade80';
                statusBadge.style.background = 'rgba(74,222,128,0.12)';
              }
            } else {
              if (statusBadge) {
                statusBadge.innerText = 'FAILED';
                statusBadge.style.color = '#f87171';
                statusBadge.style.background = 'rgba(248,113,113,0.12)';
              }
              if (btnHeal) {
                btnHeal.style.display = 'inline-block';
                btnHeal.onclick = () => {
                  const inputScope = document.getElementById('input-heal-scope');
                  const inputFailure = document.getElementById('input-heal-failure');
                  if (inputScope) inputScope.value = testPath;
                  if (inputFailure) inputFailure.value = res.output;
                  switchTab('inbox');
                  const controls = document.getElementById('real-workspace-controls');
                  if (controls) controls.scrollIntoView({ behavior: 'smooth' });
                };
              }
            }
          } catch (err) {
            clearInterval(timer);
            if (statusBadge) {
              statusBadge.innerText = 'ERROR';
              statusBadge.style.color = '#f87171';
            }
            if (termOutput) termOutput.innerHTML = ansiToHtml("Execution failed: " + err.message);
          }
        };
        return;
      }

      // Synchronous fallback if EventSource is unavailable
      try {
        const res = await apiPost('/api/real/run-test', { test_path: testPath, cmd: cmd });
        clearInterval(timer);
        if (elapsedLabel) elapsedLabel.innerText = (res.elapsed_s || 0) + 's';
        if (termOutput) termOutput.innerHTML = ansiToHtml(res.output || "No output returned.");

        if (res.passed) {
          if (statusBadge) {
            statusBadge.innerText = 'PASSED';
            statusBadge.style.color = '#4ade80';
            statusBadge.style.background = 'rgba(74,222,128,0.12)';
          }
        } else {
          if (statusBadge) {
            statusBadge.innerText = 'FAILED';
            statusBadge.style.color = '#f87171';
            statusBadge.style.background = 'rgba(248,113,113,0.12)';
          }
          if (btnHeal) {
            btnHeal.style.display = 'inline-block';
            btnHeal.onclick = () => {
              const inputScope = document.getElementById('input-heal-scope');
              const inputFailure = document.getElementById('input-heal-failure');
              if (inputScope) inputScope.value = testPath;
              if (inputFailure) inputFailure.value = res.output;
              switchTab('inbox');
              const controls = document.getElementById('real-workspace-controls');
              if (controls) controls.scrollIntoView({ behavior: 'smooth' });
            };
          }
        }
      } catch (err) {
        clearInterval(timer);
        if (statusBadge) {
          statusBadge.innerText = 'ERROR';
          statusBadge.style.color = '#f87171';
        }
        if (termOutput) termOutput.innerHTML = ansiToHtml("Execution failed: " + err.message);
      }
    }

    // Terminal Drawer Controls
    const btnTermClose = document.getElementById('btn-term-close');
    const btnTermClear = document.getElementById('btn-term-clear');
    const btnTermCopy = document.getElementById('btn-term-copy');
    const btnTermExpand = document.getElementById('btn-term-expand');

    if (btnTermClose) btnTermClose.addEventListener('click', () => {
      const drawer = document.getElementById('terminal-drawer');
      if (drawer) drawer.style.display = 'none';
    });
    if (btnTermClear) btnTermClear.addEventListener('click', () => {
      const termOutput = document.getElementById('term-output');
      if (termOutput) termOutput.innerText = '';
    });
    if (btnTermCopy) btnTermCopy.addEventListener('click', () => {
      const termOutput = document.getElementById('term-output');
      if (termOutput) {
        navigator.clipboard.writeText(termOutput.innerText);
        btnTermCopy.innerText = "✅ Copied";
        setTimeout(() => { btnTermCopy.innerText = "📋 Copy"; }, 1500);
      }
    });
    if (btnTermExpand) btnTermExpand.addEventListener('click', () => {
      const drawer = document.getElementById('terminal-drawer');
      if (drawer) {
        const isExp = drawer.style.height === '480px';
        drawer.style.height = isExp ? '230px' : '480px';
        btnTermExpand.innerText = isExp ? '↕ Expand' : '↕ Compact';
      }
    });

    if (btnLoadWorkspace && inputRealWorkspace) {
      btnLoadWorkspace.addEventListener('click', async () => {
        const path = inputRealWorkspace.value.trim();
        if (!path) return;
        try {
          btnLoadWorkspace.innerText = "Loading...";
          const res = await apiPost('/api/real/workspace', { workspace_path: path });
          if (res && res.workspace_id) {
            state.workspaceId = res.workspace_id;
            state.workspaceName = res.workspace_name;
            if (labelWorkspace) labelWorkspace.innerText = res.workspace_name;
            await fetchDoctorStatus(false);
            await loadRealSnapshots();
            await discoverRealWorkspace();
            switchRailTab('tests');
          }
        } catch (err) {
          alert("Failed to load workspace: " + err.message);
        } finally {
          btnLoadWorkspace.innerText = "📂 Load";
        }
      });
      inputRealWorkspace.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') btnLoadWorkspace.click();
      });
    }

    async function executeRealHeal(isShadow) {
      const scopeVal = inputHealScope ? inputHealScope.value.trim() : "";
      const cmdVal = inputHealCmd ? inputHealCmd.value.trim() : "";
      const scope = scopeVal ? scopeVal.split(',').map(s => s.trim()) : null;
      const pytest_cmd = cmdVal ? cmdVal.split(' ') : null;

      const btn = isShadow ? btnRunShadow : btnRunRealHeal;
      const origText = btn ? btn.innerText : "";
      if (btn) {
        btn.disabled = true;
        btn.innerText = isShadow ? "🛡️ Running Shadow Pass..." : "⚡ Healing & Verifying...";
      }

      switchTab('sprint');
      connectSSE(state.workspaceId);

      try {
        const res = await apiPost('/api/real/heal', {
          workspace_path: inputRealWorkspace ? inputRealWorkspace.value.trim() : null,
          scope: scope,
          pytest_cmd: pytest_cmd,
          shadow: isShadow
        });
        state.status = res.workspace_status || (isShadow ? "SHADOW_SUGGESTION" : "COMPLETED");
        state.sprintId = res.sprint_id;
        state.snapshotId = res.snapshot_id;
        updateUI();
        await loadProposalDiff();
        await loadRealSnapshots();
      } catch (e) {
        alert("Heal execution error: " + e.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerText = origText;
        }
      }
    }

    if (btnRunShadow) btnRunShadow.addEventListener('click', () => executeRealHeal(true));
    if (btnRunRealHeal) btnRunRealHeal.addEventListener('click', () => executeRealHeal(false));

    async function loadRealSnapshots() {
      const tmList = document.getElementById('tm-snapshot-list');
      if (!tmList) return;
      try {
        const res = await apiGet('/api/real/snapshots');
        if (res && res.snapshots && res.snapshots.length > 0) {
          let html = '';
          for (const s of res.snapshots) {
            const timeStr = s.created_at ? new Date(s.created_at * 1000).toLocaleTimeString() : "Recent";
            const files = s.files ? Object.keys(s.files).join(', ') : (s.target || "workspace");
            html += `
              <div class="detail-card" style="margin-bottom: 8px;">
                <div class="detail-card-header">
                  <div>
                    <div style="font-size: 13px; font-weight: 600; font-family: var(--font-mono);">${s.snapshot_id}</div>
                    <div style="display: flex; gap: 6px; margin-top: 4px;">
                      <span class="tag-badge test-bug">${timeStr}</span>
                      <span class="tag-badge test-bug">Files: ${files}</span>
                    </div>
                  </div>
                  <div style="display: flex; gap: 6px;">
                    <button class="btn-top btn-snap-diff" data-snap="${s.snapshot_id}" style="padding: 4px 8px; font-size: 11px;">👁️ Diff</button>
                    <button class="btn-action-rewind btn-snap-rollback" data-snap="${s.snapshot_id}" style="padding: 4px 8px; font-size: 11px;">↺ Rollback</button>
                  </div>
                </div>
              </div>`;
          }
          tmList.innerHTML = html;

          document.querySelectorAll('.btn-snap-rollback').forEach(b => {
            b.addEventListener('click', async () => {
              const snapId = b.getAttribute('data-snap');
              if (confirm(`Rollback workspace to snapshot ${snapId}?`)) {
                try {
                  await apiPost('/api/real/rollback', { snapshot_id: snapId });
                  alert(`Restored workspace to ${snapId}!`);
                  state.status = "ROLLED_BACK";
                  updateUI();
                  await loadRealSnapshots();
                } catch (err) {
                  alert("Rollback failed: " + err.message);
                }
              }
            });
          });

          document.querySelectorAll('.btn-snap-diff').forEach(b => {
            b.addEventListener('click', () => {
              switchTab('diff');
            });
          });
        }
      } catch (e) {}
    }

    // =========================================================================
    // Text Escaping & ANSI Color Support
    // =========================================================================
    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function ansiToHtml(str) {
      if (!str) return '';
      return escapeHtml(str)
        .replace(/\\x1b\\[32m/g, '<span style="color:#4ade80;font-weight:600;">')
        .replace(/\\x1b\\[31m/g, '<span style="color:#f87171;font-weight:600;">')
        .replace(/\\x1b\\[33m/g, '<span style="color:#fbbf24;font-weight:600;">')
        .replace(/\\x1b\\[36m/g, '<span style="color:#38bdf8;">')
        .replace(/\\x1b\\[35m/g, '<span style="color:#c084fc;">')
        .replace(/\\x1b\\[1m/g, '<span style="font-weight:bold;">')
        .replace(/\\x1b\\[0m|\\x1b\\[39m/g, '</span>');
    }

    // =========================================================================
    // Side-by-Side Split Diff Engine
    // =========================================================================
    function renderSplitDiff(diffText) {
      const leftCol = document.getElementById('diff-split-left');
      const rightCol = document.getElementById('diff-split-right');
      if (!leftCol || !rightCol) return;

      const lines = (diffText || '').split('\\n');
      let leftHtml = '';
      let rightHtml = '';
      let leftNum = 1;
      let rightNum = 1;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.startsWith('---') || line.startsWith('+++')) continue;
        if (line.startsWith('@@')) {
          const match = line.match(/@@\\s+-(\\d+)(?:,\\d+)?\\s+\\+(\\d+)(?:,\\d+)?\\s+@@/);
          if (match) {
            leftNum = parseInt(match[1], 10);
            rightNum = parseInt(match[2], 10);
          }
          leftHtml += `<div style="color:var(--text-dim); background:rgba(255,255,255,0.03); padding:2px 8px; font-size:10px;">${escapeHtml(line)}</div>`;
          rightHtml += `<div style="color:var(--text-dim); background:rgba(255,255,255,0.03); padding:2px 8px; font-size:10px;">${escapeHtml(line)}</div>`;
          continue;
        }

        if (line.startsWith('-')) {
          leftHtml += `<div class="diff-line-row diff-line-del"><span class="diff-line-num" style="color:#ef4444;">${leftNum++}</span><span style="user-select:none; color:#ef4444; padding:0 4px;">-</span><span class="diff-line-content">${escapeHtml(line.slice(1))}</span></div>`;
        } else if (line.startsWith('+')) {
          rightHtml += `<div class="diff-line-row diff-line-add"><span class="diff-line-num" style="color:#22c55e;">${rightNum++}</span><span style="user-select:none; color:#22c55e; padding:0 4px;">+</span><span class="diff-line-content">${escapeHtml(line.slice(1))}</span></div>`;
        } else {
          const content = line.startsWith(' ') ? line.slice(1) : line;
          leftHtml += `<div class="diff-line-row"><span class="diff-line-num">${leftNum++}</span><span style="user-select:none; opacity:0; padding:0 4px;"> </span><span class="diff-line-content">${escapeHtml(content)}</span></div>`;
          rightHtml += `<div class="diff-line-row"><span class="diff-line-num">${rightNum++}</span><span style="user-select:none; opacity:0; padding:0 4px;"> </span><span class="diff-line-content">${escapeHtml(content)}</span></div>`;
        }
      }

      leftCol.innerHTML = leftHtml || '<div style="padding:10px; color:var(--text-dim);">No baseline differences</div>';
      rightCol.innerHTML = rightHtml || '<div style="padding:10px; color:var(--text-dim);">No proposal differences</div>';
    }

    function switchDiffMode(mode) {
      const btnUnified = document.getElementById('btn-diff-mode-unified');
      const btnSplit = document.getElementById('btn-diff-mode-split');
      const btnEdit = document.getElementById('btn-diff-mode-edit');
      const viewUnified = document.getElementById('diff-text');
      const viewSplit = document.getElementById('diff-split-view');
      const viewEdit = document.getElementById('diff-manual-view');

      if (btnUnified) btnUnified.classList.toggle('active', mode === 'unified');
      if (btnSplit) btnSplit.classList.toggle('active', mode === 'split');
      if (btnEdit) btnEdit.classList.toggle('active', mode === 'edit');

      if (viewUnified) viewUnified.style.display = (mode === 'unified') ? 'block' : 'none';
      if (viewSplit) viewSplit.style.display = (mode === 'split') ? 'flex' : 'none';
      if (viewEdit) viewEdit.style.display = (mode === 'edit') ? 'block' : 'none';

      if (mode === 'split' && state.diffText) {
        renderSplitDiff(state.diffText);
      } else if (mode === 'edit') {
        const editor = document.getElementById('diff-manual-editor');
        if (editor && !editor.dataset.userEdited) {
          editor.value = state.diffText || "# Edit proposed patch code here...";
        }
      }
    }

    const btnDiffModeUnified = document.getElementById('btn-diff-mode-unified');
    const btnDiffModeSplit = document.getElementById('btn-diff-mode-split');
    const btnDiffModeEdit = document.getElementById('btn-diff-mode-edit');
    const btnCopyDiff = document.getElementById('btn-copy-diff');
    const btnDownloadPatch = document.getElementById('btn-download-patch');

    if (btnDiffModeUnified) btnDiffModeUnified.addEventListener('click', () => switchDiffMode('unified'));
    if (btnDiffModeSplit) btnDiffModeSplit.addEventListener('click', () => switchDiffMode('split'));
    if (btnDiffModeEdit) btnDiffModeEdit.addEventListener('click', () => switchDiffMode('edit'));

    if (btnCopyDiff) {
      btnCopyDiff.addEventListener('click', () => {
        if (state.diffText) {
          navigator.clipboard.writeText(state.diffText);
          btnCopyDiff.innerText = "✓ Copied";
          setTimeout(() => { btnCopyDiff.innerText = "📋 Copy Diff"; }, 1500);
        }
      });
    }

    if (btnDownloadPatch) {
      btnDownloadPatch.addEventListener('click', () => {
        if (!state.diffText) return;
        const blob = new Blob([state.diffText], { type: 'text/x-diff' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `hermes_${state.sprintId || 'patch'}.patch`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    // Manual Tweaker AST Validation
    const btnValidateManualAST = document.getElementById('btn-validate-manual-ast');
    const diffManualEditor = document.getElementById('diff-manual-editor');
    const diffAstBadge = document.getElementById('diff-ast-badge');
    const diffAstFeedback = document.getElementById('diff-ast-feedback');

    if (diffManualEditor) {
      diffManualEditor.addEventListener('input', () => {
        diffManualEditor.dataset.userEdited = "1";
        if (diffAstBadge) diffAstBadge.style.display = 'none';
        if (diffAstFeedback) diffAstFeedback.style.display = 'none';
      });
    }

    if (btnValidateManualAST && diffManualEditor) {
      btnValidateManualAST.addEventListener('click', async () => {
        const code = diffManualEditor.value;
        const targetPath = state.scope[0] || "patch.py";
        btnValidateManualAST.disabled = true;
        btnValidateManualAST.innerText = "Validating...";

        try {
          const res = await apiPost('/api/real/validate-ast', {
            code: code,
            filepath: targetPath,
            allow_test_modification: true
          });

          if (res.valid) {
            if (diffAstBadge) {
              diffAstBadge.style.display = 'inline-block';
              diffAstBadge.innerText = '✓ AST VERIFIED';
              diffAstBadge.style.background = 'rgba(74,222,128,0.15)';
              diffAstBadge.style.color = '#4ade80';
            }
            if (diffAstFeedback) {
              diffAstFeedback.style.display = 'block';
              diffAstFeedback.style.color = '#4ade80';
              diffAstFeedback.innerText = '✓ Code passed AST Patch Guard with zero prohibited calls and verified assertion integrity.';
            }
            state.diffText = code;
            if (diffTextContainer) diffTextContainer.innerText = state.diffText;
            renderSplitDiff(state.diffText);
          } else {
            if (diffAstBadge) {
              diffAstBadge.style.display = 'inline-block';
              diffAstBadge.innerText = '✗ AST REJECTED';
              diffAstBadge.style.background = 'rgba(248,113,113,0.15)';
              diffAstBadge.style.color = '#f87171';
            }
            if (diffAstFeedback) {
              diffAstFeedback.style.display = 'block';
              diffAstFeedback.style.color = '#f87171';
              diffAstFeedback.innerText = `Security / Syntax Violation:\n${res.error || 'Syntax validation failed'}`;
            }
          }
        } catch (err) {
          if (diffAstFeedback) {
            diffAstFeedback.style.display = 'block';
            diffAstFeedback.style.color = '#f87171';
            diffAstFeedback.innerText = "Validation error: " + err.message;
          }
        } finally {
          btnValidateManualAST.disabled = false;
          btnValidateManualAST.innerText = "✓ Validate AST & Apply";
        }
      });
    }

    // =========================================================================
    // Playwright Locator Resilience Studio (UI Self-Healing)
    // =========================================================================
    const btnAuditSelector = document.getElementById('btn-audit-selector');
    const inputAuditSelector = document.getElementById('input-audit-selector');
    const btnCopyPyLocator = document.getElementById('btn-copy-py-locator');
    const btnCopyTsLocator = document.getElementById('btn-copy-ts-locator');
    const btnOpenTraceViewer = document.getElementById('btn-open-trace-viewer');

    async function auditLocator(selector) {
      const sel = selector || (inputAuditSelector ? inputAuditSelector.value.trim() : 'button#checkout');
      if (!sel) return;
      try {
        const res = await apiPost('/api/real/locator-audit', { selector: sel, is_python: true });
        if (res && res.status === 'success') {
          const scoreEl = document.getElementById('locator-score-label');
          const badgeEl = document.getElementById('locator-studio-badge');
          const brittleText = document.getElementById('locator-brittle-text');
          const brittleReason = document.getElementById('locator-brittle-reason');
          const healedText = document.getElementById('locator-healed-text');
          const healedReason = document.getElementById('locator-healed-reason');

          if (scoreEl) {
            scoreEl.innerText = `${res.resilience_score}%`;
            scoreEl.style.color = res.resilience_score >= 80 ? '#4ade80' : (res.resilience_score >= 50 ? '#fbbf24' : '#f87171');
          }
          if (badgeEl) {
            badgeEl.innerText = res.is_brittle ? "BRITTLE DETECTED" : "RESILIENT INVARIANT";
            badgeEl.style.color = res.is_brittle ? "#f87171" : "#4ade80";
            badgeEl.style.background = res.is_brittle ? "rgba(248,113,113,0.15)" : "rgba(74,222,128,0.15)";
          }
          if (brittleText) brittleText.innerText = res.original_selector;
          if (brittleReason) brittleReason.innerText = res.reasons.length ? res.reasons.join(' ') : "Selector strategy evaluated.";
          if (healedText) healedText.innerText = res.upgraded_python;
          if (healedReason) healedReason.innerText = "Modern accessible Playwright locator. Auto-waits and respects ARIA hierarchy.";

          const altList = document.getElementById('locator-alt-list');
          if (altList && res.alternatives) {
            let altHtml = '<span>Alternatives:</span> ';
            res.alternatives.slice(1).forEach((alt, idx) => {
              if (idx > 0) altHtml += ' <span>&middot;</span> ';
              altHtml += `<span class="locator-alt-tag" data-py="${escapeHtml(alt.py)}" style="cursor:pointer;" title="${alt.strategy}">${escapeHtml(alt.strategy.split(' ')[0])} (${alt.resilience}%)</span>`;
            });
            altList.innerHTML = altHtml;
            altList.querySelectorAll('.locator-alt-tag').forEach(tag => {
              tag.addEventListener('click', () => {
                const pyCode = tag.getAttribute('data-py');
                if (healedText) healedText.innerText = pyCode;
              });
            });
          }
        }
      } catch (e) {
        console.error("Locator audit error:", e);
      }
    }

    if (btnAuditSelector) btnAuditSelector.addEventListener('click', () => auditLocator());
    if (inputAuditSelector) {
      inputAuditSelector.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') auditLocator();
      });
    }

    if (btnCopyPyLocator) {
      btnCopyPyLocator.addEventListener('click', () => {
        const text = document.getElementById('locator-healed-text');
        if (text) {
          navigator.clipboard.writeText(text.innerText);
          btnCopyPyLocator.innerText = "✓ Copied";
          setTimeout(() => { btnCopyPyLocator.innerText = "📋 Python"; }, 1500);
        }
      });
    }

    if (btnCopyTsLocator) {
      btnCopyTsLocator.addEventListener('click', () => {
        const sel = inputAuditSelector ? inputAuditSelector.value.trim() : "";
        const clean = sel.replace(/^[#\\.]|[>\\(\\)\"']/g, '').split(' ').pop() || "element";
        const cleanTitle = clean.replace(/[-_]/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
        const tsCode = `page.getByRole('button', { name: '${cleanTitle}' })`;
        navigator.clipboard.writeText(tsCode);
        btnCopyTsLocator.innerText = "✓ Copied";
        setTimeout(() => { btnCopyTsLocator.innerText = "📋 TS"; }, 1500);
      });
    }

    if (btnOpenTraceViewer) {
      btnOpenTraceViewer.addEventListener('click', async () => {
        const tracePath = btnOpenTraceViewer.getAttribute('data-trace-path');
        if (!tracePath) return;
        try {
          btnOpenTraceViewer.innerText = "Launching Trace...";
          const res = await apiPost('/api/real/open-trace', { trace_path: tracePath });
          alert(res.message || "Trace viewer launched!");
        } catch (err) {
          alert("Failed to launch trace viewer: " + err.message);
        } finally {
          btnOpenTraceViewer.innerText = "🎭 Open in Trace Viewer";
        }
      });
    }

    // =========================================================================
    // Interactive DOM & Selector Strict-Mode Validator
    // =========================================================================
    const btnPlaygroundToggle = document.getElementById('btn-playground-toggle');
    const playgroundContainer = document.getElementById('playground-container');
    const btnPlaygroundSample = document.getElementById('btn-playground-load-sample');
    const playgroundDom = document.getElementById('playground-dom');
    const playgroundPreview = document.getElementById('playground-preview');
    const playgroundMatchCount = document.getElementById('playground-match-count');
    const playgroundStatusBadge = document.getElementById('playground-status-badge');

    if (btnPlaygroundToggle && playgroundContainer) {
      btnPlaygroundToggle.addEventListener('click', () => {
        const isHidden = playgroundContainer.style.display === 'none';
        playgroundContainer.style.display = isHidden ? 'flex' : 'none';
        btnPlaygroundToggle.innerText = isHidden ? '▲ Hide' : '↕ Toggle';
      });
    }

    const sampleHtmlSnippet = `<div class="checkout-container" id="checkout-view">\n  <h2>Shopping Cart & Checkout</h2>\n  <div class="cart-items">\n    <div class="item" data-testid="cart-item-1">Item A - $29.99</div>\n  </div>\n  <div class="actions">\n    <button id="checkout" class="btn btn-primary" data-testid="checkout-btn" aria-label="Proceed to checkout">Checkout</button>\n    <button class="btn btn-secondary" data-testid="cancel-btn">Cancel</button>\n  </div>\n</div>`;

    if (btnPlaygroundSample && playgroundDom) {
      btnPlaygroundSample.addEventListener('click', () => {
        playgroundDom.value = sampleHtmlSnippet;
        if (playgroundContainer) playgroundContainer.style.display = 'flex';
        if (btnPlaygroundToggle) btnPlaygroundToggle.innerText = '▲ Hide';
        evaluatePlaygroundSelector();
      });
    }

    function evaluatePlaygroundSelector() {
      if (!playgroundDom || !playgroundPreview) return;
      const html = playgroundDom.value.trim();
      const sel = (inputAuditSelector ? inputAuditSelector.value.trim() : '');
      if (!html) {
        playgroundPreview.innerHTML = '<div style="color: var(--text-dim); font-size: 10px;">Paste DOM HTML or click Sample DOM to evaluate...</div>';
        if (playgroundMatchCount) playgroundMatchCount.innerText = '0 matched';
        return;
      }
      try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        let matchedElements = [];

        if (sel.startsWith('//') || sel.startsWith('(')) {
          const xpathResult = doc.evaluate(sel, doc.body, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          for (let i = 0; i < xpathResult.snapshotLength; i++) {
            matchedElements.push(xpathResult.snapshotItem(i));
          }
        } else {
          const cleanCss = sel.replace(/:has-text\\([^)]+\\)/g, '').trim();
          if (cleanCss) {
            matchedElements = Array.from(doc.querySelectorAll(cleanCss));
          }
        }

        const count = matchedElements.length;
        if (playgroundMatchCount) {
          playgroundMatchCount.innerText = count + (count === 1 ? ' element' : ' elements');
        }

        if (playgroundStatusBadge) {
          if (count === 1) {
            playgroundStatusBadge.innerText = 'STRICT PASS ✅';
            playgroundStatusBadge.style.color = '#4ade80';
            playgroundStatusBadge.style.background = 'rgba(74,222,128,0.15)';
          } else if (count > 1) {
            playgroundStatusBadge.innerText = 'VIOLATION ⚠️ (' + count + ')';
            playgroundStatusBadge.style.color = '#f87171';
            playgroundStatusBadge.style.background = 'rgba(248,113,113,0.15)';
          } else {
            playgroundStatusBadge.innerText = 'NO MATCH ❌';
            playgroundStatusBadge.style.color = '#fbbf24';
            playgroundStatusBadge.style.background = 'rgba(251,191,36,0.15)';
          }
        }

        if (count === 0) {
          playgroundPreview.innerHTML = '<div style="color: #f87171; font-size: 11px;">No elements match selector <code>' + escapeHtml(sel) + '</code>.</div>';
        } else {
          let outHtml = '<div style="color: #4ade80; font-size: 10px; margin-bottom: 4px;">Found ' + count + ' matching node(s):</div>';
          matchedElements.forEach((el, idx) => {
            const tag = el.tagName ? el.tagName.toLowerCase() : 'node';
            const idAttr = el.id ? ' id="' + el.id + '"' : '';
            const classAttr = el.className ? ' class="' + el.className + '"' : '';
            const testId = el.getAttribute('data-testid') ? ' data-testid="' + el.getAttribute('data-testid') + '"' : '';
            const text = (el.innerText || el.textContent || '').trim().substring(0, 30);
            outHtml += '<div style="background: rgba(74,222,128,0.08); border-left: 2px solid #4ade80; padding: 2px 6px; margin-bottom: 3px; font-size: 10px;">' +
              '<strong>#' + (idx + 1) + '</strong> &lt;' + tag + idAttr + classAttr + testId + '&gt; ' + escapeHtml(text) +
            '</div>';
          });
          playgroundPreview.innerHTML = outHtml;
        }
      } catch (err) {
        if (playgroundPreview) {
          playgroundPreview.innerHTML = '<div style="color: #f87171; font-size: 10px;">Selector Evaluation Error: ' + escapeHtml(err.message) + '</div>';
        }
      }
    }

    if (playgroundDom) playgroundDom.addEventListener('input', evaluatePlaygroundSelector);
    if (inputAuditSelector) inputAuditSelector.addEventListener('input', evaluatePlaygroundSelector);

    // 1-Click Commit to Git Branch
    const btnCreateBranch = document.getElementById('btn-create-branch');
    if (btnCreateBranch) {
      btnCreateBranch.addEventListener('click', async () => {
        const origText = btnCreateBranch.innerHTML;
        try {
          btnCreateBranch.innerText = "Creating Branch...";
          const res = await apiPost('/api/real/create-git-branch', {});
          if (res && res.status === 'success') {
            alert('✅ Branch Created & Changes Committed Successfully!\\n\\n• Branch: ' + res.branch + '\\n• Commit: ' + res.commit_sha + '\\n\\n' + res.message);
            btnCreateBranch.innerHTML = '🌿 ' + res.branch;
            setTimeout(() => { btnCreateBranch.innerHTML = origText; }, 4000);
          }
        } catch (err) {
          alert("Branch Creation Failed: " + err.message);
        } finally {
          if (btnCreateBranch.innerText === "Creating Branch...") {
            btnCreateBranch.innerHTML = origText;
          }
        }
      });
    }

    // =========================================================================
    // Discovered Tests & Artifacts Explorer & Real-Time Filtering
    // =========================================================================
    let discoveredTestsList = [];
    let discoveredArtifactsList = [];
    let currentFilterType = 'all';

    const filterPillAll = document.getElementById('filter-pill-all');
    const filterPillPy = document.getElementById('filter-pill-py');
    const filterPillPw = document.getElementById('filter-pill-pw');
    const filterPillArt = document.getElementById('filter-pill-art');
    const countArtifacts = document.getElementById('count-artifacts');

    // Screenshot Lightbox Elements
    const modalLightbox = document.getElementById('modal-screenshot-lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxTitle = document.getElementById('lightbox-title');
    const lightboxPath = document.getElementById('lightbox-path');
    const lightboxDownload = document.getElementById('lightbox-download-link');
    const btnCloseLightbox = document.getElementById('btn-close-lightbox');

    function openScreenshotLightbox(relPath) {
      if (!modalLightbox || !lightboxImg) return;
      const fileUrl = `/api/real/artifact-file?path=${encodeURIComponent(relPath)}`;
      lightboxImg.src = fileUrl;
      if (lightboxTitle) lightboxTitle.innerText = `🖼️ Failure Screenshot: ${relPath.split('/').pop()}`;
      if (lightboxPath) lightboxPath.innerText = relPath;
      if (lightboxDownload) lightboxDownload.href = fileUrl;
      modalLightbox.style.display = 'flex';
    }

    if (btnCloseLightbox && modalLightbox) {
      btnCloseLightbox.addEventListener('click', () => {
        modalLightbox.style.display = 'none';
        if (lightboxImg) lightboxImg.src = '';
      });
      modalLightbox.addEventListener('click', (e) => {
        if (e.target === modalLightbox) {
          modalLightbox.style.display = 'none';
          if (lightboxImg) lightboxImg.src = '';
        }
      });
    }

    function renderFilteredDiscoveredTests() {
      const testsContainer = document.getElementById('rail-tests-list');
      const countLabel = document.getElementById('count-discovered-tests');
      const countAll = document.getElementById('count-all-tests');
      const filterInput = document.getElementById('filter-tests-input');
      const query = filterInput ? filterInput.value.toLowerCase().trim() : '';

      if (!testsContainer) return;

      if (countArtifacts) countArtifacts.innerText = discoveredArtifactsList.length;

      // Handle Artifacts view
      if (currentFilterType === 'art') {
        const filteredArt = discoveredArtifactsList.filter(a => {
          return !query || a.rel_path.toLowerCase().includes(query) || a.file_name.toLowerCase().includes(query);
        });
        if (countLabel) countLabel.innerText = filteredArt.length;
        if (countAll) countAll.innerText = discoveredTestsList.length;

        let html = '';
        if (!filteredArt.length) {
          html = '<div style="padding: 12px; color: var(--text-dim); font-size: 11px;">No failure artifacts found.</div>';
        } else {
          filteredArt.forEach(a => {
            let icon = '📋';
            let badgeClass = 'tag-badge';
            let actionBtn = '';
            if (a.type === 'FAILURE_SCREENSHOT') {
              icon = '🖼️';
              badgeClass = 'tag-badge test-bug';
              actionBtn = `<button class="btn-top btn-view-screenshot" data-rel="${escapeHtml(a.rel_path)}" style="padding: 2px 6px; font-size: 10px; color: #60a5fa; border-color: rgba(96,165,250,0.3);" title="Preview failure screenshot">👁️ View</button>`;
            } else if (a.type === 'PLAYWRIGHT_TRACE') {
              icon = '🎭';
              badgeClass = 'tag-badge prod-bug';
              actionBtn = `<button class="btn-top btn-open-trace-art" data-rel="${escapeHtml(a.rel_path)}" style="padding: 2px 6px; font-size: 10px; color: #c084fc; border-color: rgba(192,132,252,0.3);" title="Launch trace viewer">🎭 Trace</button>`;
            } else {
              icon = '📊';
              badgeClass = 'tag-badge';
              actionBtn = `<button class="btn-top btn-ingest-art" data-rel="${escapeHtml(a.rel_path)}" style="padding: 2px 6px; font-size: 10px; color: var(--copper); border-color: var(--copper-border);" title="Ingest into Healer Inbox">⚡ Triage</button>`;
            }
            html += `
              <div class="inbox-row artifact-row" style="cursor: default;">
                <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 4px;">
                  <div class="inbox-row-title" style="word-break: break-all; font-size: 11px;" title="${escapeHtml(a.rel_path)}">${icon} ${escapeHtml(a.file_name)}</div>
                </div>
                <div class="inbox-row-meta" style="justify-content: space-between; align-items: center; margin-top: 4px;">
                  <span class="${badgeClass}" style="font-size: 9px;">${a.type}</span>
                  <div style="display: flex; gap: 4px;">
                    ${actionBtn}
                  </div>
                </div>
              </div>`;
          });
        }
        testsContainer.innerHTML = html;

        document.querySelectorAll('.btn-view-screenshot').forEach(b => {
          b.addEventListener('click', (e) => {
            e.stopPropagation();
            const rel = b.getAttribute('data-rel');
            openScreenshotLightbox(rel);
          });
        });
        document.querySelectorAll('.btn-open-trace-art').forEach(b => {
          b.addEventListener('click', async (e) => {
            e.stopPropagation();
            const rel = b.getAttribute('data-rel');
            await apiPost('/api/real/open-trace', { trace_path: rel });
          });
        });
        document.querySelectorAll('.btn-ingest-art').forEach(b => {
          b.addEventListener('click', async (e) => {
            e.stopPropagation();
            const rel = b.getAttribute('data-rel');
            try {
              const res = await apiPost('/api/real/ingest-artifact', { artifact_rel_path: rel });
              alert('Ingested ' + (res.tickets_found || 0) + ' failure ticket(s) from ' + rel + '!');
              switchTab('inbox');
            } catch (err) {
              alert('Ingestion error: ' + err.message);
            }
          });
        });
        return;
      }

      const filtered = discoveredTestsList.filter(t => {
        const matchesQuery = !query || t.rel_path.toLowerCase().includes(query) || t.file_name.toLowerCase().includes(query);
        if (!matchesQuery) return false;
        if (currentFilterType === 'py') return t.framework === 'Pytest';
        if (currentFilterType === 'pw') return t.framework.includes('Playwright');
        return true;
      });

      if (countLabel) countLabel.innerText = filtered.length;
      if (countAll) countAll.innerText = discoveredTestsList.length;

      let html = '';
      if (filtered.length === 0) {
        html = '<div style="padding: 12px; color: var(--text-dim); font-size: 11px;">No tests matching filter.</div>';
      } else {
        filtered.forEach(t => {
          const fwBadge = t.framework === 'Python Playwright' ? 'tag-badge test-bug' : (t.framework === 'Playwright TS/JS' ? 'tag-badge' : 'tag-badge prod-bug');
          const fwIcon = t.framework.includes('Playwright') ? '🎭' : '🐍';
          html += `
            <div class="inbox-row discovered-test-row" data-test-path="${t.rel_path}">
              <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 4px;">
                <div class="inbox-row-title" style="word-break: break-all; font-size: 11px;" title="${t.rel_path}">${fwIcon} ${t.file_name}</div>
              </div>
              <div class="inbox-row-meta" style="justify-content: space-between; align-items: center; margin-top: 4px;">
                <span class="${fwBadge}" style="font-size: 9px;">${t.framework}</span>
                <div style="display: flex; gap: 4px;">
                  <button class="btn-top btn-run-single-test" data-test="${t.rel_path}" style="padding: 2px 6px; font-size: 10px;" title="Run test in workspace">▶ Run</button>
                  <button class="btn-top btn-heal-single-test" data-test="${t.rel_path}" style="padding: 2px 6px; font-size: 10px; color: var(--copper); border-color: var(--copper-border);" title="Send to autonomous healer">⚡ Heal</button>
                </div>
              </div>
            </div>`;
        });
      }
      testsContainer.innerHTML = html;

      document.querySelectorAll('.btn-run-single-test').forEach(b => {
        b.addEventListener('click', async (e) => {
          e.stopPropagation();
          const testPath = b.getAttribute('data-test');
          await runTestInTerminal(testPath);
        });
      });

      document.querySelectorAll('.btn-heal-single-test').forEach(b => {
        b.addEventListener('click', (e) => {
          e.stopPropagation();
          const testPath = b.getAttribute('data-test');
          const inputScope = document.getElementById('input-heal-scope');
          if (inputScope) inputScope.value = testPath;
          switchTab('inbox');
          const controls = document.getElementById('real-workspace-controls');
          if (controls) controls.scrollIntoView({ behavior: 'smooth' });
        });
      });
    }

    const filterTestsInput = document.getElementById('filter-tests-input');
    if (filterTestsInput) {
      filterTestsInput.addEventListener('input', () => renderFilteredDiscoveredTests());
    }

    function setFilterPillActive(activePill, type) {
      [filterPillAll, filterPillPy, filterPillPw, filterPillArt].forEach(p => {
        if (p) p.classList.remove('active');
      });
      if (activePill) activePill.classList.add('active');
      currentFilterType = type;
      renderFilteredDiscoveredTests();
    }

    if (filterPillAll) filterPillAll.addEventListener('click', () => setFilterPillActive(filterPillAll, 'all'));
    if (filterPillPy) filterPillPy.addEventListener('click', () => setFilterPillActive(filterPillPy, 'py'));
    if (filterPillPw) filterPillPw.addEventListener('click', () => setFilterPillActive(filterPillPw, 'pw'));
    if (filterPillArt) filterPillArt.addEventListener('click', () => setFilterPillActive(filterPillArt, 'art'));

    function updateRecentWorkspacesDropdown(newPath) {
      try {
        let recents = JSON.parse(localStorage.getItem('hermes_recent_workspaces') || '[]');
        if (newPath) {
          recents = [newPath, ...recents.filter(p => p !== newPath)].slice(0, 8);
          localStorage.setItem('hermes_recent_workspaces', JSON.stringify(recents));
        }
        const dl = document.getElementById('recent-workspaces-list');
        if (dl) {
          dl.innerHTML = recents.map(p => `<option value="${escapeHtml(p)}"></option>`).join('');
        }
      } catch (_) {}
    }
    updateRecentWorkspacesDropdown();

    const btnRunAllTests = document.getElementById('btn-run-all-tests');
    if (btnRunAllTests) {
      btnRunAllTests.addEventListener('click', async () => {
        if (!discoveredTestsList.length) return;
        const testPaths = discoveredTestsList.map(t => t.rel_path);
        await runTestInTerminal(testPaths.slice(0, 5).join(' '));
      });
    }

    // =========================================================================
    // Agent Step Details Inspector Modal
    // =========================================================================
    const agentDetailsData = {
      1: {
        title: "1. CIFailureIngestor & RequirementsAgent (TIER_2_SENIOR_SWE)",
        overview: "Ingests JUnit XML, CTRF JSON, and Playwright trace.zip artifacts without workspace mutations. Computes SHA-256 failure fingerprints, deduplicates failure signatures, and synthesizes crisp Acceptance Criteria (AC).",
        prompt: "You are RequirementsAgent / CIFailureIngestor.\\n- Input: CI failure traces, Playwright trace stack traces, JUnit XML failures.\\n- Output: Structured failure ticket with classification (PRODUCT_BUG, TEST_BUG, FLAKY_TEST, ENVIRONMENT_NOISE).\\n- Invariant: Zero workspace modifications allowed.",
        ast: "AST Guard: Read-Only Verification\\n- Prohibited: File writes, external sockets, shell subprocesses.\\n- Scope: Artifact parsing only.\\n- Acceptance Criteria Enforced: AC-1 through AC-n."
      },
      2: {
        title: "2. ScrumMasterOrchestrator & TicketRouter (TIER_1_TECH_LEAD)",
        overview: "Constructs topologically sorted directed acyclic graph (SprintDAGScheduler) of worker agents. Implements strict role containment: routes PRODUCT_BUG exclusively to DeveloperAgent and TEST_BUG to TestHealerAgent.",
        prompt: "You are ScrumMasterOrchestrator.\\n- Role: Enforce least-privilege file access.\\n- If PRODUCT_BUG: DeveloperAgent may modify src/ only. tests/ are strictly read-only.\\n- If TEST_BUG: TestHealerAgent may modify tests/ only. src/ is strictly read-only.\\n- If ENVIRONMENT_NOISE: Code modifications strictly prohibited.",
        ast: "Role Invariants:\\n- DeveloperAgent: tests/* access = PROHIBITED\\n- TestHealerAgent: src/* access = PROHIBITED\\n- Blast Radius containment: Enforced via AST."
      },
      3: {
        title: "3. Multi-Tier Worker Agent (DeveloperAgent / TestHealerAgent)",
        overview: "Synthesizes surgical AST patches using Multi-Tier models (Tier 1 Tech Lead, Tier 2 Senior SWE, Tier 3 Junior SWE) or local Ollama (qwen2.5-coder:7b). Applies fuzzy 3-level search-and-replace matching.",
        prompt: "Synthesize a minimal, surgical fix addressing the failure.\\n- Match original indentation and context.\\n- Wrap changes in valid diff or JSON edits format.\\n- Never introduce new external dependencies or disable assertions.",
        ast: "Syntax Validation: Python AST ast.parse / Tree-sitter\\n- Formatting: Normalization of quotes (r'...' vs '...')\\n- Invariant: Strict file scope restrictions."
      },
      4: {
        title: "4. ASTPatchGuard & QACriticAgent (TIER_4_QA_CRITIC)",
        overview: "Line-by-line rubric evaluation. Enforces Python AST and TypeScript Playwright safety, ensuring zero assertion erosion, no skip injection (@pytest.mark.skip, test.skip), and valid syntax.",
        prompt: "Audit proposed patch for assertion degradation.\\n- Ensure all baseline test assertions remain intact or strengthened.\\n- Flag any suppressed error handling or artificial delays (time.sleep).\\n- Verify strict mode locator compliance.",
        ast: "Assertion Erosion Check:\\n- Assert statements: Preserved (>= baseline count)\\n- Prohibited decorators: pytest.mark.skip, xfail without issue tracker\\n- Verdict: PASS"
      },
      5: {
        title: "5. SecurityBlastRadiusAgent (TIER_4_QA_CRITIC)",
        overview: "Static AST security audit preventing command injection, path traversal, socket leakage, and unmasked secrets via DLP Session Vault.",
        prompt: "Scan proposed changes for high-risk security constructs:\\n- subprocess.run with shell=True -> Hard block (SEC-SUBPROCESS-001)\\n- os.system, eval, exec -> Hard block\\n- Raw socket / urllib calls to untracked origins -> Block\\n- Plaintext API keys or tokens -> Redact via DLP Vault.",
        ast: "Security Blast Radius Rubric:\\n- Command Injection (shell=True): ZERO FINDINGS\\n- Path Traversal (../): ZERO FINDINGS\\n- Secret Leakage: ZERO FINDINGS\\n- Blast Radius Scope: Isolated to single target file."
      },
      6: {
        title: "6. AutomationTesterAgent & Ephemeral Sandbox (TIER_3_JUNIOR_SWE)",
        overview: "Executes test suite across 3 isolated ephemeral git worktrees (repeat=3) to verify patch determinism and ensure zero flaky regressions before write authorization.",
        prompt: "Run target test runner in isolated worktree sandbox:\\n- Repeat: 3 runs\\n- Timeout guard: 120s per run\\n- Exit code requirement: 0 across all runs.",
        ast: "Verification Sandbox Report:\\n- Run 1: PASSED (exit code 0)\\n- Run 2: PASSED (exit code 0)\\n- Run 3: PASSED (exit code 0)\\n- Determinism: 100% PASS"
      },
      7: {
        title: "7. HumanWriteGateController & Time Machine (GOVERNED WRITE GATE)",
        overview: "Human-in-the-loop governance barrier. Pins pre-apply cryptographic snapshot in Time Machine. Workspace remains 100% byte-for-byte untouched until human approver authorizes write.",
        prompt: "Write Gate Policy:\\n- Requires authorized human QA Lead / Engineer identity.\\n- Generates audit trail record.\\n- Provides microsecond rollback (git reset / Time Machine snapshot) on demand.",
        ast: "Governance Controls:\\n- Pre-Apply Snapshot: Pinned\\n- Rollback Engine: Armed\\n- Auto-PR generation: hermes/heal-<id> branch ready."
      }
    };

    const modalAgentInspector = document.getElementById('modal-agent-inspector');
    const btnCloseInspector = document.getElementById('btn-close-inspector');
    const btnCloseInspectorFooter = document.getElementById('btn-close-inspector-footer');
    const tabInspOverview = document.getElementById('tab-insp-overview');
    const tabInspPrompt = document.getElementById('tab-insp-prompt');
    const tabInspAst = document.getElementById('tab-insp-ast');
    const inspectorOverviewBody = document.getElementById('inspector-overview-body');
    const inspectorPromptBody = document.getElementById('inspector-prompt-body');
    const inspectorAstBody = document.getElementById('inspector-ast-body');
    const inspectorAgentTitle = document.getElementById('inspector-agent-title');

    function openAgentInspector(stepNum) {
      const data = agentDetailsData[stepNum] || agentDetailsData[1];
      if (inspectorAgentTitle) inspectorAgentTitle.innerText = data.title;
      if (inspectorOverviewBody) inspectorOverviewBody.innerHTML = `<p>${data.overview}</p>`;
      if (inspectorPromptBody) inspectorPromptBody.innerText = data.prompt;
      if (inspectorAstBody) inspectorAstBody.innerText = data.ast;
      if (modalAgentInspector) modalAgentInspector.style.display = 'flex';
      switchInspectorTab('overview');
    }

    function switchInspectorTab(tab) {
      [tabInspOverview, tabInspPrompt, tabInspAst].forEach(t => {
        if (t) t.classList.remove('active');
      });
      const contentOverview = document.getElementById('inspector-tab-overview');
      const contentPrompt = document.getElementById('inspector-tab-prompt');
      const contentAst = document.getElementById('inspector-tab-ast');

      if (contentOverview) contentOverview.style.display = (tab === 'overview') ? 'block' : 'none';
      if (contentPrompt) contentPrompt.style.display = (tab === 'prompt') ? 'block' : 'none';
      if (contentAst) contentAst.style.display = (tab === 'ast') ? 'block' : 'none';

      if (tab === 'overview' && tabInspOverview) tabInspOverview.classList.add('active');
      if (tab === 'prompt' && tabInspPrompt) tabInspPrompt.classList.add('active');
      if (tab === 'ast' && tabInspAst) tabInspAst.classList.add('active');
    }

    if (tabInspOverview) tabInspOverview.addEventListener('click', () => switchInspectorTab('overview'));
    if (tabInspPrompt) tabInspPrompt.addEventListener('click', () => switchInspectorTab('prompt'));
    if (tabInspAst) tabInspAst.addEventListener('click', () => switchInspectorTab('ast'));

    if (btnCloseInspector) btnCloseInspector.addEventListener('click', () => {
      if (modalAgentInspector) modalAgentInspector.style.display = 'none';
    });
    if (btnCloseInspectorFooter) btnCloseInspectorFooter.addEventListener('click', () => {
      if (modalAgentInspector) modalAgentInspector.style.display = 'none';
    });

    for (let i = 1; i <= 7; i++) {
      const card = document.getElementById(`card-step-${i}`);
      if (card) {
        card.style.cursor = 'pointer';
        card.title = `Click to inspect Agent ${i} prompts & AST invariants`;
        card.addEventListener('click', () => openAgentInspector(i));
      }
    }

    // Screenshot Lightbox Modal
    const modalScreenshot = document.getElementById('modal-screenshot-preview');
    const btnCloseScreenshot = document.getElementById('btn-close-screenshot');
    const btnCloseScreenshotFooter = document.getElementById('btn-close-screenshot-footer');
    if (btnCloseScreenshot) btnCloseScreenshot.addEventListener('click', () => {
      if (modalScreenshot) modalScreenshot.style.display = 'none';
    });
    if (btnCloseScreenshotFooter) btnCloseScreenshotFooter.addEventListener('click', () => {
      if (modalScreenshot) modalScreenshot.style.display = 'none';
    });

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

      // Non-blocking real-workspace diagnostics
      loadProviders();
      fetchDoctorStatus(false);
      loadRealSnapshots();
      discoverRealWorkspace();
      auditLocator("button#checkout");
    });
  </script>
</body>
</html>
"""
