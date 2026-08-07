"""Resolve first direct Clip/Sequence from Media Panel selection."""

from __future__ import annotations

from typing import Any

import dgpy_flame_types

__version__ = "0.5.1"


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
