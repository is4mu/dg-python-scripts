"""Cutdata: mark cuts on copies; build hard-committed clips from markers."""

from __future__ import annotations

import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.7"

CUTDATA_REEL_NAME = "Cutdata"
MARKER_TIME_OFFSET = -1
SHORTCUT_CREATE_SUBCLIP = "Create Subclip"
SHORTCUT_HARD_COMMIT = "Hard Commit Selection in Timeline"


def _attr(obj, name: str, default=None):
    if obj is None or not hasattr(obj, name):
        return default
    val = getattr(obj, name)
    if val is not None and hasattr(val, "get_value"):
        try:
            unwrapped = val.get_value()
            if unwrapped is not None:
                return unwrapped
        except Exception:  # noqa: BLE001
            pass
    return val if val is not None else default


def _list_attr(obj, name: str) -> list:
    if obj is None or not hasattr(obj, name):
        return []
    raw = getattr(obj, name)
    if raw is not None and hasattr(raw, "get_value"):
        try:
            unwrapped = raw.get_value()
            if unwrapped is not None:
                raw = unwrapped
        except Exception:  # noqa: BLE001
            pass
    try:
        return list(raw or [])
    except TypeError:
        return []


def _name(obj) -> str:
    return str(_attr(obj, "name", "") or "")


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
    return bool(_list_attr(obj, "markers"))


def _is_in_cutdata_reel(obj) -> bool:
    parent = getattr(obj, "parent", None)
    if parent is None or not dgpy_flame_types.is_reel(parent):
        return False
    return _name(parent) == CUTDATA_REEL_NAME


def get_create_targets(selection, *, logger=None) -> list:
    """Cutdata reel children that have markers."""
    return [
        c
        for c in get_targets(selection, logger=logger)
        if _is_in_cutdata_reel(c) and _has_markers(c)
    ]


def has_create_targets(selection, *, logger=None) -> bool:
    return bool(get_create_targets(selection, logger=logger))


def _ensure_timeline_tab(logger) -> None:
    import flame

    try:
        flame.set_current_tab("Timeline")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cutdata: set_current_tab Timeline failed: %s", exc)


def _primary_track(clip):
    return _attr(clip, "primary_track", None)


def _versions(clip) -> list:
    return _list_attr(clip, "versions")


def _as_timeline_sequence(clip, logger, label: str):
    """
    Open clip in Timeline for shortcut ops.

    ``open_as_sequence()`` returns the live PySequence and may invalidate
    the previous reference — always use the return value.
    """
    open_fn = getattr(clip, "open_as_sequence", None)
    if open_fn is None:
        return clip
    try:
        opened = open_fn()
        if opened is not None:
            logger.info(
                "%s: open_as_sequence → %s (use returned object)",
                label,
                dgpy_flame_types.item_label(opened),
            )
            return opened
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: open_as_sequence failed for %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )
    return clip


def _marker_time_from_transition(transition):
    """record_time + MARKER_TIME_OFFSET (-1 frame)."""
    import flame

    rt = _attr(transition, "record_time", None)
    if rt is None:
        rt = getattr(transition, "record_time", None)
    if rt is None:
        return None
    try:
        return rt + MARKER_TIME_OFFSET
    except TypeError:
        pass
    frame = getattr(rt, "frame", None)
    if frame is None:
        try:
            frame = int(rt)
        except (TypeError, ValueError):
            return None
    try:
        return flame.PyTime(int(frame) + MARKER_TIME_OFFSET)
    except Exception:  # noqa: BLE001
        return None


def _find_or_create_cutdata_reel(clip, logger):
    import flame

    try:
        reel = getattr(clip, "parent", None)
        reel_group = getattr(reel, "parent", None) if reel is not None else None
        if reel_group is None:
            return None
        reels = list(getattr(reel_group, "reels", None) or [])
        for r in reels:
            if _name(r) == CUTDATA_REEL_NAME:
                return r
        return reel_group.create_reel(CUTDATA_REEL_NAME)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Cutdata: failed to resolve/create %s reel: %s",
            CUTDATA_REEL_NAME,
            exc,
        )
        return None


