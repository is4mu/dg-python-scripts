"""Flame host helpers. Unique basename for Flame hook scan."""

from __future__ import annotations

from typing import Any

import dgpy_log

__version__ = "0.3.32"

RESCAN_SHORTCUT = "Rescan Python Hooks"
TIMELINE_TAB = "Timeline"
SHORTCUT_CLOSE_CURRENT = "Close Current Sequence"


def ensure_timeline_tab(*, logger=None, label: str = "") -> bool:
    """Switch Flame UI to Timeline before version/track/segment/audio edits.

    Mutations on versions, tracks, segments, and audio tracks often no-op
    unless the Timeline tab is active. Call this at the start of such jobs.
    """
    log = logger or dgpy_log.get_logger()
    prefix = f"{label}: " if label else ""
    try:
        import flame  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.warning("%sflame module unavailable; skip Timeline tab: %s", prefix, exc)
        return False
    try:
        flame.set_current_tab(TIMELINE_TAB)
        log.debug("%sset_current_tab(%s)", prefix, TIMELINE_TAB)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "%sset_current_tab(%s) failed: %s",
            prefix,
            TIMELINE_TAB,
            exc,
        )
        return False


def execute_shortcut(name: str, *, logger=None, label: str = "") -> bool:
    """Run ``flame.execute_shortcut``; treat False as failure."""
    log = logger or dgpy_log.get_logger()
    prefix = f"{label}: " if label else ""
    try:
        import flame  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.warning("%sflame unavailable; skip shortcut %r: %s", prefix, name, exc)
        return False
    try:
        ok = bool(flame.execute_shortcut(name))
        if not ok:
            log.warning("%sshortcut %r returned False", prefix, name)
        return ok
    except Exception as exc:  # noqa: BLE001
        log.warning("%sshortcut %r failed: %s", prefix, name, exc)
        return False


def close_current_sequence(*, logger=None, label: str = "") -> bool:
    """Close Timeline tab. ``sequence.close()`` does not exist."""
    log = logger or dgpy_log.get_logger()
    prefix = f"{label}: " if label else ""
    log.info("%sClose Current Sequence", prefix)
    return execute_shortcut(
        SHORTCUT_CLOSE_CURRENT, logger=log, label=label.rstrip(": ")
    )


def open_clip_as_sequence(
    obj, *, logger=None, label: str = ""
) -> tuple[Any, bool]:
    """
    Open a PyClip as Timeline sequence when needed.

    Returns ``(host, opened)``. If ``obj`` is already a sequence, returns
    ``(obj, False)`` and does not open. Always use the returned host.
    """
    import dgpy_flame_types

    log = logger or dgpy_log.get_logger()
    prefix = f"{label}: " if label else ""
    if obj is None:
        return None, False
    if dgpy_flame_types.is_sequence(obj):
        return obj, False
    open_fn = getattr(obj, "open_as_sequence", None)
    if not callable(open_fn):
        return obj, False
    try:
        opened = open_fn()
        if opened is not None:
            log.info(
                "%sopen_as_sequence → %s",
                prefix,
                dgpy_flame_types.item_label(opened),
            )
            return opened, True
    except Exception as exc:  # noqa: BLE001
        log.warning("%sopen_as_sequence failed: %s", prefix, exc)
    return obj, False


class PendingSelection:
    """isVisible → execute selection bridge (Media Panel context)."""

    def __init__(self) -> None:
        self._items: list | None = None

    def capture(self, selection) -> list:
        import dgpy_flame_types

        items = dgpy_flame_types.as_list(selection)
        self._items = items
        return items

    def resolve(self, selection, *, logger=None, label: str = "") -> list:
        import dgpy_flame_types

        log = logger or dgpy_log.get_logger()
        execute_items = dgpy_flame_types.as_list(selection)
        pending = self._items
        self._items = None
        if not pending:
            return execute_items
        if execute_items and dgpy_flame_types.summarize(
            pending
        ) != dgpy_flame_types.summarize(execute_items):
            log.debug(
                "%s using isVisible context %s (execute had %s)",
                label or "pending",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending

    def clear(self) -> None:
        self._items = None


def rescan_python_hooks(*, process_events: bool = False) -> bool:
    """
    Trigger Flame's Rescan Python Hooks via execute_shortcut.

    Returns True if Flame reported success. Safe no-op outside Flame.
    When ``process_events`` is True, pump the Qt event loop after Rescan
    (hooks may reload UI).
    """
    logger = dgpy_log.get_logger()
    try:
        import flame  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("flame module unavailable; skip rescan: %s", exc)
        return False

    try:
        ok = bool(flame.execute_shortcut(RESCAN_SHORTCUT))
        if ok:
            logger.info("Executed shortcut: %s", RESCAN_SHORTCUT)
        else:
            logger.warning(
                "execute_shortcut(%r) returned False",
                RESCAN_SHORTCUT,
            )
        if process_events:
            try:
                from PySide6 import QtWidgets

                QtWidgets.QApplication.processEvents()
            except Exception:  # noqa: BLE001
                pass
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.exception("Rescan Python Hooks failed: %s", exc)
        return False
