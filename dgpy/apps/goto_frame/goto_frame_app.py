"""Go To First/Last/In/Out/Custom Frame on clips/sequences."""

from __future__ import annotations

import dgpy_flame_attr
import dgpy_flame_types
import dgpy_log

__version__ = "1.0.3"


def _frame_number(time_obj) -> int | None:
    if time_obj is None:
        return None
    if hasattr(time_obj, "get_value"):
        try:
            time_obj = time_obj.get_value()
        except Exception:  # noqa: BLE001
            pass
    if time_obj is None:
        return None
    if hasattr(time_obj, "frame"):
        try:
            frame_attr = time_obj.frame
            if hasattr(frame_attr, "get_value"):
                try:
                    return int(frame_attr.get_value())
                except Exception:  # noqa: BLE001
                    pass
            return int(frame_attr)
        except Exception:  # noqa: BLE001
            pass
    try:
        return int(time_obj)
    except Exception:  # noqa: BLE001
        return None


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


def _ask_custom_frame(parent=None) -> int | None:
    from PySide6 import QtWidgets

    value, ok = QtWidgets.QInputDialog.getInt(
        parent,
        "Custom Frame",
        "Frame number:",
        1,
        1,
        2_000_000_000,
        1,
    )
    if not ok:
        return None
    return int(value)


def _set_current_time(clip, time_value, logger, label: str) -> bool:
    try:
        clip.current_time = time_value
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s failed for %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )
        return False


def _run(selection, *, label: str, resolve_time, parent=None) -> None:
    logger = dgpy_log.setup()
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    ok = 0
    failed = 0
    skipped = 0
    for clip in clips:
        time_value = resolve_time(clip)
        if time_value is None:
            skipped += 1
            logger.warning(
                "%s: no target time on %s",
                label,
                dgpy_flame_types.item_label(clip),
            )
            continue
        if _set_current_time(clip, time_value, logger, label):
            ok += 1
        else:
            failed += 1

    logger.info(
        "%s: clips=%s ok=%s skipped=%s failed=%s",
        label,
        len(clips),
        ok,
        skipped,
        failed,
    )


def go_to_first_frame(selection, parent=None) -> None:
    _run(selection, label="Go To First Frame", resolve_time=lambda _c: 1, parent=parent)


def go_to_last_frame(selection, parent=None) -> None:
    def _resolve(clip):
        out_mark = _frame_number(dgpy_flame_attr.attr_value(clip, "out_mark", None)) or 0
        duration = _frame_number(dgpy_flame_attr.attr_value(clip, "duration", None)) or 0
        value = max(out_mark, duration)
        return value if value > 0 else None

    _run(selection, label="Go To Last Frame", resolve_time=_resolve, parent=parent)


def go_to_in_mark(selection, parent=None) -> None:
    def _resolve(clip):
        return dgpy_flame_attr.attr_value(clip, "in_mark", None)

    _run(selection, label="Go To In Mark", resolve_time=_resolve, parent=parent)


def go_to_out_mark(selection, parent=None) -> None:
    def _resolve(clip):
        return dgpy_flame_attr.attr_value(clip, "out_mark", None)

    _run(selection, label="Go To Out Mark", resolve_time=_resolve, parent=parent)


def go_to_custom_frame(selection, parent=None) -> None:
    logger = dgpy_log.setup()
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("Go To Custom Frame: nothing selected")
        return

    frame = _ask_custom_frame(parent)
    if frame is None:
        logger.info("Go To Custom Frame: cancelled")
        return

    _run(
        selection,
        label="Go To Custom Frame",
        resolve_time=lambda _c: frame,
        parent=parent,
    )
