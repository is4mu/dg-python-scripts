"""Create DG Sources reel clips (match + Subclip + Hard Commit + strip audio)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_attr
import dgpy_flame_types

from segment_handle_clips_util import TITLE, __version__  # noqa: F401


DEFAULT_REEL = "DG Sources"
SHORTCUT_CREATE_SUBCLIP = "Create Subclip"
SHORTCUT_DESELECT = "Deselect"
SHORTCUT_HARD_COMMIT = "Hard Commit Selection in Timeline"
SHORTCUT_HARD_COMMIT_SEQ = "Hard Commit Sequence Under Cursor"


def find_or_create_sources_reel(anchor, logger, *, reel_name: str = DEFAULT_REEL):
    """Find or create ``DG Sources`` on the Desktop reel group near ``anchor``."""
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
            logger.warning("Consolidate Handles: no reel group for %s", reel_name)
            return None, "missing"

        for r in list(getattr(reel_group, "reels", None) or []):
            if str(dgpy_flame_attr.attr_value(r, "name", "") or "") == reel_name:
                return r, "existing"

        create = getattr(reel_group, "create_reel", None)
        if not create:
            logger.warning("Consolidate Handles: create_reel unavailable")
            return None, "missing"
        created = create(reel_name)
        return created, "created"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Consolidate Handles: reel %s failed: %s", reel_name, exc)
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
        logger.warning("Consolidate Handles: rename to %r failed: %s", name, exc)


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
            "Consolidate Handles: segment.match → %s",
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
            "Consolidate Handles: set %s=%s failed: %s", name, frame, exc
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
                "Consolidate Handles: clear %s failed: %s", name, exc
            )
            ok = False
    return ok


def _list_attr(obj, name: str) -> list:
    try:
        return list(getattr(obj, name, None) or [])
    except Exception:  # noqa: BLE001
        return []


def _close_opened_sequence(logger) -> None:
    import flame

    try:
        ok = flame.execute_shortcut("Close Current Sequence")
        if ok is False:
            logger.warning(
                "Consolidate Handles: Close Current Sequence returned False"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: Close Current Sequence failed: %s", exc
        )


def _ensure_sequence_for_edit(obj, logger):
    """Open PyClip as sequence for Hard Commit / audio. Returns (host, opened)."""
    if dgpy_flame_types.is_sequence(obj):
        return obj, False
    open_fn = getattr(obj, "open_as_sequence", None)
    if not callable(open_fn):
        logger.warning(
            "Consolidate Handles: no open_as_sequence — edit may no-op"
        )
        return obj, False
    try:
        opened = open_fn()
        if opened is not None:
            logger.info(
                "Consolidate Handles: open_as_sequence for edit → %s",
                dgpy_flame_types.item_label(opened),
            )
            return opened, True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: open_as_sequence (edit) failed: %s", exc
        )
    return obj, False


def _delete_audio_on_host(host, logger) -> tuple[int, int]:
    """Delete audio_tracks on already-open host. Returns (ok, failed)."""
    import flame

    tracks = _list_attr(host, "audio_tracks")
    if not tracks:
        logger.info(
            "Consolidate Handles: no audio_tracks on %s",
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
            logger.warning(
                "Consolidate Handles: audio delete failed: %s", exc
            )
    remaining = len(_list_attr(host, "audio_tracks"))
    if ok and remaining:
        logger.warning(
            "Consolidate Handles: deleted=%s but %s audio_tracks remain on %s",
            ok,
            remaining,
            dgpy_flame_types.item_label(host),
        )
        failed += remaining
    elif ok:
        logger.info(
            "Consolidate Handles: deleted %s audio track(s) on %s",
            ok,
            dgpy_flame_types.item_label(host),
        )
    return ok, failed


def hard_commit_zero_handles(host, logger) -> str:
    """Bake selection to drop head/tail. Returns ok|failed."""
    _select_only(host, logger)
    if _run_shortcut(SHORTCUT_HARD_COMMIT, logger):
        logger.info(
            "Consolidate Handles: %s → %s",
            SHORTCUT_HARD_COMMIT,
            dgpy_flame_types.item_label(host),
        )
        return "ok"
    logger.warning(
        "Consolidate Handles: %s failed — try %s",
        SHORTCUT_HARD_COMMIT,
        SHORTCUT_HARD_COMMIT_SEQ,
    )
    _select_only(host, logger)
    if _run_shortcut(SHORTCUT_HARD_COMMIT_SEQ, logger):
        logger.info(
            "Consolidate Handles: %s → %s",
            SHORTCUT_HARD_COMMIT_SEQ,
            dgpy_flame_types.item_label(host),
        )
        return "ok"
    return "failed"


def post_subclip_cleanup(clip, logger) -> tuple[str, str, str]:
    """
    One open_as_sequence session: Hard Commit → audio delete → clear marks.

    Returns (handles_status, audio_status, marks_status).
    """
    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(
        logger=logger, label="Consolidate Handles"
    )
    host, opened = _ensure_sequence_for_edit(clip, logger)
    try:
        handles_status = hard_commit_zero_handles(host, logger)
        _a_ok, a_fail = _delete_audio_on_host(host, logger)
        audio_status = "failed" if a_fail else "ok"
        marks_status = "ok" if clear_keep_marks(host, logger) else "failed"
        return handles_status, audio_status, marks_status
    finally:
        if opened:
            _close_opened_sequence(logger)


def _deselect(logger) -> None:
    import flame

    try:
        flame.execute_shortcut(SHORTCUT_DESELECT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Consolidate Handles: Deselect failed: %s", exc)


def _select_only(clip, logger) -> None:
    import flame

    _deselect(logger)
    try:
        flame.media_panel.selected_entries = [clip]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Consolidate Handles: selected_entries failed: %s", exc)
    try:
        clip.selected = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Consolidate Handles: clip.selected failed: %s", exc)


def _open_as_sequence(clip, logger):
    """Return Timeline host for Create Subclip; prefer open_as_sequence result."""
    open_fn = getattr(clip, "open_as_sequence", None)
    if not callable(open_fn):
        return clip
    try:
        seq = open_fn()
        if seq is not None:
            logger.info(
                "Consolidate Handles: open_as_sequence → %s",
                dgpy_flame_types.item_label(seq),
            )
            return seq
    except Exception as exc:  # noqa: BLE001
        logger.warning("Consolidate Handles: open_as_sequence failed: %s", exc)
    return clip


def _run_shortcut(name: str, logger) -> bool:
    import flame

    try:
        ok = bool(flame.execute_shortcut(name))
        if not ok:
            logger.warning(
                "Consolidate Handles: shortcut %r returned False", name
            )
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: shortcut %r failed: %s", name, exc
        )
        return False


def _delete_clip(clip, logger, *, what: str) -> bool:
    import flame

    try:
        flame.delete(clip)
        logger.info(
            "Consolidate Handles: deleted %s %s",
            what,
            dgpy_flame_types.item_label(clip),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: delete %s failed: %s", what, exc
        )
        return False


def subclip_keep_range(clip, reel, start: int, end: int, name: str, logger):
    """
    Create Subclip from In/Out marks; Hard Commit + audio + clear marks; drop host.

    Returns (final_clip, marks_status, cut_status, audio_status, handles_status).
    """
    if clip is None:
        return None, "n/a", "n/a", "n/a", "n/a"

    marks_ok = set_keep_marks(clip, start, end, logger)
    if not marks_ok:
        logger.warning(
            "Consolidate Handles: marks failed — skip Create Subclip for %s",
            name,
        )
        return clip, "failed", "failed", "skip", "skip"

    host = _open_as_sequence(clip, logger)
    if host is not clip:
        set_keep_marks(host, start, end, logger)

    before = _reel_ids(reel)
    before.add(id(clip))
    before.add(id(host))

    _select_only(host, logger)
    if not _run_shortcut(SHORTCUT_CREATE_SUBCLIP, logger):
        return clip, "ok", "failed", "skip", "skip"

    sub = None
    for c in _reel_entries(reel):
        if id(c) not in before and _looks_like_clip(c):
            sub = c
            break
    if sub is None:
        logger.warning(
            "Consolidate Handles: Create Subclip produced no new clip on DG Sources"
        )
        return clip, "ok", "failed", "skip", "skip"

    _set_name(sub, name, logger)

    handles_status, audio_status, marks_final = post_subclip_cleanup(
        sub, logger
    )
    # Also clear marks on Media Panel entry after close
    if not clear_keep_marks(sub, logger):
        marks_final = "failed"

    if host is not sub:
        _delete_clip(host, logger, what="full-length host")
    if clip is not host and clip is not sub:
        _delete_clip(clip, logger, what="full-length original")

    return sub, marks_final, "ok", audio_status, handles_status


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

    Returns dict with status, marks, cut, audio, handles, message, label, clip.
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
        logger.info(
            "Consolidate Handles: fallback media_panel.copy for %s", label
        )
        clip = _copy_to_reel(owner_clip, reel, logger)
        if clip is not None:
            method = "media_panel.copy"

    if clip is None:
        return {
            "status": "skip",
            "marks": "n/a",
            "cut": "n/a",
            "audio": "n/a",
            "handles": "n/a",
            "message": "no copy source",
            "label": label,
        }

    _set_name(clip, label, logger)
    final, marks_status, cut_status, audio_status, handles_status = (
        subclip_keep_range(clip, reel, start, end, label, logger)
    )

    out_clip = final or clip
    reel_index = None
    try:
        for i, c in enumerate(list(getattr(reel, "clips", None) or [])):
            if c is out_clip or id(c) == id(out_clip):
                reel_index = i
                break
        if reel_index is None and out_clip is not None:
            # Fall back: last clip on reel (just created).
            clips = list(getattr(reel, "clips", None) or [])
            if clips:
                reel_index = len(clips) - 1
                out_clip = clips[reel_index]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: reel index resolve failed: %s", exc
        )

    # 0.6.8: status is always ok when a source clip existed; Replace gates on cut.
    return {
        "status": "ok",
        "marks": marks_status,
        "cut": cut_status,
        "audio": audio_status,
        "handles": handles_status,
        "hard_commit": handles_status,
        "message": f"keep {start}..{end} via {method}",
        "label": dgpy_flame_attr.clip_name(out_clip) or label,
        "clip": out_clip,
        "reel_index": reel_index,
        "clip_name": dgpy_flame_attr.clip_name(out_clip) or label,
    }


def create_merged_clips(
    *,
    merged: list,
    jobs: list[dict],
    reel,
    logger,
    rows: list[dict] | None = None,
) -> list[dict]:
    """Create one DG Sources clip per MergedRange. ``merged`` from merge_keep_ranges."""
    del rows  # 0.6.8 accepted rows; unused
    results = []
    for m in merged:
        skip = {
            "status": "skip",
            "marks": "n/a",
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
