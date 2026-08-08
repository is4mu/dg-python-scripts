"""Resolve selection to Primary-track video segments (non-Gap)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_attr
import dgpy_flame_types

from segment_handle_clips_util import __version__, unwrap


def _is_segment(item: Any) -> bool:
    try:
        import flame

        cls = getattr(flame, "PySegment", None)
        if cls is None:
            return False
        return isinstance(item, cls)
    except Exception:  # noqa: BLE001
        return False


def is_gap_segment(seg: Any) -> bool:
    for attr in ("type", "segment_type", "name"):
        val = dgpy_flame_attr.attr_value(seg, attr, None)
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
            w = dgpy_flame_attr.attr_value(seg, "source_width", None)
            h = dgpy_flame_attr.attr_value(seg, "source_height", None)
            if w is None or h is None:
                return True
            if int(w) <= 0 or int(h) <= 0:
                return True
        except Exception:  # noqa: BLE001
            return True
    else:
        return True
    return False


def primary_track(clip) -> Any:
    return dgpy_flame_attr.attr_value(clip, "primary_track", None)


def _track_segments(track) -> list:
    return list(getattr(track, "segments", None) or [])


def _owning_clip(segment) -> Any:
    """Walk parents to a Clip/Sequence when possible."""
    obj = segment
    for _ in range(8):
        parent = unwrap(getattr(obj, "parent", None))
        if parent is None:
            break
        if dgpy_flame_types.is_clip(parent) or dgpy_flame_types.is_sequence(
            parent
        ):
            return parent
        obj = parent
    return None


def _segment_on_track(segment, track) -> bool:
    if segment is None or track is None:
        return False
    for seg in _track_segments(track):
        if seg is segment or id(seg) == id(segment):
            return True
    return False


def segments_from_clip(clip) -> list:
    """Primary video track segments only."""
    track = primary_track(clip)
    if track is None:
        return []
    return [s for s in _track_segments(track) if not is_gap_segment(s)]


def resolve_segment_jobs(selection, *, logger=None) -> list[dict]:
    """
    Return list of dicts:
      segment, owner_clip, clip_name
    """
    out: list[dict] = []
    seen: set[int] = set()

    def add(seg, owner) -> None:
        if seg is None or is_gap_segment(seg):
            return
        oid = id(seg)
        if oid in seen:
            return
        seen.add(oid)
        name = dgpy_flame_attr.clip_name(owner) if owner is not None else None
        if not name:
            name = str(
                dgpy_flame_attr.attr_value(seg, "name", "") or ""
            ).strip()
        if not name:
            name = "clip"
        out.append({"segment": seg, "owner_clip": owner, "clip_name": name})

    for item in dgpy_flame_types.as_list(selection):
        if _is_segment(item):
            owner = _owning_clip(item)
            track = primary_track(owner) if owner is not None else None
            if owner is not None and track is not None:
                if not _segment_on_track(item, track):
                    if logger:
                        logger.info(
                            "Consolidate Handles: skip segment not on "
                            "Primary track (%s)",
                            dgpy_flame_attr.attr_value(item, "name", "?"),
                        )
                    continue
            add(item, owner)
            continue

        if dgpy_flame_types.is_clip(item) or dgpy_flame_types.is_sequence(item):
            for seg in segments_from_clip(item):
                add(seg, item)
            continue

        if dgpy_flame_types.is_reel(item):
            for child in dgpy_flame_types.clips_from_container(
                item, logger=logger
            ):
                for seg in segments_from_clip(child):
                    add(seg, child)
            continue

        # Folder / Library explicitly ignored

    return out


def has_jobs(selection, *, logger=None) -> bool:
    return bool(resolve_segment_jobs(selection, logger=logger))
