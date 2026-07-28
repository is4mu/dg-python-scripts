"""Lock / unlock all audio channels on selected clips/sequences."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_log

__version__ = "1.0.2"


def _attr(obj, name: str, default=None):
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
    out: list = []
    seen: set[int] = set()

    def _add(obj) -> None:
        if not (dgpy_flame_types.is_clip(obj) or dgpy_flame_types.is_sequence(obj)):
            return
        if not list(getattr(obj, "audio_tracks", None) or []):
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


def _channels(track):
    return list(getattr(track, "channels", None) or [])


def _iter_channels(clip):
    for track in list(getattr(clip, "audio_tracks", None) or []):
        for ch in _channels(track):
            yield ch


def has_unlocked_audio(selection, *, logger=None) -> bool:
    for clip in get_targets(selection, logger=logger):
        for ch in _iter_channels(clip):
            if not bool(_attr(ch, "locked", False)):
                return True
    return False


def has_locked_audio(selection, *, logger=None) -> bool:
    for clip in get_targets(selection, logger=logger):
        for ch in _iter_channels(clip):
            if bool(_attr(ch, "locked", False)):
                return True
    return False


def _set_locked(clips: list, locked: bool, label: str) -> None:
    logger = dgpy_log.setup()
    ok = 0
    failed = 0
    for clip in clips:
        try:
            for ch in _iter_channels(clip):
                try:
                    ch.locked = locked
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    logger.warning("%s channel failed: %s", label, exc)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s failed for %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )
    logger.info("%s: channels ok=%s failed=%s", label, ok, failed)


def lock_tracks(selection) -> None:
    clips = get_targets(selection, logger=dgpy_log.setup())
    if not clips:
        dgpy_log.setup().info("Lock Audio Tracks: nothing selected")
        return
    _set_locked(clips, True, "Lock Audio Tracks")


def unlock_tracks(selection) -> None:
    clips = get_targets(selection, logger=dgpy_log.setup())
    if not clips:
        dgpy_log.setup().info("Unlock Audio Tracks: nothing selected")
        return
    _set_locked(clips, False, "Unlock Audio Tracks")
