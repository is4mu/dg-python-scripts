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

__version__ = "0.11.5"

LogFn = Callable[[str], None]
StepFn = Callable[[int, int, str], None]

REPO_URL = "https://github.com/pq-yang/MatAnyone2.git"
TORCH_INDEXES = (
    "https://download.pytorch.org/whl/cu124",
    "https://download.pytorch.org/whl/cu128",
)
WEIGHT_URL = (
    "https://github.com/pq-yang/MatAnyone2/releases/download/v1.0.0/matanyone2.pth"
)
MIN_PY = (3, 10)

# Deterministic steps for the progress bar.
SETUP_STEPS: list[str] = [
    "Prepare folders",
    "Ensure Miniforge Python >= 3.10",
    "Clone MatAnyone 2 repository",
    "Create Python venv",
    "Upgrade pip / wheel",
    "Install PyTorch (largest download)",
    "Install MatAnyone 2 package",
    "Fetch weights / image helpers",
    "Write READY marker",
]


def setup_step_count() -> int:
    return len(SETUP_STEPS)


def setup_step_label(index: int) -> str:
    if 0 <= index < len(SETUP_STEPS):
        return SETUP_STEPS[index]
    return ""


def _log(cb: LogFn | None, message: str) -> None:
    if cb:
        cb(message)


def _step(cb: StepFn | None, index: int, label: str | None = None) -> None:
    if cb:
        cb(index, len(SETUP_STEPS), label or setup_step_label(index))


def _remove_step(
    cb: StepFn | None, index: int, total: int, label: str
) -> None:
    if cb:
        cb(index, total, label)


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
    """Return an isolated Python >=3.10, or None.

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
    """Find or install Miniforge Python >= 3.10 under the runtime folder.

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
    _log(log, "Patched MatAnyone 2 deps: cchardet → faust-cchardet (Py3.10+ build fix)")


_INFER_PATCH_MARK = "# dgpy-patch: max_size-mask-resize-v1"


def patch_inference_matanyone2(
    repo: Path | None = None,
    *,
    log: LogFn | None = None,
) -> bool:
    """Fix upstream UnboundLocalError on mask resize when video is already ≤ max_size.

    Upstream ``inference_matanyone2.py`` sets ``new_h``/``new_w`` only when the
    video short side exceeds ``max_size``, but always resizes the mask with those
    names when ``max_size > 0``. Our jobs always pass ``--max_size 1080`` and the
    export is already short-side-capped, so Forward/Backward crash every time.
    """
    import re

    root = repo or paths.repo_dir()
    path = root / paths.INFERENCE_SCRIPT_NAME
    if not path.is_file():
        _log(log, f"Inference script missing, skip patch: {path}")
        return False
    text = path.read_text(encoding="utf-8")
    if _INFER_PATCH_MARK in text:
        return False

    new_resize = (
        "    # resize if needed\n"
        f"    {_INFER_PATCH_MARK}\n"
        "    h, w = vframes.shape[-2:]\n"
        "    if max_size > 0:\n"
        "        min_side = min(h, w)\n"
        "        if min_side > max_size:\n"
        "            h = int(h / min_side * max_size)\n"
        "            w = int(w / min_side * max_size)\n"
        "            vframes = F.interpolate(vframes, size=(h, w), mode=\"area\")\n"
        "            print(f'Resize to {h}x{w} for processing...')\n"
    )
    new_mask = (
        "    # Match mask spatial size to (possibly resized) video frames.\n"
        "    if mask.shape[-2] != h or mask.shape[-1] != w:\n"
        "        mask = F.interpolate(\n"
        "            mask.unsqueeze(0).unsqueeze(0), size=(h, w), mode=\"nearest\"\n"
        "        )[0, 0]\n"
    )

    resize_re = re.compile(
        r"    # resize if needed\n"
        r"    if max_size > 0:\n"
        r"        h, w = vframes\.shape\[-2:\]\n"
        r"        min_side = min\(h, w\)\n"
        r"        if min_side > max_size:\n"
        r"            new_h = int\(h / min_side \* max_size\)\n"
        r"            new_w = int\(w / min_side \* max_size\)\n"
        r"            vframes = F\.interpolate\(vframes, size=\(new_h, new_w\), "
        r"mode=[\"']area[\"']\)\n"
        r"            print\(f'Resize to \{new_h\}x\{new_w\} for processing\.\.\.'\)\n"
        r"[ \t]*\n?",
    )
    mask_re = re.compile(
        r"    if max_size > 0:  # resize needed\n"
        r"        mask = F\.interpolate\(mask\.unsqueeze\(0\)\.unsqueeze\(0\), "
        r"size=\(new_h, new_w\), mode=[\"']nearest[\"']\)\n"
        r"        mask = mask\[0,\s*0\]\n"
    )

    text2, n1 = resize_re.subn(new_resize + "\n", text, count=1)
    text3, n2 = mask_re.subn(new_mask, text2, count=1)
    if n1 != 1 or n2 != 1:
        _log(
            log,
            "inference_matanyone2.py layout unexpected; cannot apply "
            f"max_size mask-resize patch automatically (resize={n1}, mask={n2})",
        )
        return False

    path.write_text(text3, encoding="utf-8")
    _log(log, f"Patched {path.name}: fix max_size mask resize (new_h UnboundLocalError)")
    return True


