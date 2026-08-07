"""
Flame main-menu: DGpy Preferences.

Menu: DGpy → Preferences…
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
    import prefs_app

    prefs_app.open_preferences()


def get_main_menu_custom_ui_actions():
    return [
        {
            "hierarchy": ["DGpy"],
            "actions": [
                {
                    "name": "Preferences…",
                    # After Script Manager (order 0 + separator); before List Plugins (50).
                    "order": 10,
                    "execute": _run,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]
