"""Resolve ffmpeg / ffprobe for DGpy2 (Export, future Portal, etc.).

Unique basename for Flame scan. No menu hook.

Resolve order:
  1. Env DGPY_FFMPEG / DGPY_FFPROBE
  2. Config override (state/ffmpeg_runtime.json)
  3. <dgpy_root>/vendor/ffmpeg/<platform>/{ffmpeg,ffprobe}
  4. PATH
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

import dgpy_paths

__version__ = "0.2.1"

_ENV_FFMPEG = "DGPY_FFMPEG"
_ENV_FFPROBE = "DGPY_FFPROBE"
_CONFIG_NAME = "ffmpeg_runtime.json"


@dataclass(frozen=True)
class ResolvedBinary:
    path: Path
    source: str  # env | config | vendor | path
    version: str = ""


def platform_id() -> str:
    """Return vendor folder name, e.g. linux-x86_64, darwin-arm64."""
    return dgpy_paths.host_platform_id()


def vendor_dir(root: Path | None = None) -> Path:
    return (root or dgpy_paths.dgpy_root()) / "vendor" / "ffmpeg" / platform_id()


def config_path(root: Path | None = None) -> Path:
    return dgpy_paths.state_dir(root) / _CONFIG_NAME


def load_config(root: Path | None = None) -> dict[str, Any]:
    path = config_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: dict[str, Any], root: Path | None = None) -> None:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _probe_version(binary: Path) -> str:
    try:
        proc = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    first = (proc.stdout or proc.stderr or "").splitlines()
    if not first:
        return ""
    # e.g. "ffmpeg version 7.1.1 Copyright ..."
    line = first[0]
    parts = line.split()
    if len(parts) >= 3 and parts[1] == "version":
        return parts[2]
    return line[:80]


def _usable(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _from_env(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_ffmpeg(root: Path | None = None) -> ResolvedBinary | None:
    cfg = load_config(root)
    candidates: list[tuple[str, Path | None]] = [
        ("env", _from_env(_ENV_FFMPEG)),
        ("config", Path(cfg["ffmpeg"]).expanduser() if cfg.get("ffmpeg") else None),
        ("vendor", vendor_dir(root) / "ffmpeg"),
        ("path", Path(shutil.which("ffmpeg") or "")),
    ]
    for source, path in candidates:
        if path and str(path) and _usable(path):
            return ResolvedBinary(path=path.resolve(), source=source, version=_probe_version(path))
    return None


def resolve_ffprobe(root: Path | None = None) -> ResolvedBinary | None:
    cfg = load_config(root)
    candidates: list[tuple[str, Path | None]] = [
        ("env", _from_env(_ENV_FFPROBE)),
        ("config", Path(cfg["ffprobe"]).expanduser() if cfg.get("ffprobe") else None),
        ("vendor", vendor_dir(root) / "ffprobe"),
        ("path", Path(shutil.which("ffprobe") or "")),
    ]
    for source, path in candidates:
        if path and str(path) and _usable(path):
            return ResolvedBinary(path=path.resolve(), source=source, version=_probe_version(path))
    return None


def set_user_ffmpeg(ffmpeg: Path | None, ffprobe: Path | None = None, root: Path | None = None) -> None:
    data = load_config(root)
    if ffmpeg is None:
        data.pop("ffmpeg", None)
    else:
        data["ffmpeg"] = str(ffmpeg.expanduser().resolve())
    if ffprobe is None:
        data.pop("ffprobe", None)
    else:
        data["ffprobe"] = str(ffprobe.expanduser().resolve())
    save_config(data, root)


def installed_meta(root: Path | None = None) -> dict[str, Any]:
    shared = (root or dgpy_paths.dgpy_root()) / "vendor" / "ffmpeg" / "installed.json"
    path = shared
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def install_binary_pair(
    *,
    ffmpeg_url: str,
    ffmpeg_sha256: str,
    ffprobe_url: str | None = None,
    ffprobe_sha256: str | None = None,
    version: str = "",
    root: Path | None = None,
) -> Path:
    """Download ffmpeg (+ optional ffprobe) into vendor/<platform>/ after sha256 check."""
    dest_dir = vendor_dir(root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dgpy_ffmpeg_") as tmp:
        tmp_path = Path(tmp)
        ff_tmp = tmp_path / "ffmpeg"
        urlretrieve(ffmpeg_url, ff_tmp)
        digest = _sha256_file(ff_tmp)
        if digest.lower() != ffmpeg_sha256.lower():
            raise RuntimeError(
                f"ffmpeg sha256 mismatch: got {digest}, want {ffmpeg_sha256}"
            )
        final_ff = dest_dir / "ffmpeg"
        final_ff.write_bytes(ff_tmp.read_bytes())
        final_ff.chmod(0o755)

        if ffprobe_url and ffprobe_sha256:
            fp_tmp = tmp_path / "ffprobe"
            urlretrieve(ffprobe_url, fp_tmp)
            digest_p = _sha256_file(fp_tmp)
            if digest_p.lower() != ffprobe_sha256.lower():
                raise RuntimeError(
                    f"ffprobe sha256 mismatch: got {digest_p}, want {ffprobe_sha256}"
                )
            final_fp = dest_dir / "ffprobe"
            final_fp.write_bytes(fp_tmp.read_bytes())
            final_fp.chmod(0o755)

    meta_path = (root or dgpy_paths.dgpy_root()) / "vendor" / "ffmpeg" / "installed.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    platforms = installed_meta(root).get("platforms") or {}
    if not isinstance(platforms, dict):
        platforms = {}
    platforms[platform_id()] = {
        "version": version,
        "ffmpeg_sha256": ffmpeg_sha256.lower(),
        "ffprobe_sha256": (ffprobe_sha256 or "").lower(),
    }
    meta_path.write_text(
        json.dumps(
            {"version": version, "platforms": platforms},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return final_ff


def status_line(root: Path | None = None) -> str:
    """Short label for UI, e.g. 'ffmpeg 7.1.1 (path)' or 'ffmpeg not found'."""
    ff = resolve_ffmpeg(root)
    if not ff:
        return "ffmpeg not found"
    ver = ff.version or "?"
    return f"ffmpeg {ver} ({ff.source})"
