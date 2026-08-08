"""Replace Media: Sources clips → original sequence segments (shortcut)."""

from __future__ import annotations

from typing import Any

import dgpy_flame_types
import dgpy_flame_util

from segment_handle_clips_util import (
    TITLE,
    __version__,
    close_current_sequence,
    deselect_all,
    run_shortcut,
    set_selected,
    unwrap,
)

SHORTCUT_REPLACE_MEDIA = "Replace Media"


def _fmt_sel(obj) -> str:
    if obj is None:
        return "None"
    try:
        return f"{type(obj).__name__}({dgpy_flame_types.item_label(obj)!r})"
    except Exception:  # noqa: BLE001
        return repr(obj)


def clear_job_segment_selection(jobs: list[dict], logger) -> None:
    """Clear segment.selected on all probe jobs (Replace precondition)."""
    n = 0
    for job in jobs:
        seg = job.get("segment")
        if seg is None:
            continue
        if set_selected(seg, False, logger, what="segment"):
            n += 1
    logger.info("%s: cleared selected on %s segment(s)", TITLE, n)


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
        parent = unwrap(getattr(obj, "parent", None))
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
                "%s: sequence.open() → %s",
                TITLE,
                dgpy_flame_types.item_label(seq),
            )
            return seq
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: sequence.open() failed: %s", TITLE, exc)
    open_as = getattr(seq, "open_as_sequence", None)
    if callable(open_as):
        try:
            opened = open_as()
            if opened is not None:
                logger.info(
                    "%s: open_as_sequence fallback → %s",
                    TITLE,
                    dgpy_flame_types.item_label(opened),
                )
                return opened
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: open_as_sequence fallback failed: %s", TITLE, exc
            )
    return seq


def _log_selection(logger, tag: str, *, segment=None, clip=None) -> None:
    import flame

    if segment is not None or clip is not None:
        logger.debug(
            "%s: [%s] intended segment=%s clip=%s",
            TITLE,
            tag,
            _fmt_sel(segment),
            _fmt_sel(clip),
        )
    try:
        entries = list(getattr(flame.media_panel, "selected_entries", None) or [])
    except Exception as exc:  # noqa: BLE001
        entries = []
        logger.debug(
            "%s: [%s] selected_entries failed: %s", TITLE, tag, exc
        )
    logger.debug(
        "%s: [%s] media_panel.selected_entries (%s) → %s",
        TITLE,
        tag,
        len(entries),
        ", ".join(_fmt_sel(e) for e in entries) or "(empty)",
    )
    try:
        tl = getattr(flame, "timeline", None)
        tclip = getattr(tl, "clip", None) if tl is not None else None
        if tclip is not None:
            logger.debug(
                "%s: [%s] timeline.clip → %s",
                TITLE,
                tag,
                _fmt_sel(tclip),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: [%s] timeline.clip failed: %s", TITLE, tag, exc)


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
            "%s: Sources resolve index=%s → %s",
            TITLE,
            reel_index,
            dgpy_flame_types.item_label(c),
        )
        return c

    want = (clip_name or "").strip().strip("'\"")
    if want:
        matches = [
            c for c in clips if dgpy_flame_attr.clip_name(c) == want
        ]
        if len(matches) == 1:
            logger.info(
                "%s: Sources resolve name=%r → %s",
                TITLE,
                want,
                dgpy_flame_types.item_label(matches[0]),
            )
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                "%s: Sources name=%r matches %s clips — need reel_index",
                TITLE,
                want,
                len(matches),
            )
        else:
            logger.warning(
                "%s: Sources name=%r not on reel (%s clips)",
                TITLE,
                want,
                len(clips),
            )
    else:
        logger.warning(
            "%s: Sources resolve missing index/name (reel has %s clips)",
            TITLE,
            len(clips),
        )
    return None


def _clear_replace_selection(segment, sources_clip, logger) -> None:
    set_selected(segment, False, logger, what="segment")
    set_selected(sources_clip, False, logger, what="sources clip")


def replace_one_segment(
    *,
    segment,
    sources_clip,
    logger,
    seg_label: str,
) -> dict:
    """
    Host sequence must already be open.

    Deselect → segment.selected + Sources selected → shortcut Replace Media.
    No confirm dialog for Replace Media.
    """
    if segment is None or sources_clip is None:
        return {
            "status": "skip",
            "label": seg_label,
            "message": "missing segment or Sources clip",
        }

    logger.info(
        "%s: Replace Media — seg=%s sources=%s",
        TITLE,
        seg_label,
        dgpy_flame_types.item_label(sources_clip),
    )

    deselect_all(logger)
    ok_seg = set_selected(segment, True, logger, what="segment")
    ok_clip = set_selected(sources_clip, True, logger, what="sources clip")
    _log_selection(
        logger, "before Replace Media", segment=segment, clip=sources_clip
    )

    if not (ok_seg and ok_clip):
        _clear_replace_selection(segment, sources_clip, logger)
        return {
            "status": "failed",
            "label": seg_label,
            "message": "select failed (segment or Sources)",
        }

    if not run_shortcut(SHORTCUT_REPLACE_MEDIA, logger):
        _clear_replace_selection(segment, sources_clip, logger)
        _log_selection(logger, "after Replace Media (failed)")
        return {
            "status": "failed",
            "label": seg_label,
            "message": "Replace Media shortcut failed",
        }

    _clear_replace_selection(segment, sources_clip, logger)
    _log_selection(logger, "after Replace Media")
    return {"status": "ok", "label": seg_label, "message": "ok"}


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
    Work is grouped by host sequence: open once → replace all → Close Current.
    """
    pending: list[tuple[int, Any, Any, Any, str]] = []
    early: list[dict] = []
    n = min(len(results), len(merged))
    for i in range(n):
        r = results[i]
        m = merged[i]
        if r.get("status") != "ok":
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

    group_order: list[int] = []
    groups: dict[int, dict] = {}
    for seq_key, seq, seg, sources, label in pending:
        if seq_key not in groups:
            groups[seq_key] = {"seq": seq, "items": []}
            group_order.append(seq_key)
        groups[seq_key]["items"].append((seg, sources, label))

    out: list[dict] = list(early)
    dgpy_flame_util.ensure_timeline_tab(logger=logger, label=TITLE)

    for seq_key in group_order:
        group = groups[seq_key]
        seq = group["seq"]
        items = group["items"]
        logger.info(
            "%s: Replace group host=%s (%s segment(s))",
            TITLE,
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
        close_current_sequence(logger)

    return out
