"""Flame object type checks (isinstance). Unique basename for Flame scan."""

from __future__ import annotations

from typing import Any

__version__ = "0.1.2"


def as_list(selection) -> list:
    if not selection:
        return []
    if isinstance(selection, (list, tuple)):
        return list(selection)
    return [selection]


def _flame():
    import flame

    return flame


def is_batch(item: Any) -> bool:
    try:
        return isinstance(item, _flame().PyBatch)
    except Exception:  # noqa: BLE001
        return False


def is_desktop(item: Any) -> bool:
    try:
        return isinstance(item, _flame().PyDesktop)
    except Exception:  # noqa: BLE001
        return False


def is_clip(item: Any) -> bool:
    """True for PyClip; PySequence often subclasses PyClip and matches too."""
    try:
        return isinstance(item, _flame().PyClip)
    except Exception:  # noqa: BLE001
        return False


def is_sequence(item: Any) -> bool:
    try:
        flame = _flame()
        seq = getattr(flame, "PySequence", None)
        if seq is None:
            return False
        return isinstance(item, seq)
    except Exception:  # noqa: BLE001
        return False


def is_reel(item: Any) -> bool:
    try:
        return isinstance(item, _flame().PyReel)
    except Exception:  # noqa: BLE001
        return False


def is_folder(item: Any) -> bool:
    try:
        return isinstance(item, _flame().PyFolder)
    except Exception:  # noqa: BLE001
        return False


def is_library(item: Any) -> bool:
    try:
        return isinstance(item, _flame().PyLibrary)
    except Exception:  # noqa: BLE001
        return False


def is_media_container(item: Any) -> bool:
    return is_reel(item) or is_folder(item) or is_library(item)


def item_label(item: Any) -> str:
    typ = type(item).__name__
    try:
        n = getattr(item, "name", None)
        if n is not None and hasattr(n, "get_value"):
            return f"{typ}({n.get_value()!r})"
        if n is not None:
            return f"{typ}({n!r})"
    except Exception:  # noqa: BLE001
        pass
    return typ


def summarize(items: list) -> str:
    if not items:
        return "(empty)"
    labels = [item_label(i) for i in items[:8]]
    extra = f" …(+{len(items) - 8})" if len(items) > 8 else ""
    return f"n={len(items)} [{', '.join(labels)}{extra}]"


def _safe_list(value) -> list:
    if not value:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def probe_container_clip_attrs(item: Any, logger=None) -> None:
    """
    Log whether ``.clips`` already contains Sequence objects.

    Call while verifying Flame behavior (Reel/Folder/Library).
    """
    if logger is None or not is_media_container(item):
        return
    clips = _safe_list(getattr(item, "clips", None))
    sequences = _safe_list(getattr(item, "sequences", None))
    seq_in_clips = sum(1 for c in clips if is_sequence(c))
    clip_types = [type(c).__name__ for c in clips[:12]]
    seq_types = [type(c).__name__ for c in sequences[:12]]
    logger.debug(
        "dgpy_flame_types probe %s name=%s: "
        "len(clips)=%s len(sequences)=%s sequences_inside_clips=%s "
        "clip_types=%s sequence_types=%s",
        type(item).__name__,
        item_label(item),
        len(clips),
        len(sequences) if hasattr(item, "sequences") else "no-attr",
        seq_in_clips,
        clip_types,
        seq_types,
    )


def clips_from_container(
    item: Any, *, logger=None, include_sequences: bool = True
) -> list:
    """
    Immediate Clip/Sequence children of Reel/Folder/Library.

    Prefer ``.clips`` (+ ``.sequences`` when ``include_sequences``).
    Fall back to ``.children`` filtered by ``is_clip`` / ``is_sequence``.
    """
    if not is_media_container(item):
        return []

    probe_container_clip_attrs(item, logger)

    out: list = []
    seen: set[int] = set()

    def _add(objs: list) -> None:
        for obj in objs:
            if not is_clip(obj) and not is_sequence(obj):
                continue
            oid = id(obj)
            if oid in seen:
                continue
            seen.add(oid)
            out.append(obj)

    has_clips = hasattr(item, "clips")
    has_seqs = include_sequences and hasattr(item, "sequences")
    if has_clips or has_seqs:
        if has_clips:
            _add(_safe_list(getattr(item, "clips", None)))
        if has_seqs:
            _add(_safe_list(getattr(item, "sequences", None)))
        return out

    _add(_safe_list(getattr(item, "children", None)))
    return out


def get_clips(selection, *, logger=None) -> list:
    """Resolve clips/sequences from selection (direct or container children)."""
    clips: list = []
    for item in as_list(selection):
        if is_clip(item) or is_sequence(item):
            clips.append(item)
            continue
        if is_media_container(item):
            clips.extend(clips_from_container(item, logger=logger))
    return clips


def get_batch_groups(selection) -> list:
    """PyBatch, or all batch_groups under PyDesktop."""
    batches: list = []
    for item in as_list(selection):
        if is_batch(item):
            batches.append(item)
        elif is_desktop(item):
            batches.extend(_safe_list(getattr(item, "batch_groups", None)))
    return batches
