"""
Hermes Console Demo Workspace Manager
Owns ephemeral test repository lifecycles for the Tester Console (AG-2, AG-3, AG-4, AG-6).
Creates isolated git repositories with reproducible bug fixtures and connects them to
ScrumMasterOrchestrator, TimeMachineEngine, and SprintStateStore.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.time_machine.engine import TimeMachineEngine
from scrum_master_orchestrator import ScrumMasterOrchestrator
from sprint_state_store import SprintStateStore


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

    # Managed orchestrator components
    tm: Optional[TimeMachineEngine] = None
    store: Optional[SprintStateStore] = None
    orchestrator: Optional[ScrumMasterOrchestrator] = None


class ConsoleDemoManager:
    """Manages isolated temp workspaces for the tester console."""

    def __init__(self):
        self._workspaces: Dict[str, DemoWorkspace] = {}
        atexit.register(self.cleanup_all)

    def get_workspace(self, workspace_id: str) -> Optional[DemoWorkspace]:
        return self._workspaces.get(workspace_id)

    def list_workspaces(self) -> List[Dict[str, Any]]:
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
        self._workspaces[ws_id] = ws
        return ws

    def create_drift_workspace(self) -> DemoWorkspace:
        """Create seeded PlaywrightDrift fixture workspace (TEST_BUG) for AG-6."""
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
        self._workspaces[ws_id] = ws
        return ws

    def delete_workspace(self, workspace_id: str) -> bool:
        ws = self._workspaces.pop(workspace_id, None)
        if ws and ws.workspace_path.exists():
            shutil.rmtree(ws.workspace_path, ignore_errors=True)
            return True
        return False

    def cleanup_all(self):
        for ws_id, ws in list(self._workspaces.items()):
            try:
                if ws.workspace_path.exists():
                    shutil.rmtree(ws.workspace_path, ignore_errors=True)
            except Exception:
                pass
        self._workspaces.clear()


# Global manager singleton
demo_manager = ConsoleDemoManager()
