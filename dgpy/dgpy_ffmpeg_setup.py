"""Install / remove ffmpeg+ffprobe under dgpy_runtimes/bin (outside python/)."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import dgpy_http
import dgpy_paths
import dgpy_tools

__version__ = "0.3.30"

LogFn = Callable[[str], None]

# https://ffbinaries.com/api — no Apple Silicon entry (only osx-64).
_FFBINARIES_PLATFORM = {
    "darwin-x86_64": "osx-64",
    "linux-x86_64": "linux-64",
    "linux-arm64": "linux-arm64",
}

_API_LATEST = "https://ffbinaries.com/api/v1/version/latest"

# Native arm64 macOS builds (ffbinaries has no osx-arm64).
# https://ffmpeg.martin-riedl.de/
_MARTIN_ARM64_FFMPEG = (
    "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"
)
_MARTIN_ARM64_FFPROBE = (
    "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip"
)


def _log(cb: LogFn | None, message: str) -> None:
    if cb:
        cb(message)


def bundled_ready(*, root: Path | None = None) -> bool:
    return (
        dgpy_tools.bundled_ffmpeg_path(root=root) is not None
        and dgpy_tools.bundled_ffprobe_path(root=root) is not None
    )


def _resolve_urls(log: LogFn | None) -> tuple[str, str, str]:
    """Return (ffmpeg_url, ffprobe_url, source_label)."""
    host = dgpy_paths.host_platform_id()
    if host == "darwin-arm64":
        _log(log, "Using martin-riedl macos/arm64/release (ffbinaries has no arm64)")
        return _MARTIN_ARM64_FFMPEG, _MARTIN_ARM64_FFPROBE, "martin-riedl"

    key = _FFBINARIES_PLATFORM.get(host)
    if not key:
        raise RuntimeError(
            f"No ffmpeg binaries package for platform {host}. "
            "Supported: darwin-arm64, "
            + ", ".join(sorted(_FFBINARIES_PLATFORM))
        )

    _log(log, f"Fetching ffbinaries catalog (platform={key})…")
    raw = dgpy_http.fetch_bytes(_API_LATEST, timeout=60)
    data = json.loads(raw.decode("utf-8"))
    bin_map = data.get("bin") or {}
    plat = bin_map.get(key)
    if not isinstance(plat, dict):
        raise RuntimeError(
            f"ffbinaries has no entry for {key}. "
            f"Available: {', '.join(sorted(bin_map))}"
        )
    ffmpeg_url = str(plat.get("ffmpeg") or "").strip()
    ffprobe_url = str(plat.get("ffprobe") or "").strip()
    if not ffmpeg_url or not ffprobe_url:
        raise RuntimeError(f"ffbinaries incomplete for {key}: {plat!r}")
    version = str(data.get("version") or "?")
    _log(log, f"ffbinaries version {version}")
    return ffmpeg_url, ffprobe_url, f"ffbinaries/{version}"


def _download_zip_tool(
    url: str,
    *,
    tool: str,
    dest_bin: Path,
    log: LogFn | None,
) -> Path:
    """Download a zip and extract ``tool`` into dest_bin."""
    dest_bin.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dgpy_ffmpeg_") as tmp:
        tmp_path = Path(tmp)
        name = Path(urlparse(url).path).name or f"{tool}.zip"
        archive = tmp_path / name
        _log(log, f"Downloading {tool}: {url}")
        dgpy_http.download_to(url, archive, timeout=600)
        with zipfile.ZipFile(archive, "r") as zf:
            members = [m for m in zf.namelist() if not m.endswith("/")]
            # Prefer exact tool name; else first file.
            pick = None
            for m in members:
                if Path(m).name == tool or Path(m).name.startswith(tool):
                    pick = m
                    break
            if pick is None and members:
                pick = members[0]
            if pick is None:
                raise RuntimeError(f"Zip for {tool} is empty: {url}")
            zf.extract(pick, path=tmp_path)
            extracted = tmp_path / pick
            if not extracted.is_file():
                raise RuntimeError(f"Extract failed for {tool}: {pick}")
            out = dest_bin / tool
            if out.exists() or out.is_symlink():
                out.unlink()
            shutil.copy2(extracted, out)
            try:
                mode = out.stat().st_mode
                out.chmod(mode | 0o111)
            except OSError:
                pass
            _log(log, f"Installed {out}")
            return out


def install_ffmpeg_tools(
    *,
    force: bool = False,
    log: LogFn | None = None,
    root: Path | None = None,
) -> Path:
    """Download ffmpeg+ffprobe into dgpy_runtimes/bin. Returns bin dir."""
    dest = dgpy_paths.runtimes_bin_dir(root)
    if bundled_ready(root=root) and not force:
        _log(log, f"Already installed under {dest}")
        return dest

    ffmpeg_url, ffprobe_url, source = _resolve_urls(log)

    # Stage into a temp dir then move, to avoid half-installed pairs.
    with tempfile.TemporaryDirectory(prefix="dgpy_ffmpeg_stage_") as stage:
        stage_bin = Path(stage) / "bin"
        _download_zip_tool(ffmpeg_url, tool="ffmpeg", dest_bin=stage_bin, log=log)
        _download_zip_tool(ffprobe_url, tool="ffprobe", dest_bin=stage_bin, log=log)
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("ffmpeg", "ffprobe"):
            src = stage_bin / name
            out = dest / name
            if out.exists() or out.is_symlink():
                out.unlink()
            shutil.copy2(src, out)
            try:
                out.chmod(out.stat().st_mode | 0o111)
            except OSError:
                pass

    # Smoke test
    for name in ("ffmpeg", "ffprobe"):
        path = dest / name
        if not path.is_file():
            raise RuntimeError(f"Install incomplete: missing {path}")
        line = dgpy_tools.tool_version_line(path)
        _log(log, f"{name}: {line or '(no -version output)'}")

    marker = dest / "README-ffmpeg.txt"
    marker.write_text(
        "Bundled ffmpeg/ffprobe for DGpy.\n"
        f"Source: {source}\n"
        "Managed by DGpy → Preferences… → Install / Remove bundled.\n"
        "DGpy prefers these over PATH when present.\n"
        "Apple Silicon: ffmpeg.martin-riedl.de (native arm64).\n"
        "Other platforms: ffbinaries.com.\n",
        encoding="utf-8",
    )
    _log(log, f"Done → {dest}")
    return dest


def remove_ffmpeg_tools(
    *,
    log: LogFn | None = None,
    root: Path | None = None,
) -> None:
    """Remove only bundled binaries under dgpy_runtimes/bin (not PATH tools)."""
    dest = dgpy_paths.runtimes_bin_dir(root)
    removed = False
    for name in ("ffmpeg", "ffprobe", "README-ffmpeg.txt"):
        path = dest / name
        if path.is_file() or path.is_symlink():
            path.unlink()
            _log(log, f"Removed {path}")
            removed = True
    if not removed:
        _log(log, f"Nothing to remove under {dest}")
    # Remove empty bin dir only if empty
    try:
        if dest.is_dir() and not any(dest.iterdir()):
            dest.rmdir()
            _log(log, f"Removed empty {dest}")
    except OSError:
        pass
