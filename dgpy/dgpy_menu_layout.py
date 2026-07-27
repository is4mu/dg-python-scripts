"""Central Media Panel menu order and separators.

Packages register actions with ``layout_key`` only; this module applies
hierarchy / group order / action order / separator. Uninstalled packages
simply omit their actions — layout rows for missing keys are ignored
(no dead menu items).

Unique basename for Flame scan.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.1"

# Temporary coexistence prefix. Flip to "DG:" when legacy is retired.
MENU_PREFIX = "DG2:"


def _h(*parts: str) -> list[str]:
    """Build hierarchy; first part may already include prefix."""
    out: list[str] = []
    for i, part in enumerate(parts):
        if i == 0 and not part.startswith(("DG", "DGpy")):
            out.append(f"{MENU_PREFIX} {part}")
        else:
            out.append(part)
    return out


# Group id → Flame group fields (hierarchy + order [+ optional group separator]).
MEDIA_PANEL_GROUPS: dict[str, dict[str, Any]] = {
    "color": {
        "hierarchy": _h("Color"),
        "order": 10,
    },
    "rename": {
        "hierarchy": [],
        "order": 20,
    },
    "batch": {
        "hierarchy": _h("Batch"),
        "order": 30,
    },
    "audio": {
        "hierarchy": _h("Audio"),
        "order": 35,
    },
    "clip": {
        "hierarchy": _h("Clip"),
        "order": 40,
    },
    "clip.goto": {
        # Nested under Clip (legacy: DG: Go To under DG: Clip).
        "hierarchy": _h("Clip", "Go To"),
        "order": 41,
        "separator": "below",
    },
    "sequence": {
        "hierarchy": _h("Sequence"),
        "order": 45,
    },
    "sequence_render": {
        "hierarchy": [],
        "order": 50,
        "separator": "below",
    },
    "export": {
        "hierarchy": [],
        "order": 55,
    },
}

# layout_key → placement inside a group (legacy-inspired orders / separators).
MEDIA_PANEL_ACTIONS: dict[str, dict[str, Any]] = {
    # Color swatches (relative order only; names come from package).
    "color.Rose": {"group": "color", "order": 0},
    "color.Red": {"group": "color", "order": 1},
    "color.Orange": {"group": "color", "order": 2},
    "color.Gold": {"group": "color", "order": 3},
    "color.Green": {"group": "color", "order": 4},
    "color.Teal": {"group": "color", "order": 5},
    "color.Blue": {"group": "color", "order": 6},
    "color.Purple": {"group": "color", "order": 7},
    "color.Black": {"group": "color", "order": 8},
    "color.Gray": {"group": "color", "order": 9},
    # Root
    "rename.root": {"group": "rename", "order": 20},
    # Batch
    "batch.open": {"group": "batch", "order": 10},
    "batch.save_setup": {"group": "batch", "order": 20},
    "batch.render": {"group": "batch", "order": 30},
    # Audio (legacy separators)
    "audio.lock": {"group": "audio", "order": 10},
    "audio.unlock": {"group": "audio", "order": 20, "separator": "below"},
    "audio.only_1_2": {"group": "audio", "order": 30, "separator": "above"},
    "audio.only_3_4": {"group": "audio", "order": 40, "separator": "below"},
    "audio.delete_mute": {"group": "audio", "order": 50, "separator": "above"},
    "audio.delete_all": {"group": "audio", "order": 60},
    # Clip (legacy: batch tools → Go To → start frame)
    "clip.create_batch": {"group": "clip", "order": 10},
    "clip.resize_all": {"group": "clip", "order": 20, "separator": "below"},
    # clip.comp_cg reserved order 30 separator below when implemented
    "clip.set_start_frame_1": {"group": "clip", "order": 50},
    "clip.goto.first": {"group": "clip.goto", "order": 10},
    "clip.goto.last": {"group": "clip.goto", "order": 20},
    "clip.goto.in_mark": {"group": "clip.goto", "order": 30},
    "clip.goto.out_mark": {"group": "clip.goto", "order": 40},
    "clip.goto.custom": {"group": "clip.goto", "order": 50},
    # Sequence (legacy: cutdata → markers → cutout → keep tracks)
    "sequence.cutdata_add_markers": {"group": "sequence", "order": 10},
    "sequence.cutdata_from_markers": {
        "group": "sequence",
        "order": 20,
        "separator": "below",
    },
    "sequence.delete_all_markers": {"group": "sequence", "order": 30},
    "sequence.cutout_first": {
        "group": "sequence",
        "order": 40,
        "separator": "above",
    },
    "sequence.cutout_last": {
        "group": "sequence",
        "order": 50,
        "separator": "below",
    },
    "sequence.only_primary": {"group": "sequence", "order": 60},
    "sequence.only_top": {"group": "sequence", "order": 70},
    "sequence.set_top_primary": {"group": "sequence", "order": 80},
    # Sequence Render (root)
    "sequence_render.selection": {"group": "sequence_render", "order": 50},
    "sequence_render.reels_hotkey": {"group": "sequence_render", "order": 51},
    # Export (root, Rename-style)
    "export.root": {"group": "export", "order": 55},
}

_FLAME_ACTION_KEYS = (
    "name",
    "order",
    "separator",
    "isVisible",
    "isEnabled",
    "execute",
    "minimumVersion",
)


def build_media_panel(raw_actions: list[dict]) -> list[dict]:
    """Apply central layout to package actions; return Flame menu groups.

    Each ``raw_actions`` item must include ``layout_key`` plus Flame fields
    (``name``, ``execute``, ``isVisible``, …). Unknown keys fall back to a
    late orphan group so menus still appear during development.
    """
    buckets: dict[str, list[dict]] = {}

    for raw in raw_actions:
        key = raw.get("layout_key")
        place = MEDIA_PANEL_ACTIONS.get(key) if key else None
        if place is None:
            group_id = "_orphan"
            action_order = 900 + len(buckets.get("_orphan", []))
            separator = None
        else:
            group_id = place["group"]
            action_order = int(place["order"])
            separator = place.get("separator")

        action = {
            k: raw[k] for k in _FLAME_ACTION_KEYS if k in raw and k != "order"
        }
        action["order"] = action_order
        if separator:
            action["separator"] = separator
        elif "separator" in action:
            del action["separator"]

        buckets.setdefault(group_id, []).append(action)

    # Emit groups in MEDIA_PANEL_GROUPS order; orphans last.
    group_ids = [gid for gid in MEDIA_PANEL_GROUPS if gid in buckets]
    if "_orphan" in buckets:
        group_ids.append("_orphan")

    out: list[dict] = []
    for group_id in group_ids:
        actions = sorted(buckets[group_id], key=lambda a: a["order"])
        if group_id == "_orphan":
            meta = {"hierarchy": [_h("Orphan")[0]], "order": 999}
        else:
            meta = MEDIA_PANEL_GROUPS[group_id]
        group: dict[str, Any] = {
            "hierarchy": list(meta.get("hierarchy") or []),
            "order": int(meta.get("order", 500)),
            "actions": actions,
        }
        if meta.get("separator"):
            group["separator"] = meta["separator"]
        out.append(group)
    return out
