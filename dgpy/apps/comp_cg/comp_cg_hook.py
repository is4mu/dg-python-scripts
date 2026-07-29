"""
Flame: DG: Clip → Comp CG Clips.

Media Panel entry; logic in comp_cg_app.
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

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        clips = dgpy_flame_types.get_clips(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Clip Comp CG Clips isVisible error pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    visible = len(clips) >= 2
    logger.debug(
        "DG: Clip Comp CG Clips isVisible pending=%s clips=%s visible=%s",
        dgpy_flame_types.summarize(items),
        len(clips),
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
                "DG: Clip Comp CG Clips using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import comp_cg_app as app

    app.run_comp_cg(_resolve_execute_selection(selection))


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "clip.comp_cg",
                "name": "Comp CG Clips",
                "isVisible": _scope_visible,
                "execute": _run,
                "minimumVersion": "2025",
            }
        ]
    )
