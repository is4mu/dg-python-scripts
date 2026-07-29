"""
Flame: DG: Sequence Render (+ hotkey-only DG: Render Sequence Reels).

Media Panel; logic in render_sequence_app.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.5"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    import render_sequence_app as app

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        targets = app.get_targets_from_selection(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Sequence Render isVisible error pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    visible = bool(targets)
    logger.debug(
        "DG: Sequence Render isVisible pending=%s targets=%s visible=%s",
        dgpy_flame_types.summarize(items),
        len(targets),
        visible,
    )
    return visible


def _resolve_execute_selection(selection) -> list:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    execute_items = dgpy_flame_types.as_list(selection)
    pending = _pending_selection
    _pending_selection = None
    if pending:
        if execute_items and dgpy_flame_types.summarize(
            pending
        ) != dgpy_flame_types.summarize(execute_items):
            logger.debug(
                "DG: Sequence Render using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run_selection(selection=None) -> None:
    import render_sequence_app as app

    app.render_from_selection(_resolve_execute_selection(selection))


def _scope_hotkey_hidden(_selection) -> bool:
    """Always hidden — Keyboard Shortcut Editor only."""
    return False


def _run_sequence_reels(selection=None) -> None:
    import render_sequence_app as app

    app.render_all_sequence_reels(selection)


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "sequence_render.selection",
                "name": "DG: Sequence Render",
                "isVisible": _scope_visible,
                "execute": _run_selection,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "sequence_render.reels_hotkey",
                "name": "DG: Render Sequence Reels",
                "isVisible": _scope_hotkey_hidden,
                "execute": _run_sequence_reels,
                "minimumVersion": "2025",
            },
        ]
    )
