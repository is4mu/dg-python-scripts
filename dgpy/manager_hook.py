"""
Flame main-menu entry for DG Script Manager (P1).

Menu (migration): DGpy → DG Script Manager

Note: Flame loads every .py under the hook path as a top-level module by
*filename*. Library modules must use unique basenames (no package __init__.py).

Silent auto-update is scheduled from get_main_menu_custom_ui_actions (once),
not app_initialized (stock hook.py owns that name on Flame 2025).
"""

from __future__ import annotations

import os
import sys

_DGPY_ROOT = os.path.dirname(os.path.abspath(__file__))
if _DGPY_ROOT not in sys.path:
    sys.path.insert(0, _DGPY_ROOT)


def _open_manager(selection=None):
    import dgpy_manager_app

    dgpy_manager_app.open_manager(selection)


def get_main_menu_custom_ui_actions():
    try:
        import dgpy_startup

        dgpy_startup.schedule_from_main_menu()
    except Exception:  # noqa: BLE001
        pass

    return [
        {
            "hierarchy": ["DGpy"],
            "actions": [
                {
                    "name": "DG Script Manager",
                    # Keep Manager first under DGpy; apps use order >= 100.
                    "order": 0,
                    "separator": "below",
                    "execute": _open_manager,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]
