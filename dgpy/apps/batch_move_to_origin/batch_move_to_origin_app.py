"""Move selected Batch schematic nodes: first to (0,0), others keep relative pos."""

from __future__ import annotations

import dgpy_flame_attr
import dgpy_flame_types
import dgpy_gui
import dgpy_log

__version__ = "1.0.0"

_TITLE = "DG: Move to Origin"


def _schematic_nodes(selection) -> list:
    """Keep objects that expose schematic pos_x (Batch nodes)."""
    out = []
    for item in dgpy_flame_types.as_list(selection):
        if item is None:
            continue
        if hasattr(item, "pos_x") and hasattr(item, "pos_y"):
            out.append(item)
    return out


def _set_xy(node, x: int, y: int, logger) -> bool:
    try:
        node.pos_x = int(x)
        node.pos_y = int(y)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: failed to set pos on %s: %s",
            _TITLE,
            dgpy_flame_types.item_label(node),
            exc,
        )
        return False


def move_selection_to_origin(selection) -> None:
    logger = dgpy_log.setup()
    nodes = _schematic_nodes(selection)
    if not nodes:
        logger.warning("%s: no schematic nodes in selection", _TITLE)
        dgpy_gui.warning(
            None,
            _TITLE,
            "Select one or more Batch nodes first.",
        )
        return

    x0, y0 = dgpy_flame_attr.node_xy(nodes[0])
    dx = -x0
    dy = -y0
    moved = 0
    for node in nodes:
        x, y = dgpy_flame_attr.node_xy(node)
        if _set_xy(node, x + dx, y + dy, logger):
            moved += 1

    logger.info(
        "%s: moved %s node(s); anchor was (%s, %s) → (0, 0)",
        _TITLE,
        moved,
        x0,
        y0,
    )