_VIDEO_FALLBACK_MARK = "# dgpy-patch: opencv-video-fallback-v1"


def patch_inference_utils_read_video(
    repo: Path | None = None,
    *,
    log: LogFn | None = None,
) -> bool:
    """Fall back to OpenCV when ``torchvision.io.read_video`` is missing.

    torchvision ≥0.26 removed OSS ``read_video`` (Mac fresh installs hit this).
    Linux with older torchvision keeps the original API path via getattr.
    """
    root = repo or paths.repo_dir()
    path = root / "matanyone2" / "utils" / "inference_utils.py"
    if not path.is_file():
        _log(log, f"inference_utils.py missing, skip video patch: {path}")
        return False
    text = path.read_text(encoding="utf-8")
    if _VIDEO_FALLBACK_MARK in text:
        return False

    old = (
        "        frames, _, info = torchvision.io.read_video("
        "filename=frame_root, pts_unit='sec', output_format='TCHW') # RGB\n"
        "        fps = info['video_fps']\n"
    )
    if old not in text:
        # Slight whitespace variants
        import re

        old_re = re.compile(
            r"[ \t]*frames, _, info = torchvision\.io\.read_video\("
            r"filename=frame_root, pts_unit=['\"]sec['\"], "
            r"output_format=['\"]TCHW['\"]\)[^\n]*\n"
            r"[ \t]*fps = info\[['\"]video_fps['\"]\]\n"
        )
        if not old_re.search(text):
            _log(
                log,
                "inference_utils.py layout unexpected; "
                "cannot apply opencv video fallback",
            )
            return False
        new = (
            "        read_video = getattr(torchvision.io, \"read_video\", None)\n"
            "        if read_video is not None:\n"
            "            frames, _, info = read_video(\n"
            "                filename=frame_root, pts_unit=\"sec\", "
            "output_format=\"TCHW\")  # RGB\n"
            "            fps = info[\"video_fps\"]\n"
            "        else:\n"
            f"            {_VIDEO_FALLBACK_MARK}\n"
            "            # torchvision>=0.26 removed read_video; OpenCV RGB TCHW.\n"
            "            cap = cv2.VideoCapture(frame_root)\n"
            "            if not cap.isOpened():\n"
            "                raise RuntimeError(f\"Cannot open video: {frame_root}\")\n"
            "            fps_v = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)\n"
            "            fps = fps_v if fps_v > 1e-3 else 24.0\n"
            "            buf = []\n"
            "            while True:\n"
            "                ok, bgr = cap.read()\n"
            "                if not ok:\n"
            "                    break\n"
            "                buf.append(bgr[..., ::-1])  # BGR→RGB\n"
            "            cap.release()\n"
            "            if not buf:\n"
            "                raise RuntimeError(f\"No frames in video: {frame_root}\")\n"
            "            frames = torch.from_numpy(\n"
            "                np.ascontiguousarray(np.stack(buf))\n"
            "            ).permute(0, 3, 1, 2).contiguous()  # TCHW uint8\n"
        )
        text2, n = old_re.subn(new, text, count=1)
        if n != 1:
            _log(log, "inference_utils.py: video fallback patch failed")
            return False
        path.write_text(text2, encoding="utf-8")
        _log(log, f"Patched {path.relative_to(root)}: OpenCV read_video fallback")
        return True

    new = (
        "        read_video = getattr(torchvision.io, \"read_video\", None)\n"
        "        if read_video is not None:\n"
        "            frames, _, info = read_video(\n"
        "                filename=frame_root, pts_unit='sec', "
        "output_format='TCHW') # RGB\n"
        "            fps = info['video_fps']\n"
        "        else:\n"
        f"            {_VIDEO_FALLBACK_MARK}\n"
        "            # torchvision>=0.26 removed read_video; OpenCV RGB TCHW.\n"
        "            cap = cv2.VideoCapture(frame_root)\n"
        "            if not cap.isOpened():\n"
        "                raise RuntimeError(f\"Cannot open video: {frame_root}\")\n"
        "            fps_v = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)\n"
        "            fps = fps_v if fps_v > 1e-3 else 24.0\n"
        "            buf = []\n"
        "            while True:\n"
        "                ok, bgr = cap.read()\n"
        "                if not ok:\n"
        "                    break\n"
        "                buf.append(bgr[..., ::-1])  # BGR→RGB\n"
        "            cap.release()\n"
        "            if not buf:\n"
        "                raise RuntimeError(f\"No frames in video: {frame_root}\")\n"
        "            frames = torch.from_numpy(\n"
        "                np.ascontiguousarray(np.stack(buf))\n"
        "            ).permute(0, 3, 1, 2).contiguous()  # TCHW uint8\n"
    )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    _log(log, f"Patched {path.relative_to(root)}: OpenCV read_video fallback")
    return True


