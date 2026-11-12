"""
Hermes Console Demo Workspace Manager
Owns ephemeral test repository lifecycles for the Tester Console (AG-2 through AG-10).
Creates isolated git repositories with reproducible bug fixtures and connects them to
ScrumMasterOrchestrator, TimeMachineEngine, and SprintStateStore.
Persists open demo registry state to SQLite so it survives page reloads and process restarts.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runners.runner_detector import detect_runner
from core.time_machine.engine import TimeMachineEngine
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore

REGISTRY_DB_PATH = Path(tempfile.gettempdir()) / "hermes_demo_sessions.db"


@dataclass
class DemoWorkspace:
    workspace_id: str
    workspace_name: str
    workspace_path: Path
    failing_test: str
    failure_output: str
    classification: str
    owner_agent: str
    scope: List[str]
    allowed_files: List[str]
    status: str = "FAILING"
    active_sprint_id: Optional[str] = None
    pre_apply_snapshot_id: Optional[str] = None
    approver: Optional[str] = None
    approval_comment: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    # Managed orchestrator components
    tm: Optional[TimeMachineEngine] = None
    store: Optional[SprintStateStore] = None
    orchestrator: Optional[ScrumMasterOrchestrator] = None


class ConsoleDemoManager:
    """Manages isolated temp workspaces for the tester console with SQLite persistence."""

    def __init__(self):
        self._workspaces: Dict[str, DemoWorkspace] = {}
        self._init_sqlite()
        self.load_persisted_workspaces()
        atexit.register(self.cleanup_all)

    def _init_sqlite(self) -> None:
        try:
            with sqlite3.connect(str(REGISTRY_DB_PATH)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS demo_workspaces (
                        workspace_id TEXT PRIMARY KEY,
                        workspace_name TEXT,
                        workspace_path TEXT,
                        failing_test TEXT,
                        failure_output TEXT,
                        classification TEXT,
                        owner_agent TEXT,
                        scope_json TEXT,
                        allowed_files_json TEXT,
                        status TEXT,
                        active_sprint_id TEXT,
                        pre_apply_snapshot_id TEXT,
                        approver TEXT,
                        approval_comment TEXT,
                        metadata_json TEXT,
                        updated_at REAL
                    )
                    """
                )
                conn.commit()
        except Exception:
            pass

    def persist_workspace(self, ws: DemoWorkspace) -> None:
        """Persist workspace state to global registry sqlite under temp (AG-10)."""
        ws.updated_at = time.time()
        self._workspaces[ws.workspace_id] = ws

        try:
            REGISTRY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(REGISTRY_DB_PATH)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS demo_workspaces (
                        workspace_id TEXT PRIMARY KEY,
                        workspace_name TEXT,
                        workspace_path TEXT,
                        failing_test TEXT,
                        failure_output TEXT,
                        classification TEXT,
                        owner_agent TEXT,
                        scope_json TEXT,
                        allowed_files_json TEXT,
                        status TEXT,
                        active_sprint_id TEXT,
                        pre_apply_snapshot_id TEXT,
                        approver TEXT,
                        approval_comment TEXT,
                        metadata_json TEXT,
                        updated_at REAL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO demo_workspaces (
                        workspace_id, workspace_name, workspace_path, failing_test,
                        failure_output, classification, owner_agent, scope_json,
                        allowed_files_json, status, active_sprint_id, pre_apply_snapshot_id,
                        approver, approval_comment, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ws.workspace_id,
                        ws.workspace_name,
                        str(ws.workspace_path),
                        ws.failing_test,
                        ws.failure_output,
                        ws.classification,
                        ws.owner_agent,
                        json.dumps(ws.scope),
                        json.dumps(ws.allowed_files),
                        ws.status,
                        ws.active_sprint_id,
                        ws.pre_apply_snapshot_id,
                        ws.approver,
                        ws.approval_comment,
                        json.dumps(ws.metadata),
                        ws.updated_at,
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def load_persisted_workspaces(self) -> None:
        """Reload persisted workspaces from sqlite on startup / GET / (AG-10)."""
        if not REGISTRY_DB_PATH.exists():
            return

        try:
            with sqlite3.connect(str(REGISTRY_DB_PATH)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                rows = cur.execute("SELECT * FROM demo_workspaces ORDER BY updated_at DESC").fetchall()
                for r in rows:
                    ws_path = Path(r["workspace_path"])
                    if not ws_path.exists():
                        continue

                    ws_id = r["workspace_id"]
                    if ws_id in self._workspaces:
                        # Update in-memory mutable fields
                        ws = self._workspaces[ws_id]
                        ws.status = r["status"]
                        ws.active_sprint_id = r["active_sprint_id"]
                        ws.pre_apply_snapshot_id = r["pre_apply_snapshot_id"]
                        ws.approver = r["approver"]
                        ws.approval_comment = r["approval_comment"]
                        ws.updated_at = r["updated_at"] or ws.updated_at
                        continue

                    # Reconstruct managed orchestrator
                    tm = TimeMachineEngine(ws_path)
                    store = SprintStateStore(ws_path / ".tm_snapshots" / "sprint_state.db")
                    orch = ScrumMasterOrchestrator(ws_path, tm_engine=tm, store=store)

                    ws = DemoWorkspace(
                        workspace_id=ws_id,
                        workspace_name=r["workspace_name"],
                        workspace_path=ws_path,
                        failing_test=r["failing_test"],
                        failure_output=r["failure_output"],
                        classification=r["classification"],
                        owner_agent=r["owner_agent"],
                        scope=json.loads(r["scope_json"]),
                        allowed_files=json.loads(r["allowed_files_json"]),
                        status=r["status"],
                        active_sprint_id=r["active_sprint_id"],
                        pre_apply_snapshot_id=r["pre_apply_snapshot_id"],
                        approver=r["approver"],
                        approval_comment=r["approval_comment"],
                        metadata=json.loads(r["metadata_json"]) if r["metadata_json"] else {},
                        updated_at=r["updated_at"] or time.time(),
                        tm=tm,
                        store=store,
                        orchestrator=orch,
                    )
                    self._workspaces[ws_id] = ws
        except Exception:
            pass

    def get_workspace(self, workspace_id: str) -> Optional[DemoWorkspace]:
        self.load_persisted_workspaces()
        return self._workspaces.get(workspace_id)

    def get_latest_workspace(self) -> Optional[DemoWorkspace]:
        self.load_persisted_workspaces()
        if not self._workspaces:
            return None
        # Prioritize active sprint / awaiting write gate workspaces
        active_sprint_ws = [
            w for w in self._workspaces.values()
            if w.status in ("AWAITING_WRITE_GATE", "APPLIED") or w.active_sprint_id
        ]
        if active_sprint_ws:
            return max(active_sprint_ws, key=lambda w: getattr(w, "updated_at", 0.0))
        return max(self._workspaces.values(), key=lambda w: getattr(w, "updated_at", 0.0))

    def list_workspaces(self) -> List[Dict[str, Any]]:
        self.load_persisted_workspaces()
        return [
            {
                "workspace_id": ws.workspace_id,
                "workspace_name": ws.workspace_name,
                "failing_test": ws.failing_test,
                "classification": ws.classification,
                "owner_agent": ws.owner_agent,
                "scope": ws.scope,
                "status": ws.status,
                "active_sprint_id": ws.active_sprint_id,
                "pre_apply_snapshot_id": ws.pre_apply_snapshot_id,
            }
            for ws in self._workspaces.values()
        ]

    def create_ledger_workspace(self) -> DemoWorkspace:
        """Create seeded InMemoryLedger workspace (PRODUCT_BUG)."""
        ws_id = f"demo_ledger_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()

        # 1. Initialize Git Repo
        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        src_dir = demo_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        # 2. Buggy InMemoryLedger: does not validate negative deposits
        buggy_ledger = (
            "class InMemoryLedger:\n"
            "    def __init__(self, initial_balance: float = 0.0):\n"
            "        self._balance = initial_balance\n\n"
            "    @property\n"
            "    def balance(self) -> float:\n"
            "        return self._balance\n\n"
            "    def deposit(self, amount: float) -> float:\n"
            "        # BUG: Fails to reject negative or zero deposits\n"
            "        self._balance += amount\n"
            "        return self._balance\n"
        )
        (src_dir / "InMemoryLedger.py").write_text(buggy_ledger, encoding="utf-8")

        # 3. Unit test with ValueError assertion
        test_content = (
            "import pytest\n"
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from InMemoryLedger import InMemoryLedger\n\n"
            "def test_deposit_valid():\n"
            "    ledger = InMemoryLedger(100.0)\n"
            "    assert ledger.deposit(50.0) == 150.0\n"
            "    assert ledger.balance == 150.0\n\n"
            "def test_deposit_rejects_negative():\n"
            "    ledger = InMemoryLedger(100.0)\n"
            "    with pytest.raises(ValueError):\n"
            "        ledger.deposit(-25.0)\n"
        )
        (tests_dir / "test_ledger.py").write_text(test_content, encoding="utf-8")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial buggy ledger"], cwd=str(demo_dir), capture_output=True, check=True)

        # Confirm failure
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_ledger.py", "-v"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
        )

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name="InMemoryLedger",
            workspace_path=demo_dir,
            failing_test="test_deposit_rejects_negative",
            failure_output=res.stdout + "\n" + res.stderr,
            classification="PRODUCT_BUG",
            owner_agent="DeveloperAgent",
            scope=["src/InMemoryLedger.py"],
            allowed_files=["src/InMemoryLedger.py"],
            status="FAILING",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={"test_cmd": [sys.executable, "-m", "pytest", "tests/test_ledger.py"]},
        )
        self.persist_workspace(ws)
        return ws

    def create_drift_workspace(self) -> DemoWorkspace:
        """Create seeded PlaywrightDrift fixture workspace (TEST_BUG) for AG-8."""
        ws_id = f"demo_drift_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()

        # 1. Initialize Git Repo
        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        src_dir = demo_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        # Correct product implementation
        cart_code = (
            "class ShoppingCart:\n"
            "    def __init__(self):\n"
            "        self.items = []\n\n"
            "    def checkout(self) -> str:\n"
            "        return 'ORDER_CONFIRMED'\n"
        )
        (src_dir / "cart.py").write_text(cart_code, encoding="utf-8")

        # Test bug: test asserts outdated return code 'CONFIRMED' instead of 'ORDER_CONFIRMED'
        drift_test = (
            "import pytest\n"
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from cart import ShoppingCart\n\n"
            "def test_checkout_drift():\n"
            "    cart = ShoppingCart()\n"
            "    # TEST BUG: Test expectation drifted from production contract\n"
            "    assert cart.checkout() == 'CONFIRMED'\n"
        )
        (tests_dir / "test_cart.py").write_text(drift_test, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial test drift"], cwd=str(demo_dir), capture_output=True, check=True)

        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_cart.py", "-v"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
        )

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name="PlaywrightDrift",
            workspace_path=demo_dir,
            failing_test="test_checkout_drift",
            failure_output=res.stdout + "\n" + res.stderr,
            classification="TEST_BUG",
            owner_agent="TestHealerAgent",
            scope=["tests/test_cart.py"],
            allowed_files=["tests/test_cart.py"],
            status="FAILING",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={"test_cmd": [sys.executable, "-m", "pytest", "tests/test_cart.py"]},
        )
        self.persist_workspace(ws)
        return ws

    def create_hostile_workspace(self) -> DemoWorkspace:
        """Create seeded HostilePatch workspace (AG-9: Security rejection / shell=True)."""
        ws_id = f"demo_hostile_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()

        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        src_dir = demo_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        service_code = (
            "class SystemHealth:\n"
            "    def check_status(self) -> str:\n"
            "        return 'ONLINE'\n"
        )
        (src_dir / "service.py").write_text(service_code, encoding="utf-8")

        test_code = (
            "import pytest\n"
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n"
            "from service import SystemHealth\n\n"
            "def test_health_metrics():\n"
            "    h = SystemHealth()\n"
            "    assert h.check_status() == 'HEALTHY_200'\n"
        )
        (tests_dir / "test_service.py").write_text(test_code, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial system service"], cwd=str(demo_dir), capture_output=True, check=True)

        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_service.py", "-v"],
            cwd=str(demo_dir),
            capture_output=True,
            text=True,
        )

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name="HostilePatch",
            workspace_path=demo_dir,
            failing_test="test_health_metrics",
            failure_output=res.stdout + "\n" + res.stderr,
            classification="PRODUCT_BUG",
            owner_agent="DeveloperAgent",
            scope=["src/service.py"],
            allowed_files=["src/service.py"],
            status="FAILING",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={
                "test_cmd": [sys.executable, "-m", "pytest", "tests/test_service.py"],
                "hostile_trigger": True,
            },
        )
        self.persist_workspace(ws)
        return ws

    def create_flake_workspace(self) -> DemoWorkspace:
        """Create seeded Playwright flake fixture workspace (FLAKY_TEST)."""
        ws_id = f"demo_flake_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()

        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        test_code = (
            "import pytest\n"
            "import random\n\n"
            "def test_intermittent_locator():\n"
            "    # Intermittent test: fails on timing race condition\n"
            "    val = random.choice([True, False, True])\n"
            "    assert val is True, 'Timeout 3000ms waiting for locator button#checkout'\n"
        )
        (tests_dir / "test_flake.py").write_text(test_code, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial flaky test"], cwd=str(demo_dir), capture_output=True, check=True)

        failure_output = (
            "============================= test session starts =============================\n"
            "tests/test_flake.py::test_intermittent_locator FAILED\n"
            "E   AssertionError: Timeout 3000ms waiting for locator button#checkout\n"
            "========================= 1 failed, 2 passed in 1.45s =========================\n"
            "--- Multi-Run Execution History ---\n"
            "Run 1: PASSED\n"
            "Run 2: FAILED (AssertionError: Timeout 3000ms waiting for locator button#checkout)\n"
            "Run 3: PASSED\n"
            "Outcome: FLAKY_TEST (Intermittent locator timing instability)"
        )

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name="PlaywrightFlake",
            workspace_path=demo_dir,
            failing_test="test_intermittent_locator",
            failure_output=failure_output,
            classification="FLAKY_TEST",
            owner_agent="TestHealerAgent",
            scope=["tests/test_flake.py"],
            allowed_files=["tests/test_flake.py"],
            status="FAILING",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={"test_cmd": [sys.executable, "-m", "pytest", "tests/test_flake.py"]},
        )
        self.persist_workspace(ws)
        return ws

    def create_env_noise_workspace(self) -> DemoWorkspace:
        """Create seeded EnvironmentNoise fixture workspace (ENVIRONMENT_NOISE)."""
        ws_id = f"demo_noise_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()

        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)

        tests_dir = demo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        test_code = (
            "import pytest\n\n"
            "def test_database_connection():\n"
            "    raise ConnectionRefusedError('[Errno 111] Connection refused on 127.0.0.1:5432')\n"
        )
        (tests_dir / "test_api.py").write_text(test_code, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial env test"], cwd=str(demo_dir), capture_output=True, check=True)

        failure_output = (
            "ConnectionRefusedError: [Errno 111] Connection refused on 127.0.0.1:5432\n"
            "E   ConnectionRefusedError: address already in use or service offline\n"
            "Outcome: ENVIRONMENT_NOISE (Infrastructure blocker. Code modification prohibited.)"
        )

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name="EnvironmentNoise",
            workspace_path=demo_dir,
            failing_test="test_database_connection",
            failure_output=failure_output,
            classification="ENVIRONMENT_NOISE",
            owner_agent="ScrumMasterOrchestrator",
            scope=["tests/test_api.py"],
            allowed_files=[],
            status="FAILING",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={"test_cmd": [sys.executable, "-m", "pytest", "tests/test_api.py"]},
        )
        self.persist_workspace(ws)
        return ws

    def connect_repository(self, repo_path: str, name: Optional[str] = None) -> DemoWorkspace:
        """Connect customer repository on disk for live triage and autonomous healing."""
        target_path = Path(repo_path).resolve()
        if not target_path.exists() or not target_path.is_dir():
            raise ValueError(f"Path does not exist or is not a directory: {repo_path}")

        # Check or init git
        if not (target_path / ".git").is_dir():
            subprocess.run(["git", "init"], cwd=str(target_path), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(target_path), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(target_path), capture_output=True, check=True)

        repo_name = name or target_path.name
        ws_id = f"repo_{repo_name}_{int(time.time())}_{uuid.uuid4().hex[:4]}"

        # Detect runner
        runner_info = detect_runner(target_path)

        # Discover tests
        discovered_tests = []
        for pat in runner_info.get("test_patterns", ["tests/**/*.py", "test/**/*.py"]):
            for f in target_path.glob(pat):
                if ".git" not in f.parts and ".tm_snapshots" not in f.parts and "node_modules" not in f.parts:
                    discovered_tests.append(str(f.relative_to(target_path)).replace("\\", "/"))

        tm = TimeMachineEngine(target_path)
        store = SprintStateStore(target_path / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(target_path, tm_engine=tm, store=store)

        first_test = discovered_tests[0] if discovered_tests else "tests/test_main.py"
        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name=repo_name,
            workspace_path=target_path,
            failing_test=first_test,
            failure_output=(
                f"Repository connected: {repo_name}\n"
                f"Discovered {len(discovered_tests)} tests.\n"
                f"Test Runner: {runner_info['runner_name']}\n"
                f"Command: {' '.join(runner_info['command'])}\n"
                "Ready for autonomous failure triage."
            ),
            classification="PRODUCT_BUG",
            owner_agent="DeveloperAgent",
            scope=discovered_tests[:5] if discovered_tests else ["src/"],
            allowed_files=discovered_tests[:5] if discovered_tests else ["src/"],
            status="CONNECTED",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={
                "discovered_tests": discovered_tests,
                "runner_info": runner_info,
                "test_cmd": runner_info["command"] + ([first_test] if runner_info["runner_name"] == "pytest" and discovered_tests else []),
                "customer_repo": True,
            },
        )
        self.persist_workspace(ws)
        return ws

    def ingest_ci_task(self, task_id: str, title: str, details: Dict[str, Any]) -> DemoWorkspace:
        """Ingest or sync CI failure task from GitHub Actions / .rerun_tasks/ into console workspace."""
        ws_id = f"demo_ci_{task_id}"
        if ws_id in self._workspaces:
            return self._workspaces[ws_id]

        failing_test = details.get("failing_test") or "tests/test_ci.py"
        run_id = details.get("run_id") or "run_ci"
        error_snippet = details.get("error_snippet") or f"GitHub Actions workflow run #{run_id} failed on {failing_test}"
        classification = "TEST_BUG" if "test" in str(failing_test).lower() else "PRODUCT_BUG"
        owner_agent = "TestHealerAgent" if classification == "TEST_BUG" else "DeveloperAgent"

        demo_dir = Path(tempfile.mkdtemp(prefix=f"hermes_{ws_id}_")).resolve()
        subprocess.run(["git", "init"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "HermesTester"], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@hermes.local"], cwd=str(demo_dir), capture_output=True, check=True)
        (demo_dir / ".gitignore").write_text(".tm_snapshots/\n__pycache__/\n*.pyc\n", encoding="utf-8")

        test_file_path = demo_dir / failing_test
        test_file_path.parent.mkdir(parents=True, exist_ok=True)
        test_file_path.write_text(
            f"# CI failure reproduced from GHA run #{run_id}\nimport pytest\n\ndef test_ci_failure():\n    assert False, 'CI assertion failure'\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=str(demo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", f"Initial commit for {task_id}"], cwd=str(demo_dir), capture_output=True, check=True)

        tm = TimeMachineEngine(demo_dir)
        store = SprintStateStore(demo_dir / ".tm_snapshots" / "sprint_state.db")
        orch = ScrumMasterOrchestrator(demo_dir, tm_engine=tm, store=store)

        ws = DemoWorkspace(
            workspace_id=ws_id,
            workspace_name=title or f"CI: {Path(failing_test).name}",
            workspace_path=demo_dir,
            failing_test=failing_test,
            failure_output=error_snippet,
            classification=classification,
            owner_agent=owner_agent,
            scope=[failing_test],
            allowed_files=[failing_test],
            status="AWAITING_APPROVAL",
            tm=tm,
            store=store,
            orchestrator=orch,
            metadata={
                "ci_task_id": task_id,
                "run_id": run_id,
                "is_ci_webhook": True,
                "test_cmd": [sys.executable, "-m", "pytest", failing_test],
            },
            updated_at=1.0,
        )
        self.persist_workspace(ws)
        return ws

    def delete_workspace(self, workspace_id: str) -> bool:
        ws = self._workspaces.pop(workspace_id, None)
        if ws:
            import gc
            ws.store = None
            ws.orchestrator = None
            ws.tm = None
            gc.collect()

            if not ws.metadata.get("customer_repo") and ws.workspace_path.exists():
                def _rm(func, path, exc):
                    import stat
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass

                shutil.rmtree(ws.workspace_path, onerror=_rm)
            try:
                with sqlite3.connect(str(REGISTRY_DB_PATH)) as conn:
                    conn.execute("DELETE FROM demo_workspaces WHERE workspace_id = ?", (workspace_id,))
                    conn.commit()
            except Exception:
                pass
            return True
        return False

    def cleanup_all(self):
        import gc

        def _rm(func, path, exc):
            import stat
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        for ws_id, ws in list(self._workspaces.items()):
            try:
                ws.store = None
                ws.orchestrator = None
                ws.tm = None
                gc.collect()
                if not ws.metadata.get("customer_repo") and ws.workspace_path.exists():
                    shutil.rmtree(ws.workspace_path, onerror=_rm)
            except Exception:
                pass
        self._workspaces.clear()
        if REGISTRY_DB_PATH.exists():
            try:
                REGISTRY_DB_PATH.unlink()
            except Exception:
                pass


# Global manager singleton
demo_manager = ConsoleDemoManager()
