"""Replace Media: Sources clips → original sequence segments (Console pattern)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_types
import dgpy_flame_util

from segment_handle_clips_util import TITLE, __version__  # noqa: F401


SHORTCUT_REPLACE_MEDIA = "Replace Media"
SHORTCUT_CLOSE_CURRENT = "Close Current Sequence"


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


def _unwrap(obj):
    if obj is None:
        return None
    if hasattr(obj, "get_value"):
        try:
            return obj.get_value()
        except Exception:  # noqa: BLE001
            return obj
    return obj


def _fmt_sel(obj) -> str:
    if obj is None:
        return "None"
    try:
        return f"{type(obj).__name__}({dgpy_flame_types.item_label(obj)!r})"
    except Exception:  # noqa: BLE001
        return repr(obj)


def _set_selected(obj, value: bool, logger, *, what: str) -> bool:
    try:
        obj.selected = value
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: %s.selected=%s failed: %s (type=%s)",
            what,
            value,
            exc,
            type(obj).__name__,
        )
        return False


def clear_job_segment_selection(jobs: list[dict], logger) -> None:
    """Clear segment.selected on all probe jobs (Replace precondition)."""
    n = 0
    for job in jobs:
        seg = job.get("segment")
        if seg is None:
            continue
        if _set_selected(seg, False, logger, what="segment"):
            n += 1
    logger.info(
        "Consolidate Handles: cleared selected on %s segment(s)", n
    )


def resolve_sequence(segment, owner_clip, logger):
    """Find editorial sequence. Prefer owner / parent walk (no open_as_sequence)."""
    if owner_clip is not None and dgpy_flame_types.is_sequence(owner_clip):
        return owner_clip

    obj = segment
    for _ in range(12):
        if obj is None:
            break
        if dgpy_flame_types.is_sequence(obj):
            return obj
        parent = _unwrap(getattr(obj, "parent", None))
        if parent is None or parent is obj:
            break
        obj = parent

    if owner_clip is not None and (
        dgpy_flame_types.is_clip(owner_clip)
        or dgpy_flame_types.is_sequence(owner_clip)
    ):
        return owner_clip
    return None


def _open_sequence(seq, logger) -> Any:
    """Console pattern: sequence.open() (not open_as_sequence)."""
    if seq is None:
        return None
    open_fn = getattr(seq, "open", None)
    if callable(open_fn):
        try:
            open_fn()
            logger.info(
                "Consolidate Handles: sequence.open() → %s",
                dgpy_flame_types.item_label(seq),
            )
            return seq
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Consolidate Handles: sequence.open() failed: %s", exc
            )
    # Last resort (prefer open)
    open_as = getattr(seq, "open_as_sequence", None)
    if callable(open_as):
        try:
            opened = open_as()
            if opened is not None:
                logger.info(
                    "Consolidate Handles: open_as_sequence fallback → %s",
                    dgpy_flame_types.item_label(opened),
                )
                return opened
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Consolidate Handles: open_as_sequence fallback failed: %s",
                exc,
            )
    return seq


def _close_current_sequence(logger) -> None:
    """sequence.close() does not exist — use Clip Mgmt shortcut."""
    logger.info("Consolidate Handles: Close Current Sequence")
    _run_shortcut(SHORTCUT_CLOSE_CURRENT, logger)


def _log_selection(logger, tag: str, *, segment=None, clip=None) -> None:
    import flame

    if segment is not None or clip is not None:
        logger.info(
            "Consolidate Handles: [%s] intended segment=%s clip=%s",
            tag,
            _fmt_sel(segment),
            _fmt_sel(clip),
        )
    try:
        entries = list(getattr(flame.media_panel, "selected_entries", None) or [])
    except Exception as exc:  # noqa: BLE001
        entries = []
        logger.warning(
            "Consolidate Handles: [%s] selected_entries failed: %s", tag, exc
        )
    logger.info(
        "Consolidate Handles: [%s] media_panel.selected_entries (%s) → %s",
        tag,
        len(entries),
        ", ".join(_fmt_sel(e) for e in entries) or "(empty)",
    )
    try:
        tl = getattr(flame, "timeline", None)
        tclip = getattr(tl, "clip", None) if tl is not None else None
        if tclip is not None:
            logger.info(
                "Consolidate Handles: [%s] timeline.clip → %s",
                tag,
                _fmt_sel(tclip),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Consolidate Handles: [%s] timeline.clip failed: %s", tag, exc
        )


def resolve_sources_clip(
    reel,
    *,
    reel_index: int | None,
    clip_name: str | None,
    logger,
):
    """Fresh Media Panel PyClip from Sources reel (Console: reel.clips[n])."""
    import dgpy_flame_attr

    clips = list(getattr(reel, "clips", None) or [])
    if reel_index is not None and 0 <= int(reel_index) < len(clips):
        c = clips[int(reel_index)]
        logger.info(
            "Consolidate Handles: Sources resolve index=%s → %s",
            reel_index,
            dgpy_flame_types.item_label(c),
        )
        return c

    want = (clip_name or "").strip().strip("'\"")
    if want:
        matches = []
        for c in clips:
            name = dgpy_flame_attr.clip_name(c)
            if name == want:
                matches.append(c)
        if len(matches) == 1:
            logger.info(
                "Consolidate Handles: Sources resolve name=%r → %s",
                want,
                dgpy_flame_types.item_label(matches[0]),
            )
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                "Consolidate Handles: Sources name=%r matches %s clips — "
                "need reel_index",
                want,
                len(matches),
            )
        else:
            logger.warning(
                "Consolidate Handles: Sources name=%r not on reel (%s clips)",
                want,
                len(clips),
            )
    else:
        logger.warning(
            "Consolidate Handles: Sources resolve missing index/name "
            "(reel has %s clips)",
            len(clips),
        )
    return None


def replace_one_segment(
    *,
    segment,
    sources_clip,
    logger,
    seg_label: str,
) -> dict:
    """
    Host sequence must already be open.
    segment.selected=True; clip.selected=True; Replace Media; selected=False.
    """
    if segment is None or sources_clip is None:
        return {
            "status": "skip",
            "label": seg_label,
            "message": "missing segment or Sources clip",
        }

    logger.info(
        "Consolidate Handles: Replace Media — seg=%s sources=%s",
        seg_label,
        dgpy_flame_types.item_label(sources_clip),
    )

    ok_seg = _set_selected(segment, True, logger, what="segment")
    ok_clip = _set_selected(sources_clip, True, logger, what="sources clip")
    _log_selection(
        logger, "before Replace Media", segment=segment, clip=sources_clip
    )

    if not (ok_seg and ok_clip):
        _set_selected(segment, False, logger, what="segment")
        return {
            "status": "failed",
            "label": seg_label,
            "message": "select failed (segment or Sources)",
        }

    if not _run_shortcut(SHORTCUT_REPLACE_MEDIA, logger):
        _set_selected(segment, False, logger, what="segment")
        _log_selection(logger, "after Replace Media (failed)")
        return {
            "status": "failed",
            "label": seg_label,
            "message": "Replace Media shortcut failed",
        }

    _set_selected(segment, False, logger, what="segment")
    _log_selection(logger, "after Replace Media")
    return {
        "status": "ok",
        "label": seg_label,
        "message": "Replace Media",
    }


def replace_merged_results(
    *,
    results: list[dict],
    merged: list,
    jobs: list[dict],
    reel,
    logger,
) -> list[dict]:
    """
    For each successful Create result, Replace Media onto each source segment.

    Sources clip is re-resolved from ``reel`` (not the stale Create handle).
    Segments reuse ``jobs[].segment``.

    Work is grouped by host sequence: open once → replace all → Close Current.
    """
    # Collect work items: (seq_key, seq, segment, sources, label)
    pending: list[tuple[int | None, Any, Any, Any, str]] = []
    early: list[dict] = []
    n = min(len(results), len(merged))
    for i in range(n):
        r = results[i]
        m = merged[i]
        if r.get("status") != "ok" or r.get("cut") != "ok":
            early.append(
                {
                    "status": "skip",
                    "label": r.get("label") or m.label,
                    "message": "create not ready for Replace",
                    "seg_indices": list(m.seg_indices),
                }
            )
            continue

        sources = resolve_sources_clip(
            reel,
            reel_index=r.get("reel_index"),
            clip_name=r.get("clip_name") or r.get("label"),
            logger=logger,
        )
        if sources is None:
            early.append(
                {
                    "status": "failed",
                    "label": r.get("label") or m.label,
                    "message": "Sources clip not found on reel",
                    "seg_indices": list(m.seg_indices),
                }
            )
            continue

        for seg_i in m.seg_indices:
            idx = seg_i - 1
            if idx < 0 or idx >= len(jobs):
                early.append(
                    {
                        "status": "skip",
                        "label": f"#{seg_i}",
                        "message": "bad seg index",
                    }
                )
                continue
            job = jobs[idx]
            seg = job.get("segment")
            owner = job.get("owner_clip")
            name = job.get("clip_name") or f"#{seg_i}"
            label = f"#{seg_i} {name}"
            seq = resolve_sequence(seg, owner, logger)
            if seq is None:
                early.append(
                    {
                        "status": "skip",
                        "label": label,
                        "message": "no host sequence",
                    }
                )
                continue
            pending.append((id(seq), seq, seg, sources, label))

    # Group by host sequence (first-seen order).
    group_order: list[int] = []
    groups: dict[int, dict] = {}
    for seq_key, seq, seg, sources, label in pending:
        assert seq_key is not None
        if seq_key not in groups:
            groups[seq_key] = {"seq": seq, "items": []}
            group_order.append(seq_key)
        groups[seq_key]["items"].append((seg, sources, label))

    out: list[dict] = list(early)
    dgpy_flame_util.ensure_timeline_tab(
        logger=logger, label="Consolidate Handles"
    )

    for seq_key in group_order:
        group = groups[seq_key]
        seq = group["seq"]
        items = group["items"]
        logger.info(
            "Consolidate Handles: Replace group host=%s (%s segment(s))",
            dgpy_flame_types.item_label(seq),
            len(items),
        )
        _open_sequence(seq, logger)
        for seg, sources, label in items:
            out.append(
                replace_one_segment(
                    segment=seg,
                    sources_clip=sources,
                    logger=logger,
                    seg_label=label,
                )
            )
        _close_current_sequence(logger)

    return out
