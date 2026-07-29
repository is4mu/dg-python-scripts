"""
Flame main-menu: Clear Archive TOCs.

Menu (migration): DGpy → Clear Archive TOCs
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
    import archive_toc_clear

    archive_toc_clear.clear_archive_tocs(parent=None)


def get_main_menu_custom_ui_actions():
    return [
        {
            "hierarchy": ["DGpy"],
            "actions": [
                {
                    "name": "Clear Archive TOCs",
                    "order": 100,
                    "execute": _run,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]
