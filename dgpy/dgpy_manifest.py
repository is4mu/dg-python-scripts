"""Remote manifest fetch and parse."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import dgpy_config
import dgpy_http

__version__ = "0.3.28"

DEV_REPO = "is4mu/dg-python-scripts-dev"
PUBLIC_REPO = dgpy_config.DEFAULT_REPO

_CONTENTS_REPO_RE = re.compile(
    r"(https://api\.github\.com/repos/)[^/]+/[^/]+(/contents/)"
)


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
    # False: show in Script Manager but skip Update All / startup for status New.
    auto_install: bool = True


@dataclass
class Manifest:
    schema: int
    channel: str
    generated_at: str
    repo: str
    packages: list[ManifestPackage]

    def by_id(self) -> dict[str, ManifestPackage]:
        return {p.package_id: p for p in self.packages}


def repo_for_channel(cfg: dgpy_config.Config) -> str:
    """GitHub owner/name for the active channel."""
    if cfg.channel == "dev":
        return DEV_REPO
    return (cfg.github_repo or PUBLIC_REPO).strip() or PUBLIC_REPO


def ref_for_channel(cfg: dgpy_config.Config) -> str:
    if cfg.channel == "stable":
        return "stable"
    return "main"


def rewrite_contents_url(url: str, repo: str) -> str:
    """Point a Contents API URL at ``repo`` (leave Release/raw URLs alone)."""
    if "api.github.com" not in url or "/contents/" not in url:
        return url
    return _CONTENTS_REPO_RE.sub(rf"\1{repo}\2", url, count=1)


def rewrite_manifest_urls(manifest: Manifest, repo: str) -> Manifest:
    """Rewrite package file Contents URLs to ``repo`` (channel=dev)."""
    for pkg in manifest.packages:
        for f in pkg.files:
            f.url = rewrite_contents_url(f.url, repo)
    return manifest


def default_manifest_url(cfg: dgpy_config.Config) -> str:
    """Manifest URL for the active channel.

    Uses the GitHub Contents API (not raw.githubusercontent.com) so Refresh is not
    stuck on the CDN's ~5 minute stale cache of branch-tip files.
    """
    if cfg.manifest_url:
        return cfg.manifest_url
    repo = repo_for_channel(cfg)
    ref = ref_for_channel(cfg)
    return (
        f"https://api.github.com/repos/{repo}/contents/dist/manifest.json"
        f"?ref={ref}"
    )


def require_token_for_channel(cfg: dgpy_config.Config) -> None:
    """Raise if channel=dev and no GitHub token is configured."""
    if cfg.channel != "dev":
        return
    import dgpy_prefs

    if dgpy_prefs.github_token():
        return
    raise RuntimeError(
        "channel=dev needs a GitHub token for private "
        f"{DEV_REPO}.\n"
        "Set it in DGpy → Preferences… (User prefs), "
        f"or export ${dgpy_prefs.ENV_GITHUB_TOKEN}."
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
                auto_install=bool(raw.get("auto_install", True)),
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
    require_token_for_channel(cfg)
    url = default_manifest_url(cfg)
    raw = dgpy_http.fetch_bytes(url)
    data = json.loads(raw.decode("utf-8"))
    manifest = parse_manifest(data)
    if cfg.channel == "dev":
        repo = DEV_REPO
        manifest.repo = repo
        rewrite_manifest_urls(manifest, repo)
    return manifest


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
