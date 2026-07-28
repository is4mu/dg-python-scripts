"""Compare manifest vs installed and install/update packages into dgpy/."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import dgpy_local_inventory
import dgpy_log
import dgpy_manifest
import dgpy_paths
import dgpy_semver
from dgpy_http import download_asset_to, download_to
from dgpy_manifest import Manifest, ManifestPackage

__version__ = "0.3.10"

STATUS_NEW = "New"
STATUS_UPDATE = "Update"
STATUS_UP_TO_DATE = "Up to date"
STATUS_LOCAL_ONLY = "Local only"
STATUS_UNKNOWN = "Unknown"

# Script Manager list: always first, in this order.
_PINNED_ORDER = {"core": 0, "manager": 1}
_STATUS_ORDER = {
    STATUS_UPDATE: 0,
    STATUS_NEW: 1,
    STATUS_UP_TO_DATE: 2,
    STATUS_LOCAL_ONLY: 3,
}


@dataclass
class PackageRow:
    package_id: str
    name: str
    installed: str
    remote: str
    status: str
    location: str
    remote_pkg: ManifestPackage | None = None


def actionable(rows: list[PackageRow]) -> list[PackageRow]:
    """Rows that Install / Update All should process (New or Update with remote pkg)."""
    return [
        r
        for r in rows
        if r.status in (STATUS_NEW, STATUS_UPDATE) and r.remote_pkg is not None
    ]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _installed_version(root: Path, package_id: str) -> str | None:
    data = dgpy_local_inventory.load_installed(root)
    pkg = (data.get("packages") or {}).get(package_id)
    if pkg and pkg.get("version"):
        return str(pkg["version"])
    # Fallback: filesystem markers for core/manager
    if package_id == "core":
        marker = root / "dgpy_paths.py"
        if marker.exists():
            return dgpy_local_inventory.read_version_attr(marker)
    if package_id == "manager":
        marker = root / "dgpy_manager_app.py"
        if marker.exists():
            return dgpy_local_inventory.read_version_attr(marker)
    apps = root / "apps" / package_id
    if apps.is_dir():
        return "unknown"
    return None


def _host_assets_missing(pkg: ManifestPackage, base: Path) -> bool:
    """True if remote lists assets for this host but local files are absent."""
    if not pkg.assets:
        return False
    host = dgpy_paths.host_platform_id()
    matched = [a for a in pkg.assets if a.platform == host]
    if not matched:
        return False
    for asset in matched:
        target = base / asset.path.lstrip("/")
        if not target.is_file():
            return True
    return False


def compare(manifest: Manifest, root: Path | None = None) -> list[PackageRow]:
    base = root or dgpy_paths.dgpy_root()
    remote_map = manifest.by_id()
    installed_data = dgpy_local_inventory.load_installed(base)
    installed_ids = set((installed_data.get("packages") or {}).keys())

    # Also treat on-disk core/manager as installed even before seed
    for pid in ("core", "manager"):
        if _installed_version(base, pid):
            installed_ids.add(pid)

    rows: list[PackageRow] = []
    seen: set[str] = set()

    for pid, rpkg in remote_map.items():
        seen.add(pid)
        local_ver = _installed_version(base, pid)
        if local_ver is None:
            status = STATUS_NEW
            installed = "—"
        elif dgpy_semver.gt(rpkg.version, local_ver):
            status = STATUS_UPDATE
            installed = local_ver
        elif dgpy_semver.eq(rpkg.version, local_ver):
            status = STATUS_UP_TO_DATE
            installed = local_ver
            # e.g. ffmpeg_runtime installed by old Manager without binaries
            if _host_assets_missing(rpkg, base):
                status = STATUS_UPDATE
        else:
            # Local newer than remote
            status = STATUS_LOCAL_ONLY
            installed = local_ver
        loc = str(base / (rpkg.files[0].path if rpkg.files else pid))
        rows.append(
            PackageRow(
                package_id=pid,
                name=rpkg.name,
                installed=installed,
                remote=rpkg.version,
                status=status,
                location=loc,
                remote_pkg=rpkg,
            )
        )

    for pid in sorted(installed_ids - seen):
        local_ver = _installed_version(base, pid) or "—"
        name = (installed_data.get("packages") or {}).get(pid, {}).get("name") or pid
        rows.append(
            PackageRow(
                package_id=pid,
                name=str(name),
                installed=local_ver,
                remote="—",
                status=STATUS_LOCAL_ONLY,
                location=str(base / "apps" / pid),
                remote_pkg=None,
            )
        )

    manifest_index = {
        p.package_id: i for i, p in enumerate(manifest.packages)
    }

    def sort_key(r: PackageRow) -> tuple:
        pin = _PINNED_ORDER.get(r.package_id, 2)
        if pin < 2:
            return (pin, 0, 0, r.name.lower())
        status = _STATUS_ORDER.get(r.status, 9)
        idx = manifest_index.get(r.package_id, 10_000)
        return (pin, status, idx, r.name.lower())

    rows.sort(key=sort_key)
    return rows


def _topo_sort(packages: list[ManifestPackage]) -> list[ManifestPackage]:
    by_id = {p.package_id: p for p in packages}
    visited: set[str] = set()
    result: list[ManifestPackage] = []

    def visit(pid: str) -> None:
        if pid in visited:
            return
        visited.add(pid)
        pkg = by_id.get(pid)
        if not pkg:
            return
        for dep in pkg.depends:
            visit(dep)
        result.append(pkg)

    for p in packages:
        visit(p.package_id)
    return result


def install_package(
    pkg: ManifestPackage,
    root: Path | None = None,
) -> None:
    """Download, verify sha256, then replace files (and matching assets) under install root."""
    base = (root or dgpy_paths.dgpy_root()).resolve()
    live = dgpy_paths.dgpy_root().resolve()
    if base != live:
        raise RuntimeError(f"Refusing to install outside live dgpy root: {base}")

    logger = dgpy_log.get_logger()
    if not pkg.files and not pkg.assets:
        raise RuntimeError(f"Package {pkg.package_id} has no files or assets")

    host = dgpy_paths.host_platform_id()
    matched_assets = [a for a in pkg.assets if a.platform == host]
    if pkg.assets and not matched_assets:
        logger.warning(
            "Package %s has assets but none for platform %s — "
            "Python files only; binaries skipped",
            pkg.package_id,
            host,
        )
    elif matched_assets:
        logger.info(
            "Package %s: %s asset(s) for platform %s",
            pkg.package_id,
            len(matched_assets),
            host,
        )

    with tempfile.TemporaryDirectory(prefix="dgpy_sync_") as tmp:
        tmp_path = Path(tmp)
        verified: list[tuple[Path, str, bool]] = []  # tmp, rel, executable

        for f in pkg.files:
            # Apps go under apps/<id>/; core/manager files stay at dgpy root.
            if pkg.package_id in ("core", "manager"):
                rel = f.path
            else:
                rel = str(Path("apps") / pkg.package_id / f.path)

            dest_tmp = tmp_path / rel
            logger.info("Downloading %s", f.url)
            download_to(f.url, dest_tmp)
            digest = _sha256_file(dest_tmp)
            if digest.lower() != f.sha256.lower():
                raise RuntimeError(
                    f"sha256 mismatch for {f.path}: got {digest}, want {f.sha256}"
                )
            verified.append((dest_tmp, rel, False))

        for asset in matched_assets:
            rel = asset.path.lstrip("/")
            # Assets must stay under dgpy root (vendor/…); refuse path escape.
            final_check = (base / rel).resolve()
            if base not in final_check.parents and final_check != base:
                raise RuntimeError(f"Refusing asset path outside dgpy root: {rel}")
            dest_tmp = tmp_path / "assets" / rel
            logger.info("Downloading asset %s (%s)", rel, asset.platform)
            download_asset_to(asset.url, dest_tmp)
            digest = _sha256_file(dest_tmp)
            if digest.lower() != asset.sha256.lower():
                raise RuntimeError(
                    f"sha256 mismatch for asset {rel}: got {digest}, want {asset.sha256}"
                )
            verified.append((dest_tmp, rel, asset.executable))

        # All verified — replace
        for dest_tmp, rel, executable in verified:
            final = base / rel
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest_tmp, final)
            if executable:
                try:
                    final.chmod(final.stat().st_mode | 0o111)
                except OSError:
                    pass
            logger.info("Installed %s", rel)

    data = dgpy_local_inventory.load_installed(base)
    packages = data.setdefault("packages", {})
    packages[pkg.package_id] = {
        "name": pkg.name,
        "version": pkg.version,
        "files": [f.path for f in pkg.files],
        "assets": [a.path for a in matched_assets],
        "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    dgpy_local_inventory.save_installed(data, base)
    logger.info("Recorded %s@%s in installed.json", pkg.package_id, pkg.version)


def install_many(
    packages: list[ManifestPackage],
    root: Path | None = None,
    *,
    use_ondisk_installer: bool = False,
) -> list[str]:
    """Install packages in dependency order. Returns list of installed ids.

    When ``use_ondisk_installer`` is True (or after installing core/manager in
    this call), ``install_package`` is loaded from on-disk ``dgpy_sync.py`` so
    later packages see updated install logic (e.g. assets[]) in the same Flame
    session. Phased Update All must pass ``use_ondisk_installer=True`` for the
    Apps phase after Manager has been written to disk.
    """
    ordered = _topo_sort(packages)
    # Only install requested set, but ensure deps that are in the list come first.
    wanted = {p.package_id for p in packages}
    done: list[str] = []
    install_fn = install_package
    if use_ondisk_installer:
        try:
            install_fn = _fresh_install_package()
        except Exception as exc:  # noqa: BLE001
            dgpy_log.get_logger().warning(
                "Could not load on-disk dgpy_sync before install (%s); "
                "using in-session install_package",
                exc,
            )
    for pkg in ordered:
        if pkg.package_id not in wanted:
            continue
        install_fn(pkg, root=root)
        done.append(pkg.package_id)
        # Manager/core update on disk must be used for later packages in this
        # same Flame session (otherwise assets[] is ignored by stale import).
        if pkg.package_id in ("core", "manager"):
            try:
                install_fn = _fresh_install_package()
            except Exception as exc:  # noqa: BLE001
                dgpy_log.get_logger().warning(
                    "Could not reload on-disk dgpy_sync after %s (%s); "
                    "continuing with in-session install_package",
                    pkg.package_id,
                    exc,
                )
    return done


def _fresh_install_package():
    """Load install_package from the on-disk dgpy_sync.py (post-Update).

    Must register the module in ``sys.modules`` *before* ``exec_module``.
    Otherwise ``@dataclass`` (PEP 563 annotations) looks up
    ``sys.modules[cls.__module__]`` and raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    """
    import importlib.util
    import sys

    name = "dgpy_sync_ondisk"
    path = dgpy_paths.dgpy_root() / "dgpy_sync.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return install_package
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod.install_package


PROTECTED_PACKAGES = frozenset({"core", "manager"})


def partition_for_phased_install(
    packages: list[ManifestPackage],
) -> tuple[list[ManifestPackage], list[ManifestPackage], list[ManifestPackage]]:
    """Split into (core, manager, apps) for Core→Manager→Rescan→Apps.

    Each of core/manager is either empty or a single-element list.
    Apps keep relative order from the input list (caller may topo-sort via
    install_many).
    """
    by_id = {p.package_id: p for p in packages}
    core = [by_id["core"]] if "core" in by_id else []
    manager = [by_id["manager"]] if "manager" in by_id else []
    apps = [p for p in packages if p.package_id not in PROTECTED_PACKAGES]
    return core, manager, apps


def uninstall_package(package_id: str, root: Path | None = None) -> None:
    """Remove an app package from dgpy/. Refuses core/manager."""
    if package_id in PROTECTED_PACKAGES:
        raise RuntimeError(
            f"Cannot uninstall '{package_id}' (required for DG Script Manager). "
            "Remove the whole dgpy/ folder manually if you want a full uninstall."
        )

    base = (root or dgpy_paths.dgpy_root()).resolve()
    live = dgpy_paths.dgpy_root().resolve()
    if base != live:
        raise RuntimeError(f"Refusing to uninstall outside live dgpy root: {base}")

    logger = dgpy_log.get_logger()
    data = dgpy_local_inventory.load_installed(base)
    packages = data.setdefault("packages", {})
    record = packages.get(package_id) or {}
    file_names = [str(x) for x in (record.get("files") or [])]

    app_dir = base / "apps" / package_id
    if app_dir.is_dir():
        shutil.rmtree(app_dir)
        logger.info("Removed directory %s", app_dir)
    else:
        for name in file_names:
            # Safety: only delete under apps/<id>/ or exact listed relative paths there
            rel = Path("apps") / package_id / name
            target = base / rel
            if target.is_file() and live in target.resolve().parents:
                target.unlink()
                logger.info("Removed %s", rel)

    for asset_rel in [str(x) for x in (record.get("assets") or [])]:
        target = (base / asset_rel).resolve()
        if target.is_file() and (live == target or live in target.parents):
            target.unlink()
            logger.info("Removed asset %s", asset_rel)

    if package_id in packages:
        del packages[package_id]
        dgpy_local_inventory.save_installed(data, base)
        logger.info("Removed %s from installed.json", package_id)


def uninstall_many(package_ids: list[str], root: Path | None = None) -> list[str]:
    done: list[str] = []
    for pid in package_ids:
        uninstall_package(pid, root=root)
        done.append(pid)
    return done
