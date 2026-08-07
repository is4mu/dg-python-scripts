"""Resolve first direct Clip/Sequence from Media Panel selection."""

from __future__ import annotations

import re
from typing import Any

import dgpy_flame_types

__version__ = "0.11.1"


def direct_clips(selection) -> list:
    """Clip/Sequence only — no Reel/Folder expansion (spec §4.1)."""
    out: list = []
    for item in dgpy_flame_types.as_list(selection):
        if dgpy_flame_types.is_clip(item) or dgpy_flame_types.is_sequence(item):
            out.append(item)
    return out


def first_clip(selection) -> Any | None:
    clips = direct_clips(selection)
    return clips[0] if clips else None


def clip_label(clip) -> str:
    name = getattr(clip, "name", None)
    if name is None:
        return "clip"
    if hasattr(name, "get_value"):
        try:
            return str(name.get_value())
        except Exception:  # noqa: BLE001
            return str(name)
    return str(name)


def safe_basename(clip) -> str:
    """Filesystem-/Flame-safe stem from clip name (no suffix)."""
    raw = clip_label(clip).strip() or "clip"
    cleaned = re.sub(r"[^\w.\-]+", "_", raw, flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "clip"
    return cleaned


def import_destination_for(clip, *, logger=None) -> Any | None:
    """Return Reel/Folder/Library parent of the source clip, or None."""
    parent = getattr(clip, "parent", None)
    if parent is None:
        if logger:
            logger.warning("MatAnyone: clip has no parent; import will use Desktop reel")
        return None
    if dgpy_flame_types.is_media_container(parent):
        if logger:
            logger.info(
                "MatAnyone: import destination %s",
                dgpy_flame_types.item_label(parent),
            )
        return parent
    if logger:
        logger.warning(
            "MatAnyone: parent is not Reel/Folder/Library (%s); "
            "import will use Desktop reel",
            dgpy_flame_types.item_label(parent),
        )
    return None
