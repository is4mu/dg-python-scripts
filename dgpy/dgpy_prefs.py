"""User prefs path helpers. Unique basename for Flame scan."""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.3.27"


def flame_user_dgpy_dir() -> Path:
    """Per-user DGpy data root — sibling of Flame ``python/`` (not scanned).

    macOS: ~/Library/Preferences/Autodesk/flame/dgpy
    Linux: ~/flame/dgpy
    """
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Preferences" / "Autodesk" / "flame" / "dgpy"
    return home / "flame" / "dgpy"


def user_prefs_path() -> Path:
    """User preferences JSON (small settings only; never under python/)."""
    return flame_user_dgpy_dir() / "prefs.json"
