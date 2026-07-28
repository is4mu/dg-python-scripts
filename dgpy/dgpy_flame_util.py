"""Flame host helpers. Unique basename for Flame hook scan."""

from __future__ import annotations

import dgpy_log

__version__ = "0.3.18"

RESCAN_SHORTCUT = "Rescan Python Hooks"
TIMELINE_TAB = "Timeline"


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


def rescan_python_hooks() -> bool:
    """
    Trigger Flame's Rescan Python Hooks via execute_shortcut.

    Returns True if Flame reported success. Safe no-op outside Flame.
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
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.exception("Rescan Python Hooks failed: %s", exc)
        return False
