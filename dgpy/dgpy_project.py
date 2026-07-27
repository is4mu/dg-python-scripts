"""Resolve current Flame project directory. Unique basename for Flame."""

from __future__ import annotations

from pathlib import Path

__version__ = "0.1.1"

_AUTODESK_PROJECT_ROOT = Path("/opt/Autodesk/project")


def _attr_str(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_value"):
        try:
            value = value.get_value()
        except Exception:  # noqa: BLE001
            pass
    return str(value).strip()


def current_project_name() -> str | None:
    try:
        import flame

        name = _attr_str(getattr(flame.project.current_project, "name", None))
        return name or None
    except Exception:  # noqa: BLE001
        return None


def current_desktop_name() -> str:
    """Current workspace desktop name, or 'Desktop'."""
    try:
        import flame

        desktop = flame.project.current_project.current_workspace.desktop
        name = _attr_str(getattr(desktop, "name", None))
        if name:
            return name
    except Exception:  # noqa: BLE001
        pass
    return "Desktop"


def _presets_base_dir():
    """Return PyExporter project presets dir, or None."""
    import flame

    exporter = flame.PyExporter
    get_dir = getattr(exporter, "get_presets_base_dir", None)
    if get_dir is None:
        return None

    # Flame version differences: PresetBaseDir.Project vs PyExporter.Project
    tokens = []
    preset_base = getattr(exporter, "PresetBaseDir", None)
    if preset_base is not None and hasattr(preset_base, "Project"):
        tokens.append(preset_base.Project)
    if hasattr(exporter, "Project"):
        tokens.append(exporter.Project)

    for token in tokens:
        try:
            raw = get_dir(token)
            if raw:
                return Path(str(raw)).resolve()
        except Exception:  # noqa: BLE001
            continue
    return None


def current_project_dir() -> Path | None:
    """
    Resolve the on-disk Flame project directory.

    Preferred: PyExporter project presets base → walk up to project root
    (community-proven; avoids shell.log parsing).

    Fallback: /opt/Autodesk/project/<current_project.name> if it exists.
    """
    import dgpy_log

    logger = dgpy_log.setup()

    try:
        presets = _presets_base_dir()
        if presets is not None:
            # Typical: <project>/export/presets/flame  (or similar depth)
            # Walk up until we hit /opt/Autodesk/project/<name> or max 5 levels.
            cursor = presets
            for _ in range(5):
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent
                if cursor.parent == _AUTODESK_PROJECT_ROOT and cursor.is_dir():
                    logger.info(
                        "Project dir via PyExporter presets: %s", cursor
                    )
                    return cursor
            # Fixed relative climb used widely on Logik forums
            climbed = (presets / "../../..").resolve()
            if climbed.is_dir():
                logger.info(
                    "Project dir via PyExporter ../../../ : %s", climbed
                )
                return climbed
    except Exception as exc:  # noqa: BLE001
        logger.info("PyExporter project dir failed: %s", exc)

    name = current_project_name()
    if name:
        candidate = _AUTODESK_PROJECT_ROOT / name
        if candidate.is_dir():
            logger.info(
                "Project dir via /opt/Autodesk/project/<name>: %s", candidate
            )
            return candidate

    logger.warning("Could not resolve Flame project directory")
    return None


def default_batch_flame_dir() -> Path | None:
    """Return <project>/batch/flame (created if possible), else None."""
    project = current_project_dir()
    if project is None:
        return None
    path = project / "batch" / "flame"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not path.is_dir():
            return None
    return path
