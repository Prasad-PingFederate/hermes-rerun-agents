"""
Backwards-compatibility shim for hermes.core.verification.semantic_assertion_guard
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parents[2] / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import hermes.core.verification.semantic_assertion_guard as _target_module
sys.modules[__name__] = _target_module
from hermes.core.verification.semantic_assertion_guard import *
