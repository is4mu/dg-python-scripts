"""Local package inventory for P1 (no remote). Unique basename for Flame."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import dgpy_paths

__version__ = "0.3.6"


@dataclass
class LocalPackage:
    package_id: str
    name: str
    version: str
    location: str
    status: str


def installed_json_path(root: Path | None = None) -> Path:
    return dgpy_paths.state_dir(root) / "installed.json"


def load_installed(root: Path | None = None) -> dict:
    path = installed_json_path(root)
    if not path.exists():
        return {"packages": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"packages": {}}


def save_installed(data: dict, root: Path | None = None) -> None:
    path = installed_json_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_version_attr(module_path: Path, fallback: str = "0.1.0") -> str:
    if not module_path.exists():
        return "—"
    for line in module_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return fallback


def _read_version_attr(module_path: Path, fallback: str = "0.1.0") -> str:
    return read_version_attr(module_path, fallback)


def scan_local(root: Path | None = None) -> list[LocalPackage]:
    base = root or dgpy_paths.dgpy_root()
    installed = load_installed(base).get("packages") or {}
    rows: list[LocalPackage] = []

    core_marker = base / "dgpy_paths.py"
    manager_marker = base / "dgpy_manager_app.py"

    known = [
        (
            "core",
            "DG Core",
            core_marker,
            _read_version_attr(core_marker),
        ),
        (
            "manager",
            "DG Script Manager",
            manager_marker,
            _read_version_attr(manager_marker),
        ),
    ]
    for pid, name, marker, ver in known:
        if marker.exists():
            ver = installed.get(pid, {}).get("version") or ver
            rows.append(
                LocalPackage(pid, name, ver, str(marker), "Installed")
            )
        else:
            rows.append(LocalPackage(pid, name, "—", str(marker), "Missing"))

    apps = dgpy_paths.apps_dir(base)
    for child in sorted(apps.iterdir()) if apps.exists() else []:
        if not child.is_dir() or child.name.startswith("."):
            continue
        pid = child.name
        meta_name = installed.get(pid, {}).get("name") or pid
        ver = installed.get(pid, {}).get("version") or "unknown"
        rows.append(
            LocalPackage(pid, str(meta_name), ver, str(child), "Installed")
        )

    return rows


def ensure_seed_installed(root: Path | None = None) -> None:
    """Seed / refresh core+manager entries from on-disk markers.

    Keeps ``installed.json`` aligned with filesystem versions so Manager
    does not show a perpetual Update when inventory is missing or stale.
    """
    base = root or dgpy_paths.dgpy_root()
    data = load_installed(base)
    packages = data.setdefault("packages", {})
    changed = False
    seeds = (
        ("core", "DG Core", base / "dgpy_paths.py"),
        ("manager", "DG Script Manager", base / "dgpy_manager_app.py"),
    )
    for pid, name, marker in seeds:
        if not marker.exists():
            continue
        ver = read_version_attr(marker)
        entry = {"name": name, "version": ver, "path": marker.name}
        existing = packages.get(pid) or {}
        if (
            existing.get("name") != entry["name"]
            or existing.get("version") != entry["version"]
            or existing.get("path") != entry["path"]
        ):
            packages[pid] = entry
            changed = True
    if changed:
        save_installed(data, base)
