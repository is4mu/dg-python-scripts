"""Resolve bundled / PATH / env tools (ffmpeg, ffprobe). Unique basename for Flame."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import dgpy_paths

__version__ = "0.3.30"

# Env overrides (highest priority).
ENV_FFMPEG = "DGPY_FFMPEG"
ENV_FFPROBE = "DGPY_FFPROBE"


@dataclass(frozen=True)
class ToolResolve:
    """Result of locating an external binary."""

    name: str
    path: Path | None
    source: str  # env | bundled | path | missing
    version_line: str = ""

    @property
    def found(self) -> bool:
        return self.path is not None and self.path.is_file()


def _version_line(executable: Path) -> str:
    try:
        proc = subprocess.run(
            [str(executable), "-version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        text = (proc.stdout or proc.stderr or "").strip()
        if not text:
            return ""
        return text.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def tool_version_line(executable: Path | str) -> str:
    """Public helper: first line of ``tool -version``."""
    return _version_line(Path(executable))


def _bundled_tool(name: str, root: Path | None = None) -> Path | None:
    candidate = dgpy_paths.runtimes_bin_dir(root) / name
    return candidate if candidate.is_file() else None


def resolve_tool(
    name: str,
    *,
    env_var: str,
    root: Path | None = None,
    probe_version: bool = True,
) -> ToolResolve:
    """Resolve order: env → dgpy_runtimes/bin → PATH."""
    env_raw = (os.environ.get(env_var) or "").strip()
    if env_raw:
        path = Path(env_raw).expanduser()
        if path.is_file():
            ver = _version_line(path) if probe_version else ""
            return ToolResolve(name, path, "env", ver)
        return ToolResolve(
            name, None, "missing", f"{env_var} set but not a file: {env_raw}"
        )

    bundled = _bundled_tool(name, root)
    if bundled is not None:
        ver = _version_line(bundled) if probe_version else ""
        return ToolResolve(name, bundled, "bundled", ver)

    which = shutil.which(name)
    if which:
        path = Path(which)
        ver = _version_line(path) if probe_version else ""
        return ToolResolve(name, path, "path", ver)

    return ToolResolve(name, None, "missing", "")


def resolve_ffmpeg(*, root: Path | None = None, probe_version: bool = True) -> ToolResolve:
    return resolve_tool(
        "ffmpeg", env_var=ENV_FFMPEG, root=root, probe_version=probe_version
    )


def resolve_ffprobe(*, root: Path | None = None, probe_version: bool = True) -> ToolResolve:
    return resolve_tool(
        "ffprobe", env_var=ENV_FFPROBE, root=root, probe_version=probe_version
    )


def ffmpeg_path(*, root: Path | None = None) -> str | None:
    """Convenience: absolute path string or None."""
    hit = resolve_ffmpeg(root=root, probe_version=False)
    return str(hit.path) if hit.found else None


def ffprobe_path(*, root: Path | None = None) -> str | None:
    hit = resolve_ffprobe(root=root, probe_version=False)
    return str(hit.path) if hit.found else None


def bundled_ffmpeg_path(*, root: Path | None = None) -> Path | None:
    return _bundled_tool("ffmpeg", root)


def bundled_ffprobe_path(*, root: Path | None = None) -> Path | None:
    return _bundled_tool("ffprobe", root)
