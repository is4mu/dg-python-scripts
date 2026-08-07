"""
Flame: DG: Clip → MatAnyone…

Media Panel; logic in matanyone_app.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "0.2.1"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    import matanyone_selection as sel

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        clips = sel.direct_clips(items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MatAnyone isVisible error: %s", exc)
        return False
    visible = bool(clips)
    logger.debug(
        "MatAnyone isVisible pending=%s clips=%s visible=%s",
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
                "MatAnyone using isVisible context %s (execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_app as app

    try:
        app.run_from_selection(_resolve_execute_selection(selection))
    except Exception as exc:  # noqa: BLE001
        dgpy_log.setup().exception("MatAnyone menu failed")
        dgpy_gui.error(None, "MatAnyone", f"Failed:\n{exc}")


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "clip.matanyone",
                "name": "MatAnyone…",
                "isVisible": _scope_visible,
                "execute": _run,
                "minimumVersion": "2025",
            },
        ]
    )
