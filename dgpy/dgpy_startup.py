"""Flame app_initialized: silent Update All for studio auto-update.

Hook basename must be unique (Flame loads every .py by filename).
"""

from __future__ import annotations

import os
import sys

_DGPY_ROOT = os.path.dirname(os.path.abspath(__file__))
if _DGPY_ROOT not in sys.path:
    sys.path.insert(0, _DGPY_ROOT)

__version__ = "0.3.11"

_RAN_THIS_SESSION = False
_DEFER_MS = 500


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
        logger.debug("startup auto-update: already ran this session")
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
    """Called after project Start. Schedules silent Update All."""
    try:
        import dgpy_log
        import dgpy_paths

        dgpy_paths.ensure_dgpy_on_sys_path()
        dgpy_log.setup().debug(
            "app_initialized(%r): schedule startup auto-update", project_name
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        from PySide6 import QtCore

        QtCore.QTimer.singleShot(_DEFER_MS, _run_quiet_update)
    except Exception:  # noqa: BLE001
        _run_quiet_update()
