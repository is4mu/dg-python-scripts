"""Merge keep ranges by source file path + gap threshold."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dgpy_flame_attr

from segment_handle_clips_util import __version__  # noqa: F401

# Tried in order on segment, then owner clip.
_PATH_ATTRS = (
    "path",
    "source_path",
    "file_path",
    "media_path",
    "source_name",
)


def _stringify_path(val: Any) -> str | None:
    if val is None:
        return None
    if hasattr(val, "get_value"):
        try:
            val = val.get_value()
        except Exception:  # noqa: BLE001
            pass
    if val is None:
        return None
    text = str(val).strip()
    if not text or text.lower() in ("none", "null"):
        return None
    if text.startswith("<") and text.endswith(">"):
        return None
    return text


def normalize_source_path(raw: str) -> str:
    """Normalize for grouping; keep string identity if not a local path."""
    text = raw.strip()
    if os.path.isabs(text) or text.startswith("/"):
        try:
            return str(Path(text).expanduser().resolve())
        except OSError:
            return os.path.normpath(text)
    return os.path.normpath(text)


def resolve_source_path(segment, owner=None, *, logger=None) -> str | None:
    """Best-effort source file path from segment or owning clip."""
    objs = [segment]
    if owner is not None and owner is not segment:
        objs.append(owner)

    for obj in objs:
        if obj is None:
            continue
        for attr in _PATH_ATTRS:
            raw = _stringify_path(dgpy_flame_attr.attr_value(obj, attr, None))
            if raw is None and hasattr(obj, attr):
                try:
                    raw = _stringify_path(getattr(obj, attr))
                except Exception:  # noqa: BLE001
                    raw = None
            if raw:
                key = normalize_source_path(raw)
                if logger:
                    logger.info(
                        "Consolidate Handles: source path via %s → %s",
                        attr,
                        key,
                    )
                return key
    return None


@dataclass
class MergedRange:
    source_path: str | None
    keep_start: int
    keep_end: int
    seg_indices: list[int] = field(default_factory=list)  # 1-based report #
    names: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def keep_frames(self) -> int:
        return max(1, abs(self.keep_end - self.keep_start) + 1)

    @property
    def label(self) -> str:
        if self.source_path:
            return Path(self.source_path).name or self.source_path
        if self.names:
            return self.names[0]
        return "(no path)"


def _flush_cluster(
    out: list[MergedRange],
    *,
    path: str | None,
    start: int,
    end: int,
    indices: list[int],
    names: list[str],
) -> None:
    out.append(
        MergedRange(
            source_path=path,
            keep_start=start,
            keep_end=end,
            seg_indices=list(indices),
            names=list(names),
            notes="" if path else "no source path",
        )
    )


def merge_keep_ranges(
    rows: list[dict],
    *,
    merge_gap: int,
) -> list[MergedRange]:
    """
    Group ok rows by source_path; merge inclusive intervals when gap ≤ merge_gap.

    gap = next_start - prev_end - 1  (adjacent → 0).
    Rows without path never merge with others (unique synthetic key).
    skip rows are ignored.
    """
    gap_max = max(0, int(merge_gap))

    # (group_key, start, end, index_1based, name, path_or_none)
    items: list[tuple[str, int, int, int, str, str | None]] = []
    for i, row in enumerate(rows, start=1):
        if row.get("skip"):
            continue
        start = row.get("keep_start")
        end = row.get("keep_end")
        if start is None or end is None:
            continue
        a, b = int(start), int(end)
        if b < a:
            a, b = b, a
        a = max(1, a)
        b = max(1, b)
        if b < a:
            b = a
        path = row.get("source_path")
        name = str(row.get("name") or "clip")
        if isinstance(path, str) and path:
            key = f"path:{path}"
            path_val: str | None = path
        else:
            key = f"nopath:{i}"
            path_val = None
        items.append((key, a, b, i, name, path_val))

    by_key: dict[str, list[tuple[int, int, int, str, str | None]]] = {}
    order: list[str] = []
    for key, a, b, idx, name, path_val in items:
        if key not in by_key:
            order.append(key)
            by_key[key] = []
        by_key[key].append((a, b, idx, name, path_val))

    merged: list[MergedRange] = []
    for key in order:
        group = sorted(by_key[key], key=lambda t: (t[0], t[1], t[2]))
        cur_a, cur_b, idx0, name0, path0 = group[0]
        indices = [idx0]
        names = [name0]
        for a, b, idx, name, _p in group[1:]:
            gap = a - cur_b - 1
            if gap <= gap_max:
                cur_b = max(cur_b, b)
                indices.append(idx)
                names.append(name)
            else:
                _flush_cluster(
                    merged,
                    path=path0,
                    start=cur_a,
                    end=cur_b,
                    indices=indices,
                    names=names,
                )
                cur_a, cur_b = a, b
                indices = [idx]
                names = [name]
        _flush_cluster(
            merged,
            path=path0,
            start=cur_a,
            end=cur_b,
            indices=indices,
            names=names,
        )

    return merged
