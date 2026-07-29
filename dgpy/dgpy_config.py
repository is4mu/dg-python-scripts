"""JSON config under dgpy/state/config.json. Unique basename for Flame."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import dgpy_paths

DEFAULT_REPO = "is4mu/dg-python-scripts"
DEFAULT_CHANNEL = "latest"

__version__ = "0.3.21"


@dataclass
class Config:
    install_root: str = ""
    github_repo: str = DEFAULT_REPO
    channel: str = DEFAULT_CHANNEL
    manifest_url: str = ""
    auto_update_on_start: bool = True

    def resolved_install_root(self) -> Path:
        """Always prefer the running dgpy folder (machine-local, from __file__)."""
        live = dgpy_paths.dgpy_root()
        if self.install_root:
            saved = Path(self.install_root)
            try:
                if saved.resolve() == live.resolve():
                    return live
            except OSError:
                pass
        return live


def config_path(root: Path | None = None) -> Path:
    return dgpy_paths.state_dir(root) / "config.json"


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _normalize(cfg: Config) -> Config:
    """Rewrite stale absolute paths from another OS/machine."""
    live = str(dgpy_paths.dgpy_root())
    if cfg.install_root != live:
        cfg.install_root = live
    return cfg


def load(root: Path | None = None) -> Config:
    # Always read/write config next to the *running* code, not a saved foreign path.
    live_root = root or dgpy_paths.dgpy_root()
    path = config_path(live_root)
    if not path.exists():
        cfg = _normalize(Config(install_root=str(live_root)))
        save(cfg, live_root)
        return cfg
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = _normalize(Config(install_root=str(live_root)))
        save(cfg, live_root)
        return cfg

    cfg = _normalize(
        Config(
            install_root=str(data.get("install_root") or live_root),
            github_repo=str(data.get("github_repo") or DEFAULT_REPO),
            channel=str(data.get("channel") or DEFAULT_CHANNEL),
            manifest_url=str(data.get("manifest_url") or ""),
            auto_update_on_start=_as_bool(
                data.get("auto_update_on_start"), default=True
            ),
        )
    )
    # Persist correction if the file still had a Mac path etc.
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        prev = {}
    if prev.get("install_root") != cfg.install_root:
        save(cfg, live_root)
    return cfg


def save(cfg: Config, root: Path | None = None) -> None:
    live_root = root or dgpy_paths.dgpy_root()
    cfg = _normalize(cfg)
    path = config_path(live_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
