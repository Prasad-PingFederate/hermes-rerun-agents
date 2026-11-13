"""
Migrate canonical code from root agents/ and core/ to src/hermes/agents and src/hermes/core,
and replace root files with thin backwards-compatibility proxy shims.
"""
from __future__ import annotations

import ast
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_HERMES = REPO_ROOT / "src" / "hermes"


def migrate():
    # 1. Copy agents to src/hermes/agents if not exists or update
    target_agents = SRC_HERMES / "agents"
    if not target_agents.exists():
        shutil.copytree(REPO_ROOT / "agents", target_agents)
        print("Copied agents/ to src/hermes/agents/")

    # 2. Copy core to src/hermes/core if not exists or update
    target_core = SRC_HERMES / "core"
    if not target_core.exists():
        shutil.copytree(REPO_ROOT / "core", target_core)
        print("Copied core/ to src/hermes/core/")

    # 3. Generate shims in root agents/
    for root, _, files in os.walk(REPO_ROOT / "agents"):
        for f in files:
            if not f.endswith(".py"):
                continue
            shim_file = Path(root) / f
            rel = shim_file.relative_to(REPO_ROOT)
            parts = rel.parts  # ('agents', 'ci_detective.py')
            mod_name = f[:-3]
            if f == "__init__.py":
                target_mod = "hermes.agents"
            else:
                target_mod = f"hermes.agents.{mod_name}"

            depth = len(parts) - 1
            parents_expr = f".parents[{depth}]"

            content = f'''"""
Backwards-compatibility shim for {target_mod}
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve(){parents_expr} / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import {target_mod} as _target_module
sys.modules[__name__] = _target_module
from {target_mod} import *
'''
            shim_file.write_text(content.strip() + "\n", encoding="utf-8")
            print(f"Generated shim for {rel} -> {target_mod}")

    # 4. Generate shims in root core/
    for root, _, files in os.walk(REPO_ROOT / "core"):
        for f in files:
            if not f.endswith(".py"):
                continue
            shim_file = Path(root) / f
            rel = shim_file.relative_to(REPO_ROOT)
            parts = rel.parts  # e.g. ('core', 'audit', 'delta_sast.py')
            mod_name = f[:-3]
            subpackages = list(parts[1:-1])
            if f == "__init__.py":
                if subpackages:
                    target_mod = f"hermes.core.{'.'.join(subpackages)}"
                else:
                    target_mod = "hermes.core"
            else:
                if subpackages:
                    target_mod = f"hermes.core.{'.'.join(subpackages)}.{mod_name}"
                else:
                    target_mod = f"hermes.core.{mod_name}"

            depth = len(parts) - 1
            parents_expr = f".parents[{depth}]"

            content = f'''"""
Backwards-compatibility shim for {target_mod}
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve(){parents_expr} / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import {target_mod} as _target_module
sys.modules[__name__] = _target_module
from {target_mod} import *
'''
            shim_file.write_text(content.strip() + "\n", encoding="utf-8")
            print(f"Generated shim for {rel} -> {target_mod}")

    print("Migration completed successfully.")


if __name__ == "__main__":
    migrate()
