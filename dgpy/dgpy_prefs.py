"""User / machine prefs path helpers (Phase B schema stub). Unique for Flame scan."""

from __future__ import annotations

import sys
from pathlib import Path

import dgpy_paths

__version__ = "0.3.26"


def machine_prefs_path(root: Path | None = None) -> Path:
    """Machine-common prefs next to install (shared dgpy → all users)."""
    return dgpy_paths.state_dir(root) / "prefs_machine.json"


def user_prefs_dir() -> Path:
    """Per-user prefs root (never under shared /opt dgpy)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "DGpy"
    return home / ".config" / "dgpy"


def user_prefs_path() -> Path:
    return user_prefs_dir() / "prefs.json"
