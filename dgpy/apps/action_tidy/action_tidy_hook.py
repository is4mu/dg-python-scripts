"""
Flame: DG: Segment — Clean Up / Toggle Fit / Strip Expressions.

Media Panel + Timeline.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "0.3.3"

_pending_selection: list | None = None


def _as_list(selection) -> list:
    import dgpy_flame_types

    return dgpy_flame_types.as_list(selection)


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    from action_tidy_selection import has_segments

    logger = dgpy_log.setup()
    items = _as_list(selection)
    _pending_selection = items
    try:
        visible = has_segments(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Segment isVisible error pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    logger.debug(
        "DG: Segment isVisible pending=%s visible=%s",
        dgpy_flame_types.summarize(items),
        visible,
    )
    return visible


def _resolve_execute_selection(selection) -> list:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    execute_items = _as_list(selection)
    pending = _pending_selection
    _pending_selection = None
    if pending:
        if execute_items and dgpy_flame_types.summarize(
            pending
        ) != dgpy_flame_types.summarize(execute_items):
            logger.debug(
                "DG: Segment using isVisible context %s (execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _summarize(result) -> str:
    return (
        f"OK: {result.ok}  Failed: {result.failed}  Skipped: {result.skipped}"
    )


def _run_job(selection, *, title: str, confirm_msg: str, runner) -> None:
    import dgpy_gui
    import dgpy_log
    from action_tidy_selection import resolve_segments

    logger = dgpy_log.setup()
    try:
        items = _resolve_execute_selection(selection)
        segments = resolve_segments(items, logger=logger)
        if not segments:
            dgpy_gui.warning(
                None,
                title,
                "No segments found.\n\n"
                "Select segments, or a clip/sequence/reel "
                "(Gaps are skipped).",
            )
            return

        n = len(segments)
        ok = dgpy_gui.confirm(
            None,
            title,
            f"{confirm_msg}\n\nSegments: {n}",
        )
        if not ok:
            return

        result = runner(segments)
        summary = _summarize(result)
        if result.failed:
            detail = "\n".join(result.messages[-12:])
            dgpy_gui.warning(
                None,
                title,
                f"Done with errors.\n\n{summary}\n\n{detail}",
            )
        else:
            dgpy_gui.info(None, title, f"{summary}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed", title)
        dgpy_gui.warning(None, title, f"Failed:\n{exc}")


def _execute_clean(selection=None):
    from action_tidy_job import run_cleanup

    _run_job(
        selection,
        title="Clean Up Action",
        confirm_msg=(
            "Apply «Clean Up Action»?\n\n"
            "• No Action → studio template as-is\n"
            "• Existing Action → clean schematic, keep axis transform"
        ),
        runner=lambda segs: run_cleanup(segs, template_id="clean"),
    )


def _execute_fit(selection=None):
    from action_tidy_job import run_cleanup

    _run_job(
        selection,
        title="Clean Up Action (Fit)",
        confirm_msg=(
            "Apply «Clean Up Action (Fit)»?\n\n"
            "• No Action → studio template as-is\n"
            "• Existing Action → clean schematic, keep axis transform"
        ),
        runner=lambda segs: run_cleanup(segs, template_id="fit"),
    )


def _execute_toggle(selection=None):
    from action_tidy_job import run_toggle_fit

    _run_job(
        selection,
        title="Toggle Fit Method",
        confirm_msg=(
            "Toggle fill↔contain on axis_rsz Expression only "
            "(max ↔ min)?\n\n"
            "Segments without Action or Expression are skipped."
        ),
        runner=run_toggle_fit,
    )


def _execute_strip(selection=None):
    from action_tidy_job import run_strip_expressions

    _run_job(
        selection,
        title="Strip Expressions",
        confirm_msg=(
            "Remove Expression lines inside axis_rsz?\n\n"
            "Segments without Action or Expression are skipped."
        ),
        runner=run_strip_expressions,
    )


def _action_entries() -> list[dict]:
    return [
        {
            "layout_key": "segment.cleanup",
            "name": "Clean Up Action",
            "isVisible": _scope_visible,
            "execute": _execute_clean,
            "minimumVersion": "2025",
        },
        {
            "layout_key": "segment.cleanup_fit",
            "name": "Clean Up Action (Fit)",
            "isVisible": _scope_visible,
            "execute": _execute_fit,
            "minimumVersion": "2025",
        },
        {
            "layout_key": "segment.toggle_fit",
            "name": "Toggle Fit Method",
            "isVisible": _scope_visible,
            "execute": _execute_toggle,
            "minimumVersion": "2025",
        },
        {
            "layout_key": "segment.strip_expr",
            "name": "Strip Expressions",
            "isVisible": _scope_visible,
            "execute": _execute_strip,
            "minimumVersion": "2025",
        },
    ]


def _timeline_actions() -> list[dict]:
    return [
        {
            "name": "Clean Up Action",
            "order": 10,
            "isVisible": _scope_visible,
            "execute": _execute_clean,
            "minimumVersion": "2025",
        },
        {
            "name": "Clean Up Action (Fit)",
            "order": 20,
            "separator": "below",
            "isVisible": _scope_visible,
            "execute": _execute_fit,
            "minimumVersion": "2025",
        },
        {
            "name": "Toggle Fit Method",
            "order": 30,
            "isVisible": _scope_visible,
            "execute": _execute_toggle,
            "minimumVersion": "2025",
        },
        {
            "name": "Strip Expressions",
            "order": 40,
            "isVisible": _scope_visible,
            "execute": _execute_strip,
            "minimumVersion": "2025",
        },
    ]


def _timeline_group() -> list[dict]:
    return [
        {
            "hierarchy": ["DG: Segment"],
            "order": 43,
            "actions": _timeline_actions(),
        }
    ]


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(_action_entries())


def get_timeline_custom_ui_actions():
    return _timeline_group()
