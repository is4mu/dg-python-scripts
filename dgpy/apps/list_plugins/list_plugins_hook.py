"""
Flame main-menu: List Plugins.

Menu: DGpy → List Plugins
Scans current Desktop (timeline FX + batch nodes) on execute only.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _run(_selection=None):
    import list_plugins_app

    list_plugins_app.open_list_plugins()


def get_main_menu_custom_ui_actions():
    return [
        {
            "hierarchy": ["DGpy"],
            "actions": [
                {
                    "name": "List Plugins",
                    "order": 50,
                    "execute": _run,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]
