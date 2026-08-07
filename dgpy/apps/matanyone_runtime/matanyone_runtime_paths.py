"""Resolve MatAnyone 2 runtime install root (outside Flame hook scan)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import dgpy_paths

__version__ = "0.4.0"

RUNTIME_NAME = "matanyone"
READY_NAME = "READY.json"
REPO_DIRNAME = "MatAnyone2"
LEGACY_REPO_DIRNAME = "MatAnyone"  # MatAnyone v1 tree (remove on upgrade)
INFERENCE_SCRIPT_NAME = "inference_matanyone2.py"
ENGINE_ID = "matanyone2"
VENV_DIRNAME = "venv"
MINIFORGE_DIRNAME = "miniforge3"
SAM2_REPO_DIRNAME = "sam2"
SAM2_CKPT_DIRNAME = "checkpoints"
SAM2_CKPT_NAME = "sam2.1_hiera_large.pt"
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"

LogFn = Callable[[str], None]


def _dgpy(root: Path | None = None) -> Path:
    return root or dgpy_paths.dgpy_root()


def legacy_runtime_roots(root: Path | None = None) -> list[Path]:
    """Former locations that Flame still scans (must be emptied)."""
    dgpy = _dgpy(root)
    python_dir = dgpy.parent
    return [
        dgpy / "runtimes" / RUNTIME_NAME,
        python_dir / "dgpy_runtimes" / RUNTIME_NAME,
    ]


def legacy_runtime_root(root: Path | None = None) -> Path:
    return legacy_runtime_roots(root)[0]


def runtime_root(root: Path | None = None) -> Path:
    """Outside Flame's python hook tree entirely.

    dgpy is typically:
      /opt/Autodesk/shared/python/dgpy  →  /opt/Autodesk/shared/dgpy_runtimes/matanyone
      ~/flame/python/dgpy               →  ~/flame/dgpy_runtimes/matanyone
    """
    dgpy = _dgpy(root)
    python_dir = dgpy.parent
    if python_dir.name == "python":
        return python_dir.parent / "dgpy_runtimes" / RUNTIME_NAME
    return dgpy.parent.parent / "dgpy_runtimes" / RUNTIME_NAME


def _rewrite_ready_paths(dest: Path, *, old_prefix: Path, log: LogFn | None = None) -> None:
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


def legacy_repo_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / LEGACY_REPO_DIRNAME


def venv_python(root: Path | None = None) -> Path | None:
    base = runtime_root(root) / VENV_DIRNAME
    for rel in ("bin/python", "bin/python3", "Scripts/python.exe"):
        candidate = base / rel
        if candidate.is_file():
            return candidate
    return None


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


def engine_id(root: Path | None = None) -> str:
    return str(load_ready(root).get("engine") or "").strip()


def needs_matanyone2_upgrade(root: Path | None = None) -> bool:
    """True if a READY exists but it is not MatAnyone 2."""
    path = ready_path(root)
    if not path.is_file():
        # leftover v1 repo without valid READY still needs upgrade messaging
        return legacy_repo_dir(root).exists() and not (
            repo_dir(root) / INFERENCE_SCRIPT_NAME
        ).is_file()
    return engine_id(root) != ENGINE_ID


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
    if engine_id(root) != ENGINE_ID:
        return False
    infer = inference_script(root)
    if infer is None or not infer.is_file():
        return False
    py = resolve_python(root)
    return py is not None and Path(py).is_file()


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
    candidate = repo_dir(root) / INFERENCE_SCRIPT_NAME
    return candidate if candidate.is_file() else None


def sam_script(root: Path | None = None) -> Path | None:
    data = load_ready(root)
    raw = str(data.get("sam_script") or "").strip()
    if raw and Path(raw).is_file():
        return Path(raw)
    candidate = runtime_root(root) / "sam2_make_mask.py"
    return candidate if candidate.is_file() else None


def sam2_repo_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / SAM2_REPO_DIRNAME


def sam2_checkpoint_path(root: Path | None = None) -> Path:
    data = load_ready(root)
    sam2 = data.get("sam2") if isinstance(data.get("sam2"), dict) else {}
    raw = str((sam2 or {}).get("checkpoint") or "").strip()
    if raw:
        return Path(raw)
    return runtime_root(root) / SAM2_CKPT_DIRNAME / SAM2_CKPT_NAME


def sam2_config_id(root: Path | None = None) -> str:
    data = load_ready(root)
    sam2 = data.get("sam2") if isinstance(data.get("sam2"), dict) else {}
    raw = str((sam2 or {}).get("config") or "").strip()
    return raw or SAM2_CONFIG


def is_sam2_ready(root: Path | None = None) -> bool:
    """True when MatAnyone 2 READY plus SAM2 package + checkpoint are present."""
    if not is_ready(root):
        return False
    data = load_ready(root)
    sam2 = data.get("sam2")
    if not isinstance(sam2, dict) or not sam2.get("ready"):
        return False
    ckpt = sam2_checkpoint_path(root)
    if not ckpt.is_file() or ckpt.stat().st_size < 1_000_000:
        return False
    helper = sam_script(root)
    return helper is not None and helper.is_file()
