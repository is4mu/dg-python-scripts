"""Resolve Clip/Sequence sources with relative dirs for folder-structure export."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import dgpy_flame_types

__version__ = "0.1.0"

_UNSAFE = re.compile(r'[<>:"|?*\\]+')


@dataclass
class ExportSource:
    """One exportable clip/sequence with path relative to selection root contents."""

    item: Any
    name: str
    relative_dir: str  # "" or "Hero/Sub" (no leading/trailing slash)
    root_label: str = ""  # selection root name when multiple roots
    enabled: bool = True
    tree_parts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def relative_path_key(self) -> str:
        if self.relative_dir:
            return f"{self.relative_dir}/{self.name}"
        return self.name


def sanitize_component(name: str) -> str:
    text = _UNSAFE.sub("_", (name or "").strip())
    text = text.replace("/", "_").replace("\0", "")
    return text or "unnamed"


def _object_name(item: Any) -> str:
    name = getattr(item, "name", None)
    if name is None:
        return type(item).__name__
    if hasattr(name, "get_value"):
        try:
            return str(name.get_value())
        except Exception:  # noqa: BLE001
            return str(name)
    return str(name)


def _safe_list(value) -> list:
    if not value:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _child_containers(item: Any) -> list:
    """Nested Folder / Reel / Library under a container."""
    out: list = []
    seen: set[int] = set()

    def add(objs: list) -> None:
        for obj in objs:
            if not dgpy_flame_types.is_media_container(obj):
                continue
            oid = id(obj)
            if oid in seen:
                continue
            seen.add(oid)
            out.append(obj)

    for attr in ("folders", "reels", "libraries", "children"):
        if hasattr(item, attr):
            add(_safe_list(getattr(item, attr, None)))
    return out


def _walk_container(
    container: Any,
    *,
    rel_parts: tuple[str, ...],
    root_label: str,
    out: list[ExportSource],
    seen_ids: set[int],
    logger=None,
) -> None:
    for clip in dgpy_flame_types.clips_from_container(container, logger=logger):
        oid = id(clip)
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        name = sanitize_component(_object_name(clip))
        rel = "/".join(rel_parts)
        out.append(
            ExportSource(
                item=clip,
                name=name,
                relative_dir=rel,
                root_label=root_label,
                tree_parts=rel_parts + (name,),
            )
        )

    for child in _child_containers(container):
        child_name = sanitize_component(_object_name(child))
        _walk_container(
            child,
            rel_parts=rel_parts + (child_name,),
            root_label=root_label,
            out=out,
            seen_ids=seen_ids,
            logger=logger,
        )


def resolve_export_sources(selection, *, logger=None) -> list[ExportSource]:
    """
    Build ExportSource list from Media Panel selection.

    - Clip/Sequence: relative_dir empty
    - Reel/Folder/Library: recurse; container name itself is NOT in relative_dir
      (contents start under Destination). Multiple roots: prefix with root name
      when relative paths would collide.
    """
    roots = dgpy_flame_types.as_list(selection)
    collected: list[ExportSource] = []
    seen_ids: set[int] = set()

    container_roots = [
        r for r in roots if dgpy_flame_types.is_media_container(r)
    ]
    multi_root = len(container_roots) > 1

    for item in roots:
        if dgpy_flame_types.is_clip(item) or dgpy_flame_types.is_sequence(item):
            oid = id(item)
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            name = sanitize_component(_object_name(item))
            collected.append(
                ExportSource(
                    item=item,
                    name=name,
                    relative_dir="",
                    root_label="",
                    tree_parts=(name,),
                )
            )
            continue

        if dgpy_flame_types.is_media_container(item):
            label = sanitize_component(_object_name(item))
            prefix: tuple[str, ...] = (label,) if multi_root else ()
            _walk_container(
                item,
                rel_parts=prefix,
                root_label=label,
                out=collected,
                seen_ids=seen_ids,
                logger=logger,
            )

    return collected


def has_exportable(selection) -> bool:
    return bool(resolve_export_sources(selection))
