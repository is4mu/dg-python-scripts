"""Flame app_initialized: silent Update All for studio auto-update.

Hook basename must be unique (Flame loads every .py by filename).
Defer with flame.schedule_idle_event (not QTimer) — see Autodesk watch_folder.py.
"""

from __future__ import annotations

import os
import sys

_DGPY_ROOT = os.path.dirname(os.path.abspath(__file__))
if _DGPY_ROOT not in sys.path:
    sys.path.insert(0, _DGPY_ROOT)

__version__ = "0.3.12"

_RAN_THIS_SESSION = False
_SCHEDULED = False
# Seconds — matches Autodesk python_utilities/examples/watch_folder.py
_IDLE_DELAY_SEC = 1


def _run_quiet_update() -> None:
    global _RAN_THIS_SESSION
    import dgpy_config
    import dgpy_local_inventory
    import dgpy_log
    import dgpy_manifest
    import dgpy_paths
    import dgpy_sync

    dgpy_paths.ensure_dgpy_on_sys_path()
    logger = dgpy_log.setup()

    if _RAN_THIS_SESSION:
        logger.info("startup auto-update: already ran this session")
        return
    _RAN_THIS_SESSION = True

    try:
        dgpy_local_inventory.ensure_seed_installed()
        cfg = dgpy_config.load()
        if not cfg.auto_update_on_start:
            logger.info("startup auto-update: skipped (disabled)")
            return

        root = cfg.resolved_install_root()
        logger.info(
            "startup auto-update: begin (channel=%s root=%s)",
            cfg.channel,
            root,
        )
        manifest = dgpy_manifest.fetch_manifest(cfg)
        rows = dgpy_sync.compare(manifest, root)
        targets = dgpy_sync.actionable(rows)
        if not targets:
            logger.info("startup auto-update: nothing to do")
            return

        packages = [r.remote_pkg for r in targets if r.remote_pkg is not None]
        packages = dgpy_sync.expand_dependencies(packages, manifest, rows)
        ids = [p.package_id for p in packages]
        logger.info("startup auto-update: installing %s", ", ".join(ids))

        result = dgpy_sync.run_phased_install(packages, root=root)
        if result.skipped:
            logger.warning("startup auto-update: skipped (%s)", result.skipped)
            return
        if result.error:
            logger.error(
                "startup auto-update: failed (%s); done=%s",
                result.error,
                result.done,
            )
            return

        logger.info(
            "startup auto-update: done=%s rescans=%s",
            result.done,
            result.rescans,
        )
        if any(pid in ("core", "manager") for pid in result.done):
            logger.info(
                "startup auto-update: core/manager updated; "
                "Flame restart recommended"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("startup auto-update: failed: %s", exc)


def app_initialized(project_name: str) -> None:
    """Called after project Start. Schedules silent Update All on idle."""
    global _SCHEDULED
    import dgpy_log
    import dgpy_paths

    dgpy_paths.ensure_dgpy_on_sys_path()
    logger = dgpy_log.setup()
    if _SCHEDULED:
        logger.info(
            "app_initialized(%r): startup auto-update already scheduled",
            project_name,
        )
        return
    _SCHEDULED = True
    logger.info(
        "app_initialized(%r): schedule startup auto-update (idle %ss)",
        project_name,
        _IDLE_DELAY_SEC,
    )

    try:
        import flame  # type: ignore

        flame.schedule_idle_event(_run_quiet_update, delay=_IDLE_DELAY_SEC)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "schedule_idle_event failed (%s); running startup auto-update now",
            exc,
        )
        _run_quiet_update()
