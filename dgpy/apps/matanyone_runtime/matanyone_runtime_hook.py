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

__version__ = "0.3.0"


def _setup(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    paths.migrate_legacy_runtime_if_needed(
        log=lambda m: logger.info("[matanyone_runtime] %s", m)
    )
    if progress.remove_is_running():
        dgpy_gui.warning(
            None,
            "MatAnyone Runtime",
            "Remove is still running. Wait until it finishes before Setup.",
        )
        return
    if progress.setup_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone Runtime",
            "Setup is already running.\n"
            "The progress window was brought to the front "
            "(Flame remains usable).",
        )
        progress.start_setup_nonblocking(force=False)
        return

    if paths.is_ready():
        if not dgpy_gui.confirm(
            None,
            "MatAnyone Runtime",
            f"MatAnyone 2 runtime already ready:\n{paths.runtime_root()}\n\n"
            "Reinstall (force)?",
        ):
            return
        force = True
    else:
        force = paths.needs_matanyone2_upgrade()
        upgrade_note = ""
        if force:
            upgrade_note = (
                "\n\nAn older MatAnyone (v1) runtime was detected.\n"
                "Setup will replace it with MatAnyone 2."
            )
        if not dgpy_gui.confirm(
            None,
            "MatAnyone Runtime",
            "Install MatAnyone 2 runtime now?\n\n"
            f"Target:\n{paths.runtime_root()}\n\n"
            "Needs network, git, NVIDIA GPU drivers, and several GB of disk.\n"
            "Python comes from Miniforge under the runtime folder "
            "(Python ≥ 3.10; no system / Flame Python install).\n\n"
            "Typical time: about 10–40 minutes "
            "(Miniforge + PyTorch download).\n"
            "A non-modal progress window opens — Flame stays usable."
            f"{upgrade_note}",
        ):
            return

    started = progress.start_setup_nonblocking(force=force)
    if not started:
        logger.info("MatAnyone 2 setup already in progress — raised existing window")
        return
    logger.info("MatAnyone 2 runtime setup started (non-modal; Flame stays usable)")


def _remove(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    if progress.setup_is_running():
        dgpy_gui.warning(
            None,
            "MatAnyone Runtime",
            "Setup is still running. Wait until it finishes before Remove.",
        )
        return
    if progress.remove_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone Runtime",
            "Remove is already running.\n"
            "The progress window was brought to the front.",
        )
        progress.start_remove_nonblocking()
        return

    paths.migrate_legacy_runtime_if_needed(
        log=lambda m: logger.info("[matanyone_runtime] %s", m)
    )
    # Also offer remove if only legacy leftovers exist.
    primary = paths.runtime_root()
    legacy_left = [p for p in paths.legacy_runtime_roots() if p.exists()]
    if not primary.exists() and not legacy_left:
        dgpy_gui.info(None, "MatAnyone Runtime", "Runtime folder not found.")
        return

    lines = []
    if primary.exists():
        lines.append(str(primary))
    for p in legacy_left:
        lines.append(f"{p} (legacy)")
    if not dgpy_gui.confirm(
        None,
        "MatAnyone Runtime",
        "Delete runtime folder(s)?\n\n" + "\n".join(lines),
    ):
        return

    started = progress.start_remove_nonblocking()
    if not started:
        logger.info("MatAnyone remove already in progress")
        return
    logger.info("MatAnyone runtime remove started (non-modal; Flame stays usable)")


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
