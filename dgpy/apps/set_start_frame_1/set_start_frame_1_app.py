"""Set start frame to 1 on clips/sequences."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_log

__version__ = "1.0.2"

_START_FRAME = 1


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


def set_start_frame_to_1(selection, parent=None) -> None:
    del parent  # unused; keep signature consistent with other apps
    logger = dgpy_log.setup()
    label = "Set Start Frame to 1"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    ok = 0
    failed = 0
    for clip in clips:
        try:
            clip.change_start_frame(_START_FRAME)
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
