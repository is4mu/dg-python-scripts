"""DG Export preset catalog and Flame XML path resolution."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

__version__ = "0.1.0"

# Shared Format Preset group (Autodesk Media Export).
SHARED_MOVIE_DG = Path("/opt/Autodesk/shared/export/presets/movie_file/DG")


@dataclass(frozen=True)
class ExportPresetDef:
    id: str
    label: str  # Media Panel menu name
    xml_name: str  # file under presets/DG/


PRESETS: tuple[ExportPresetDef, ...] = (
    ExportPresetDef(id="master", label="Master", xml_name="Master.xml"),
    ExportPresetDef(id="oa_master", label="OA Master", xml_name="OA Master.xml"),
    ExportPresetDef(id="to_ma", label="to_MA", xml_name="to_MA.xml"),
    ExportPresetDef(id="youtube", label="YouTube", xml_name="YouTube.xml"),
)


def package_presets_dir() -> Path:
    return Path(__file__).resolve().parent / "presets" / "DG"


def find_preset(preset_id: str) -> ExportPresetDef | None:
    for preset in PRESETS:
        if preset.id == preset_id:
            return preset
    return None


def resolve_preset_xml(preset: ExportPresetDef) -> Path:
    """
    Resolve Flame Media Export preset XML.

    Order: package presets/DG → Shared movie_file/DG.
    XML bodies are supplied later; missing file raises RuntimeError.
    """
    package_path = package_presets_dir() / preset.xml_name
    if package_path.is_file() and package_path.stat().st_size > 0:
        return package_path

    shared_path = SHARED_MOVIE_DG / preset.xml_name
    if shared_path.is_file() and shared_path.stat().st_size > 0:
        return shared_path

    raise RuntimeError(
        f"Export preset XML not found for '{preset.label}'.\n\n"
        f"Place a Flame Media Export Movie preset at either:\n"
        f"  • {package_path}\n"
        f"  • {shared_path}\n\n"
        "Create it in Media Export (Save), then copy the XML here."
    )


def try_install_package_presets_to_shared() -> list[str]:
    """Copy non-empty package XMLs into Shared DG group. Returns notes."""
    notes: list[str] = []
    src_dir = package_presets_dir()
    if not src_dir.is_dir():
        return notes
    xmls = [p for p in src_dir.glob("*.xml") if p.is_file() and p.stat().st_size > 0]
    if not xmls:
        return notes
    try:
        SHARED_MOVIE_DG.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        notes.append(f"Shared DG dir not writable: {exc}")
        return notes
    for src in xmls:
        dest = SHARED_MOVIE_DG / src.name
        try:
            if not dest.is_file() or dest.stat().st_size == 0:
                shutil.copy2(src, dest)
                notes.append(f"Installed Shared preset: {dest}")
            elif src.stat().st_mtime > dest.stat().st_mtime:
                shutil.copy2(src, dest)
                notes.append(f"Updated Shared preset: {dest}")
        except OSError as exc:
            notes.append(f"Could not copy {src.name}: {exc}")
    return notes
