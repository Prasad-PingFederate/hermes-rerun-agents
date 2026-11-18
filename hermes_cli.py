"""
Backwards-compatibility shim for hermes.cli
Single source of truth is located under src/hermes/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure UTF-8 output encoding across Windows cp1252 consoles and CI runners
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import hermes.cli as _target_module
sys.modules[__name__] = _target_module
from hermes.cli import *

if __name__ == "__main__":
    import sys
    sys.exit(main())
