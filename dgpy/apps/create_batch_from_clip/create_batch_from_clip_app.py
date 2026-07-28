"""Create Batch groups from clips: Clip → Render, prefs-driven reel counts."""

from __future__ import annotations

import dgpy_batch_prefs
import dgpy_flame_types
import dgpy_log

__version__ = "1.0.9"

_BIT_DEPTH_FP_THRESHOLD = 16
# Schematic gap Clip → Render (Flame coords; ~2× legacy node unit)
_RENDER_OFFSET_X = 300


def _attr_value(obj, name: str, default=None):
    if obj is None or not hasattr(obj, name):
        return default
    val = getattr(obj, name)
    if val is not None and hasattr(val, "get_value"):
        try:
            return val.get_value()
        except Exception:  # noqa: BLE001
            pass
    return val


def _clip_name(clip) -> str:
    name = _attr_value(clip, "name", None)
    if name is None:
        return "clip"
    text = str(name).strip().strip("'\"")
    return text or "clip"


def _primary_segment(clip):
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


def _find_clip_node(batch, before_ids: set[int]):
    nodes = list(getattr(batch, "nodes", None) or [])
    for node in reversed(nodes):
        if id(node) in before_ids:
            continue
        typ = str(getattr(node, "type", "") or "")
        if "Clip" in typ or typ in ("", "clip"):
            return node
    for node in reversed(nodes):
        if id(node) not in before_ids:
            return node
    return nodes[-1] if nodes else None


def _try_set(obj, name: str, value, logger) -> None:
    if value is None:
        return
    try:
        setattr(obj, name, value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("skip set %s: %s", name, exc)


def _node_xy(node) -> tuple[int, int]:
    x = _attr_value(node, "pos_x", 0)
    y = _attr_value(node, "pos_y", 0)
    try:
        xi = int(x or 0)
    except (TypeError, ValueError):
        xi = 0
    try:
        yi = int(y or 0)
    except (TypeError, ValueError):
        yi = 0
    return xi, yi


def _place_render_right_of_clip(clip_node, render, logger) -> None:
    """Put Render to the right of Clip (pos_x may be PyAttribute)."""
    cx, cy = _node_xy(clip_node)
    rx = cx + _RENDER_OFFSET_X
    try:
        render.pos_x = rx
        render.pos_y = cy
        logger.info(
            "Create Batch from Clip: place Render at (%s, %s) "
            "(clip was %s, %s)",
            rx,
            cy,
            cx,
            cy,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Create Batch from Clip: could not set Render pos: %s", exc
        )


def _bit_depth_string(clip) -> str | None:
    raw = _attr_value(clip, "bit_depth", None)
    if raw is None:
        return None
    try:
        depth = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    suffix = " fp" if depth >= _BIT_DEPTH_FP_THRESHOLD else ""
    return f"{depth}-bit{suffix}"


def _connect_clip_to_render(batch, clip_node, render, logger) -> bool:
    attempts = (
        ("Default", None),
        ("Result", None),
        ("Default", "Front"),
        ("Result", "Front"),
    )
    for out_sock, in_sock in attempts:
        try:
            if in_sock is None:
                batch.connect_nodes(clip_node, out_sock, render)
            else:
                batch.connect_nodes(clip_node, out_sock, render, in_sock)
            return True
        except TypeError:
            try:
                batch.connect_nodes(clip_node, out_sock, render)
                return True
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001
            continue
    logger.warning("Create Batch from Clip: could not connect Clip→Render")
    return False


def _apply_render_metadata(
    clip, clip_node, render, batch, shelf_name: str, logger
) -> None:
    duration = _attr_value(clip_node, "duration", None)
    if duration is None:
        duration = _attr_value(clip, "duration", None)

    _try_set(render, "range_start", 1, logger)
    if duration is not None:
        _try_set(batch, "duration", duration, logger)
        _try_set(render, "range_end", duration, logger)

    _try_set(render, "frame_rate", _attr_value(clip, "frame_rate", None), logger)
    _try_set(render, "bit_depth", _bit_depth_string(clip), logger)
    _try_set(render, "format", "RGB-A", logger)
    _try_set(render, "setup_mode", False, logger)
    _try_set(render, "destination", ("Batch Reels", shelf_name), logger)

    segment = _primary_segment(clip)
    if segment is not None:
        _try_set(
            render, "shot_name", _attr_value(segment, "shot_name", None), logger
        )
        _try_set(
            render, "tape_name", _attr_value(segment, "tape_name", None), logger
        )
        _try_set(
            render,
            "source_timecode",
            _attr_value(segment, "source_in", None),
            logger,
        )
        _try_set(
            render,
            "record_timecode",
            _attr_value(segment, "record_in", None),
            logger,
        )

    in_mark = _attr_value(clip, "in_mark", None)
    out_mark = _attr_value(clip, "out_mark", None)
    if in_mark is not None:
        _try_set(render, "in_mark", in_mark, logger)
    if out_mark is not None:
        _try_set(render, "out_mark", out_mark, logger)

    _try_set(render, "name", _clip_name(clip), logger)


def _create_one_batch(flame, clip, nb_reels: int, shelves: list[str], logger) -> None:
    name = _clip_name(clip)
    create = flame.batch.create_batch_group
    try:
        batch = create(name, nb_reels=nb_reels, shelf_reels=shelves)
    except TypeError:
        logger.info(
            "Create Batch from Clip: shelf_reels unsupported; "
            "using nb_reels=%s only",
            nb_reels,
        )
        batch = create(name, nb_reels=nb_reels)

    reels = list(getattr(batch, "reels", None) or [])
    if not reels:
        raise RuntimeError("batch has no schematic reels")

    before_ids = {id(n) for n in (getattr(batch, "nodes", None) or [])}
    flame.media_panel.copy(clip, reels[0])
    clip_node = _find_clip_node(batch, before_ids)
    if clip_node is None:
        raise RuntimeError("clip node not found after copy")

    render = batch.create_node("Render")
    _connect_clip_to_render(batch, clip_node, render, logger)
    shelf_name = shelves[0] if shelves else "Batch Renders"
    _apply_render_metadata(clip, clip_node, render, batch, shelf_name, logger)
    # After connect/metadata — Flame may leave Render on top of Clip
    _place_render_right_of_clip(clip_node, render, logger)
    try:
        batch.frame_all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("frame_all: %s", exc)


def create_batches_from_selection(selection) -> None:
    import flame

    logger = dgpy_log.setup()
    clips = dgpy_flame_types.get_clips(selection, logger=logger)
    if not clips:
        logger.info("Create Batch from Clip: no clips")
        return

    nb_reels = dgpy_batch_prefs.schematic_reel_count()
    shelves = dgpy_batch_prefs.shelf_reel_names()
    logger.info(
        "Create Batch from Clip: clips=%s nb_reels=%s shelf_reels=%s",
        len(clips),
        nb_reels,
        shelves,
    )

    try:
        flame.set_current_tab("Batch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Create Batch from Clip: set_current_tab failed: %s", exc)

    ok = 0
    failed = 0
    for clip in clips:
        try:
            _create_one_batch(flame, clip, nb_reels, shelves, logger)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "Create Batch from Clip failed for %s: %s",
                _clip_name(clip),
                exc,
            )
    logger.info("Create Batch from Clip: ok %s (failed %s)", ok, failed)
