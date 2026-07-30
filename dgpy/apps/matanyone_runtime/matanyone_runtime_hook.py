"""
Flame main menu: MatAnyone Runtime Setup / Remove.

Menu: DGpy → MatAnyone Runtime…
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "0.1.4"


def _setup(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    if paths.is_ready():
        if not dgpy_gui.confirm(
            None,
            "MatAnyone Runtime",
            f"Runtime already ready:\n{paths.runtime_root()}\n\n"
            "Reinstall (force)?",
        ):
            return
        force = True
    else:
        force = False
        if not dgpy_gui.confirm(
            None,
            "MatAnyone Runtime",
            "Install MatAnyone runtime now?\n\n"
            f"Target:\n{paths.runtime_root()}\n\n"
            "Needs network, git, NVIDIA GPU drivers, and several GB of disk.\n"
            "Python comes from Miniforge under the runtime folder "
            "(no system / Flame Python install).\n\n"
            "Typical time: about 10–40 minutes "
            "(Miniforge + PyTorch download).\n"
            "A progress window will show steps and live log.",
        ):
            return

    ok, err = progress.run_setup_with_progress(force=force)
    if not ok:
        logger.error("MatAnyone runtime setup failed: %s", err)
        dgpy_gui.error(
            None,
            "MatAnyone Runtime",
            f"Setup failed:\n{err}",
        )
        return

    dgpy_gui.info(
        None,
        "MatAnyone Runtime",
        f"Ready.\n\n{paths.runtime_root()}\npython={paths.resolve_python()}",
    )


def _remove(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_setup as setup

    logger = dgpy_log.setup()
    if not paths.runtime_root().exists():
        dgpy_gui.info(None, "MatAnyone Runtime", "Runtime folder not found.")
        return
    if not dgpy_gui.confirm(
        None,
        "MatAnyone Runtime",
        f"Delete runtime folder?\n\n{paths.runtime_root()}",
    ):
        return
    try:
        setup.remove_runtime(log=lambda m: logger.info("[matanyone_runtime] %s", m))
    except Exception as exc:  # noqa: BLE001
        logger.exception("MatAnyone runtime remove failed")
        dgpy_gui.error(None, "MatAnyone Runtime", f"Remove failed:\n{exc}")
        return
    dgpy_gui.info(None, "MatAnyone Runtime", "Removed.")


def get_main_menu_custom_ui_actions():
    return [
        {
            "hierarchy": ["DGpy"],
            "actions": [
                {
                    "name": "MatAnyone Runtime Setup…",
                    "order": 80,
                    "execute": _setup,
                    "minimumVersion": "2025",
                },
                {
                    "name": "MatAnyone Runtime Remove…",
                    "order": 81,
                    "execute": _remove,
                    "minimumVersion": "2025",
                },
            ],
        }
    ]
