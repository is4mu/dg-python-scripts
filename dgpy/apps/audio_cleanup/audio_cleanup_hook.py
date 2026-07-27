"""
Flame: DG2: Audio → Only 1-2 / 3-4 / Delete Mute / Delete All.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.2"

_pending_selection: list | None = None


def _capture(selection) -> list:
    global _pending_selection
    import dgpy_flame_types

    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    return items


def _resolve(selection) -> list:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    execute_items = dgpy_flame_types.as_list(selection)
    pending = _pending_selection
    _pending_selection = None
    if pending:
        if execute_items and dgpy_flame_types.summarize(
            pending
        ) != dgpy_flame_types.summarize(execute_items):
            dgpy_log.setup().debug(
                "DG2: Audio Cleanup using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _scope(pred_name: str, selection) -> bool:
    import audio_cleanup_app as app
    import dgpy_log

    items = _capture(selection)
    logger = dgpy_log.setup()
    try:
        pred = getattr(app, pred_name)
        visible = bool(pred(items, logger=logger))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audio Cleanup %s isVisible error: %s", pred_name, exc)
        return False
    logger.debug("Audio Cleanup %s isVisible=%s", pred_name, visible)
    return visible


def _scope_multi(selection) -> bool:
    return _scope("has_multi_audio", selection)


def _scope_mute(selection) -> bool:
    return _scope("has_mute_audio", selection)


def _scope_any(selection) -> bool:
    return _scope("has_any_audio", selection)


def _run(fn_name: str, selection=None) -> None:
    import audio_cleanup_app as app

    getattr(app, fn_name)(_resolve(selection))


def _run_only_12(selection=None) -> None:
    _run("only_1_2", selection)


def _run_only_34(selection=None) -> None:
    _run("only_3_4", selection)


def _run_delete_mute(selection=None) -> None:
    _run("delete_mute", selection)


def _run_delete_all(selection=None) -> None:
    _run("delete_all", selection)


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "audio.only_1_2",
                "name": "Only 1-2 Track",
                "isVisible": _scope_multi,
                "execute": _run_only_12,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "audio.only_3_4",
                "name": "Only 3-4 Track",
                "isVisible": _scope_multi,
                "execute": _run_only_34,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "audio.delete_mute",
                "name": "Delete Mute Tracks",
                "isVisible": _scope_mute,
                "execute": _run_delete_mute,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "audio.delete_all",
                "name": "Delete All Audio Tracks",
                "isVisible": _scope_any,
                "execute": _run_delete_all,
                "minimumVersion": "2025",
            },
        ]
    )
