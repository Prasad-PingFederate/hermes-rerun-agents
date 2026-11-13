"""
Backwards-compatibility shim for hermes.agents
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parents[1] / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import hermes.agents as _target_module
def __getattr__(name: str):
    return getattr(_target_module, name)
from hermes.agents import *
