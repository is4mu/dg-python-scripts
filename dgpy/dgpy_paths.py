"""Path helpers for dgpy install root (unique module name for Flame scan)."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

__version__ = "0.3.24"


def dgpy_root() -> Path:
    """Return the install root (.../dgpy)."""
    return Path(__file__).resolve().parent


def host_platform_id() -> str:
    """Vendor / asset platform key, e.g. linux-x86_64, darwin-arm64."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine
    if system == "darwin":
        return f"darwin-{arch}"
    if system == "linux":
        return f"linux-{arch}"
    return f"{system}-{arch}"


def ensure_dgpy_on_sys_path() -> Path:
    root = dgpy_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def flame_user_python() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Preferences" / "Autodesk" / "flame" / "python"
    return home / "flame" / "python"


def flame_shared_python() -> Path:
    return Path("/opt/Autodesk/shared/python")


def state_dir(root: Path | None = None) -> Path:
    base = (root or dgpy_root()).resolve()
    # Never create dirs outside the live dgpy tree (guards stale Mac paths on Linux).
    live = dgpy_root().resolve()
    if live != base and live not in base.parents and base != live:
        if not str(base).startswith(str(live)):
            base = live
    path = base / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apps_dir(root: Path | None = None) -> Path:
    base = root or dgpy_root()
    path = base / "apps"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_log_path(root: Path | None = None) -> Path:
    return state_dir(root) / "dgpy.log"


def detect_parent_kind(root: Path | None = None) -> str:
    parent = (root or dgpy_root()).resolve().parent
    try:
        if parent == flame_user_python().resolve():
            return "user"
        if parent == flame_shared_python().resolve():
            return "shared"
    except OSError:
        pass
    return "other"


def check_writable(root: Path | None = None) -> tuple[bool, str]:
    """Return (ok, message) for write access to dgpy root."""
    base = (root or dgpy_root()).resolve()
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".dgpy_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, ""
    except OSError as exc:
        kind = detect_parent_kind(base)
        hint = ""
        if kind == "shared":
            hint = (
                " 共有パスです。管理者権限で配置するか、"
                "ユーザ python に bootstrap し直してください。"
            )
        return False, f"書き込みできません: {base} ({exc}).{hint}"


def list_dgpy_locations() -> list[tuple[str, Path]]:
    """Known places where a dgpy/ folder might exist."""
    found: list[tuple[str, Path]] = []
    candidates = [
        ("user", flame_user_python() / "dgpy"),
        ("shared", flame_shared_python() / "dgpy"),
    ]
    for label, path in candidates:
        try:
            if path.is_dir():
                found.append((label, path.resolve()))
        except OSError:
            continue
    return found


def duplicate_dgpy_warning(current: Path | None = None) -> str | None:
    """Warn if more than one dgpy install exists (user + shared)."""
    live = (current or dgpy_root()).resolve()
    locations = list_dgpy_locations()
    if len(locations) < 2:
        return None
    paths = ", ".join(f"{k}:{p}" for k, p in locations)
    return (
        "ユーザと共有の両方に dgpy があります。\n"
        f"{paths}\n現在の Manager は次を更新します: {live}\n"
        "どちらか一方だけ残すことを推奨します。"
    )


def env_hook_paths() -> list[Path]:
    raw = os.environ.get("DL_PYTHON_HOOK_PATH", "")
    if not raw:
        return []
    return [Path(p) for p in raw.split(os.pathsep) if p.strip()]
