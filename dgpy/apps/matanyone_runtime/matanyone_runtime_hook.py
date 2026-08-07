"""
Flame main menu: DGpy → MatAnyone → Runtime / SAM2 / Remove All.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "0.11.0"


def _setup(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    paths.migrate_legacy_runtime_if_needed(
        log=lambda m: logger.info("[matanyone_runtime] %s", m)
    )
    if progress.remove_is_running() or progress.sam2_setup_is_running():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "Another MatAnyone runtime job is still running. Wait until it finishes.",
        )
        return
    if progress.setup_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone",
            "Setup is already running.\n"
            "The progress window was brought to the front "
            "(Flame remains usable).",
        )
        progress.start_setup_nonblocking(force=False)
        return

    if paths.is_ready():
        if not dgpy_gui.confirm(
            None,
            "MatAnyone",
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
            "MatAnyone",
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


def _setup_sam2(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    if progress.setup_is_running() or progress.remove_is_running():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "Another MatAnyone runtime job is still running. Wait until it finishes.",
        )
        return
    if progress.sam2_setup_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone",
            "SAM2 Setup is already running.\n"
            "The progress window was brought to the front.",
        )
        progress.start_sam2_setup_nonblocking(force=False)
        return

    if not paths.is_ready():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "MatAnyone 2 runtime is not ready.\n"
            "Run DGpy → MatAnyone → Runtime Setup… first.",
        )
        return

    if paths.is_sam2_ready():
        if not dgpy_gui.confirm(
            None,
            "MatAnyone",
            f"SAM2 already ready:\n{paths.sam2_checkpoint_path(size='tiny')}\n\n"
            "Reinstall (force)?",
        ):
            return
        force = True
    else:
        force = False
        if not dgpy_gui.confirm(
            None,
            "MatAnyone",
            "Install SAM2 into the MatAnyone runtime?\n\n"
            f"Target:\n{paths.sam2_repo_dir()}\n"
            f"Checkpoint (tiny):\n{paths.runtime_root()}/checkpoints/"
            f"{paths.SAM2_CKPT_TINY}\n\n"
            "Uses the existing runtime venv (no system Python / dnf).\n"
            "Download is ~40 MB (tiny). Non-modal progress — Flame stays usable.",
        ):
            return

    started = progress.start_sam2_setup_nonblocking(force=force)
    if not started:
        logger.info("SAM2 setup already in progress")
        return
    logger.info("MatAnyone SAM2 setup started (non-modal)")


def _remove(_selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as paths
    import matanyone_runtime_progress as progress

    logger = dgpy_log.setup()
    if progress.setup_is_running() or progress.sam2_setup_is_running():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "Setup is still running. Wait until it finishes before Remove All.",
        )
        return
    if progress.remove_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone",
            "Remove All is already running.\n"
            "The progress window was brought to the front.",
        )
        progress.start_remove_nonblocking()
        return

    paths.migrate_legacy_runtime_if_needed(
        log=lambda m: logger.info("[matanyone_runtime] %s", m)
    )
    primary = paths.runtime_root()
    legacy_left = [p for p in paths.legacy_runtime_roots() if p.exists()]
    if not primary.exists() and not legacy_left:
        dgpy_gui.info(None, "MatAnyone", "Runtime folder not found.")
        return

    lines = []
    if primary.exists():
        lines.append(str(primary))
    for p in legacy_left:
        lines.append(f"{p} (legacy)")
    if not dgpy_gui.confirm(
        None,
        "MatAnyone",
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
            "hierarchy": ["DGpy", "MatAnyone"],
            "actions": [
                {
                    "name": "Runtime Setup…",
                    "order": 10,
                    "execute": _setup,
                    "minimumVersion": "2025",
                },
                {
                    "name": "SAM2 Setup…",
                    "order": 20,
                    "execute": _setup_sam2,
                    "minimumVersion": "2025",
                },
                {
                    "name": "Remove All…",
                    "order": 30,
                    "execute": _remove,
                    "minimumVersion": "2025",
                },
            ],
        }
    ]
