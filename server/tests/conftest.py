"""Expose the canonical VM-side server (`server-mirror.py` at the repo root)
as a `server_mirror` pytest fixture loaded via `importlib.util` (the dash in
the filename makes it un-importable as a regular module).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def server_mirror():
    """Load and return the canonical VM-side server module."""
    path = _REPO_ROOT / "server-mirror.py"
    spec = importlib.util.spec_from_file_location("server_mirror", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_mirror"] = mod
    spec.loader.exec_module(mod)
    return mod
