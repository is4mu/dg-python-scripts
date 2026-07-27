"""Only 1-2 / 3-4, delete mute / all audio tracks; compact helpers."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.1"

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
    for track in tracks:
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("%s: delete failed: %s", label, exc)
    return ok, failed


def _try_remap_inputs_to_12(clip, logger, label: str) -> None:
    """Best-effort: set remaining channel input mapping toward 1–2."""
    tracks = _tracks(clip)
    if not tracks:
        return
    track = tracks[0]
    channels = _channels(track)
    if not channels:
        logger.info("%s: no channels to remap on %s", label, dgpy_flame_types.item_label(clip))
        return

    # Probe once for diagnostics (DEBUG — noisy for production Terminal)
    sample = channels[0]
    names = [n for n in dir(sample) if not n.startswith("_")]
    logger.debug(
        "%s: probe channel attrs (first 40)=%s",
        label,
        names[:40],
    )

    targets = list(range(1, len(channels) + 1))  # 1, 2, ...
    wrote = 0
    for ch, want in zip(channels, targets):
        for attr in _INPUT_ATTR_CANDIDATES:
            if not hasattr(ch, attr):
                continue
            try:
                setattr(ch, attr, want)
                wrote += 1
                logger.debug(
                    "%s: set %s=%s on channel",
                    label,
                    attr,
                    want,
                )
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s: cannot set %s: %s", label, attr, exc)
        # Also try track-level once
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

    deleted = 0
    failed = 0
    for clip in clips:
        try:
            victims = pick_tracks(clip)
            d_ok, d_fail = _delete_tracks(clip, victims, logger, label)
            deleted += d_ok
            failed += d_fail
            if after_clip is not None:
                after_clip(clip, logger, label)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "%s failed for %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )
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
