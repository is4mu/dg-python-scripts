"""Flame PyAttribute helpers (unique basename for Flame scan)."""

from __future__ import annotations

__version__ = "0.1.0"

_BIT_DEPTH_FP_THRESHOLD = 16


def attr_value(obj, name: str, default=None):
    """Read ``obj.name``, unwrapping ``get_value()`` when present."""
    if obj is None or not hasattr(obj, name):
        return default
    val = getattr(obj, name)
    if val is not None and hasattr(val, "get_value"):
        try:
            return val.get_value()
        except Exception:  # noqa: BLE001
            pass
    return val


def clip_name(clip) -> str:
    """Clip display name without wrapping quotes; fallback ``clip``."""
    name = attr_value(clip, "name", None)
    if name is None:
        return "clip"
    text = str(name).strip().strip("'\"")
    return text or "clip"


def try_set(obj, name: str, value, logger) -> None:
    """``setattr`` ignoring None and logging failures at DEBUG."""
    if value is None:
        return
    try:
        setattr(obj, name, value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("skip set %s: %s", name, exc)


def primary_segment(clip):
    """First segment of versions[0].tracks[0], or None."""
    try:
        versions = getattr(clip, "versions", None) or []
        if not versions:
            return None
        tracks = getattr(versions[0], "tracks", None) or []
        if not tracks:
            return None
        segments = getattr(tracks[0], "segments", None) or []
        if not segments:
            return None
        return segments[0]
    except Exception:  # noqa: BLE001
        return None


def bit_depth_string(clip) -> str | None:
    """e.g. ``16-bit fp`` / ``10-bit`` from clip.bit_depth."""
    raw = attr_value(clip, "bit_depth", None)
    if raw is None:
        return None
    try:
        depth = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    suffix = " fp" if depth >= _BIT_DEPTH_FP_THRESHOLD else ""
    return f"{depth}-bit{suffix}"


def node_xy(node) -> tuple[int, int]:
    """Schematic node ``pos_x`` / ``pos_y`` as ints."""
    x = attr_value(node, "pos_x", 0)
    y = attr_value(node, "pos_y", 0)
    try:
        xi = int(x or 0)
    except (TypeError, ValueError):
        xi = 0
    try:
        yi = int(y or 0)
    except (TypeError, ValueError):
        yi = 0
    return xi, yi


def apply_render_metadata(
    clip,
    clip_node,
    render,
    batch,
    shelf_name: str,
    logger,
    *,
    render_name: str | None = None,
) -> None:
    """Copy duration / TC / marks onto a Batch Render node.

    ``range_start`` is always 1. Destination is
    ``("Batch Reels", shelf_name)``. When ``render_name`` is omitted,
    uses ``clip_name(clip)``.
    """
    duration = attr_value(clip_node, "duration", None)
    if duration is None:
        duration = attr_value(clip, "duration", None)

    try_set(render, "range_start", 1, logger)
    if duration is not None:
        try_set(batch, "duration", duration, logger)
        try_set(render, "range_end", duration, logger)

    try_set(render, "frame_rate", attr_value(clip, "frame_rate", None), logger)
    try_set(render, "bit_depth", bit_depth_string(clip), logger)
    try_set(render, "format", "RGB-A", logger)
    try_set(render, "setup_mode", False, logger)
    try_set(render, "destination", ("Batch Reels", shelf_name), logger)

    segment = primary_segment(clip)
    if segment is not None:
        try_set(
            render, "shot_name", attr_value(segment, "shot_name", None), logger
        )
        try_set(
            render, "tape_name", attr_value(segment, "tape_name", None), logger
        )
        try_set(
            render,
            "source_timecode",
            attr_value(segment, "source_in", None),
            logger,
        )
        try_set(
            render,
            "record_timecode",
            attr_value(segment, "record_in", None),
            logger,
        )

    in_mark = attr_value(clip, "in_mark", None)
    out_mark = attr_value(clip, "out_mark", None)
    if in_mark is not None:
        try_set(render, "in_mark", in_mark, logger)
    if out_mark is not None:
        try_set(render, "out_mark", out_mark, logger)

    name = render_name if render_name is not None else clip_name(clip)
    try_set(render, "name", name, logger)