def ensure_matanyone2_patches(
    repo: Path | None = None,
    *,
    log: LogFn | None = None,
) -> list[str]:
    """Apply all known MatAnyone2 source patches; return labels applied."""
    applied: list[str] = []
    if patch_inference_matanyone2(repo, log=log):
        applied.append("max_size-mask-resize")
    if patch_inference_utils_read_video(repo, log=log):
        applied.append("opencv-video-fallback")
    return applied


def _purge_matanyone_v1(root: Path, *, log: LogFn | None = None) -> None:
    """Remove leftover MatAnyone v1 clone so Flame/operators do not mix engines."""
    legacy = root / paths.LEGACY_REPO_DIRNAME
    if legacy.exists():
        _log(log, f"Removing MatAnyone v1 tree: {legacy}")
        shutil.rmtree(legacy)


def _ensure_weights(repo: Path, *, log: LogFn | None = None) -> None:
    """Best-effort download of matanyone2.pth (also auto-fetched on first infer)."""
    import urllib.request

    dest_dir = repo / "pretrained_models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "matanyone2.pth"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        _log(log, f"Weights already present: {dest}")
        return
    _log(log, f"Downloading weights: {WEIGHT_URL}")
    try:
        urllib.request.urlretrieve(WEIGHT_URL, str(dest))
        _log(log, f"Weights saved: {dest}")
    except Exception as exc:  # noqa: BLE001
        _log(
            log,
            f"Weight download skipped ({exc}). "
            "First inference may download automatically.",
        )


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
    """SAM2 point-mask helper (runs inside the isolated runtime venv)."""
    dest.write_text(
        '''#!/usr/bin/env python3
"""Make a binary mask PNG from an RGB image + click points (SAM2).

Usage:
  python sam2_make_mask.py --image frame.png --points "x1,y1;x2,y2,0" --out mask.png \\
      --checkpoint /path/to/sam2.1_hiera_large.pt \\
      --config configs/sam2.1/sam2.1_hiera_l.yaml

Points: ``x,y`` or ``x,y,label`` (label 1=positive / 0=negative; default 1).
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import torch
from PIL import Image


def _unshadow_sam2_package() -> None:
    """Drop this script's directory from sys.path.

    The helper lives under …/dgpy_runtimes/matanyone/. A clone folder named
    ``sam2`` beside it would otherwise win on sys.path[0] and shadow the
    installed ``sam2`` package (Meta's build_sam raises RuntimeError).
    """
    script_dir = str(Path(__file__).resolve().parent)
    while script_dir in sys.path:
        sys.path.remove(script_dir)
    # Prefer empty cwd entry over a shadowed runtime root.
    cwd = os.getcwd()
    if cwd == script_dir or Path(cwd).name in ("sam2", "sam2_src"):
        while "" in sys.path:
            sys.path.remove("")
        if cwd in sys.path:
            sys.path.remove(cwd)


def _parse_points(raw: str):
    pts = []
    labels = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.split(",")
        if len(bits) == 2:
            x_s, y_s = bits
            label = 1
        elif len(bits) == 3:
            x_s, y_s, lab_s = bits
            label = int(lab_s)
        else:
            raise SystemExit(f"Bad point token: {part!r} (want x,y or x,y,label)")
        if label not in (0, 1):
            raise SystemExit(f"label must be 0 or 1, got {label}")
        pts.append((float(x_s), float(y_s)))
        labels.append(label)
    if not pts:
        raise SystemExit("No points given")
    if 1 not in labels:
        raise SystemExit("Need at least one positive point (label=1)")
    return pts, labels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument(
        "--points",
        required=True,
        help="x,y or x,y,label; … (label 1=fg / 0=bg; default 1)",
    )
    ap.add_argument("--out", required=True)
    ap.add_argument("--checkpoint", default=os.environ.get("SAM2_CHECKPOINT", ""))
    ap.add_argument(
        "--config",
        default=os.environ.get("SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_l.yaml"),
    )
    args = ap.parse_args()

    ckpt = str(args.checkpoint or "").strip()
    if not ckpt or not Path(ckpt).is_file():
        print(
            "SAM2 checkpoint missing. Open DGpy → Preferences… → SAM2 Setup…",
            file=sys.stderr,
        )
        return 2

    _unshadow_sam2_package()
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except Exception as exc:  # noqa: BLE001
        print(
            "sam2 package not importable in this Python. "
            "Open DGpy → Preferences… → SAM2 Setup…\\n"
            f"{exc}\\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        return 2

    try:
        image = np.array(Image.open(args.image).convert("RGB"))
        points, labels = _parse_points(args.points)
        point_coords = np.array(points, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(
            f"SAM2 device={device} ckpt={ckpt} config={args.config} "
            f"sam2_path={__import__('sam2').__path__}",
            flush=True,
        )
        predictor = SAM2ImagePredictor(build_sam2(args.config, ckpt, device=device))
        with torch.inference_mode():
            predictor.set_image(image)
            masks, scores, _ = predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                multimask_output=True,
            )
        mask = masks[int(np.argmax(scores))]
        # bool / float → binary 0/255 (float 0..1 must not use astype(uint8) alone)
        binary = (mask > 0.5).astype(np.uint8) * 255
        out = np.ascontiguousarray(binary)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out, mode="L").save(args.out)
        print(args.out)
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    try:
        dest.chmod(0o755)
    except OSError:
        pass


SAM2_REPO_URL = "https://github.com/facebookresearch/sam2.git"
SAM2_CKPT_TINY_URL = (
    "https://dl.fbaipublicfiles.com/segment_anything_2/092824/"
    "sam2.1_hiera_tiny.pt"
)

SAM2_SETUP_STEPS: list[str] = [
    "Check MatAnyone 2 runtime",
    "Clone SAM2 repository",
    "Install SAM2 into runtime venv",
    "Download SAM2.1 tiny checkpoint",
    "Write helper + READY.sam2",
]


def sam2_setup_step_count() -> int:
    return len(SAM2_SETUP_STEPS)


def sam2_setup_step_label(index: int) -> str:
    if 0 <= index < len(SAM2_SETUP_STEPS):
        return SAM2_SETUP_STEPS[index]
    return ""


def _update_ready_sam2(
    *,
    checkpoint: Path,
    checkpoint_tiny: Path,
    config: str,
    config_tiny: str,
    repo: Path,
    log: LogFn | None = None,
) -> None:
    data = paths.load_ready()
    if not data:
        raise RuntimeError("READY.json missing — open DGpy → Preferences… and run Runtime Setup first")
    data["sam2"] = {
        "ready": True,
        "repo": str(repo),
        "checkpoint": str(checkpoint),
        "checkpoint_tiny": str(checkpoint_tiny),
        "config": config,
        "config_tiny": config_tiny,
    }
    helper = paths.runtime_root() / "sam2_make_mask.py"
    data["sam_script"] = str(helper)
    paths.ready_path().write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    _log(log, f"READY.sam2 updated → tiny={checkpoint_tiny} large={checkpoint}")


def _download_ckpt(
    url: str,
    dest: Path,
    *,
    min_bytes: int,
    force: bool,
    log: LogFn | None = None,
) -> None:
    import urllib.request

    if force and dest.exists():
        try:
            dest.unlink()
        except OSError:
            pass
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        _log(log, f"Checkpoint already present: {dest}")
        return
    _log(log, f"Downloading SAM2 checkpoint: {url}")
    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        urllib.request.urlretrieve(url, str(tmp))
        tmp.replace(dest)
    except Exception as exc:  # noqa: BLE001
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise RuntimeError(f"Failed to download SAM2 checkpoint: {exc}") from exc
    _log(log, f"Checkpoint saved: {dest} ({dest.stat().st_size} bytes)")


def _tiny_ckpt_ok(root: Path | None = None) -> bool:
    ckpt = paths.sam2_checkpoint_path(root, size="tiny")
    return ckpt.is_file() and ckpt.stat().st_size >= 100_000


def setup_sam2(
    *,
    log: LogFn | None = None,
    step: StepFn | None = None,
    force: bool = False,
) -> Path:
    """Install facebookresearch/sam2 + tiny checkpoint into the MatAnyone runtime.

    Stays under dgpy_runtimes/matanyone — no OS packages, no …/python/**.
    Tiny weights are required; large is optional (kept if already present).
    """
    paths.migrate_legacy_runtime_if_needed(log=log)
    root = paths.runtime_root()

    def _s(index: int, label: str | None = None) -> None:
        if step:
            step(index, len(SAM2_SETUP_STEPS), label or sam2_setup_step_label(index))

    _s(0)
    if not paths.is_ready():
        raise RuntimeError(
            "MatAnyone 2 runtime is not ready.\n"
            "Open DGpy → Preferences… and run Runtime Setup… first."
        )
    py = paths.resolve_python()
    if not py:
        raise RuntimeError("Runtime python missing")

    if paths.is_sam2_ready() and not force:
        _log(log, f"SAM2 already ready: {paths.sam2_checkpoint_path(size='tiny')}")
        _s(len(SAM2_SETUP_STEPS) - 1, "Already ready")
        return root

    # Soft repair: previous Setup left package ready but tiny missing / not marked.
    helper_path = root / "sam2_make_mask.py"
    repo = paths.sam2_repo_dir()
    marker = repo / "sam2" / "build_sam.py"
    soft_repair = (
        not force
        and helper_path.is_file()
        and marker.is_file()
        and not _tiny_ckpt_ok()
    )
    if soft_repair:
        _s(3, "Download SAM2.1 tiny checkpoint (repair)")
        ckpt_dir = root / paths.SAM2_CKPT_DIRNAME
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        ckpt = ckpt_dir / paths.SAM2_CKPT_NAME
        ckpt_tiny = ckpt_dir / paths.SAM2_CKPT_TINY
        _download_ckpt(
            SAM2_CKPT_TINY_URL,
            ckpt_tiny,
            min_bytes=100_000,
            force=False,
            log=log,
        )
        _s(4)
        _write_sam_helper(helper_path)
        large_path = ckpt if ckpt.is_file() else ckpt_tiny
        _update_ready_sam2(
            checkpoint=large_path,
            checkpoint_tiny=ckpt_tiny,
            config=paths.SAM2_CONFIG if ckpt.is_file() else paths.SAM2_CONFIG_TINY,
            config_tiny=paths.SAM2_CONFIG_TINY,
            repo=repo,
            log=log,
        )
        if not paths.is_sam2_ready():
            raise RuntimeError("SAM2 tiny repair finished but is_sam2_ready() is still False")
        _log(log, "SAM2 tiny checkpoint repair complete")
        return root

    _s(1)
    if force and repo.exists():
        _log(log, f"Removing existing SAM2 repo: {repo}")
        shutil.rmtree(repo)
    if not marker.is_file():
        if repo.exists():
            shutil.rmtree(repo)
        git = _which("git")
        if not git:
            raise RuntimeError("git not found on PATH")
        _run([git, "clone", "--depth", "1", SAM2_REPO_URL, str(repo)], log=log)
    else:
        _log(log, f"SAM2 repo already present: {repo}")

    _s(2)
    # Avoid requiring system CUDA toolkit / nvcc for optional CUDA ops.
    env = {
        **os.environ,
        "SAM2_BUILD_CUDA": "0",
        "SAM2_BUILD_ALLOW_ERRORS": "1",
    }
    pip = [py, "-m", "pip"]
    _run(
        pip + ["install", "-e", str(repo)],
        cwd=repo,
        env=env,
        log=log,
    )

    _s(3)
    ckpt_dir = root / paths.SAM2_CKPT_DIRNAME
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / paths.SAM2_CKPT_NAME
    ckpt_tiny = ckpt_dir / paths.SAM2_CKPT_TINY
    _download_ckpt(
        SAM2_CKPT_TINY_URL,
        ckpt_tiny,
        min_bytes=100_000,
        force=force,
        log=log,
    )
    if ckpt.is_file():
        _log(log, f"Optional large checkpoint already present (kept): {ckpt}")
    else:
        _log(log, "Skipping optional large checkpoint download (tiny-only Setup)")

    _s(4)
    helper = root / "sam2_make_mask.py"
    _write_sam_helper(helper)
    large_path = ckpt if ckpt.is_file() else ckpt_tiny
    _update_ready_sam2(
        checkpoint=large_path,
        checkpoint_tiny=ckpt_tiny,
        config=paths.SAM2_CONFIG if ckpt.is_file() else paths.SAM2_CONFIG_TINY,
        config_tiny=paths.SAM2_CONFIG_TINY,
        repo=repo,
        log=log,
    )
    # Smoke import
    _run(
        [
            py,
            "-c",
            "from sam2.build_sam import build_sam2; "
            "from sam2.sam2_image_predictor import SAM2ImagePredictor; "
            "print('sam2 import ok')",
        ],
        cwd=str(repo),
        log=log,
    )
    if not paths.is_sam2_ready():
        raise RuntimeError("SAM2 Setup finished but is_sam2_ready() is still False")
    _log(log, "SAM2 Setup complete")
    return root


def setup_runtime(
    *,
    log: LogFn | None = None,
    step: StepFn | None = None,
    force: bool = False,
) -> Path:
    """Clone MatAnyone 2, create venv, install deps, write READY.json."""
    paths.migrate_legacy_runtime_if_needed(log=log)
    root = paths.runtime_root()

    _step(step, 0)
    root.mkdir(parents=True, exist_ok=True)
    if paths.is_ready() and not force:
        existing = paths.resolve_python()
        if existing and _venv_is_usable(Path(existing), log=log):
            _log(log, f"Already ready (MatAnyone 2): {paths.ready_path()}")
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
    else:
        _purge_matanyone_v1(root, log=log)
        # Stale READY from MatAnyone v1
        ready = paths.ready_path()
        if ready.is_file() and paths.engine_id() != paths.ENGINE_ID:
            _log(log, f"Removing stale READY (engine={paths.engine_id()!r})")
            try:
                ready.unlink()
            except OSError:
                pass

    _step(step, 1)
    host_py = ensure_host_python(log=log)

    _step(step, 2)
    repo = paths.repo_dir()
    infer_name = paths.INFERENCE_SCRIPT_NAME
    if not (repo / infer_name).is_file():
        if repo.exists():
            _log(log, f"Removing incomplete repo: {repo}")
            shutil.rmtree(repo)
        git = _which("git")
        if not git:
            raise RuntimeError("git not found on PATH")
        _run([git, "clone", "--depth", "1", REPO_URL, str(repo)], log=log)
    else:
        _log(log, f"Repo already present: {repo}")
    _patch_matanyone_deps(repo, log=log)
    patch_inference_matanyone2(repo, log=log)
    patch_inference_utils_read_video(repo, log=log)

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
    torch_ok = False
    last_err: Exception | None = None
    for index_url in TORCH_INDEXES:
        try:
            _run(
                pip
                + [
                    "install",
                    "torch",
                    "torchvision",
                    "--index-url",
                    index_url,
                ],
                log=log,
            )
            torch_ok = True
            break
        except RuntimeError as exc:
            last_err = exc
            _log(log, f"torch install via {index_url} failed; trying next")
    if not torch_ok:
        _log(log, "CUDA wheel indexes failed; trying default PyPI torch")
        try:
            _run(pip + ["install", "torch", "torchvision"], log=log)
            torch_ok = True
        except RuntimeError as exc:
            last_err = exc
    if not torch_ok:
        raise RuntimeError(f"PyTorch install failed: {last_err}")

    _step(step, 6)
    # Preinstall maintained fork so pip does not try to compile abandoned cchardet.
    _run(pip + ["install", "faust-cchardet>=2.1.18"], log=log)
    _run(pip + ["install", "-e", str(repo)], cwd=repo, log=log)

    _step(step, 7)
    _run(pip + ["install", "Pillow", "numpy", "opencv-python-headless"], log=log)
    _ensure_weights(repo, log=log)

    _step(step, 8)
    sam_helper = root / "sam2_make_mask.py"
    _write_sam_helper(sam_helper)

    infer = repo / infer_name
    if not infer.is_file():
        raise RuntimeError(f"Missing inference script: {infer}")

    ready = {
        "version": __version__,
        "engine": paths.ENGINE_ID,
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
    _log(log, f"READY written (MatAnyone 2): {paths.ready_path()}")
    return root


def remove_step_count(targets: list[Path] | None = None) -> int:
    """Progress steps = folders to delete (at least 1 for the 'done' tick)."""
    if targets is None:
        targets = _remove_targets()
    return max(len(targets), 1)


def _remove_targets() -> list[Path]:
    """Primary runtime + any legacy scanned locations that still exist."""
    paths.migrate_legacy_runtime_if_needed()
    out: list[Path] = []
    seen: set[str] = set()
    for target in (paths.runtime_root(), *paths.legacy_runtime_roots()):
        if not target.exists():
            continue
        try:
            key = str(target.resolve())
        except OSError:
            key = str(target)
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def remove_runtime(
    *,
    log: LogFn | None = None,
    step: StepFn | None = None,
) -> None:
    """Delete runtime + legacy folders under dgpy_runtimes / old scan paths.

    Does not touch OS packages, shell profiles, or …/shared/python apps.
    """
    targets = _remove_targets()
    total = max(len(targets), 1)
    if not targets:
        _remove_step(step, 0, total, "Nothing to remove")
        _log(log, f"Nothing to remove (checked {paths.runtime_root()})")
        return

    for index, target in enumerate(targets):
        _remove_step(step, index, total, f"Removing {target}")
        _log(log, f"Removing {target}")
        shutil.rmtree(target, ignore_errors=False)
        # Clean empty parent (e.g. dgpy_runtimes/) when safe.
        parent = target.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                _log(log, f"Removed empty parent {parent}")
        except OSError:
            pass

    _remove_step(step, total - 1, total, "Done")
    _log(log, "Remove finished")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="MatAnyone runtime setup")
    ap.add_argument("action", choices=("setup", "setup-sam2", "remove", "status"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    def _print(msg: str) -> None:
        print(msg)

    def _print_step(index: int, total: int, label: str) -> None:
        print(f"[step {index + 1}/{total}] {label}")

    if args.action == "status":
        print(f"root={paths.runtime_root()}")
        print(f"ready={paths.is_ready()}")
        print(f"sam2_ready={paths.is_sam2_ready()}")
        print(f"python={paths.resolve_python()}")
        return 0
    if args.action == "remove":
        remove_runtime(log=_print, step=_print_step)
        return 0
    if args.action == "setup-sam2":
        setup_sam2(log=_print, step=_print_step, force=args.force)
        return 0
    setup_runtime(log=_print, step=_print_step, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
