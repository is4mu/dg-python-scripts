"""Resolve MatAnyone runtime install root (outside Flame Python)."""

from __future__ import annotations

import json
from pathlib import Path

import dgpy_paths

__version__ = "0.1.2"

RUNTIME_NAME = "matanyone"
READY_NAME = "READY.json"
REPO_DIRNAME = "MatAnyone"
VENV_DIRNAME = "venv"


def runtime_root(root: Path | None = None) -> Path:
    """.../dgpy/runtimes/matanyone"""
    return (root or dgpy_paths.dgpy_root()) / "runtimes" / RUNTIME_NAME


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
    path = ready_path(root)
    if not path.is_file():
        return False
    py = resolve_python(root)
    return py is not None and Path(py).is_file()


def load_ready(root: Path | None = None) -> dict:
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
