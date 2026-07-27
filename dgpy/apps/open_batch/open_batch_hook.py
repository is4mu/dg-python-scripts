"""
Flame: DG2: Batch → Open.

Media Panel: open selected PyBatch, or all batch_groups under selected PyDesktop.
After open(), set expanded=False (legacy behavior).

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

__version__ = "1.0.6"

_pending_selection: list | None = None


def _is_closed(batch) -> bool:
    return not bool(getattr(batch, "opened", True))


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    try:
        items = dgpy_flame_types.as_list(selection)
        _pending_selection = items
        batches = dgpy_flame_types.get_batch_groups(items)
        visible = any(_is_closed(b) for b in batches)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG2: Batch Open isVisible error: %s",
            exc,
        )
        return False
    logger.debug(
        "DG2: Batch Open isVisible pending=%s closed=%s",
        dgpy_flame_types.summarize(items),
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
                "DG2: Batch Open using isVisible context %s (execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _open_batches(selection=None) -> None:
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    items = _resolve_execute_selection(selection)
    batches = [
        b for b in dgpy_flame_types.get_batch_groups(items) if _is_closed(b)
    ]
    if not batches:
        logger.info("DG2: Batch Open: nothing closed to open")
        return

    ok = 0
    failed = 0
    for batch in batches:
        try:
            batch.open()
            batch.expanded = False
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "DG2: Batch Open failed for %s: %s",
                dgpy_flame_types.item_label(batch),
                exc,
            )
    logger.info("DG2: Batch Open: opened %s (failed %s)", ok, failed)


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "batch.open",
                "name": "Open",
                "isVisible": _scope_visible,
                "execute": _open_batches,
                "minimumVersion": "2025",
            }
        ]
    )
