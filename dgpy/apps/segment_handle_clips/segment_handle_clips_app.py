"""Consolidate Handles — probe report + optional Create on Sources."""

from __future__ import annotations

from pathlib import Path

import dgpy_log

from segment_handle_clips_create import (
    create_merged_clips,
    find_or_create_sources_reel,
)
from segment_handle_clips_dialog import (
    ProbeReportDialog,
    ask_probe_options,
    run_results_dialog,
)
from segment_handle_clips_merge import merge_keep_ranges, resolve_source_path
from segment_handle_clips_replace import (
    clear_job_segment_selection,
    replace_merged_results,
)
from segment_handle_clips_selection import resolve_segment_jobs
from segment_handle_clips_tw import (
    probe_source_range,
    record_duration_frames,
    source_in_out,
)
from segment_handle_clips_util import TITLE, __version__, is_skip_tw


def _fmt_num(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        if abs(val - round(val)) < 1e-6:
            return str(int(round(val)))
        return f"{val:.4g}"
    return str(val)


def _probe_row(job: dict, handles: int, logger) -> dict:
    seg = job["segment"]
    name = job["clip_name"]
    owner = job.get("owner_clip")
    sin, sout = source_in_out(seg)
    rec = record_duration_frames(seg)

    row = {
        "name": name,
        "source_path": resolve_source_path(seg, owner, logger=logger),
        "seg_in": sin,
        "seg_out": sout,
        "rec_dur": rec,
        "tw": "—",
        "keep_start": None,
        "keep_end": None,
        "keep_frames": None,
        "notes": "",
        "skip": False,
    }

    rng, _detail, _raw = probe_source_range(
        seg, head=handles, tail=handles, logger=logger
    )
    if is_skip_tw(rng):
        row["skip"] = True
        row["tw"] = "skip"
        row["notes"] = str(rng.reason)
        return row

    row["tw"] = rng.tw_mode
    row["keep_start"] = rng.source_start
    row["keep_end"] = rng.source_end
    row["keep_frames"] = rng.source_frames
    notes = []
    if row["source_path"] is None:
        notes.append("no source path")
    if rng.speed is not None:
        notes.append(f"speed={rng.speed:.6g}")
    row["notes"] = " | ".join(notes)
    return row


def _format_report(
    rows: list[dict],
    *,
    handles: int,
    merge_gap: int,
    merged: list,
) -> str:
    lines = [
        f"{TITLE} — handles={handles}F merge_gap={merge_gap}F",
        f"segments={len(rows)}  "
        f"ok={sum(1 for r in rows if not r['skip'])}  "
        f"skip={sum(1 for r in rows if r['skip'])}  "
        f"merged={len(merged)}",
        "",
        (
            f"{'#':>3}  {'name':<28}  {'tw':<8}  "
            f"{'seg IN':>8}  {'seg OUT':>8}  {'rec':>5}  "
            f"{'keep IN':>8}  {'keep OUT':>8}  {'keep F':>6}  notes"
        ),
        "-" * 120,
    ]
    for i, r in enumerate(rows, start=1):
        lines.append(
            f"{i:3d}  {r['name'][:28]:<28}  {r['tw']:<8}  "
            f"{_fmt_num(r['seg_in']):>8}  {_fmt_num(r['seg_out']):>8}  "
            f"{_fmt_num(r['rec_dur']):>5}  "
            f"{_fmt_num(r['keep_start']):>8}  {_fmt_num(r['keep_end']):>8}  "
            f"{_fmt_num(r['keep_frames']):>6}  {r['notes']}"
        )

    lines.append("")
    lines.append(
        f"=== Merged clips (path key, merge_gap={merge_gap}) ==="
    )
    lines.append(
        f"{'#':>3}  {'label':<36}  "
        f"{'keep IN':>8}  {'keep OUT':>8}  {'keep F':>6}  "
        f"{'segs':>4}  from#  notes"
    )
    lines.append("-" * 120)
    for i, m in enumerate(merged, start=1):
        from_s = ",".join(str(x) for x in m.seg_indices)
        label = m.label[:36]
        lines.append(
            f"{i:3d}  {label:<36}  "
            f"{m.keep_start:8d}  {m.keep_end:8d}  {m.keep_frames:6d}  "
            f"{len(m.seg_indices):4d}  {from_s}  {m.notes}"
        )
        if m.source_path:
            full = m.source_path
            if Path(full).name != label or len(full) > 36:
                lines.append(f"     path: {full}")

    lines.append("")
    lines.append(
        "Close = done.  "
        "Create on Sources → then Replace Media on this same window."
    )
    return "\n".join(lines)


def _format_create_section(
    *,
    reel_status: str,
    results: list[dict],
) -> str:
    lines = [
        "",
        "=== Create on Sources ===",
        f"  Sources reel: {reel_status}",
    ]
    ok_n = sum(1 for r in results if r.get("status") == "ok")
    fail_n = sum(1 for r in results if r.get("status") == "failed")
    skip_n = sum(1 for r in results if r.get("status") == "skip")
    lines.append(f"  ok={ok_n}  failed={fail_n}  skipped={skip_n}")
    for i, r in enumerate(results, start=1):
        lines.append(
            f"  #{i} {r.get('label', '?'):<28}  "
            f"status={r.get('status')} "
            f"cut={r.get('cut')} audio={r.get('audio')} "
            f"handles={r.get('handles')}  "
            f"{r.get('message', '')}"
        )
    return "\n".join(lines)


def _format_replace_section(results: list[dict]) -> str:
    lines = ["", "=== Replace Media ==="]
    ok_n = sum(1 for r in results if r.get("status") == "ok")
    fail_n = sum(1 for r in results if r.get("status") == "failed")
    skip_n = sum(1 for r in results if r.get("status") == "skip")
    lines.append(f"  ok={ok_n}  failed={fail_n}  skipped={skip_n}")
    for i, r in enumerate(results, start=1):
        msg = r.get("message") or ""
        extra = f"  {msg}" if msg and msg != "ok" else ""
        lines.append(
            f"  #{i} {r.get('label', '?'):<28}  "
            f"replace={r.get('status')}{extra}"
        )
    return "\n".join(lines)


def _count_replaceable_segments(results: list[dict], merged: list) -> int:
    n = 0
    for i, r in enumerate(results):
        if i >= len(merged):
            break
        if r.get("status") == "ok" and r.get("cut") == "ok":
            n += len(merged[i].seg_indices)
    return n


def run_probe(selection) -> None:
    logger = dgpy_log.setup()
    jobs = resolve_segment_jobs(selection, logger=logger)
    if not jobs:
        run_results_dialog(
            "No Primary-track segments found.\n\n"
            "Select a segment, clip/sequence, or reel "
            "(Folder/Library are ignored; Gaps skipped).",
            show_create=False,
        )
        return

    opts = ask_probe_options(segment_count=len(jobs))
    if opts is None:
        logger.info("%s: cancelled (dialog)", TITLE)
        return
    handles, merge_gap = opts

    rows = [_probe_row(job, handles, logger) for job in jobs]
    merged = merge_keep_ranges(rows, merge_gap=merge_gap)
    report = _format_report(
        rows, handles=handles, merge_gap=merge_gap, merged=merged
    )
    for line in report.splitlines():
        logger.info("%s: %s", TITLE, line)

    state: dict = {"results": None, "reel": None}

    def on_create(dlg: ProbeReportDialog) -> None:
        if not merged:
            msg = (
                "\n=== Create on Sources ===\n"
                "  Nothing to create (no merged ranges)."
            )
            logger.info("%s:%s", TITLE, msg.replace("\n", " "))
            dlg.append_text(msg)
            dlg.set_phase_done()
            return

        anchor = jobs[0].get("owner_clip") or jobs[0].get("segment")
        reel, reel_status = find_or_create_sources_reel(anchor, logger)
        if reel is None:
            msg = (
                "\n=== Create on Sources ===\n"
                "  Could not find or create Sources reel."
            )
            logger.warning("%s: Sources reel failed", TITLE)
            dlg.append_text(msg)
            dlg.set_phase_done()
            return

        results = create_merged_clips(
            merged=merged,
            jobs=jobs,
            reel=reel,
            logger=logger,
        )
        clear_job_segment_selection(jobs, logger)

        create_section = _format_create_section(
            reel_status=reel_status, results=results
        )
        for line in create_section.splitlines():
            if line:
                logger.info("%s: %s", TITLE, line)
        dlg.append_text(create_section)

        state["results"] = results
        state["reel"] = reel

        replace_n = _count_replaceable_segments(results, merged)
        if replace_n <= 0:
            dlg.append_text("\n  Nothing to Replace Media.")
            dlg.set_phase_done()
            logger.info("%s: nothing to Replace Media", TITLE)
            return

        dlg.append_text(
            f"\n  Ready to Replace Media ({replace_n} segment(s)).\n"
            f"  Press Replace Media on this window (no extra confirm)."
        )
        dlg.set_phase_after_create(can_replace=True, on_replace=on_replace)

    def on_replace(dlg: ProbeReportDialog) -> None:
        results = state.get("results")
        reel = state.get("reel")
        if not results or reel is None:
            dlg.append_text(
                "\n=== Replace Media ===\n  Missing Create results."
            )
            dlg.set_phase_done()
            return

        replace_results = replace_merged_results(
            results=results,
            merged=merged,
            jobs=jobs,
            reel=reel,
            logger=logger,
        )
        replace_section = _format_replace_section(replace_results)
        for line in replace_section.splitlines():
            if line:
                logger.info("%s: %s", TITLE, line)
        dlg.append_text(replace_section)
        dlg.set_phase_done()

    run_results_dialog(report, on_create=on_create, show_create=True)
