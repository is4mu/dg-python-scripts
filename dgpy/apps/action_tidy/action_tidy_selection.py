"""Resolve Timeline / Media Panel selection to segments (primary-version aware)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_types

__version__ = "0.3.1"


def _attr(obj: Any, name: str, default=None):
    if obj is None or not hasattr(obj, name):
        return default
    val = getattr(obj, name)
    if val is not None and hasattr(val, "get_value"):
        try:
            return val.get_value()
        except Exception:  # noqa: BLE001
            pass
    return val


def is_segment(item: Any) -> bool:
    try:
        import flame

        cls = getattr(flame, "PySegment", None)
        if cls is None:
            return False
        return isinstance(item, cls)
    except Exception:  # noqa: BLE001
        return False


def is_track(item: Any) -> bool:
    try:
        import flame

        for name in ("PyTrack", "PyVideoTrack"):
            cls = getattr(flame, name, None)
            if cls is not None and isinstance(item, cls):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


def is_gap_segment(seg: Any) -> bool:
    """
    Skip blank / Gap timeline segments.

    Prefer type/name == Gap; also treat missing source_width/height like legacy.
    """
    for attr in ("type", "segment_type", "name"):
        val = _attr(seg, attr, None)
        if val is None:
            continue
        text = str(val).strip().lower()
        if text == "gap" or text.startswith("gap"):
            return True

    typ = type(seg).__name__.lower()
    if "gap" in typ:
        return True

    has_w = hasattr(seg, "source_width")
    has_h = hasattr(seg, "source_height")
    if has_w and has_h:
        try:
            w = _attr(seg, "source_width", None)
            h = _attr(seg, "source_height", None)
            if w is None or h is None:
                return True
            if int(w) <= 0 or int(h) <= 0:
                return True
        except Exception:  # noqa: BLE001
            return True
    else:
        # Legacy: no source_* attrs → skip (typical Gap)
        return True

    return False


def _primary_track(clip) -> Any:
    return _attr(clip, "primary_track", None)


def _segments_on_track(track) -> list:
    return list(getattr(track, "segments", None) or [])


def _primary_version(clip) -> Any:
    primary = _primary_track(clip)
    if primary is not None:
        parent = getattr(primary, "parent", None)
        if parent is not None:
            return parent
    return None


def _segments_from_clip(clip) -> list:
    """All segments on all tracks of the version that owns primary_track."""
    version = _primary_version(clip)
    if version is not None:
        out: list = []
        for track in list(getattr(version, "tracks", None) or []):
            out.extend(_segments_on_track(track))
        return out

    # Fallback: first version that has any segments
    for version in list(getattr(clip, "versions", None) or []):
        out = []
        for track in list(getattr(version, "tracks", None) or []):
            out.extend(_segments_on_track(track))
        if out:
            return out
    return []


def _clips_from_reel(reel, *, logger=None) -> list:
    return list(dgpy_flame_types.clips_from_container(reel, logger=logger) or [])


def resolve_segments(selection, *, logger=None) -> list:
    """
    Build unique non-Gap segment list:

    - PySegment → itself (if not Gap)
    - PyTrack → its segments
    - Clip / Sequence → all segments on primary version tracks
    - Reel → clips/sequences → same
    """
    out: list = []
    seen: set[int] = set()

    def add_seg(seg) -> None:
        if seg is None or is_gap_segment(seg):
            return
        oid = id(seg)
        if oid in seen:
            return
        seen.add(oid)
        out.append(seg)

    for item in dgpy_flame_types.as_list(selection):
        if is_segment(item):
            add_seg(item)
            continue
        if is_track(item):
            for seg in _segments_on_track(item):
                add_seg(seg)
            continue
        if dgpy_flame_types.is_clip(item) or dgpy_flame_types.is_sequence(item):
            for seg in _segments_from_clip(item):
                add_seg(seg)
            continue
        if dgpy_flame_types.is_reel(item):
            for clip in _clips_from_reel(item, logger=logger):
                for seg in _segments_from_clip(clip):
                    add_seg(seg)
            continue

    return out


def has_segments(selection, *, logger=None) -> bool:
    return bool(resolve_segments(selection, logger=logger))


def segment_label(seg) -> str:
    name = _attr(seg, "name", None)
    if name:
        return str(name)
    return type(seg).__name__