def _add_markers_on_copy(clip, logger) -> int:
    primary = _primary_track(clip)
    if primary is None:
        logger.warning(
            "Add Markers for Cutdata: no primary on %s",
            dgpy_flame_types.item_label(clip),
        )
        return 0
    version = getattr(primary, "parent", None)
    if version is None:
        logger.warning(
            "Add Markers for Cutdata: no version for primary on %s",
            dgpy_flame_types.item_label(clip),
        )
        return 0
    tracks = list(getattr(version, "tracks", None) or [])
    if not tracks:
        return 0
    track0 = tracks[0]
    transitions = list(getattr(track0, "transitions", None) or [])
    created = 0
    for transition in transitions:
        try:
            when = _marker_time_from_transition(transition)
            if when is None:
                continue
            clip.create_marker(when)
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Add Markers for Cutdata: create_marker failed: %s", exc
            )
    return created


def add_markers_for_cutdata(selection, parent=None) -> None:
    del parent
    import flame

    logger = dgpy_log.setup()
    label = "Add Markers for Cutdata"
    clips = get_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    cutdata_reel = _find_or_create_cutdata_reel(clips[0], logger)
    if cutdata_reel is None:
        dgpy_gui.error(
            None,
            label,
            f"Failed to get or create the {CUTDATA_REEL_NAME} reel.",
        )
        return

    try:
        copied = flame.media_panel.copy(clips, cutdata_reel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: media_panel.copy failed: %s", label, exc)
        dgpy_gui.error(None, label, f"Copy to {CUTDATA_REEL_NAME} failed:\n{exc}")
        return

    copies = list(copied) if copied else []
    if not copies:
        logger.info("%s: copy produced no clips", label)
        return

    marker_total = 0
    clip_ok = 0
    for clip in copies:
        try:
            n = _add_markers_on_copy(clip, logger)
            marker_total += n
            clip_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: failed on %s: %s",
                label,
                dgpy_flame_types.item_label(clip),
                exc,
            )

    logger.info(
        "%s: source=%s copies=%s markers=%s",
        label,
        len(clips),
        clip_ok,
        marker_total,
    )


def _delete_all_audio(clip, logger, label: str) -> tuple[int, int]:
    import flame

    tracks = _list_attr(clip, "audio_tracks")
    if not tracks:
        logger.info(
            "%s: no audio_tracks on %s",
            label,
            dgpy_flame_types.item_label(clip),
        )
        return 0, 0
    for track in tracks:
        for ch in _list_attr(track, "channels"):
            try:
                ch.locked = False
            except Exception:  # noqa: BLE001
                pass
    ok = 0
    failed = 0
    for track in tracks:
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("%s: audio delete failed: %s", label, exc)
    return ok, failed


def _deselect(logger, label: str) -> None:
    import flame

    try:
        flame.execute_shortcut("Deselect")
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: Deselect shortcut failed: %s", label, exc)


def _select_only(clip, logger, label: str) -> None:
    """Clear selection, then select only this clip/sequence (for Subclip etc.)."""
    import flame

    _deselect(logger, label)

    try:
        flame.media_panel.selected_entries = [clip]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: selected_entries failed for %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )

    try:
        clip.selected = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: clip.selected failed for %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )


def _open_as_sequence(clip, logger, label: str) -> None:
    open_fn = getattr(clip, "open_as_sequence", None)
    if open_fn is None:
        return
    try:
        open_fn()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: open_as_sequence failed for %s: %s",
            label,
            dgpy_flame_types.item_label(clip),
            exc,
        )


def _primary_version(clip):
    primary = _primary_track(clip)
    if primary is not None:
        parent = getattr(primary, "parent", None)
        if parent is not None and hasattr(parent, "get_value"):
            try:
                unwrapped = parent.get_value()
                if unwrapped is not None:
                    parent = unwrapped
            except Exception:  # noqa: BLE001
                pass
        if parent is not None:
            return parent
    versions = _versions(clip)
    if versions:
        return versions[0]
    return None


