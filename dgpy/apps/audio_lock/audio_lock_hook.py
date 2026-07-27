"""
Flame: DG2: Audio → Lock / Unlock Audio Tracks.
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
                "DG2: Audio Lock using isVisible context %s (execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _scope_lock(selection) -> bool:
    import audio_lock_app as app
    import dgpy_log

    items = _capture(selection)
    try:
        visible = app.has_unlocked_audio(items, logger=dgpy_log.setup())
    except Exception as exc:  # noqa: BLE001
        dgpy_log.setup().warning("Lock Audio isVisible error: %s", exc)
        return False
    dgpy_log.setup().debug("Lock Audio Tracks isVisible=%s", visible)
    return visible


def _scope_unlock(selection) -> bool:
    import audio_lock_app as app
    import dgpy_log

    items = _capture(selection)
    try:
        visible = app.has_locked_audio(items, logger=dgpy_log.setup())
    except Exception as exc:  # noqa: BLE001
        dgpy_log.setup().warning("Unlock Audio isVisible error: %s", exc)
        return False
    dgpy_log.setup().debug("Unlock Audio Tracks isVisible=%s", visible)
    return visible


def _run_lock(selection=None) -> None:
    import audio_lock_app as app

    app.lock_tracks(_resolve(selection))


def _run_unlock(selection=None) -> None:
    import audio_lock_app as app

    app.unlock_tracks(_resolve(selection))


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "audio.lock",
                "name": "Lock Audio Tracks",
                "isVisible": _scope_lock,
                "execute": _run_lock,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "audio.unlock",
                "name": "Unlock Audio Tracks",
                "isVisible": _scope_unlock,
                "execute": _run_unlock,
                "minimumVersion": "2025",
            },
        ]
    )
