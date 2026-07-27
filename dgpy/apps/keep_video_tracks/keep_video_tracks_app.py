"""Only Primary / Only Top video tracks; Set Top as Primary."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.3"


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


def _primary_track(clip):
    return _attr_value(clip, "primary_track", None)


def _is_video_track(track) -> bool:
    """True unless clearly an audio track."""
    typ = str(_attr_value(track, "type", "") or "")
    name = str(_attr_value(track, "name", "") or "")
    combined = f"{typ} {name}".lower()
    if "audio" in combined:
        return False
    if typ in ("A", "Audio", "audio"):
        return False
    return True


def _all_version_tracks(clip) -> list:
    """All tracks across all versions (Hard Commit leftovers may sit off primary)."""
    out: list = []
    seen: set[int] = set()
    for version in list(getattr(clip, "versions", None) or []):
        for track in list(getattr(version, "tracks", None) or []):
            tid = id(track)
            if tid in seen:
                continue
            seen.add(tid)
            out.append(track)
    return out


def _version_tracks_for_top(clip) -> list:
    """Tracks on the primary track's version (for Top = tracks[-1])."""
    versions = list(getattr(clip, "versions", None) or [])
    if not versions:
        return []
    primary = _primary_track(clip)
    if primary is not None:
        parent = getattr(primary, "parent", None)
        if parent is not None:
            tracks = list(getattr(parent, "tracks", None) or [])
            if tracks:
                return tracks
    return list(getattr(versions[0], "tracks", None) or [])


def _top_track(clip):
    tracks = _version_tracks_for_top(clip)
    if not tracks:
        return None
    return tracks[-1]


def _video_tracks_except(clip, keep) -> list:
    if keep is None:
        return []
    out: list = []
    for track in _all_version_tracks(clip):
        if track is keep or id(track) == id(keep):
            continue
        # Prefer != as well (Flame wrappers; matches legacy delete_tracks).
        try:
            if track == keep:
                continue
        except Exception:  # noqa: BLE001
            pass
        if not _is_video_track(track):
            continue
        out.append(track)
    return out


def _ensure_timeline_tab(logger) -> None:
    import flame

    try:
        flame.set_current_tab("Timeline")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Keep Video Tracks: set_current_tab Timeline failed: %s", exc
        )


def _delete_tracks(tracks: list, logger, label: str) -> tuple[int, int]:
    import flame

    ok = 0
    failed = 0
    for track in tracks:
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s: failed to delete track %s: %s",
                label,
                dgpy_flame_types.item_label(track),
                exc,
            )
    return ok, failed


def only_primary_track(selection, parent=None) -> None:
    logger = dgpy_log.setup()
    label = "Only Primary Track"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    n = len(clips)
    msg = (
        f"Delete all video tracks except the primary track "
        f"on {n} clip(s)?"
    )
    if not dgpy_gui.confirm(parent, label, msg):
        logger.info("%s: cancelled (%s clip(s))", label, n)
        return

    _ensure_timeline_tab(logger)
    clip_ok = 0
    clip_skip = 0
    deleted = 0
    failed = 0
    for clip in clips:
        keep = _primary_track(clip)
        if keep is None:
            clip_skip += 1
            logger.warning(
                "%s: no primary track on %s",
                label,
                dgpy_flame_types.item_label(clip),
            )
            continue
        victims = _video_tracks_except(clip, keep)
        d_ok, d_fail = _delete_tracks(victims, logger, label)
        deleted += d_ok
        failed += d_fail
        clip_ok += 1
    logger.info(
        "%s: clips=%s skipped=%s deleted=%s failed=%s",
        label,
        clip_ok,
        clip_skip,
        deleted,
        failed,
    )


def only_top_track(selection, parent=None) -> None:
    logger = dgpy_log.setup()
    label = "Only Top Track"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    n = len(clips)
    msg = (
        f"Delete all video tracks except the top track "
        f"on {n} clip(s)?"
    )
    if not dgpy_gui.confirm(parent, label, msg):
        logger.info("%s: cancelled (%s clip(s))", label, n)
        return

    _ensure_timeline_tab(logger)
    clip_ok = 0
    clip_skip = 0
    deleted = 0
    failed = 0
    for clip in clips:
        keep = _top_track(clip)
        if keep is None:
            clip_skip += 1
            logger.warning(
                "%s: no top track on %s",
                label,
                dgpy_flame_types.item_label(clip),
            )
            continue
        victims = _video_tracks_except(clip, keep)
        d_ok, d_fail = _delete_tracks(victims, logger, label)
        deleted += d_ok
        failed += d_fail
        clip_ok += 1
    logger.info(
        "%s: clips=%s skipped=%s deleted=%s failed=%s",
        label,
        clip_ok,
        clip_skip,
        deleted,
        failed,
    )


def set_top_as_primary(selection, parent=None) -> None:
    logger = dgpy_log.setup()
    label = "Set Top as Primary"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    ok = 0
    failed = 0
    for clip in clips:
        top = _top_track(clip)
        if top is None:
            failed += 1
            logger.warning(
                "%s: no top track on %s",
                label,
                dgpy_flame_types.item_label(clip),
            )
            continue
        try:
            clip.primary_track = top
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
