"""Read Flame Editdesk Batch reel preferences (unique basename for Flame scan)."""

from __future__ import annotations

import json
from pathlib import Path

__version__ = "0.1.0"

_DEFAULT_SCHEMATIC_REELS = 3
_DEFAULT_SHELF_REELS = 1

_KEY_SCHEMATIC = "DefaultBatchGroupReelsNumber"
_KEY_SHELF = "DefaultBatchRenderGroupReelsNumber"


def editdesk_reels_pref_paths() -> list[Path]:
    home = Path.home()
    return [
        home
        / "Library/Preferences/Autodesk/flame/status/EditdeskReelsCurrent.json",
        home / "flame/status/EditdeskReelsCurrent.json",
    ]


def read_editdesk_int(name: str, default: int) -> int:
    """Read a positive int Setting from EditdeskReelsCurrent.json."""
    for path in editdesk_reels_pref_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in data.get("Settings") or []:
            if not isinstance(row, dict):
                continue
            if row.get("name") != name:
                continue
            try:
                value = int(row.get("value"))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default
    return default


def schematic_reel_count() -> int:
    """Schematic reel count for create_batch_group(nb_reels=...)."""
    return read_editdesk_int(_KEY_SCHEMATIC, _DEFAULT_SCHEMATIC_REELS)


def shelf_reel_count() -> int:
    """Batch shelf reel count for create_batch_group(shelf_reels=...)."""
    return read_editdesk_int(_KEY_SHELF, _DEFAULT_SHELF_REELS)


def shelf_reel_names(count: int | None = None) -> list[str]:
    """Names for shelf_reels: Batch Renders, Batch Renders 2, ..."""
    n = shelf_reel_count() if count is None else count
    if n <= 0:
        n = _DEFAULT_SHELF_REELS
    if n == 1:
        return ["Batch Renders"]
    return ["Batch Renders"] + [f"Batch Renders {i}" for i in range(2, n + 1)]
