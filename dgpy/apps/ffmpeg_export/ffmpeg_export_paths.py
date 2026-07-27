"""Output path helpers for FFmpeg Export (folder structure + tokens)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ffmpeg_export_presets import ExportPreset
from ffmpeg_export_selection import ExportSource

__version__ = "0.1.0"


def resolve_filename_pattern(pattern: str, source: ExportSource, index: int) -> str:
    text = pattern or "<name>"
    text = text.replace("<name>", source.name)
    text = text.replace("<date>", datetime.now().strftime("%y%m%d"))

    def _index(match: re.Match[str]) -> str:
        pads = match.group(1) or ""
        return str(index).zfill(len(pads)) if pads else str(index)

    return re.sub(r"<index(#*)>", _index, text)


def extension_for(preset: ExportPreset) -> str:
    if preset.kind == "frames":
        return preset.container.lstrip(".")
    return preset.container.lstrip(".")


def output_path_for(
    destination: Path,
    source: ExportSource,
    *,
    preset: ExportPreset,
    filename_pattern: str,
    keep_structure: bool,
    index: int,
) -> Path:
    dest = destination.expanduser().resolve()
    base_name = resolve_filename_pattern(filename_pattern, source, index)
    ext = extension_for(preset)

    if preset.kind == "frames":
        # directory for sequence: .../rel/name/
        rel = source.relative_dir if keep_structure else ""
        folder = dest / rel / base_name if rel else dest / base_name
        return folder / f"{base_name}.%06d.{ext}"

    file_name = f"{base_name}.{ext}"
    if keep_structure and source.relative_dir:
        return dest / source.relative_dir / file_name
    return dest / file_name


def preview_path(
    destination: str,
    sources: list[ExportSource],
    *,
    preset: ExportPreset,
    filename_pattern: str,
    keep_structure: bool,
) -> str:
    enabled = [s for s in sources if s.enabled]
    if not enabled or not destination.strip():
        return ""
    path = output_path_for(
        Path(destination),
        enabled[0],
        preset=preset,
        filename_pattern=filename_pattern,
        keep_structure=keep_structure,
        index=1,
    )
    return str(path)
