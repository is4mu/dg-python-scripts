"""DG Export presets — menu items from apps/dg_export/presets/*.xml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__version__ = "0.1.7"


@dataclass(frozen=True)
class ExportPresetDef:
    id: str  # stable key (filename stem)
    label: str  # Media Panel menu name (= stem)
    path: Path  # absolute path to XML


def package_presets_dir() -> Path:
    return Path(__file__).resolve().parent / "presets"


def list_presets() -> list[ExportPresetDef]:
    """One menu entry per non-empty *.xml in presets/ (sorted by name).

    Filenames must not contain spaces (Manager download URLs).
    Underscores in the stem become spaces in the menu label
    (OA_Master.xml → "OA Master", to_MA.xml → "to MA").
    """
    root = package_presets_dir()
    if not root.is_dir():
        return []
    out: list[ExportPresetDef] = []
    for path in sorted(root.glob("*.xml"), key=lambda p: p.name.lower()):
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        stem = path.stem.strip()
        if not stem:
            continue
        if " " in path.name:
            continue  # skip illegal names rather than break Install
        label = stem.replace("_", " ")
        out.append(ExportPresetDef(id=stem, label=label, path=path.resolve()))
    return out


def find_preset(preset_id: str) -> ExportPresetDef | None:
    for preset in list_presets():
        if preset.id == preset_id:
            return preset
    return None


def resolve_preset_xml(preset: ExportPresetDef) -> Path:
    path = preset.path
    if path.is_file() and path.stat().st_size > 0:
        return path
    raise RuntimeError(
        f"Export preset XML missing or empty:\n{path}\n\n"
        f"Place Flame Media Export Movie presets in:\n"
        f"  {package_presets_dir()}\n"
        "(filename without .xml becomes the menu label)"
    )
