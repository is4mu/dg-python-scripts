"""Create Sources reel clips (match + Subclip + Hard Commit + strip audio)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_attr
import dgpy_flame_types

from segment_handle_clips_util import (
    TITLE,
    __version__,
    close_current_sequence,
    deselect_all,
    run_shortcut,
    set_selected,
)

DEFAULT_REEL = "Sources"
SHORTCUT_CREATE_SUBCLIP = "Create Subclip"
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


def _reel_clips(reel) -> list:
    try:
        return list(getattr(reel, "clips", None) or [])
    except Exception:  # noqa: BLE001
        return []


def _reel_index_of(reel, clip) -> int | None:
    if clip is None:
        return None
    try:
        for i, c in enumerate(_reel_clips(reel)):
            if c is clip or id(c) == id(clip):
                return i
    except Exception:  # noqa: BLE001
        return None
    return None


def _find_new_on_reel(reel, before: set[int]):
    """Return (clip, reel_index_in_clips_or_None) for first new reel entry."""
    clips = _reel_clips(reel)
    for i, c in enumerate(clips):
        if id(c) not in before and _looks_like_clip(c):
            return c, i
    for c in _reel_entries(reel):
        if id(c) not in before and _looks_like_clip(c):
            return c, _reel_index_of(reel, c)
    return None, None


def post_subclip_cleanup(clip, logger) -> tuple[str, str]:
    """
    One open_as_sequence session: Hard Commit → audio delete → clear marks.

    Returns (hard_commit_status, audio_status). Mark clear is log-only.
    """
    import dgpy_flame_util

    dgpy_flame_util.ensure_timeline_tab(logger=logger, label=TITLE)
    host, opened = _open_as_sequence(clip, logger, for_edit=True)
    try:
        hard = hard_commit_zero_handles(host, logger)
        _a_ok, a_fail = _delete_audio_on_host(host, logger)
        audio_status = "failed" if a_fail else "ok"
        clear_keep_marks(host, logger)
        return hard, audio_status
    finally:
        if opened:
            close_current_sequence(logger)


def _deselect(logger) -> None:
    deselect_all(logger)


def _select_only(clip, logger) -> None:
    import flame

    _deselect(logger)
    try:
        flame.media_panel.selected_entries = [clip]
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: selected_entries failed: %s", TITLE, exc)
    set_selected(clip, True, logger, what="clip")


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


def _resolve_host_remove_indices(
    reel,
    *,
    source_idx: int | None,
    host_idx: int | None,
    reel_index: int | None,
    logger,
) -> list[int]:
    """
    Indices of full-length hosts to delete after Create Subclip.

    Subclip may append (source_idx still valid) or insert at/before the
    source (full-length shifts to source_idx+1). Never delete reel_index.
    """
    n = len(_reel_clips(reel))
    remove: list[int] = []
    for base in (source_idx, host_idx):
        if base is None:
            continue
        for j in (base, base + 1):
            if j < 0 or j >= n:
                continue
            if reel_index is not None and j == reel_index:
                continue
            remove.append(j)
    out = sorted(set(remove))
    logger.info(
        "%s: host remove indices=%s (source_idx=%s host_idx=%s sub=%s n=%s)",
        TITLE,
        out,
        source_idx,
        host_idx,
        reel_index,
        n,
    )
    return out


def _delete_indices_adjust(
    reel, remove: list[int], reel_index: int | None, logger
) -> int | None:
    """Delete reel.clips at indices (desc); adjust reel_index when lower slots go."""
    idx = reel_index
    for j in sorted(set(remove), reverse=True):
        clips = _reel_clips(reel)
        if j < 0 or j >= len(clips):
            continue
        if idx is not None and j == idx:
            logger.warning(
                "%s: skip delete at reel_index=%s (would remove subclip)",
                TITLE,
                j,
            )
            continue
        if not _delete_clip(clips[j], logger, what=f"reel.clips[{j}]"):
            continue
        if idx is not None and j < idx:
            idx -= 1
    return idx


def subclip_keep_range(clip, reel, start: int, end: int, name: str, logger):
    """
    Create Subclip from In/Out marks; Hard Commit + audio; drop full-length hosts.

    Returns (final_clip, cut_status, audio_status, hard_commit_status, reel_index).
    ``reel_index`` is taken at Create Subclip time. Full-length delete indices
    are captured **before** Subclip (post-Subclip PyClip id match is unreliable).
    """
    if clip is None:
        return None, "n/a", "n/a", "n/a", None

    if not set_keep_marks(clip, start, end, logger):
        logger.warning(
            "%s: marks failed — skip Create Subclip for %s", TITLE, name
        )
        return clip, "failed", "n/a", "n/a", None

    # Capture while match/copy handle still matches reel.clips[i].
    source_idx = _reel_index_of(reel, clip)
    if source_idx is None:
        logger.warning(
            "%s: source not found on Sources before Subclip (%s)",
            TITLE,
            dgpy_flame_types.item_label(clip),
        )

    host, host_opened = _open_as_sequence(clip, logger)
    host_idx: int | None = None
    sub = None
    reel_index: int | None = None
    try:
        if host is not clip:
            set_keep_marks(host, start, end, logger)

        host_idx = _reel_index_of(reel, host)

        before = _reel_ids(reel)
        before.add(id(clip))
        before.add(id(host))

        _select_only(host, logger)
        if not run_shortcut(SHORTCUT_CREATE_SUBCLIP, logger):
            return clip, "failed", "n/a", "n/a", None

        sub, reel_index = _find_new_on_reel(reel, before)
        if sub is None:
            logger.warning(
                "%s: Create Subclip produced no new clip on Sources", TITLE
            )
            return clip, "failed", "n/a", "n/a", None

        logger.info(
            "%s: Create Subclip → %s reel_index=%s "
            "(source_idx=%s host_idx=%s)",
            TITLE,
            dgpy_flame_types.item_label(sub),
            reel_index,
            source_idx,
            host_idx,
        )
        _set_name(sub, name, logger)
    finally:
        if host_opened:
            close_current_sequence(logger)

    if sub is None:
        return clip, "failed", "n/a", "n/a", None

    # After Subclip: insert can shift the full-length host (source_idx+1).
    # Delete hosts BEFORE Hard Commit cleanup so indices stay stable.
    remove = _resolve_host_remove_indices(
        reel,
        source_idx=source_idx,
        host_idx=host_idx,
        reel_index=reel_index,
        logger=logger,
    )
    if not remove:
        logger.warning(
            "%s: no full-length indices to delete "
            "(source_idx=%s host_idx=%s sub_index=%s)",
            TITLE,
            source_idx,
            host_idx,
            reel_index,
        )

    reel_index = _delete_indices_adjust(reel, remove, reel_index, logger)

    fresh = None
    if reel_index is not None:
        clips_now = _reel_clips(reel)
        if 0 <= reel_index < len(clips_now):
            fresh = clips_now[reel_index]
    target = fresh or sub

    hard_status, audio_status = post_subclip_cleanup(target, logger)

    # Hard Commit may refresh the PyClip — re-read by index.
    if reel_index is not None:
        clips_now = _reel_clips(reel)
        if 0 <= reel_index < len(clips_now):
            target = clips_now[reel_index]
    return (
        target,
        "ok",
        audio_status,
        hard_status,
        reel_index,
    )


def finalize_reel_indices(results: list[dict], reel, logger) -> None:
    """
    After a Create batch, re-bind reel_index by clip_name FIFO on reel.clips.

    Survives index drift from deletes / Hard Commit. Same-name clips are
    assigned in creation order.
    """
    clips = _reel_clips(reel)
    queues: dict[str, list[int]] = {}
    for i, c in enumerate(clips):
        n = (dgpy_flame_attr.clip_name(c) or "").strip()
        queues.setdefault(n, []).append(i)

    for r in results:
        if r.get("cut") != "ok":
            continue
        name = (r.get("clip_name") or r.get("label") or "").strip()
        q = queues.get(name) or []
        if not q:
            logger.warning(
                "%s: finalize — no reel clip named %r", TITLE, name
            )
            r["reel_index"] = None
            r["status"] = "failed"
            msg = r.get("message") or ""
            if "(no reel_index)" not in msg:
                r["message"] = f"{msg} (no reel_index)".strip()
            continue
        idx = q.pop(0)
        r["reel_index"] = idx
        r["clip"] = clips[idx]
        r["status"] = "ok"
        r["clip_name"] = dgpy_flame_attr.clip_name(clips[idx]) or name
        r["label"] = r["clip_name"]
        logger.info(
            "%s: finalize reel_index=%s → %s",
            TITLE,
            idx,
            dgpy_flame_types.item_label(clips[idx]),
        )


def _result_dict(
    *,
    status: str,
    cut: str,
    audio: str,
    hard_commit: str,
    message: str,
    label: str,
    clip=None,
    reel_index: int | None = None,
    clip_name: str | None = None,
) -> dict:
    return {
        "status": status,
        "cut": cut,
        "audio": audio,
        "hard_commit": hard_commit,
        "message": message,
        "label": label,
        "clip": clip,
        "reel_index": reel_index,
        "clip_name": clip_name or label,
    }


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
    Match/copy, Subclip, Hard Commit handles, strip audio.

    Provisional ``status`` follows cut; ``finalize_reel_indices`` sets final
    status after the batch.
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
        return _result_dict(
            status="skip",
            cut="n/a",
            audio="n/a",
            hard_commit="n/a",
            message="no copy source",
            label=label,
        )

    _set_name(clip, label, logger)
    final, cut_status, audio_status, hard_status, reel_index = (
        subclip_keep_range(clip, reel, start, end, label, logger)
    )

    if cut_status != "ok":
        return _result_dict(
            status="failed",
            cut=cut_status,
            audio=audio_status,
            hard_commit=hard_status,
            message=f"keep {start}..{end} via {method}",
            label=label,
            clip=final,
            reel_index=reel_index,
        )

    name = dgpy_flame_attr.clip_name(final) if final is not None else label
    return _result_dict(
        status="ok",
        cut=cut_status,
        audio=audio_status,
        hard_commit=hard_status,
        message=f"keep {start}..{end} via {method}",
        label=name or label,
        clip=final,
        reel_index=reel_index,
        clip_name=name or label,
    )


def create_merged_clips(
    *,
    merged: list,
    jobs: list[dict],
    reel,
    logger,
) -> list[dict]:
    """Create one Sources clip per MergedRange, then finalize reel_index."""
    results = []
    for m in merged:
        if not m.seg_indices:
            results.append(
                _result_dict(
                    status="skip",
                    cut="n/a",
                    audio="n/a",
                    hard_commit="n/a",
                    message="empty from#",
                    label=m.label,
                )
            )
            continue
        idx0 = m.seg_indices[0] - 1
        if idx0 < 0 or idx0 >= len(jobs):
            results.append(
                _result_dict(
                    status="skip",
                    cut="n/a",
                    audio="n/a",
                    hard_commit="n/a",
                    message=f"bad from# {m.seg_indices[0]}",
                    label=m.label,
                )
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
    finalize_reel_indices(results, reel, logger)
    return results
