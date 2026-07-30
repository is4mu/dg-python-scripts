"""Resolve MatAnyone runtime install root (outside Flame hook scan)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import dgpy_paths

__version__ = "0.1.7"

RUNTIME_NAME = "matanyone"
READY_NAME = "READY.json"
REPO_DIRNAME = "MatAnyone"
VENV_DIRNAME = "venv"
MINIFORGE_DIRNAME = "miniforge3"

LogFn = Callable[[str], None]


def legacy_runtime_root(root: Path | None = None) -> Path:
    """Old location under dgpy/ (slow Flame hook scan — do not use for new installs)."""
    return (root or dgpy_paths.dgpy_root()) / "runtimes" / RUNTIME_NAME


def runtime_root(root: Path | None = None) -> Path:
    """Sibling of dgpy/: .../python/dgpy_runtimes/matanyone

    Kept outside dgpy/ so Flame's \"Scanning for python hooks\" does not walk
    Miniforge / venv (tens of thousands of .py files).
    """
    return (root or dgpy_paths.dgpy_root()).parent / "dgpy_runtimes" / RUNTIME_NAME


def migrate_legacy_runtime_if_needed(*, log: LogFn | None = None) -> Path:
    """Move dgpy/runtimes/matanyone → dgpy_runtimes/matanyone when needed."""
    legacy = legacy_runtime_root()
    dest = runtime_root()
    if not legacy.exists():
        return dest
    if dest.exists():
        if log:
            log(
                f"Legacy runtime still present at {legacy} but {dest} exists. "
                f"Delete the legacy folder to speed up Flame hook scan."
            )
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if log:
        log(f"Migrating runtime out of dgpy/ (hook-scan safe):\n  {legacy}\n→ {dest}")
    shutil.move(str(legacy), str(dest))
    # Remove empty dgpy/runtimes if possible.
    try:
        parent = legacy.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
    return dest


def miniforge_root(root: Path | None = None) -> Path:
    return runtime_root(root) / MINIFORGE_DIRNAME


def miniforge_python(root: Path | None = None) -> Path | None:
    base = miniforge_root(root)
    for rel in ("bin/python", "bin/python3"):
        candidate = base / rel
        if candidate.is_file():
            return candidate
    return None


def ready_path(root: Path | None = None) -> Path:
    return runtime_root(root) / READY_NAME


def repo_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / REPO_DIRNAME


def venv_python(root: Path | None = None) -> Path | None:
    base = runtime_root(root) / VENV_DIRNAME
    for rel in ("bin/python", "bin/python3", "Scripts/python.exe"):
        candidate = base / rel
        if candidate.is_file():
            return candidate
    return None


def is_ready(root: Path | None = None) -> bool:
    migrate_legacy_runtime_if_needed()
    path = ready_path(root)
    if not path.is_file():
        # Legacy READY still under dgpy/ before migrate failed?
        legacy_ready = legacy_runtime_root(root) / READY_NAME
        if legacy_ready.is_file():
            migrate_legacy_runtime_if_needed()
            path = ready_path(root)
    if not path.is_file():
        return False
    py = resolve_python(root)
    return py is not None and Path(py).is_file()


def load_ready(root: Path | None = None) -> dict:
    migrate_legacy_runtime_if_needed()
    path = ready_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_python(root: Path | None = None) -> str | None:
    data = load_ready(root)
    raw = str(data.get("python") or "").strip()
    if raw and Path(raw).is_file():
        return raw
    found = venv_python(root)
    return str(found) if found else None


def inference_script(root: Path | None = None) -> Path | None:
    data = load_ready(root)
    raw = str(data.get("inference_script") or "").strip()
    if raw and Path(raw).is_file():
        return Path(raw)
    candidate = repo_dir(root) / "inference_matanyone.py"
    return candidate if candidate.is_file() else None


def sam_script(root: Path | None = None) -> Path | None:
    data = load_ready(root)
    raw = str(data.get("sam_script") or "").strip()
    if raw and Path(raw).is_file():
        return Path(raw)
    candidate = runtime_root(root) / "sam2_make_mask.py"
    return candidate if candidate.is_file() else None
