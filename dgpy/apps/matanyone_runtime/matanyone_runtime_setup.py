"""Install / remove MatAnyone conda-or-venv runtime under dgpy/runtimes/."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import matanyone_runtime_paths as paths

__version__ = "0.1.5"

LogFn = Callable[[str], None]
StepFn = Callable[[int, int, str], None]

REPO_URL = "https://github.com/pq-yang/MatAnyone.git"
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
MIN_PY = (3, 8)

# Deterministic steps for the progress bar (weights are relative).
SETUP_STEPS: list[tuple[str, int]] = [
    ("Prepare folders", 1),
    ("Ensure Miniforge Python >= 3.8", 3),
    ("Clone MatAnyone repository", 2),
    ("Create Python venv", 1),
    ("Upgrade pip / wheel", 1),
    ("Install PyTorch (largest download)", 8),
    ("Install MatAnyone package", 3),
    ("Install image helpers (Pillow/OpenCV)", 1),
    ("Write READY marker", 1),
]


def setup_step_count() -> int:
    return len(SETUP_STEPS)


def setup_step_label(index: int) -> str:
    if 0 <= index < len(SETUP_STEPS):
        return SETUP_STEPS[index][0]
    return ""


def _log(cb: LogFn | None, message: str) -> None:
    if cb:
        cb(message)


def _step(cb: StepFn | None, index: int, label: str | None = None) -> None:
    if cb:
        cb(index, len(SETUP_STEPS), label or setup_step_label(index))


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    log: LogFn | None = None,
) -> None:
    _log(log, "$ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip()
        if text:
            _log(log, text)
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {' '.join(cmd)}")


def _which(name: str) -> str | None:
    return shutil.which(name)


def _python_version(executable: str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [
                executable,
                "-c",
                "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
        major_s, minor_s = out.split(".", 1)
        return int(major_s), int(minor_s)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _is_flame_python(executable: str) -> bool:
    """Flame embedded / Autodesk app Python must not host MatAnyone."""
    lower = executable.replace("\\", "/").lower()
    markers = (
        "/flamefamily_",
        "/flame/",
        "/flare/",
        "/opt/autodesk/flame",
        "python_packages",
        "/flicicw",
    )
    return any(m in lower for m in markers)


def try_find_host_python(*, log: LogFn | None = None) -> str | None:
    """Return an isolated Python >=3.8, or None.

    Order (no system package install):
    1. MATANYONE_PYTHON (explicit override)
    2. Bundled Miniforge under runtimes/matanyone/
    """
    candidates: list[str] = []
    env_py = (os.environ.get("MATANYONE_PYTHON") or "").strip()
    if env_py:
        candidates.append(env_py)

    bundled = paths.miniforge_python()
    if bundled is not None:
        candidates.append(str(bundled))

    seen: set[str] = set()
    for raw in candidates:
        path = str(Path(raw).expanduser())
        if path in seen:
            continue
        seen.add(path)
        ver = _python_version(path)
        flame = _is_flame_python(path)
        if ver is None:
            continue
        if flame:
            _log(log, f"Skip Flame Python: {path} ({ver[0]}.{ver[1]})")
            continue
        if ver < MIN_PY:
            _log(log, f"Skip too-old Python: {path} ({ver[0]}.{ver[1]})")
            continue
        _log(log, f"Using Python: {path} ({ver[0]}.{ver[1]})")
        return path
    return None


def find_host_python(*, log: LogFn | None = None) -> str:
    """Return Python >=3.8 via Miniforge (or MATANYONE_PYTHON)."""
    return ensure_host_python(log=log)


def _miniforge_installer() -> tuple[str, str]:
    """Return (url, filename) for this platform."""
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("amd64",):
        machine = "x86_64"
    if machine in ("arm64",) and system == "linux":
        machine = "aarch64"

    if system == "linux" and machine in ("x86_64", "aarch64"):
        name = f"Miniforge3-Linux-{machine}.sh"
    elif system == "darwin" and machine in ("x86_64", "arm64"):
        name = f"Miniforge3-MacOSX-{machine}.sh"
    else:
        raise RuntimeError(
            f"Unsupported platform for Miniforge bootstrap: {system}/{machine}"
        )
    url = (
        "https://github.com/conda-forge/miniforge/releases/latest/download/"
        + name
    )
    return url, name


def _install_python_via_miniforge(*, log: LogFn | None = None) -> str:
    """Download Miniforge into runtimes/matanyone (no root / no OS packages)."""
    import urllib.request

    root = paths.runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    existing = paths.miniforge_python()
    if existing is not None:
        ver = _python_version(str(existing))
        if ver is not None and ver >= MIN_PY:
            _log(log, f"Reusing bundled Miniforge: {existing}")
            return str(existing)

    url, name = _miniforge_installer()
    installer = root / name
    prefix = paths.miniforge_root()
    if prefix.exists():
        _log(log, f"Removing incomplete Miniforge: {prefix}")
        shutil.rmtree(prefix)

    _log(log, f"Downloading Miniforge: {url}")
    try:
        urllib.request.urlretrieve(url, str(installer))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to download Miniforge ({url}): {exc}\n"
            "Check network / GitHub access from this machine."
        ) from exc

    bash = _which("bash") or "/bin/bash"
    _run(
        [bash, str(installer), "-b", "-p", str(prefix)],
        log=log,
    )
    try:
        installer.unlink()
    except OSError:
        pass

    py = paths.miniforge_python()
    if py is None:
        raise RuntimeError(f"Miniforge installed but python missing under {prefix}")
    ver = _python_version(str(py))
    if ver is None or ver < MIN_PY:
        raise RuntimeError(f"Miniforge python unusable: {py} ({ver})")
    _log(log, f"Bundled Miniforge Python ready: {py} ({ver[0]}.{ver[1]})")
    return str(py)


def ensure_host_python(*, log: LogFn | None = None) -> str:
    """Find or install Miniforge Python >= 3.8 under the runtime folder.

    Does not install OS packages (dnf/yum) and does not use Flame Python.
    Override with MATANYONE_PYTHON if needed.
    """
    found = try_find_host_python(log=log)
    if found:
        return found

    _log(
        log,
        "No bundled Miniforge yet — downloading into "
        f"{paths.miniforge_root()} (no system Python install).",
    )
    return _install_python_via_miniforge(log=log)


def _patch_matanyone_deps(repo: Path, *, log: LogFn | None = None) -> None:
    """Replace abandoned cchardet (fails on Py3.10+) with faust-cchardet."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        _log(log, f"No pyproject.toml to patch under {repo}")
        return
    text = pyproject.read_text(encoding="utf-8")
    original = text
    for old, new in (
        ("'cchardet >= 2.1.7'", "'faust-cchardet >= 2.1.18'"),
        ('"cchardet >= 2.1.7"', '"faust-cchardet >= 2.1.18"'),
        ("cchardet >= 2.1.7", "faust-cchardet >= 2.1.18"),
        ("'cchardet>=2.1.7'", "'faust-cchardet>=2.1.18'"),
    ):
        text = text.replace(old, new)
    if text == original:
        _log(log, "MatAnyone pyproject.toml: no cchardet pin to patch")
        return
    pyproject.write_text(text, encoding="utf-8")
    _log(log, "Patched MatAnyone deps: cchardet → faust-cchardet (Py3.10+ build fix)")


