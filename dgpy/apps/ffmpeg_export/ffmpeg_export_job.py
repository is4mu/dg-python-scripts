"""Export job: Flame intermediate (PyExporter) → ffmpeg → destination."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import dgpy_paths
from ffmpeg_export_paths import output_path_for
from ffmpeg_export_presets import ExportPreset
from ffmpeg_export_selection import ExportSource

__version__ = "0.1.3"

ProgressCb = Callable[[int, int, str], None]  # done, total, message
CancelCb = Callable[[], bool]

_MEDIA_EXT = {".mov", ".mxf", ".mp4", ".m4v", ".avi", ".mkv", ".mpg", ".mpeg"}

# Prefer quality intermediates that ffmpeg can usually decode.
_PREFERRED_PRESET_NAMES = (
    "Final Cut Pro (Apple ProRes 422).xml",
    "Final Cut Pro (Apple ProRes 422 HQ).xml",
    "Cinedeck (Apple ProRes 422).xml",
    "Avid Media Composer (QuickTime DNxHR HQ 8-bit).xml",
    "QuickTime (8-bit Uncompressed).xml",
)


@dataclass
class JobResult:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    messages: list[str] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []


def _ensure_runtime_import() -> None:
    import sys

    runtime = dgpy_paths.dgpy_root() / "apps" / "ffmpeg_runtime"
    if runtime.is_dir() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))


def _config_path() -> Path:
    return dgpy_paths.state_dir() / "ffmpeg_export.json"


def load_export_config() -> dict:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _encoder_available(ffmpeg: Path, codec: str) -> bool:
    if not codec:
        return True
    try:
        proc = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = (proc.stdout or "") + (proc.stderr or "")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == codec:
            return True
    return False


def build_ffmpeg_cmd(
    ffmpeg: Path,
    intermediate: Path,
    output: Path,
    preset: ExportPreset,
) -> list[str]:
    cmd = [str(ffmpeg), "-y", "-i", str(intermediate)]

    if preset.kind == "audio":
        cmd += ["-vn"]
        if preset.audio_codec:
            cmd += ["-c:a", preset.audio_codec]
        if preset.audio_bitrate and preset.audio_codec not in ("pcm_s24le", "pcm_s16le"):
            cmd += ["-b:a", preset.audio_bitrate]
    elif preset.kind in ("still", "frames"):
        cmd += ["-an"]
        if preset.kind == "still":
            cmd += ["-frames:v", "1"]
    else:
        if preset.video_codec:
            cmd += ["-c:v", preset.video_codec]
        if preset.crf is not None:
            cmd += ["-crf", str(preset.crf)]
        elif preset.video_bitrate:
            cmd += ["-b:v", preset.video_bitrate]
        if preset.pix_fmt:
            cmd += ["-pix_fmt", preset.pix_fmt]
        if preset.audio_channels == "none":
            cmd += ["-an"]
        elif preset.audio_codec:
            cmd += ["-c:a", preset.audio_codec]
            if preset.audio_bitrate:
                cmd += ["-b:a", preset.audio_bitrate]

    if preset.scale and preset.scale != "source" and "x" in preset.scale.lower():
        cmd += ["-vf", f"scale={preset.scale.replace('×', 'x')}"]
    if preset.fps and preset.fps != "source":
        cmd += ["-r", str(preset.fps)]

    cmd.extend(preset.extra_ffmpeg)
    cmd.append(str(output))
    return cmd


def _movie_preset_roots() -> list[Path]:
    roots: list[Path] = []
    presets_root = Path("/opt/Autodesk/presets")
    if presets_root.is_dir():
        for path in sorted(presets_root.glob("*/export/presets/flame/movie_file")):
            if path.is_dir():
                roots.append(path)
    shared = Path("/opt/Autodesk/shared/export/presets/flame/movie_file")
    if shared.is_dir():
        roots.append(shared)

    try:
        import flame

        exporter = flame.PyExporter
        get_dir = getattr(exporter, "get_presets_base_dir", None)
        if get_dir:
            tokens = []
            preset_base = getattr(exporter, "PresetBaseDir", None)
            if preset_base is not None and hasattr(preset_base, "Project"):
                tokens.append(preset_base.Project)
            if hasattr(exporter, "Project"):
                tokens.append(exporter.Project)
            for token in tokens:
                try:
                    base = Path(str(get_dir(token)))
                except Exception:  # noqa: BLE001
                    continue
                movie = base / "movie_file"
                if movie.is_dir():
                    roots.append(movie)
                    break
    except Exception:  # noqa: BLE001
        pass
    return roots


def resolve_flame_movie_preset() -> Path:
    """Locate a Flame Movie File export preset XML for intermediate export."""
    cfg = load_export_config()
    override = str(cfg.get("flame_movie_preset") or "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
        raise RuntimeError(f"Configured flame_movie_preset not found: {path}")

    roots = _movie_preset_roots()
    by_name: dict[str, Path] = {}
    for root in roots:
        for xml in root.rglob("*.xml"):
            by_name.setdefault(xml.name, xml)

    for name in _PREFERRED_PRESET_NAMES:
        if name in by_name:
            return by_name[name]

    # Any movie preset as last resort
    for root in roots:
        found = sorted(root.rglob("*.xml"))
        if found:
            return found[0]

    raise RuntimeError(
        "No Flame Movie File export preset found under "
        "/opt/Autodesk/presets/.../movie_file. "
        "Set flame_movie_preset in dgpy/state/ffmpeg_export.json"
    )


def _pick_exported_media(out_dir: Path) -> Path:
    files = [
        p
        for p in out_dir.rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in _MEDIA_EXT
    ]
    if not files:
        files = [
            p
            for p in out_dir.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        ]
    if not files:
        raise RuntimeError(f"Flame export produced no files in {out_dir}")
    return max(files, key=lambda p: p.stat().st_size)


def export_intermediate_flame(clip, work_dir: Path, logger) -> Path:
    """
    Flame PyExporter → temp movie.

    Real signature (Flame 2025):
      exporter.export(sources, preset_path, output_directory, ...)
    """
    import flame

    preset_path = resolve_flame_movie_preset()
    out_dir = work_dir / "flame_out"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exporter = flame.PyExporter()
    if hasattr(exporter, "foreground"):
        exporter.foreground = True
    if hasattr(exporter, "export_between_marks"):
        exporter.export_between_marks = False
    if hasattr(exporter, "use_top_video_track"):
        exporter.use_top_video_track = True

    logger.info(
        "PyExporter.export sources=%s preset=%s out=%s",
        type(clip).__name__,
        preset_path,
        out_dir,
    )

    # sources: object* — try list first (common), then bare object
    errors: list[str] = []
    for sources in ([clip], clip):
        try:
            exporter.export(sources, str(preset_path), str(out_dir))
            break
        except TypeError as exc:
            errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            logger.warning("PyExporter.export failed: %s", exc)
    else:
        raise RuntimeError(
            "Flame intermediate export failed.\n"
            f"Preset: {preset_path}\n"
            + ("; ".join(errors[:2]) if errors else "Unknown error")
        )

    media = _pick_exported_media(out_dir)
    # Stable path for ffmpeg
    dest = work_dir / f"intermediate{media.suffix.lower()}"
    if media.resolve() != dest.resolve():
        shutil.copy2(media, dest)
        return dest
    return media


def run_export(
    sources: list[ExportSource],
    *,
    destination: Path,
    preset: ExportPreset,
    filename_pattern: str,
    keep_structure: bool,
    conflict: str = "suffix",
    progress: ProgressCb | None = None,
    should_cancel: CancelCb | None = None,
) -> JobResult:
    _ensure_runtime_import()
    import ffmpeg_runtime_resolve
    import dgpy_log

    logger = dgpy_log.setup()
    result = JobResult()
    ff = ffmpeg_runtime_resolve.resolve_ffmpeg()
    if not ff:
        raise RuntimeError(
            "ffmpeg not found. Install FFmpeg Runtime, set DGPY_FFMPEG, "
            "or Browse for ffmpeg in the dialog."
        )

    if conflict == "ask":
        logger.warning("conflict=ask is not supported in worker; using suffix")
        conflict = "suffix"

    if preset.video_codec and not _encoder_available(ff.path, preset.video_codec):
        raise RuntimeError(
            f"This ffmpeg build has no encoder '{preset.video_codec}'. "
            "Install/Update FFmpeg Runtime from Script Manager, or pick another preset. "
            "ProRes needs prores_ks in the ffmpeg build."
        )

    # Resolve preset early so failure is clear before the queue runs
    flame_preset = resolve_flame_movie_preset()
    logger.info("Using Flame intermediate preset: %s", flame_preset)

    enabled = [s for s in sources if s.enabled]
    total = len(enabled)
    if total == 0:
        return result

    with tempfile.TemporaryDirectory(prefix="dgpy_export_") as tmp:
        tmp_root = Path(tmp)
        for index, source in enumerate(enabled, start=1):
            if should_cancel and should_cancel():
                result.messages.append("Cancelled")
                break

            name = source.name
            if progress:
                progress(index - 1, total, f"Exporting {name}…")

            out_path = output_path_for(
                destination,
                source,
                preset=preset,
                filename_pattern=filename_pattern,
                keep_structure=keep_structure,
                index=index,
            )

            final_out = out_path
            if preset.kind != "frames" and final_out.exists():
                if conflict == "skip":
                    result.skipped += 1
                    result.messages.append(f"Skip existing: {final_out}")
                    continue
                if conflict == "suffix":
                    stem = final_out.stem
                    suffix = final_out.suffix
                    parent_dir = final_out.parent
                    n = 2
                    while True:
                        candidate = parent_dir / f"{stem}_{n}{suffix}"
                        if not candidate.exists():
                            final_out = candidate
                            break
                        n += 1

            try:
                final_out.parent.mkdir(parents=True, exist_ok=True)
                item_dir = tmp_root / f"{index:04d}"
                item_dir.mkdir(parents=True, exist_ok=True)
                intermediate = export_intermediate_flame(
                    source.item, item_dir, logger
                )

                if preset.kind == "frames":
                    seq_pattern = final_out
                    seq_pattern.parent.mkdir(parents=True, exist_ok=True)
                    cmd = build_ffmpeg_cmd(
                        ff.path, intermediate, seq_pattern, preset
                    )
                else:
                    cmd = build_ffmpeg_cmd(
                        ff.path, intermediate, final_out, preset
                    )

                logger.info("ffmpeg: %s", " ".join(cmd))
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip()[-800:]
                    raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err}")

                result.ok += 1
                result.messages.append(f"OK: {final_out}")
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.messages.append(f"FAIL {name}: {exc}")
                logger.exception("Export failed for %s", name)

            if progress:
                progress(index, total, f"Done {name}")

    return result
