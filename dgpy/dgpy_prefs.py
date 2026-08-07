"""User prefs (prefs.json) — load/save, token, import/export. Unique for Flame."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__version__ = "0.3.28"

ENV_GITHUB_TOKEN = "DGPY_GITHUB_TOKEN"
PREFS_SCHEMA = 1


def flame_user_dgpy_dir() -> Path:
    """Per-user DGpy data root — sibling of Flame ``python/`` (not scanned).

    macOS: ~/Library/Preferences/Autodesk/flame/dgpy
    Linux: ~/flame/dgpy
    """
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Preferences" / "Autodesk" / "flame" / "dgpy"
    return home / "flame" / "dgpy"


def user_prefs_path() -> Path:
    """User preferences JSON (small settings only; never under python/)."""
    return flame_user_dgpy_dir() / "prefs.json"


@dataclass
class UserPrefs:
    """In-memory prefs. Extra keys preserved for forward compatibility."""

    schema: int = PREFS_SCHEMA
    github_token: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.extra)
        data["schema"] = int(self.schema) or PREFS_SCHEMA
        token = (self.github_token or "").strip()
        if token:
            data["github_token"] = token
        else:
            data.pop("github_token", None)
        return data


def _from_dict(data: dict[str, Any]) -> UserPrefs:
    known = {"schema", "github_token"}
    extra = {k: v for k, v in data.items() if k not in known}
    return UserPrefs(
        schema=int(data.get("schema") or PREFS_SCHEMA),
        github_token=str(data.get("github_token") or "").strip(),
        extra=extra,
    )


def load() -> UserPrefs:
    path = user_prefs_path()
    if not path.is_file():
        return UserPrefs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UserPrefs()
    if not isinstance(raw, dict):
        return UserPrefs()
    return _from_dict(raw)


def save(prefs: UserPrefs) -> Path:
    path = user_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def github_token() -> str | None:
    """Resolved token: env DGPY_GITHUB_TOKEN, else prefs.json. None if empty."""
    env = (os.environ.get(ENV_GITHUB_TOKEN) or "").strip()
    if env:
        return env
    token = load().github_token.strip()
    return token or None


def token_status_label() -> str:
    """Safe one-line status for UI/logs (never the full token)."""
    env = (os.environ.get(ENV_GITHUB_TOKEN) or "").strip()
    if env:
        return f"set via ${ENV_GITHUB_TOKEN} (…{env[-4:]})"
    prefs = load().github_token.strip()
    if prefs:
        return f"set in prefs.json (…{prefs[-4:]})"
    return "not set"


def export_prefs(dest: Path) -> Path:
    """Copy current prefs.json to dest (creates empty schema file if missing)."""
    dest = Path(dest)
    src = user_prefs_path()
    if not src.is_file():
        save(UserPrefs())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def import_prefs(src: Path) -> UserPrefs:
    """Replace prefs.json from src after validating JSON object."""
    src = Path(src)
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid prefs JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("prefs JSON must be an object")
    prefs = _from_dict(raw)
    save(prefs)
    return prefs
