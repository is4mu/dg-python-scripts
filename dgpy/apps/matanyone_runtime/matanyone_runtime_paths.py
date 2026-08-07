"""Resolve MatAnyone runtime install root (outside Flame hook scan)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import dgpy_paths

__version__ = "0.2.1"

RUNTIME_NAME = "matanyone"
READY_NAME = "READY.json"
REPO_DIRNAME = "MatAnyone"
VENV_DIRNAME = "venv"
MINIFORGE_DIRNAME = "miniforge3"

LogFn = Callable[[str], None]


def _dgpy(root: Path | None = None) -> Path:
    return root or dgpy_paths.dgpy_root()


def legacy_runtime_roots(root: Path | None = None) -> list[Path]:
    """Former locations that Flame still scans (must be emptied)."""
    dgpy = _dgpy(root)
    python_dir = dgpy.parent
    return [
        # Original: under dgpy/ (worst — inside package tree)
        dgpy / "runtimes" / RUNTIME_NAME,
        # 0.1.7: beside dgpy but still under …/python/ (still scanned)
        python_dir / "dgpy_runtimes" / RUNTIME_NAME,
    ]


def legacy_runtime_root(root: Path | None = None) -> Path:
    """Oldest legacy path (compat for callers)."""
    return legacy_runtime_roots(root)[0]


def runtime_root(root: Path | None = None) -> Path:
    """Outside Flame's python hook tree entirely.

    dgpy is typically:
      /opt/Autodesk/shared/python/dgpy  →  /opt/Autodesk/shared/dgpy_runtimes/matanyone
      ~/flame/python/dgpy               →  ~/flame/dgpy_runtimes/matanyone

    Anything under …/python/ is scanned for hooks.
    """
    dgpy = _dgpy(root)
    python_dir = dgpy.parent
    if python_dir.name == "python":
        return python_dir.parent / "dgpy_runtimes" / RUNTIME_NAME
    # Unusual layout: go one level above dgpy anyway
    return dgpy.parent.parent / "dgpy_runtimes" / RUNTIME_NAME


def _rewrite_ready_paths(dest: Path, *, old_prefix: Path, log: LogFn | None = None) -> None:
    """Fix absolute paths inside READY.json after a directory move."""
    ready = dest / READY_NAME
    if not ready.is_file():
        return
    try:
        data = json.loads(ready.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    old_s = str(old_prefix)
    new_s = str(dest)
    changed = False
    for key in ("python", "host_python", "repo", "inference_script", "sam_script"):
        raw = str(data.get(key) or "")
        if old_s in raw:
            data[key] = raw.replace(old_s, new_s, 1)
            changed = True
    if changed:
        ready.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if log:
            log(f"Updated READY.json paths after migrate → {dest}")


def migrate_legacy_runtime_if_needed(*, log: LogFn | None = None) -> Path:
    """Move any scanned legacy location → outside …/python/."""
    dest = runtime_root()
    for legacy in legacy_runtime_roots():
        if not legacy.exists():
            continue
        if legacy.resolve() == dest.resolve():
            continue
        if dest.exists():
            if log:
                log(
                    f"Legacy runtime still at {legacy} while {dest} exists. "
                    f"Delete the legacy folder so Flame stops scanning it."
                )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if log:
            log(
                "Migrating MatAnyone runtime out of Flame python scan path:\n"
                f"  {legacy}\n→ {dest}"
            )
        shutil.move(str(legacy), str(dest))
        _rewrite_ready_paths(dest, old_prefix=legacy, log=log)
        # Clean empty parents (runtimes/, dgpy_runtimes/ under python/)
        for parent in (legacy.parent,):
            try:
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
        for legacy in legacy_runtime_roots(root):
            if (legacy / READY_NAME).is_file():
                migrate_legacy_runtime_if_needed()
                path = ready_path(root)
                break
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
