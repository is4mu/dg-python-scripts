"""Resize All Clips: one rsz Batch, master Resize + mimic_link chain."""

from __future__ import annotations

import dgpy_batch_prefs
import dgpy_flame_attr
import dgpy_flame_types
import dgpy_log

__version__ = "1.0.5"

_NODE_UNIT = 150
_BATCH_NAME = "rsz"
_MASTER_NAME = "rsz_master"


def _set_xy(node, x: int, y: int, logger, label: str) -> None:
    try:
        node.pos_x = int(x)
        node.pos_y = int(y)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resize All Clips: could not set %s pos: %s", label, exc)


def _node_type(node) -> str:
    return str(getattr(node, "type", "") or "")


def _is_clip_schematic_node(node) -> bool:
    typ = _node_type(node)
    if "Resize" in typ or "Render" in typ:
        return False
    if "Clip" in typ or typ in ("", "clip"):
        return True
    # Copied media often reports as Clip; accept unknown non-effect nodes
    # only when type looks like media (avoid Action etc.)
    return typ.lower() in ("clip", "sequence", "pyclip", "pysequence")


def _clip_nodes_after_copy(batch, before_ids: set[int]) -> list:
    nodes = list(getattr(batch, "nodes", None) or [])
    added = [n for n in nodes if id(n) not in before_ids]
    clips = [n for n in added if _is_clip_schematic_node(n)]
    return clips if clips else added


def _connect(batch, src, dst, logger, label: str) -> bool:
    attempts = (
        ("Default", None),
        ("Result", None),
        ("Default", "Front"),
        ("Result", "Front"),
    )
    for out_sock, in_sock in attempts:
        try:
            if in_sock is None:
                batch.connect_nodes(src, out_sock, dst)
            else:
                batch.connect_nodes(src, out_sock, dst, in_sock)
            return True
        except TypeError:
            try:
                batch.connect_nodes(src, out_sock, dst)
                return True
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001
            continue
    logger.warning("Resize All Clips: could not connect %s", label)
    return False


def _wire_one(
    batch, clip, clip_node, rsz_master, shelf_name: str, logger
) -> None:
    rsz = batch.create_node("Resize")
    try:
        batch.mimic_link(rsz_master, rsz)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resize All Clips: mimic_link failed: %s", exc)

    cx, cy = dgpy_flame_attr.node_xy(clip_node)
    rsz_x = cx + (_NODE_UNIT * 2)
    render_x = rsz_x + _NODE_UNIT
    _set_xy(rsz, rsz_x, cy, logger, "Resize")

    _connect(batch, clip_node, rsz, logger, "Clip→Resize")

    render = batch.create_node("Render")
    _connect(batch, rsz, render, logger, "Resize→Render")
    _set_xy(render, render_x, cy, logger, "Render")
    dgpy_flame_attr.apply_render_metadata(
        clip,
        clip_node,
        render,
        batch,
        shelf_name,
        logger,
        render_name=f"{dgpy_flame_attr.clip_name(clip)}_rsz",
    )
    # Re-place in case metadata/connect reset layout
    _set_xy(rsz, rsz_x, cy, logger, "Resize")
    _set_xy(render, render_x, cy, logger, "Render")


def resize_all_clips_from_selection(selection) -> None:
    import flame

    logger = dgpy_log.setup()
    clips = dgpy_flame_types.get_clips(selection, logger=logger)
    if not clips:
        logger.info("Resize All Clips: no clips")
        return

    nb_reels = dgpy_batch_prefs.schematic_reel_count()
    shelves = dgpy_batch_prefs.shelf_reel_names()
    shelf_name = shelves[0] if shelves else "Batch Renders"
    logger.info(
        "Resize All Clips: clips=%s nb_reels=%s shelf_reels=%s",
        len(clips),
        nb_reels,
        shelves,
    )

    try:
        flame.set_current_tab("Batch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resize All Clips: set_current_tab failed: %s", exc)

    create = flame.batch.create_batch_group
    try:
        batch = create(_BATCH_NAME, nb_reels=nb_reels, shelf_reels=shelves)
    except TypeError:
        logger.info(
            "Resize All Clips: shelf_reels unsupported; using nb_reels=%s only",
            nb_reels,
        )
        batch = create(_BATCH_NAME, nb_reels=nb_reels)

    reels = list(getattr(batch, "reels", None) or [])
    if not reels:
        logger.warning("Resize All Clips: batch has no schematic reels")
        return

    before_ids = {id(n) for n in (getattr(batch, "nodes", None) or [])}
    try:
        flame.media_panel.copy(clips, reels[0])
    except TypeError:
        for clip in clips:
            flame.media_panel.copy(clip, reels[0])

    clip_nodes = _clip_nodes_after_copy(batch, before_ids)
    if not clip_nodes:
        logger.warning("Resize All Clips: no clip nodes after copy")
        return

    if len(clip_nodes) != len(clips):
        logger.warning(
            "Resize All Clips: clip/node count mismatch clips=%s nodes=%s",
            len(clips),
            len(clip_nodes),
        )

    rsz_master = batch.create_node("Resize")
    dgpy_flame_attr.try_set(rsz_master, "name", _MASTER_NAME, logger)
    _set_xy(rsz_master, 0, _NODE_UNIT, logger, "rsz_master")

    ok = 0
    failed = 0
    for clip, clip_node in zip(clips, clip_nodes):
        try:
            _wire_one(batch, clip, clip_node, rsz_master, shelf_name, logger)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "Resize All Clips failed for %s: %s",
                dgpy_flame_attr.clip_name(clip),
                exc,
            )

    try:
        batch.frame_all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("frame_all: %s", exc)

    logger.info("Resize All Clips: ok %s (failed %s)", ok, failed)
