"""
Flame: DG2: Segment — Clean Up Action / Clean Up Action (Fit).

Media Panel + Timeline. Template reset via TimelineFX Action load_setup.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _as_list(selection) -> list:
    if not selection:
        return []
    if isinstance(selection, (list, tuple)):
        return list(selection)
    return [selection]


def _scope_visible(selection) -> bool:
    import dgpy_log
    from action_tidy_selection import has_segments

    logger = dgpy_log.setup()
    try:
        return has_segments(_as_list(selection), logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Clean Up Action isVisible error: %s", exc)
        return False


def _run(selection, *, template_id: str, title: str) -> None:
    import dgpy_gui
    import dgpy_log
    from action_tidy_job import run_cleanup
    from action_tidy_selection import resolve_segments

    logger = dgpy_log.setup()
    try:
        segments = resolve_segments(_as_list(selection), logger=logger)
        if not segments:
            dgpy_gui.warning(
                None,
                title,
                "No segments found.\n\n"
                "Select segments, or a clip/sequence/reel with a primary track.",
            )
            return

        n = len(segments)
        ok = dgpy_gui.confirm(
            None,
            title,
            f"Apply «{title}» to {n} segment(s)?\n\n"
            "Existing Action Timeline FX will be replaced by the studio template.",
        )
        if not ok:
            return

        result = run_cleanup(segments, template_id=template_id)
        if result.failed:
            detail = "\n".join(result.messages[-12:])
            dgpy_gui.warning(
                None,
                title,
                f"Done with errors.\n\nOK: {result.ok}  Failed: {result.failed}\n\n{detail}",
            )
        else:
            dgpy_gui.information(
                None,
                title,
                f"Applied to {result.ok} segment(s).",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed", title)
        dgpy_gui.warning(None, title, f"Failed:\n{exc}")


def _execute_clean(selection=None):
    _run(selection, template_id="clean", title="Clean Up Action")


def _execute_fit(selection=None):
    _run(selection, template_id="fit", title="Clean Up Action (Fit)")


def _action_entries() -> list[dict]:
    return [
        {
            "layout_key": "segment.cleanup",
            "name": "Clean Up Action",
            "isVisible": _scope_visible,
            "execute": _execute_clean,
            "minimumVersion": "2025",
        },
        {
            "layout_key": "segment.cleanup_fit",
            "name": "Clean Up Action (Fit)",
            "isVisible": _scope_visible,
            "execute": _execute_fit,
            "minimumVersion": "2025",
        },
    ]


def _timeline_group() -> list[dict]:
    return [
        {
            "name": "DG2: Segment",
            "hierarchy": ["DG2: Segment"],
            "order": 43,
            "actions": [
                {
                    "name": "Clean Up Action",
                    "order": 10,
                    "isVisible": _scope_visible,
                    "execute": _execute_clean,
                    "minimumVersion": "2025",
                },
                {
                    "name": "Clean Up Action (Fit)",
                    "order": 20,
                    "isVisible": _scope_visible,
                    "execute": _execute_fit,
                    "minimumVersion": "2025",
                },
            ],
        }
    ]


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(_action_entries())


def get_timeline_custom_ui_actions():
    return _timeline_group()