def _venv_is_usable(venv_python: Path | None, *, log: LogFn | None = None) -> bool:
    if venv_python is None or not venv_python.is_file():
        return False
    ver = _python_version(str(venv_python))
    if ver is None or ver < MIN_PY:
        _log(
            log,
            f"Existing venv Python is unusable ({ver}); will recreate.",
        )
        return False
    return True


def _write_sam_helper(dest: Path) -> None:
    """Minimal SAM / SAM2 point-mask helper used when Mask source = SAM2."""
    dest.write_text(
        '''#!/usr/bin/env python3
"""Make a binary mask PNG from an RGB image + foreground click points.

Tries segment_anything / sam2 if installed; otherwise fails with a clear error.
Usage:
  python sam2_make_mask.py --image frame.png --points "x1,y1;x2,y2" --out mask.png
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def _parse_points(raw: str):
    pts = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        x_s, y_s = part.split(",", 1)
        pts.append((float(x_s), float(y_s)))
    if not pts:
        raise SystemExit("No points given")
    return pts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--points", required=True, help="x,y;x,y … foreground clicks")
    ap.add_argument("--out", required=True)
    ap.add_argument("--checkpoint", default="", help="Optional SAM checkpoint path")
    args = ap.parse_args()

    image = np.array(Image.open(args.image).convert("RGB"))
    points = _parse_points(args.points)
    point_coords = np.array(points, dtype=np.float32)
    point_labels = np.ones(len(points), dtype=np.int32)

    mask = None
    err = None
    try:
        from segment_anything import SamPredictor, sam_model_registry

        ckpt = args.checkpoint or os.environ.get("SAM_CHECKPOINT", "")
        if not ckpt or not Path(ckpt).is_file():
            raise RuntimeError(
                "SAM checkpoint missing. Set --checkpoint or SAM_CHECKPOINT."
            )
        sam = sam_model_registry["vit_h"](checkpoint=ckpt)
        predictor = SamPredictor(sam)
        predictor.set_image(image)
        masks, scores, _ = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True,
        )
        mask = masks[int(np.argmax(scores))]
    except Exception as exc:  # noqa: BLE001
        err = exc
        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            ckpt = args.checkpoint or os.environ.get("SAM2_CHECKPOINT", "")
            cfg = os.environ.get("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml")
            if not ckpt or not Path(ckpt).is_file():
                raise RuntimeError(
                    "SAM2 checkpoint missing. Set --checkpoint or SAM2_CHECKPOINT."
                )
            predictor = SAM2ImagePredictor(build_sam2(cfg, ckpt))
            predictor.set_image(image)
            masks, scores, _ = predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                multimask_output=True,
            )
            mask = masks[int(np.argmax(scores))]
            err = None
        except Exception as exc2:  # noqa: BLE001
            err = exc2 if err is None else err

    if mask is None:
        print(
            "SAM/SAM2 mask failed. Install segment_anything (or sam2) into the "
            f"MatAnyone runtime and provide a checkpoint.\\nLast error: {err}",
            file=sys.stderr,
        )
        return 2

    out = (mask.astype(np.uint8) * 255)
    Image.fromarray(out, mode="L").save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    try:
        dest.chmod(0o755)
    except OSError:
        pass


def setup_runtime(
    *,
    log: LogFn | None = None,
    step: StepFn | None = None,
    force: bool = False,
) -> Path:
    """Clone MatAnyone, create venv, install deps, write READY.json."""
    root = paths.runtime_root()

    _step(step, 0)
    root.mkdir(parents=True, exist_ok=True)
    if paths.is_ready() and not force:
        existing = paths.resolve_python()
        if existing and _venv_is_usable(Path(existing), log=log):
            _log(log, f"Already ready: {paths.ready_path()}")
            _step(step, len(SETUP_STEPS) - 1, "Already ready")
            return root
        _log(
            log,
            "READY exists but Python is too old / missing — repairing.",
        )
        force = True

    if force and root.exists():
        _log(log, f"Removing existing runtime: {root}")
        shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)

    _step(step, 1)
    host_py = ensure_host_python(log=log)

    _step(step, 2)
    repo = paths.repo_dir()
    if not (repo / "inference_matanyone.py").is_file():
        git = _which("git")
        if not git:
            raise RuntimeError("git not found on PATH")
        _run([git, "clone", "--depth", "1", REPO_URL, str(repo)], log=log)
    else:
        _log(log, f"Repo already present: {repo}")
    _patch_matanyone_deps(repo, log=log)

    _step(step, 3)
    venv_dir = root / paths.VENV_DIRNAME
    py_bin = paths.venv_python()
    if not _venv_is_usable(py_bin, log=log):
        if venv_dir.exists():
            _log(log, f"Removing broken/old venv: {venv_dir}")
            shutil.rmtree(venv_dir)
        _run([host_py, "-m", "venv", str(venv_dir)], log=log)
        py_bin = paths.venv_python()
    else:
        _log(log, f"Reusing venv Python: {py_bin}")

    if py_bin is None:
        raise RuntimeError(f"venv python not found under {venv_dir}")
    ver = _python_version(str(py_bin))
    if ver is None or ver < MIN_PY:
        raise RuntimeError(
            f"venv Python is still < {MIN_PY[0]}.{MIN_PY[1]}: {py_bin} ({ver})"
        )

    pip = [str(py_bin), "-m", "pip"]
    _step(step, 4)
    _run(pip + ["install", "--upgrade", "pip", "wheel", "setuptools"], log=log)

    _step(step, 5)
    _log(
        log,
        "Note: PyTorch download is usually the slowest step "
        "(often several minutes; can exceed 15–30 min on slow links).",
    )
    try:
        _run(
            pip
            + [
                "install",
                "torch",
                "torchvision",
                "--index-url",
                TORCH_INDEX,
            ],
            log=log,
        )
    except RuntimeError:
        _log(log, "cu124 torch install failed; trying default PyPI torch")
        _run(pip + ["install", "torch", "torchvision"], log=log)

    _step(step, 6)
    # Preinstall maintained fork so pip does not try to compile abandoned cchardet.
    _run(pip + ["install", "faust-cchardet>=2.1.18"], log=log)
    _run(pip + ["install", "-e", str(repo)], cwd=repo, log=log)

    _step(step, 7)
    _run(pip + ["install", "Pillow", "numpy", "opencv-python-headless"], log=log)

    _step(step, 8)
    sam_helper = root / "sam2_make_mask.py"
    _write_sam_helper(sam_helper)

    infer = repo / "inference_matanyone.py"
    if not infer.is_file():
        raise RuntimeError(f"Missing inference script: {infer}")

    ready = {
        "version": __version__,
        "python": str(py_bin),
        "host_python": host_py,
        "repo": str(repo),
        "inference_script": str(infer),
        "sam_script": str(sam_helper),
        "max_size_default": 1080,
    }
    paths.ready_path().write_text(
        json.dumps(ready, indent=2) + "\n", encoding="utf-8"
    )
    _log(log, f"READY written: {paths.ready_path()}")
    return root


def remove_runtime(*, log: LogFn | None = None) -> None:
    root = paths.runtime_root()
    if not root.exists():
        _log(log, f"Nothing to remove: {root}")
        return
    _log(log, f"Removing {root}")
    shutil.rmtree(root)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="MatAnyone runtime setup")
    ap.add_argument("action", choices=("setup", "remove", "status"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    def _print(msg: str) -> None:
        print(msg)

    def _print_step(index: int, total: int, label: str) -> None:
        print(f"[step {index + 1}/{total}] {label}")

    if args.action == "status":
        print(f"root={paths.runtime_root()}")
        print(f"ready={paths.is_ready()}")
        print(f"python={paths.resolve_python()}")
        return 0
    if args.action == "remove":
        remove_runtime(log=_print)
        return 0
    setup_runtime(log=_print, step=_print_step, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
