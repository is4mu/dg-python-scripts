"""Create Sources reel clips (match + Subclip + Hard Commit + strip audio)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_attr
import dgpy_flame_types

from segment_handle_clips_util import (
    TITLE,
    __version__,
    close_current_sequence,
    run_shortcut,
)

DEFAULT_REEL = "Sources"
SHORTCUT_CREATE_SUBCLIP = "Create Subclip"
SHORTCUT_DESELECT = "Deselect"
SHORTCUT_HARD_COMMIT = "Hard Commit Selection in Timeline"
SHORTCUT_HARD_COMMIT_SEQ = "Hard Commit Sequence Under Cursor"


def find_or_create_sources_reel(anchor, logger, *, reel_name: str = DEFAULT_REEL):
    """Find or create Sources on the Desktop reel group near ``anchor``."""
    try:
        reel = getattr(anchor, "parent", None)
        reel_group = getattr(reel, "parent", None) if reel is not None else None
        if reel_group is None:
            try:
                import flame

                desktop = flame.project.current_project.current_workspace.desktop
                groups = list(getattr(desktop, "reel_groups", None) or [])
                if groups:
                    reel_group = groups[0]
            except Exception:  # noqa: BLE001
                pass
        if reel_group is None:
            logger.warning("%s: no reel group for %s", TITLE, reel_name)
            return None, "missing"

        for r in list(getattr(reel_group, "reels", None) or []):
            if str(dgpy_flame_attr.attr_value(r, "name", "") or "") == reel_name:
                return r, "existing"

        create = getattr(reel_group, "create_reel", None)
        if not create:
            logger.warning("%s: create_reel unavailable", TITLE)
            return None, "missing"
        created = create(reel_name)
        return created, "created"
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: reel %s failed: %s", TITLE, reel_name, exc)
        return None, "missing"


def _reel_entries(reel) -> list:
    out = []
    out.extend(list(getattr(reel, "clips", None) or []))
    out.extend(list(getattr(reel, "sequences", None) or []))
    return out


def _reel_ids(reel) -> set[int]:
    return {id(c) for c in _reel_entries(reel)}


def _looks_like_clip(obj) -> bool:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return False
    return dgpy_flame_types.is_clip(obj) or dgpy_flame_types.is_sequence(obj)


def _resolve_new_clip(result, reel, before: set[int], logger, label: str):
    if isinstance(result, (list, tuple)):
        for item in result:
            if _looks_like_clip(item):
                return item
    if _looks_like_clip(result):
        return result
    for c in _reel_entries(reel):
        if id(c) not in before and _looks_like_clip(c):
            return c
    logger.warning("%s: no new clip on destination reel", label)
    return None


def _set_name(clip, name: str, logger) -> None:
    try:
        attr = getattr(clip, "name", None)
        if attr is not None and hasattr(attr, "set_value"):
            attr.set_value(name)
            return
        if hasattr(clip, "name"):
            clip.name = name
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: rename to %r failed: %s", TITLE, name, exc)


def _match_segment_to_reel(segment, reel, logger) -> Any | None:
    """PySegment.match(destination) — prefer over copy_to_media_panel."""
    fn = getattr(segment, "match", None)
    if not callable(fn):
        logger.debug("match unavailable on %s", type(segment).__name__)
        return None
    before = _reel_ids(reel)
    result = None
    try:
        result = fn(
            reel,
            preserve_handle=False,
            use_sequence_info=False,
            include_nested_content=False,
            include_timeline_fx=False,
        )
    except TypeError:
        try:
            result = fn(reel, False, False, False, False)
        except TypeError:
            try:
                result = fn(reel)
            except Exception as exc:  # noqa: BLE001
                logger.warning("segment.match failed: %s", exc)
                return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("segment.match failed: %s", exc)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("segment.match failed: %s", exc)
        return None

    clip = _resolve_new_clip(result, reel, before, logger, "segment.match")
    if clip is not None:
        logger.info(
            "%s: segment.match → %s",
            TITLE,
            dgpy_flame_types.item_label(clip),
        )
    return clip


def _copy_segment_to_media_panel(segment, reel, logger) -> Any | None:
    fn = getattr(segment, "copy_to_media_panel", None)
    if not callable(fn):
        return None
    before = _reel_ids(reel)
    result = None
    try:
        result = fn(reel, duplicate_action="add")
    except TypeError:
        try:
            result = fn(reel, "add")
        except TypeError:
            try:
                result = fn(reel)
            except Exception as exc:  # noqa: BLE001
                logger.warning("copy_to_media_panel failed: %s", exc)
                return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("copy_to_media_panel failed: %s", exc)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("copy_to_media_panel failed: %s", exc)
        return None
    return _resolve_new_clip(result, reel, before, logger, "copy_to_media_panel")


def _copy_to_reel(source, reel, logger) -> Any | None:
    import flame

    before = _reel_ids(reel)
    try:
        result = flame.media_panel.copy(source, reel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("media_panel.copy failed: %s", exc)
        return None
    return _resolve_new_clip(result, reel, before, logger, "media_panel.copy")


def _as_pytime(frame: int):
    try:
        import flame

        return flame.PyTime(int(frame))
    except Exception:  # noqa: BLE001
        return int(frame)


def _set_one_mark(clip, name: str, frame: int, logger) -> bool:
    val = _as_pytime(frame)
    try:
        a = getattr(clip, name, None)
        if a is not None and hasattr(a, "set_value"):
            a.set_value(val)
            return True
        setattr(clip, name, val)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: set %s=%s failed: %s", TITLE, name, frame, exc
        )
        return False


def set_keep_marks(clip, start: int, end: int, logger) -> bool:
    """Set clip in_mark/out_mark to planned cut (keep) range."""
    ok_in = _set_one_mark(clip, "in_mark", start, logger)
    ok_out = _set_one_mark(clip, "out_mark", end, logger)
    return ok_in and ok_out


def clear_keep_marks(clip, logger) -> bool:
    """Clear in_mark/out_mark via attributes (not Clear In/Out shortcut)."""
    ok = True
    for name in ("in_mark", "out_mark"):
        try:
            a = getattr(clip, name, None)
            if a is not None and hasattr(a, "set_value"):
                a.set_value(None)
                continue
            setattr(clip, name, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: clear %s failed: %s", TITLE, name, exc
            )
            ok = False
    return ok


def _list_attr(obj, name: str) -> list:
    try:
        return list(getattr(obj, name, None) or [])
    except Exception:  # noqa: BLE001
        return []


def _delete_audio_on_host(host, logger) -> tuple[int, int]:
    """Delete audio_tracks on already-open host. Returns (ok, failed)."""
    import flame

    tracks = _list_attr(host, "audio_tracks")
    if not tracks:
        logger.info(
            "%s: no audio_tracks on %s",
            TITLE,
            dgpy_flame_types.item_label(host),
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
    for track in reversed(list(tracks)):
        try:
            flame.delete(track)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("%s: audio delete failed: %s", TITLE, exc)
    remaining = len(_list_attr(host, "audio_tracks"))
    if ok and remaining:
        logger.warning(
            "%s: deleted=%s but %s audio_tracks remain on %s",
            TITLE,
            ok,
            remaining,
            dgpy_flame_types.item_label(host),
        )
        failed += remaining
    elif ok:
        logger.info(
            "%s: deleted %s audio track(s) on %s",
            TITLE,
            ok,
            dgpy_flame_types.item_label(host),
        )
    return ok, failed


def hard_commit_zero_handles(host, logger) -> str:
    """Bake selection to drop head/tail. Returns ok|failed."""
    _select_only(host, logger)
    if run_shortcut(SHORTCUT_HARD_COMMIT, logger):
        logger.info(
            "%s: %s → %s",
            TITLE,
            SHORTCUT_HARD_COMMIT,
            dgpy_flame_types.item_label(host),
        )
        return "ok"
    logger.warning(
        "%s: %s failed — try %s",
        TITLE,
        SHORTCUT_HARD_COMMIT,
        SHORTCUT_HARD_COMMIT_SEQ,
    )
    _select_only(host, logger)
    if run_shortcut(SHORTCUT_HARD_COMMIT_SEQ, logger):
        logger.info(
            "%s: %s → %s",
            TITLE,
            SHORTCUT_HARD_COMMIT_SEQ,
            dgpy_flame_types.item_label(host),
        )
        return "ok"
    return "failed"


def _open_as_sequence(obj, logger, *, for_edit: bool = False):
    """
    Open clip as Timeline sequence when needed.

    Returns (host, opened). ``opened`` is True only when open_as_sequence ran.
    """
    if dgpy_flame_types.is_sequence(obj):
        return obj, False
    open_fn = getattr(obj, "open_as_sequence", None)
    if not callable(open_fn):
        if for_edit:
            logger.warning("%s: no open_as_sequence — edit may no-op", TITLE)
        return obj, False
    try:
        opened = open_fn()
        if opened is not None:
            logger.info(
                "%s: open_as_sequence → %s",
                TITLE,
                dgpy_flame_types.item_label(opened),
            )
            return opened, True
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: open_as_sequence failed: %s", TITLE, exc)
    return obj, False


def post_subclip_cleanup(clip, logger) -> tuple[str, str]:
    """
    One open_as_sequence session: Hard Commit → audio delete → clear marks.

    Returns (handles_status, audio_status). Mark clear failures are log-only.
    """
    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(logger=logger, label=TITLE)
    host, opened = _open_as_sequence(clip, logger, for_edit=True)
    try:
        handles_status = hard_commit_zero_handles(host, logger)
        _a_ok, a_fail = _delete_audio_on_host(host, logger)
        audio_status = "failed" if a_fail else "ok"
        clear_keep_marks(host, logger)
        return handles_status, audio_status
    finally:
        if opened:
            close_current_sequence(logger)


def _deselect(logger) -> None:
    import flame

    try:
        flame.execute_shortcut(SHORTCUT_DESELECT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: Deselect failed: %s", TITLE, exc)


def _select_only(clip, logger) -> None:
    import flame

    _deselect(logger)
    try:
        flame.media_panel.selected_entries = [clip]
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: selected_entries failed: %s", TITLE, exc)
    try:
        clip.selected = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: clip.selected failed: %s", TITLE, exc)


def _delete_clip(clip, logger, *, what: str) -> bool:
    import flame

    try:
        flame.delete(clip)
        logger.info(
            "%s: deleted %s %s",
            TITLE,
            what,
            dgpy_flame_types.item_label(clip),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: delete %s failed: %s", TITLE, what, exc)
        return False


def subclip_keep_range(clip, reel, start: int, end: int, name: str, logger):
    """
    Create Subclip from In/Out marks; Hard Commit + audio + clear marks; drop host.

    Returns (final_clip, cut_status, audio_status, handles_status, reel_index).
    ``reel_index`` is captured at Create Subclip time and adjusted when hosts are deleted
    (post-cleanup PyClip ids often no longer match ``reel.clips``).
    """
    if clip is None:
        return None, "n/a", "n/a", "n/a", None

    if not set_keep_marks(clip, start, end, logger):
        logger.warning(
            "%s: marks failed — skip Create Subclip for %s", TITLE, name
        )
        return clip, "failed", "skip", "skip", None

    host, _opened = _open_as_sequence(clip, logger)
    if host is not clip:
        set_keep_marks(host, start, end, logger)

    before = _reel_ids(reel)
    before.add(id(clip))
    before.add(id(host))

    _select_only(host, logger)
    if not run_shortcut(SHORTCUT_CREATE_SUBCLIP, logger):
        return clip, "failed", "skip", "skip", None

    sub = None
    reel_index = None
    clips = list(getattr(reel, "clips", None) or [])
    for i, c in enumerate(clips):
        if id(c) not in before and _looks_like_clip(c):
            sub = c
            reel_index = i
            break
    if sub is None:
        # Subclip may land in sequences list on some setups.
        for c in _reel_entries(reel):
            if id(c) not in before and _looks_like_clip(c):
                sub = c
                break
        if sub is not None:
            reel_index = _reel_index_of(reel, sub)
    if sub is None:
        logger.warning(
            "%s: Create Subclip produced no new clip on Sources", TITLE
        )
        return clip, "failed", "skip", "skip", None

    logger.info(
        "%s: Create Subclip → %s reel_index=%s",
        TITLE,
        dgpy_flame_types.item_label(sub),
        reel_index,
    )
    _set_name(sub, name, logger)

    handles_status, audio_status = post_subclip_cleanup(sub, logger)
    clear_keep_marks(sub, logger)

    if host is not sub:
        reel_index = _delete_clip_adjust_index(
            host, reel, reel_index, logger, what="full-length host"
        )
    if clip is not host and clip is not sub:
        reel_index = _delete_clip_adjust_index(
            clip, reel, reel_index, logger, what="full-length original"
        )

    # Fresh handle from reel (Create handle may be stale after open/close).
    fresh = None
    if reel_index is not None:
        try:
            clips_now = list(getattr(reel, "clips", None) or [])
            if 0 <= reel_index < len(clips_now):
                fresh = clips_now[reel_index]
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: reel refresh failed: %s", TITLE, exc)
    if fresh is None:
        fresh = sub

    return fresh, "ok", audio_status, handles_status, reel_index


def _reel_index_of(reel, clip) -> int | None:
    if clip is None:
        return None
    try:
        for i, c in enumerate(list(getattr(reel, "clips", None) or [])):
            if c is clip or id(c) == id(clip):
                return i
    except Exception:  # noqa: BLE001
        return None
    return None


def _delete_clip_adjust_index(
    clip, reel, reel_index: int | None, logger, *, what: str
) -> int | None:
    """Delete clip on reel; if it sat before ``reel_index``, decrement index."""
    del_i = _reel_index_of(reel, clip)
    if not _delete_clip(clip, logger, what=what):
        return reel_index
    if (
        reel_index is not None
        and del_i is not None
        and del_i < reel_index
    ):
        return reel_index - 1
    if reel_index is not None and del_i is not None and del_i == reel_index:
        logger.warning(
            "%s: deleted %s at reel_index=%s (subclip index)", TITLE, what, del_i
        )
        return None
    return reel_index


def create_merged_clip(
    *,
    segment,
    owner_clip,
    clip_name: str,
    keep_start: int,
    keep_end: int,
    reel,
    logger,
) -> dict:
    """
    Match/copy, Subclip, Hard Commit handles, strip audio, clear marks.

    ``status`` is ok only when Subclip (cut) succeeded and reel_index is known.
    """
    label = clip_name or "clip"
    start = max(1, int(keep_start))
    end = max(1, int(keep_end))
    if end < start:
        end = start

    clip = None
    method = ""
    if segment is not None:
        clip = _match_segment_to_reel(segment, reel, logger)
        if clip is not None:
            method = "match"
        else:
            clip = _copy_segment_to_media_panel(segment, reel, logger)
            if clip is not None:
                method = "copy_to_media_panel"

    if clip is None and owner_clip is not None and _looks_like_clip(owner_clip):
        logger.info("%s: fallback media_panel.copy for %s", TITLE, label)
        clip = _copy_to_reel(owner_clip, reel, logger)
        if clip is not None:
            method = "media_panel.copy"

    if clip is None:
        return {
            "status": "skip",
            "cut": "n/a",
            "audio": "n/a",
            "handles": "n/a",
            "message": "no copy source",
            "label": label,
        }

    _set_name(clip, label, logger)
    final, cut_status, audio_status, handles_status, reel_index = (
        subclip_keep_range(clip, reel, start, end, label, logger)
    )

    if cut_status != "ok":
        return {
            "status": "failed",
            "cut": cut_status,
            "audio": audio_status,
            "handles": handles_status,
            "message": f"keep {start}..{end} via {method}",
            "label": label,
            "clip": final,
            "reel_index": reel_index,
            "clip_name": label,
        }

    if reel_index is None:
        logger.warning(
            "%s: Subclip ok but reel_index unresolved for %s", TITLE, label
        )
        return {
            "status": "failed",
            "cut": cut_status,
            "audio": audio_status,
            "handles": handles_status,
            "message": f"keep {start}..{end} via {method} (no reel_index)",
            "label": label,
            "clip": final,
            "reel_index": None,
            "clip_name": label,
        }

    name = dgpy_flame_attr.clip_name(final) if final is not None else label
    return {
        "status": "ok",
        "cut": cut_status,
        "audio": audio_status,
        "handles": handles_status,
        "message": f"keep {start}..{end} via {method}",
        "label": name or label,
        "clip": final,
        "reel_index": reel_index,
        "clip_name": name or label,
    }


def create_merged_clips(
    *,
    merged: list,
    jobs: list[dict],
    reel,
    logger,
) -> list[dict]:
    """Create one Sources clip per MergedRange. ``merged`` from merge_keep_ranges."""
    results = []
    for m in merged:
        skip = {
            "status": "skip",
            "cut": "n/a",
            "audio": "n/a",
            "handles": "n/a",
            "label": m.label,
        }
        if not m.seg_indices:
            results.append({**skip, "message": "empty from#"})
            continue
        idx0 = m.seg_indices[0] - 1
        if idx0 < 0 or idx0 >= len(jobs):
            results.append(
                {**skip, "message": f"bad from# {m.seg_indices[0]}"}
            )
            continue
        job = jobs[idx0]
        name = (m.names[0] if m.names else job.get("clip_name")) or "clip"
        results.append(
            create_merged_clip(
                segment=job.get("segment"),
                owner_clip=job.get("owner_clip"),
                clip_name=str(name),
                keep_start=m.keep_start,
                keep_end=m.keep_end,
                reel=reel,
                logger=logger,
            )
        )
    return results
