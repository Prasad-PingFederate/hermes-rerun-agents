"""
Backwards-compatibility shim for hermes.guards.ast_patch_guard
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import hermes.guards.ast_patch_guard as _target_module
sys.modules[__name__] = _target_module
from hermes.guards.ast_patch_guard import *
