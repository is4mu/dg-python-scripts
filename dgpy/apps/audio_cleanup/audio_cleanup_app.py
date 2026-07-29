"""Only 1-2 / 3-4, delete mute / all audio tracks; compact helpers."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.6"

_INPUT_ATTR_CANDIDATES = (
    "input",
    "input_channel",
    "input_strip",
    "strip",
    "patch",
    "patch_input",
    "channel",
    "channel_number",
    "number",
    "index",
)


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


def _tracks(clip) -> list:
    return list(getattr(clip, "audio_tracks", None) or [])


def _channels(track) -> list:
    return list(getattr(track, "channels", None) or [])


def has_any_audio(selection, *, logger=None) -> bool:
    return bool(get_targets(selection, logger=logger))


def has_multi_audio(selection, *, logger=None) -> bool:
    for clip in get_targets(selection, logger=logger):
        if len(_tracks(clip)) > 1:
            return True
    return False


def has_mute_audio(selection, *, logger=None) -> bool:
    for clip in get_targets(selection, logger=logger):
        for track in _tracks(clip):
            if bool(_attr(track, "mute", False)):
                return True
    return False


def _ensure_sequence_for_audio(obj, logger, label: str) -> tuple[object, bool]:
    """Return (host, opened). Source PyClip needs open_as_sequence for delete.

    PySequence already editable. PySequence subclasses PyClip — detect via
    is_sequence first. ``opened`` is True only when we called open_as_sequence
    successfully (caller should Close Current Sequence afterward).
    """
    if dgpy_flame_types.is_sequence(obj):
        return obj, False

    open_fn = getattr(obj, "open_as_sequence", None)
    if not callable(open_fn):
        logger.warning(
            "%s: no open_as_sequence on %s — delete may be no-op",
            label,
            dgpy_flame_types.item_label(obj),
        )
        return obj, False
    try:
        opened = open_fn()
        if opened is not None:
            logger.info(
                "%s: open_as_sequence %s → %s (audio edit)",
                label,
                dgpy_flame_types.item_label(obj),
                dgpy_flame_types.item_label(opened),
            )
            return opened, True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: open_as_sequence failed for %s: %s",
            label,
            dgpy_flame_types.item_label(obj),
            exc,
        )
    return obj, False


def _close_opened_sequence(logger, label: str) -> None:
    """Close timeline tab opened by open_as_sequence (Clip Mgmt shortcut)."""
    import flame

    try:
        ok = flame.execute_shortcut("Close Current Sequence")
        if ok is False:
            logger.warning(
                "%s: Close Current Sequence returned False",
                label,
            )
        else:
            logger.debug("%s: Close Current Sequence", label)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: Close Current Sequence failed: %s", label, exc)


def _unlock(clip) -> None:
    for track in _tracks(clip):
        for ch in _channels(track):
            try:
                ch.locked = False
            except Exception:  # noqa: BLE001
                pass


def _delete_tracks(clip, tracks: list, logger, label: str) -> tuple[int, int]:
    import flame

    if not tracks:
        return 0, 0
    _unlock(clip)
    ok = 0
    failed = 0
    # Highest index first — safer if Flame mutates the track list live.
    for track in reversed(list(tracks)):
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("%s: delete failed: %s", label, exc)
    remaining = len(_tracks(clip))
    if ok and remaining:
        logger.warning(
            "%s: deleted=%s but %s audio_tracks remain on %s",
            label,
            ok,
            remaining,
            dgpy_flame_types.item_label(clip),
        )
    return ok, failed


def _try_remap_inputs_to_12(clip, logger, label: str) -> None:
    """Best-effort: set remaining channel input mapping toward 1–2."""
    tracks = _tracks(clip)
    if not tracks:
        return
    track = tracks[0]
    channels = _channels(track)
    if not channels:
        logger.info(
            "%s: no channels to remap on %s",
            label,
            dgpy_flame_types.item_label(clip),
        )
        return

    sample = channels[0]
    names = [n for n in dir(sample) if not n.startswith("_")]
    logger.debug(
        "%s: probe channel attrs (first 40)=%s",
        label,
        names[:40],
    )

    targets = list(range(1, len(channels) + 1))
    wrote = 0
    for ch, want in zip(channels, targets):
        for attr in _INPUT_ATTR_CANDIDATES:
            if not hasattr(ch, attr):
                continue
            try:
                setattr(ch, attr, want)
                wrote += 1
                logger.debug("%s: set %s=%s on channel", label, attr, want)
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s: cannot set %s: %s", label, attr, exc)
    for attr in _INPUT_ATTR_CANDIDATES:
        if not hasattr(track, attr):
            continue
        try:
            setattr(track, attr, 1)
            wrote += 1
            logger.debug("%s: set track.%s=1", label, attr)
            break
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s: cannot set track.%s: %s", label, attr, exc)

    if wrote == 0:
        logger.warning(
            "%s: input remap to 1-2 not available via API "
            "(channels stay on original inputs). clip=%s",
            label,
            dgpy_flame_types.item_label(clip),
        )


def _run_delete(
    selection,
    *,
    label: str,
    confirm_msg: str,
    pick_tracks,
    after_clip=None,
    parent=None,
) -> None:
    logger = dgpy_log.setup()
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return
    if not dgpy_gui.confirm(parent, label, confirm_msg.format(n=len(clips))):
        logger.info("%s: cancelled (%s)", label, len(clips))
        return

    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(logger=logger, label=label)

    deleted = 0
    failed = 0
    for clip in clips:
        opened = False
        try:
            host, opened = _ensure_sequence_for_audio(clip, logger, label)
            victims = pick_tracks(host)
            d_ok, d_fail = _delete_tracks(host, victims, logger, label)
            deleted += d_ok
            failed += d_fail
            if after_clip is not None:
                after_clip(host, logger, label)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s failed for %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )
        finally:
            if opened:
                _close_opened_sequence(logger, label)
    logger.info("%s: deleted=%s failed=%s", label, deleted, failed)


def only_1_2(selection, parent=None) -> None:
    _run_delete(
        selection,
        label="Only 1-2 Track",
        confirm_msg="Delete audio tracks other than 1-2 on {n} clip(s)?",
        pick_tracks=lambda c: [t for i, t in enumerate(_tracks(c)) if i != 0],
        parent=parent,
    )


def only_3_4(selection, parent=None) -> None:
    _run_delete(
        selection,
        label="Only 3-4 Track",
        confirm_msg=(
            "Delete audio tracks other than 3-4 on {n} clip(s)? "
            "(Input remap to 1-2 is best-effort if the API allows.)"
        ),
        pick_tracks=lambda c: [t for i, t in enumerate(_tracks(c)) if i != 1],
        after_clip=_try_remap_inputs_to_12,
        parent=parent,
    )


def delete_mute(selection, parent=None) -> None:
    def pick(clip):
        return [t for t in _tracks(clip) if bool(_attr(t, "mute", False))]

    _run_delete(
        selection,
        label="Delete Mute Tracks",
        confirm_msg="Delete muted audio tracks on {n} clip(s)?",
        pick_tracks=pick,
        parent=parent,
    )


def delete_all(selection, parent=None) -> None:
    _run_delete(
        selection,
        label="Delete All Audio Tracks",
        confirm_msg="Delete ALL audio tracks on {n} clip(s)?",
        pick_tracks=_tracks,
        parent=parent,
    )
