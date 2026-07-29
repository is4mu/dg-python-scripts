"""Delete all markers on clips/sequences."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_log

__version__ = "1.0.4"


def get_targets(selection, *, logger=None) -> list:
    """Clip/Sequence, or Reel/Folder/Library direct children."""
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
        if dgpy_flame_types.is_media_container(item):
            for child in dgpy_flame_types.clips_from_container(
                item, logger=logger
            ):
                _add(child)
    return out


def _has_markers(obj) -> bool:
    markers = getattr(obj, "markers", None)
    if not markers:
        return False
    try:
        return len(list(markers)) > 0
    except TypeError:
        return bool(markers)


def has_markers(selection, *, logger=None) -> bool:
    """True if any resolved Clip/Sequence has at least one marker."""
    for clip in get_targets(selection, logger=logger):
        if _has_markers(clip):
            return True
    return False


def delete_all_markers(selection, parent=None) -> None:
    del parent
    import flame

    logger = dgpy_log.setup()
    label = "Delete All Markers"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(logger=logger, label=label)

    clip_ok = 0
    deleted = 0
    failed = 0
    for clip in clips:
        markers = list(getattr(clip, "markers", None) or [])
        if not markers:
            continue
        clip_ok += 1
        for marker in markers:
            try:
                flame.delete(marker)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning(
                    "%s: failed to delete marker on %s: %s",
                    label,
                    dgpy_flame_types.item_label(clip),
                    exc,
                )

    logger.info(
        "%s: clips=%s with_markers=%s deleted=%s failed=%s",
        label,
        len(clips),
        clip_ok,
        deleted,
        failed,
    )
