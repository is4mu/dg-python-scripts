"""Shared helpers for Consolidate Handles (no Flame-app imports)."""

from __future__ import annotations

__version__ = "0.8.0"

TITLE = "Consolidate Handles"
SHORTCUT_CLOSE_CURRENT = "Close Current Sequence"
SHORTCUT_DESELECT = "Deselect"


def is_skip_tw(rng) -> bool:
    """True for SkipTW-like objects (duck-typed; survives module reload)."""
    return (
        getattr(rng, "reason", None) is not None
        and not hasattr(rng, "tw_mode")
    )


def unwrap(obj):
    """Unwrap PyAttribute via get_value when present."""
    if obj is None:
        return None
    if hasattr(obj, "get_value"):
        try:
            return obj.get_value()
        except Exception:  # noqa: BLE001
            return obj
    return obj


def run_shortcut(name: str, logger) -> bool:
    import flame

    try:
        ok = bool(flame.execute_shortcut(name))
        if not ok:
            logger.warning("%s: shortcut %r returned False", TITLE, name)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: shortcut %r failed: %s", TITLE, name, exc)
        return False


def close_current_sequence(logger) -> None:
    """sequence.close() does not exist — Clip Mgmt shortcut."""
    logger.info("%s: Close Current Sequence", TITLE)
    run_shortcut(SHORTCUT_CLOSE_CURRENT, logger)


def deselect_all(logger) -> None:
    try:
        run_shortcut(SHORTCUT_DESELECT, logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: Deselect failed: %s", TITLE, exc)


def set_selected(obj, value: bool, logger, *, what: str) -> bool:
    try:
        obj.selected = value
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "%s: %s.selected=%s failed: %s (type=%s)",
            TITLE,
            what,
            value,
            exc,
            type(obj).__name__,
        )
        return False


def status_counts(results: list[dict]) -> str:
    """Format ok/failed/skipped line for Results report."""
    ok_n = sum(1 for r in results if r.get("status") == "ok")
    fail_n = sum(1 for r in results if r.get("status") == "failed")
    skip_n = sum(1 for r in results if r.get("status") == "skip")
    return f"ok={ok_n}  failed={fail_n}  skipped={skip_n}"
