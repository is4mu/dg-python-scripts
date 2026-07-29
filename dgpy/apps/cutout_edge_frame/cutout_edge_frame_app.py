"""Cutout first or last frame via cut + flame.delete (all tracks/channels)."""

from __future__ import annotations

import dgpy_flame_attr
import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.9"

_FIRST_CUT_FRAME = 2
_DEFAULT_RANGE_START = 1


def get_targets(selection, *, logger=None) -> list:
    """Clip/Sequence, or Reel direct children only."""
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
            for child in dgpy_flame_types.clips_from_container(
                item, logger=logger
            ):
                _add(child)
    return out


def _frame_number(time_obj) -> int | None:
    if time_obj is None:
        return None
    # PyAttribute → get_value → PyTime.frame
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


def _clip_duration_frame(clip) -> int | None:
    dur = dgpy_flame_attr.attr_value(clip, "duration", None)
    return _frame_number(dur)


def _segment_duration_frames(segment) -> int | None:
    """Length in frames. Prefer record_duration (real-machine probe 2026-07-27).

    Findings:
    - segment.duration → usually None (useless)
    - record_duration.frame → true length (1F → 1)
    - record_out - record_in → 1F → 0 (inclusive); N → N-1
    """
    rec = _frame_number(dgpy_flame_attr.attr_value(segment, "record_duration", None))
    if rec is not None and rec > 0:
        return rec
    dur = _frame_number(dgpy_flame_attr.attr_value(segment, "duration", None))
    if dur is not None and dur > 0:
        return dur
    rin = _frame_number(dgpy_flame_attr.attr_value(segment, "record_in", None))
    rout = _frame_number(dgpy_flame_attr.attr_value(segment, "record_out", None))
    if rin is not None and rout is not None:
        span = abs(rout - rin)
        # Inclusive 1F: in==out → span 0; longer: span == length - 1
        if span == 0:
            return 1
        return span + 1
    return None


def _is_clearly_longer_than_one_frame(segment) -> bool:
    """True only when record_duration (etc.) is known and strictly greater than 1."""
    dur = _segment_duration_frames(segment)
    return dur is not None and dur > 1


def _edge_segments(clip, *, first: bool) -> list:
    """Collect edge segments on all video tracks and audio channels."""
    index = 0 if first else -1
    out: list = []

    for version in list(getattr(clip, "versions", None) or []):
        for track in list(getattr(version, "tracks", None) or []):
            segments = list(getattr(track, "segments", None) or [])
            if segments:
                out.append(segments[index])

    for audio_track in list(getattr(clip, "audio_tracks", None) or []):
        for channel in list(getattr(audio_track, "channels", None) or []):
            segments = list(getattr(channel, "segments", None) or [])
            if segments:
                out.append(segments[index])

    return out


def _ensure_timeline_tab(logger) -> None:
    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(
        logger=logger, label="Cutout Edge Frame"
    )


def _cut_frame_for(clip, *, first: bool, logger, label: str) -> int | None:
    if first:
        return _FIRST_CUT_FRAME
    cut_frame = _clip_duration_frame(clip)
    if cut_frame is None:
        logger.warning(
            "%s: no duration on %s",
            label,
            dgpy_flame_types.item_label(clip),
        )
    return cut_frame


def _cutout_one(clip, *, first: bool, logger, label: str) -> tuple[int, int, int]:
    """Returns (deleted, skipped, failed)."""
    import flame

    cut_frame = _cut_frame_for(clip, first=first, logger=logger, label=label)
    if cut_frame is None:
        return 0, 0, 1

    try:
        clip.cut(flame.PyTime(cut_frame))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: cut failed on %s at frame %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            cut_frame,
            exc,
        )
        return 0, 0, 1

    deleted = 0
    skipped = 0
    failed = 0
    for segment in _edge_segments(clip, first=first):
        # After cut, edge should be 1F. Prefer record_duration; skip only if >1.
        if _is_clearly_longer_than_one_frame(segment):
            skipped += 1
            logger.warning(
                "%s: skip non-1F edge segment on %s (duration=%s)",
                label,
                dgpy_flame_types.item_label(clip),
                _segment_duration_frames(segment),
            )
            continue
        try:
            flame.delete(segment)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s: delete segment failed on %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )

    try:
        clip.current_time = _DEFAULT_RANGE_START
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: reset current_time failed on %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )

    return deleted, skipped, failed


def _run_cutout(selection, *, first: bool, parent=None) -> None:
    logger = dgpy_log.setup()
    label = "Cutout First Frame" if first else "Cutout Last Frame"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    n = len(clips)
    if first:
        msg = f"Cut out the first frame on {n} clip(s)?"
    else:
        msg = f"Cut out the last frame on {n} clip(s)?"
    if not dgpy_gui.confirm(parent, label, msg):
        logger.info("%s: cancelled (%s clip(s))", label, n)
        return

    _ensure_timeline_tab(logger)
    deleted = 0
    skipped = 0
    failed = 0
    for clip in clips:
        d, s, f = _cutout_one(clip, first=first, logger=logger, label=label)
        deleted += d
        skipped += s
        failed += f

    logger.info(
        "%s: clips=%s deleted_segments=%s skipped=%s failed=%s",
        label,
        len(clips),
        deleted,
        skipped,
        failed,
    )


def cutout_first_frame(selection, parent=None) -> None:
    _run_cutout(selection, first=True, parent=parent)


def cutout_last_frame(selection, parent=None) -> None:
    _run_cutout(selection, first=False, parent=parent)
