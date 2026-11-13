"""
Backwards-compatibility shim for hermes.core.rerun_bridge
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parents[2] / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import hermes.core.rerun_bridge as _target_module
def __getattr__(name: str):
    return getattr(_target_module, name)
from hermes.core.rerun_bridge import *
