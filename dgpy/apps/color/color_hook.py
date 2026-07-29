"""
Flame: DG: Color (set item.colour from palette).

Contexts: Media Panel, Timeline, Batch.
Menu: DG: Color → <color name> (hierarchy ["DG: Color"])

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

__version__ = "1.0.5"

# Redesigned 10-color palette (muted 和色-inspired). Menu names: English short.
COLORS: dict[str, tuple[float, float, float]] = {
    "Rose": (0.580, 0.320, 0.430),  # 蘇芳〜牡丹
    "Red": (0.560, 0.220, 0.230),  # 紅海老茶
    "Orange": (0.600, 0.360, 0.230),  # 代赭
    "Gold": (0.560, 0.460, 0.220),  # 黄土
    "Green": (0.150, 0.450, 0.320),  # 常磐
    "Teal": (0.100, 0.400, 0.430),  # 青磁
    "Blue": (0.110, 0.330, 0.510),  # 縹
    "Purple": (0.470, 0.320, 0.500),  # 古代紫
    "Black": (0.085, 0.085, 0.065),  # 墨（暖黒）
    "Gray": (0.280, 0.290, 0.290),  # 鼠
}

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
        logger.warning("DG: Color isVisible error: %s", exc)
        return False
    logger.debug("DG: Color isVisible pending=%s", _summarize(items))
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
                "DG: Color using isVisible context %s (execute had %s)",
                _summarize(pending),
                _summarize(execute_items),
            )
        return pending
    return execute_items


def _set_colour(items: list, rgb: tuple[float, float, float]) -> int:
    ok = 0
    for item in items:
        try:
            item.colour = rgb
            ok += 1
        except Exception:  # noqa: BLE001
            import dgpy_log

            dgpy_log.setup().warning(
                "DG: Color failed on %s", _item_label(item), exc_info=True
            )
    return ok


def _make_set_color(name: str, rgb: tuple[float, float, float]):
    def _execute(selection=None):
        import dgpy_log

        items = _resolve_execute_selection(selection)
        if not items:
            return
        n = _set_colour(items, rgb)
        dgpy_log.setup().info("DG: Color set %s on %s item(s)", name, n)

    return _execute


def _color_actions_media() -> list[dict]:
    import dgpy_menu_layout

    raw = []
    for name, rgb in COLORS.items():
        raw.append(
            {
                "layout_key": f"color.{name}",
                "name": name,
                "isVisible": _scope_visible,
                "execute": _make_set_color(name, rgb),
                "minimumVersion": "2025",
            }
        )
    return dgpy_menu_layout.build_media_panel(raw)


def _color_actions_other() -> list[dict]:
    """Timeline / Batch: keep local order until layout covers those contexts."""
    actions = []
    for idx, (name, rgb) in enumerate(COLORS.items()):
        actions.append(
            {
                "name": name,
                "order": idx,
                "isVisible": _scope_visible,
                "execute": _make_set_color(name, rgb),
                "minimumVersion": "2025",
            }
        )
    return [
        {
            "hierarchy": ["DG: Color"],
            "order": 10,
            "actions": actions,
        }
    ]


def get_media_panel_custom_ui_actions():
    return _color_actions_media()


def get_timeline_custom_ui_actions():
    return _color_actions_other()


def get_batch_custom_ui_actions():
    return _color_actions_other()
