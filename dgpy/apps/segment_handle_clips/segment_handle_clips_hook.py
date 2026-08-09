"""
Flame: DG: Segment → Consolidate Handles…

Media Panel + Timeline. Probe report, then optional Create on DG Sources.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from segment_handle_clips_util import TITLE, __version__  # noqa: E402

_pending_selection: list | None = None

_MENU = "Consolidate Handles…"


def _reload_pkg() -> None:
    """Rescan often leaves stale submodule imports; reload on execute."""
    import importlib
    import sys as _sys

    # Leaves before dependents so `from … import` in app sees fresh modules.
    preferred = [
        "segment_handle_clips_util",
        "segment_handle_clips_tw",
        "segment_handle_clips_merge",
        "segment_handle_clips_selection",
        "segment_handle_clips_dialog",
        "segment_handle_clips_create",
        "segment_handle_clips_replace",
        "segment_handle_clips_app",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for name in preferred:
        if name in _sys.modules:
            ordered.append(name)
            seen.add(name)
    for name in sorted(_sys.modules):
        if name.startswith("segment_handle_clips_") and name not in seen:
            ordered.append(name)
    for name in ordered:
        mod = _sys.modules.get(name)
        if mod is None:
            continue
        try:
            importlib.reload(mod)
        except Exception:  # noqa: BLE001
            pass


def _as_list(selection) -> list:
    import dgpy_flame_types

    return dgpy_flame_types.as_list(selection)


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    from segment_handle_clips_selection import has_jobs

    logger = dgpy_log.setup()
    items = _as_list(selection)
    _pending_selection = items
    try:
        visible = has_jobs(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s isVisible error pending=%s: %s",
            TITLE,
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
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
                "%s using isVisible context %s (execute had %s)",
                TITLE,
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import dgpy_gui
    import dgpy_log

    _reload_pkg()
    import segment_handle_clips_app as app

    logger = dgpy_log.setup()
    try:
        app.run_probe(_resolve_execute_selection(selection))
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", TITLE, exc)
        dgpy_gui.warning(None, TITLE, f"Failed:\n{exc}")


def _media_actions() -> list[dict]:
    return [
        {
            "layout_key": "segment.consolidate_handles",
            "name": _MENU,
            "isVisible": _scope_visible,
            "execute": _run,
            "minimumVersion": "2025",
        }
    ]


def _timeline_group() -> list[dict]:
    return [
        {
            "hierarchy": ["DG: Segment"],
            "order": 43,
            "actions": [
                {
                    "name": _MENU,
                    "order": 50,
                    "separator": "above",
                    "isVisible": _scope_visible,
                    "execute": _run,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(_media_actions())


def get_timeline_custom_ui_actions():
    return _timeline_group()
