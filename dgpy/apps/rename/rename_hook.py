"""
Flame: DG: Rename (batch rename dialog).

Contexts (v1.1): Media Panel, Timeline, Batch, Action.
Menu: context menu root → DG: Rename (hierarchy [])

Selection note (Flame quirk):
  isVisible(selection) receives the right-click context object.
  execute(selection) often receives the panel's selected entries instead.
  We keep a short-lived pending selection from isVisible and prefer it in execute.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Right-click context captured in isVisible; consumed by execute.
_pending_selection: list | None = None


def _as_list(selection) -> list:
    if not selection:
        return []
    if isinstance(selection, (list, tuple)):
        return list(selection)
    return [selection]


def _item_label(item) -> str:
    typ = type(item).__name__
    try:
        n = getattr(item, "name", None)
        if n is not None and hasattr(n, "get_value"):
            return f"{typ}({n.get_value()!r})"
        if n is not None:
            return f"{typ}({n!r})"
    except Exception:  # noqa: BLE001
        pass
    return typ


def _summarize(items: list) -> str:
    if not items:
        return "(empty)"
    labels = [_item_label(i) for i in items[:8]]
    extra = f" …(+{len(items) - 8})" if len(items) > 8 else ""
    return f"n={len(items)} [{', '.join(labels)}{extra}]"


def _scope_visible(selection) -> bool:
    """Show when Flame gives a context target; remember it for execute."""
    global _pending_selection
    import dgpy_log

    logger = dgpy_log.setup()
    try:
        items = _as_list(selection)
        _pending_selection = items
        visible = bool(items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DG: Rename isVisible error: %s", exc)
        return False
    logger.debug("DG: Rename isVisible pending=%s", _summarize(items))
    return visible


def _resolve_execute_selection(selection) -> list:
    """Prefer isVisible pending (right-click target); else execute arg."""
    global _pending_selection
    import dgpy_log

    logger = dgpy_log.setup()
    execute_items = _as_list(selection)
    pending = _pending_selection
    _pending_selection = None

    if pending:
        if execute_items and _summarize(pending) != _summarize(execute_items):
            logger.debug(
                "DG: Rename using isVisible context %s (execute had %s)",
                _summarize(pending),
                _summarize(execute_items),
            )
        return pending
    return execute_items


def _open_rename(selection=None):
    import rename_dialog

    items = _resolve_execute_selection(selection)
    try:
        rename_dialog.open_rename(items)
    except Exception as exc:  # noqa: BLE001
        import dgpy_gui
        import dgpy_log

        dgpy_log.setup().exception("DG: Rename failed: %s", exc)
        dgpy_gui.warning(None, "DG: Rename", f"Failed to open:\n{exc}")


def _rename_actions_other() -> list[dict]:
    return [
        {
            "hierarchy": [],
            "order": 20,
            "actions": [
                {
                    "name": "DG: Rename",
                    "order": 20,
                    "isVisible": _scope_visible,
                    "execute": _open_rename,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "rename.root",
                "name": "DG: Rename",
                "isVisible": _scope_visible,
                "execute": _open_rename,
                "minimumVersion": "2025",
            }
        ]
    )


def get_timeline_custom_ui_actions():
    return _rename_actions_other()


def get_batch_custom_ui_actions():
    return _rename_actions_other()


def get_action_custom_ui_actions():
    return _rename_actions_other()
