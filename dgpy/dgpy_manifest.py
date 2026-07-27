"""Remote manifest fetch and parse."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import dgpy_config
import dgpy_http

__version__ = "0.3.2"


@dataclass
class ManifestFile:
    path: str
    sha256: str
    url: str


@dataclass
class ManifestAsset:
    """Platform-specific binary (not stored in git; Release URL)."""

    platform: str
    path: str  # relative to dgpy root, e.g. vendor/ffmpeg/darwin-arm64/ffmpeg
    sha256: str
    url: str
    executable: bool = True


@dataclass
class ManifestPackage:
    package_id: str
    name: str
    version: str
    min_flame: str = "2025"
    depends: list[str] = field(default_factory=list)
    category: str = "Utility"
    summary: str = ""
    changelog: str = ""
    files: list[ManifestFile] = field(default_factory=list)
    assets: list[ManifestAsset] = field(default_factory=list)


@dataclass
class Manifest:
    schema: int
    channel: str
    generated_at: str
    repo: str
    packages: list[ManifestPackage]

    def by_id(self) -> dict[str, ManifestPackage]:
        return {p.package_id: p for p in self.packages}


def default_manifest_url(cfg: dgpy_config.Config) -> str:
    """Manifest URL for the active channel.

    Uses the GitHub Contents API (not raw.githubusercontent.com) so Refresh is not
    stuck on the CDN's ~5 minute stale cache of branch-tip files.
    """
    if cfg.manifest_url:
        return cfg.manifest_url
    repo = cfg.github_repo or dgpy_config.DEFAULT_REPO
    # latest -> main; stable -> tag/branch named stable
    ref = "main" if cfg.channel != "stable" else "stable"
    return (
        f"https://api.github.com/repos/{repo}/contents/dist/manifest.json"
        f"?ref={ref}"
    )


def parse_manifest(data: dict[str, Any]) -> Manifest:
    packages: list[ManifestPackage] = []
    for raw in data.get("packages") or []:
        files = [
            ManifestFile(
                path=str(f["path"]),
                sha256=str(f["sha256"]).lower(),
                url=str(f["url"]),
            )
            for f in (raw.get("files") or [])
        ]
        assets = [
            ManifestAsset(
                platform=str(a["platform"]),
                path=str(a["path"]),
                sha256=str(a["sha256"]).lower(),
                url=str(a["url"]),
                executable=bool(a.get("executable", True)),
            )
            for a in (raw.get("assets") or [])
        ]
        packages.append(
            ManifestPackage(
                package_id=str(raw["id"]),
                name=str(raw.get("name") or raw["id"]),
                version=str(raw["version"]),
                min_flame=str(raw.get("min_flame") or "2025"),
                depends=[str(d) for d in (raw.get("depends") or [])],
                category=str(raw.get("category") or "Utility"),
                summary=str(raw.get("summary") or ""),
                changelog=str(raw.get("changelog") or ""),
                files=files,
                assets=assets,
            )
        )
    return Manifest(
        schema=int(data.get("schema") or 1),
        channel=str(data.get("channel") or "latest"),
        generated_at=str(data.get("generated_at") or ""),
        repo=str(data.get("repo") or ""),
        packages=packages,
    )


def fetch_manifest(cfg: dgpy_config.Config) -> Manifest:
    url = default_manifest_url(cfg)
    raw = dgpy_http.fetch_bytes(url)
    data = json.loads(raw.decode("utf-8"))
    return parse_manifest(data)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
