"""Sequence / Reel render helpers: clip.render() loops."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_log

__version__ = "1.0.3"

_SEQUENCES_REEL_TYPE = "Sequences"


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


def _reel_type(reel) -> str:
    raw = _attr_value(reel, "type", "")
    return str(raw or "")


def get_targets_from_selection(selection, *, logger=None) -> list:
    """
    Clip/Sequence, or direct children of a selected Reel only.

    Folder / Library / Desktop are ignored.
    """
    out: list = []
    seen: set[int] = set()

    def _add(obj) -> None:
        if not (dgpy_flame_types.is_clip(obj) or dgpy_flame_types.is_sequence(obj)):
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)
        out.append(obj)

    for item in dgpy_flame_types.as_list(selection):
        if dgpy_flame_types.is_clip(item) or dgpy_flame_types.is_sequence(item):
            _add(item)
            continue
        if dgpy_flame_types.is_reel(item):
            for child in dgpy_flame_types.clips_from_container(item, logger=logger):
                _add(child)
    return out


def get_targets_from_sequence_reels(*, logger=None) -> list:
    """All Clip/Sequence under Desktop reels whose type is Sequences."""
    import flame

    out: list = []
    seen: set[int] = set()

    def _add(obj) -> None:
        if not (dgpy_flame_types.is_clip(obj) or dgpy_flame_types.is_sequence(obj)):
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)
        out.append(obj)

    try:
        desktop = flame.project.current_project.current_workspace.desktop
        reel_groups = list(getattr(desktop, "reel_groups", None) or [])
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.warning(
                "Render Sequence Reels: could not read desktop reel_groups: %s",
                exc,
            )
        return []

    for group in reel_groups:
        reels = list(getattr(group, "reels", None) or [])
        for reel in reels:
            if _reel_type(reel) != _SEQUENCES_REEL_TYPE:
                continue
            if logger:
                logger.info(
                    "Render Sequence Reels: scanning %s",
                    dgpy_flame_types.item_label(reel),
                )
            for child in dgpy_flame_types.clips_from_container(reel, logger=logger):
                _add(child)
    return out


def render_targets(targets: list, *, label: str) -> tuple[int, int]:
    logger = dgpy_log.setup()
    if not targets:
        logger.info("%s: nothing to render", label)
        return 0, 0

    ok = 0
    failed = 0
    for clip in targets:
        try:
            clip.render()
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s failed for %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )
    logger.info("%s: ok %s (failed %s)", label, ok, failed)
    return ok, failed


def render_from_selection(selection) -> None:
    logger = dgpy_log.setup()
    targets = get_targets_from_selection(selection, logger=logger)
    render_targets(targets, label="DG2: Sequence Render")


def render_all_sequence_reels(_selection=None) -> None:
    logger = dgpy_log.setup()
    targets = get_targets_from_sequence_reels(logger=logger)
    render_targets(targets, label="DG2: Render Sequence Reels")
