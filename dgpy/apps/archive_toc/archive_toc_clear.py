"""Clear contents of /opt/Autodesk/archive (Online TOCs). Unique basename."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import dgpy_gui
import dgpy_log

__version__ = "1.0.6"

ARCHIVE_DIR = Path("/opt/Autodesk/archive")


def _list_entries(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.iterdir(), key=lambda p: p.name.lower())


def _visible_entry_count(entries: list[Path]) -> int:
    """Count for the confirm dialog — omit dotfiles (e.g. .DS_Store)."""
    return sum(1 for p in entries if not p.name.startswith("."))


def _is_inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def clear_archive_tocs(parent=None) -> None:
    logger = dgpy_log.setup()
    root = ARCHIVE_DIR

    if not root.exists():
        dgpy_gui.warning(
            parent,
            "Clear Archive TOCs",
            f"Directory not found:\n{root}",
        )
        return
    if not root.is_dir():
        dgpy_gui.error(
            parent,
            "Clear Archive TOCs",
            f"Not a directory:\n{root}",
        )
        return

    entries = _list_entries(root)
    count = _visible_entry_count(entries)
    msg = (
        f"Delete ALL contents under:\n{root}\n\n"
        f"Entries: {count}\n\n"
        "This deletes OTOCs.\n"
        "Does not delete actual archive media.\n"
        "Recovery options for corrupted headers will be lost."
    )
    if not dgpy_gui.confirm(parent, "Clear Archive TOCs", msg):
        logger.info("Clear Archive TOCs cancelled")
        return

    if not os.access(root, os.W_OK):
        dgpy_gui.error(
            parent,
            "Clear Archive TOCs",
            f"No write permission:\n{root}\n"
            "Ask an administrator for access, or run as a user with write permission.",
        )
        return

    removed = 0
    removed_visible = 0
    errors: list[str] = []
    for entry in entries:
        try:
            if not _is_inside(root, entry):
                errors.append(f"skip (outside): {entry}")
                continue
            if entry.is_symlink():
                # Remove the symlink itself only if it lives directly under root
                if entry.parent.resolve() == root.resolve():
                    entry.unlink()
                    removed += 1
                    if not entry.name.startswith("."):
                        removed_visible += 1
                else:
                    errors.append(f"skip symlink: {entry}")
                continue
            if entry.is_dir():
                # Ensure resolved path stays under archive
                if not _is_inside(root, entry):
                    errors.append(f"skip dir: {entry}")
                    continue
                shutil.rmtree(entry)
                removed += 1
                if not entry.name.startswith("."):
                    removed_visible += 1
            elif entry.is_file():
                entry.unlink()
                removed += 1
                if not entry.name.startswith("."):
                    removed_visible += 1
            else:
                # sockets etc.
                entry.unlink(missing_ok=True)
                removed += 1
                if not entry.name.startswith("."):
                    removed_visible += 1
        except OSError as exc:
            errors.append(f"{entry.name}: {exc}")
            logger.warning("Failed to remove %s: %s", entry, exc)

    logger.info(
        "Clear Archive TOCs: removed %s entr(y/ies) (%s visible)",
        removed,
        removed_visible,
    )
    summary = f"Deleted {removed_visible} entr(y/ies)."
    if errors:
        summary += "\n\nSome failures:\n" + "\n".join(errors[:20])
        if len(errors) > 20:
            summary += f"\n…and {len(errors) - 20} more"
        dgpy_gui.warning(parent, "Clear Archive TOCs", summary)
    else:
        dgpy_gui.info(parent, "Clear Archive TOCs", summary)
