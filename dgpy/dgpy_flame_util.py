"""Flame host helpers. Unique basename for Flame hook scan."""

from __future__ import annotations

import dgpy_log

__version__ = "0.3.0"

RESCAN_SHORTCUT = "Rescan Python Hooks"


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