def _select_track_for_commit(track, logger, label: str) -> None:
    """Select the bake layer (track and/or its segments) for Hard Commit."""
    try:
        track.selected = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: track.selected failed: %s", label, exc)

    for seg in _list_attr(track, "segments"):
        try:
            seg.selected = True
        except Exception:  # noqa: BLE001
            pass


def _hard_commit_sequence(clip, logger, label: str) -> bool:
    """
    Add top empty V via create_track(-1), select it, Hard Commit.

    Caller must pass a live sequence from ``_as_timeline_sequence``.
    """
    import flame

    _deselect(logger, label)

    try:
        flame.media_panel.selected_entries = [clip]
    except Exception:  # noqa: BLE001
        pass
    try:
        clip.selected = True
    except Exception:  # noqa: BLE001
        pass

    version = _primary_version(clip)
    if version is None:
        logger.warning(
            "%s: no version for create_track on %s "
            "(versions=%s primary_track=%s)",
            label,
            dgpy_flame_types.item_label(clip),
            len(_versions(clip)),
            _primary_track(clip) is not None,
        )
        return False

    create = getattr(version, "create_track", None)
    if create is None:
        logger.warning("%s: PyVersion.create_track unavailable", label)
        return False

    try:
        # track_index=-1 appends at the top (Flame 2025 API).
        new_track = create(track_index=-1)
    except TypeError:
        try:
            new_track = create(-1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: create_track failed: %s", label, exc)
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: create_track failed: %s", label, exc)
        return False

    if new_track is None:
        logger.warning("%s: create_track returned None", label)
        return False

    _deselect(logger, label)
    _select_track_for_commit(new_track, logger, label)
    logger.info(
        "%s: hard-commit via top track on %s",
        label,
        dgpy_flame_types.item_label(clip),
    )
    return _run_shortcut(SHORTCUT_HARD_COMMIT, logger, label)


def _run_shortcut(name: str, logger, label: str) -> bool:
    import flame

    try:
        flame.execute_shortcut(name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: shortcut %r failed: %s "
            "(check Keyboard Shortcut Editor description)",
            label,
            name,
            exc,
        )
        return False


def _delete_markers(clip, logger, label: str) -> int:
    import flame

    markers = _list_attr(clip, "markers")
    deleted = 0
    for marker in markers:
        try:
            flame.delete(marker)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: marker delete failed: %s", label, exc)
    return deleted


def _is_video_track(track) -> bool:
    typ = str(_attr(track, "type", "") or "")
    name = str(_attr(track, "name", "") or "")
    combined = f"{typ} {name}".lower()
    if "audio" in combined:
        return False
    if typ in ("A", "Audio", "audio"):
        return False
    return True


def _all_version_tracks(clip) -> list:
    out: list = []
    seen: set[int] = set()
    for version in _versions(clip):
        for track in _list_attr(version, "tracks"):
            tid = id(track)
            if tid in seen:
                continue
            seen.add(tid)
            out.append(track)
    return out


def _keep_primary_only(clip, logger, label: str) -> tuple[int, int]:
    import flame

    keep = _primary_track(clip)
    if keep is None:
        logger.warning(
            "%s: no primary on %s",
            label,
            dgpy_flame_types.item_label(clip),
        )
        return 0, 0
    ok = 0
    failed = 0
    for track in _all_version_tracks(clip):
        if track is keep or id(track) == id(keep):
            continue
        try:
            if track == keep:
                continue
        except Exception:  # noqa: BLE001
            pass
        if not _is_video_track(track):
            continue
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("%s: track delete failed: %s", label, exc)
    return ok, failed


def _frame_number(time_obj) -> int | None:
    """Best-effort frame int for sorting/logging (goto_frame style)."""
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


def _unwrap_location(marker):
    """Return marker.location as PyTime-like value (do not reduce to bare int)."""
    loc = getattr(marker, "location", None)
    if loc is None:
        return None
    # PyAttribute → underlying PyTime; keep PyTime itself.
    if hasattr(loc, "get_value"):
        try:
            unwrapped = loc.get_value()
            if unwrapped is not None:
                return unwrapped
        except Exception:  # noqa: BLE001
            pass
    return loc


def _snapshot_marker_locations(clip) -> list:
    """PyTime locations, ascending by frame (timeline order). Caller deletes markers."""
    items: list[tuple[int, object]] = []
    for marker in _list_attr(clip, "markers"):
        loc = _unwrap_location(marker)
        if loc is None:
            continue
        frame = _frame_number(loc)
        items.append((frame if frame is not None else 0, loc))
    items.sort(key=lambda t: t[0])
    return [loc for _, loc in items]


def create_cutdata_from_markers(selection, parent=None) -> None:
    """Bake → primary-only → no audio → snapshot+clear markers → subclip → delete src."""
    import flame

    logger = dgpy_log.setup()
    label = "Create Cutdata from Markers"
    clips = get_create_targets(selection, logger=logger)
    if not clips:
        logger.info("%s: nothing selected", label)
        return

    n = len(clips)
    msg = (
        "Hard-commit, keep primary video only, delete audio, "
        "then create subclips at each marker and delete the original.\n"
        "This cannot be undone.\n\n"
        f"Clips: {n}"
    )
    if not dgpy_gui.confirm(parent, label, msg):
        logger.info("%s: cancelled (%s clip(s))", label, n)
        return

    _ensure_timeline_tab(logger)

    processed = 0
    hard_ok = 0
    hard_fail = 0
    tracks_deleted = 0
    tracks_failed = 0
    audio_deleted = 0
    audio_failed = 0
    markers_cleared = 0
    subclip_ok = 0
    subclip_fail = 0
    deleted_src = 0

    for clip in list(clips):
        if not _list_attr(clip, "markers"):
            continue
        processed += 1

        # Timeline shortcuts need the sequence open; use the returned object.
        seq = _as_timeline_sequence(clip, logger, label)

        if _hard_commit_sequence(seq, logger, label):
            hard_ok += 1
        else:
            hard_fail += 1
            logger.warning(
                "%s: skip remaining steps for %s (hard-commit failed)",
                label,
                dgpy_flame_types.item_label(seq),
            )
            continue

        t_ok, t_fail = _keep_primary_only(seq, logger, label)
        tracks_deleted += t_ok
        tracks_failed += t_fail

        a_ok, a_fail = _delete_all_audio(seq, logger, label)
        audio_deleted += a_ok
        audio_failed += a_fail

        locations = _snapshot_marker_locations(seq)
        if not locations:
            logger.warning(
                "%s: no marker locations after bake on %s",
                label,
                dgpy_flame_types.item_label(seq),
            )
            continue

        frame_log = [_frame_number(loc) for loc in locations]
        logger.info(
            "%s: %s marker locations frames=%s",
            label,
            dgpy_flame_types.item_label(seq),
            frame_log,
        )

        markers_cleared += _delete_markers(seq, logger, label)

        for loc in locations:
            frame = _frame_number(loc)
            try:
                _select_only(seq, logger, label)
                try:
                    seq.current_time = loc
                except Exception:
                    fps = _attr(seq, "frame_rate", None)
                    if frame is None:
                        raise
                    if fps is not None:
                        seq.current_time = flame.PyTime(frame, fps)
                    else:
                        seq.current_time = flame.PyTime(frame)
                if not _run_shortcut(SHORTCUT_CREATE_SUBCLIP, logger, label):
                    subclip_fail += 1
                    continue
                subclip_ok += 1
            except Exception as exc:  # noqa: BLE001
                subclip_fail += 1
                logger.warning(
                    "%s: subclip at frame %s failed: %s", label, frame, exc
                )

        try:
            flame.delete(seq)
            deleted_src += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: failed to delete original %s: %s",
                label,
                dgpy_flame_types.item_label(seq),
                exc,
            )

    logger.info(
        "%s: clips=%s hard=%s/%s tracks_del=%s/%s audio_del=%s/%s "
        "markers_cleared=%s subclips=%s fail=%s src_deleted=%s",
        label,
        processed,
        hard_ok,
        hard_fail,
        tracks_deleted,
        tracks_failed,
        audio_deleted,
        audio_failed,
        markers_cleared,
        subclip_ok,
        subclip_fail,
        deleted_src,
    )
