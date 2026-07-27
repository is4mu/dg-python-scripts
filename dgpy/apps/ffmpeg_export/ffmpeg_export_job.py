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

__version__ = "0.1.6"

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]

_MEDIA_EXT = {".mov", ".mxf", ".mp4", ".m4v", ".avi", ".mkv", ".mpg", ".mpeg"}

_WARN_FLAGS = (
    "warn_on_mixed_colour_space",
    "warn_on_link_unsupported",
    "warn_on_no_media",
    "warn_on_pending_render",
    "warn_on_reimport_unsupported",
    "warn_on_unlinked",
    "warn_on_unrendered",
)

# Intermediate (Flame → disk before ffmpeg). MAX quality first:
# 1) ProRes 4444 XQ — 12-bit 4:4:4, HDR-oriented (studio max mezzanine)
# 2) ProRes 4444 — slightly lighter than XQ
# 3) ProRes 422 HQ / 422 — fallbacks if 4444 presets missing
# Avoid H.264/MP4/XAVC as mezzanine (double lossy encode).
_PREFERRED_RELATIVE = (
    "Apple Final Cut Pro/Final Cut Pro (Apple ProRes 4444 XQ).xml",
    "Apple Final Cut Pro/Final Cut Pro (Apple ProRes 4444).xml",
    "Apple Final Cut Pro/Final Cut Pro (Apple ProRes 422 HQ).xml",
    "Apple Final Cut Pro/Final Cut Pro (Apple ProRes 422).xml",
    "Avid Media Composer/Avid Media Composer (QuickTime DNxHR HQX 10-bit).xml",
    "Cinedeck/Cinedeck (Apple ProRes 422).xml",
    "QuickTime/QuickTime (8-bit Uncompressed).xml",
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


def _apply_exporter_quiet_flags(exporter) -> None:
    """Disable Flame export confirmation dialogs that have API toggles."""
    for name in _WARN_FLAGS:
        if hasattr(exporter, name):
            try:
                setattr(exporter, name, False)
            except Exception:  # noqa: BLE001
                pass


class _AutoContinueFlameDialogs:
    """Click Continue on Flame modals that lack a Python suppress flag.

    Example: "Export preset is from an old version".
    Colour-space warnings should already be off via warn_on_mixed_colour_space.
    """

    _TITLE_HINTS = ("old version", "confirm operation", "export preset")
    _BUTTON_HINTS = ("continue", "continue export", "ok", "yes")

    def __init__(self) -> None:
        self._timer = None

    def start(self) -> None:
        from PySide6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        def tick() -> None:
            for widget in app.topLevelWidgets():
                if not widget.isVisible():
                    continue
                title = (widget.windowTitle() or "").lower()
                if any(h in title for h in self._TITLE_HINTS) or self._looks_like_export_warning(
                    widget
                ):
                    self._click_continue(widget)

        self._timer = QtCore.QTimer()
        self._timer.setInterval(200)
        self._timer.timeout.connect(tick)
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @staticmethod
    def _looks_like_export_warning(widget) -> bool:
        from PySide6 import QtWidgets

        texts = [(label.text() or "").lower() for label in widget.findChildren(QtWidgets.QLabel)]
        blob = " ".join(texts)
        return (
            "older version" in blob
            or "colour space" in blob
            or "color space" in blob
            or "export preset" in blob
        )

    @classmethod
    def _click_continue(cls, widget) -> None:
        from PySide6 import QtWidgets

        for btn in widget.findChildren(QtWidgets.QPushButton):
            text = (btn.text() or "").strip().lower().replace("&", "")
            if text in cls._BUTTON_HINTS or text.startswith("continue"):
                if btn.isEnabled() and btn.isVisible():
                    btn.click()
                    return


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

    try:
        import flame

        preset_dir = Path(
            flame.PyExporter.get_presets_dir(
                flame.PyExporter.PresetVisibility.Autodesk,
                flame.PyExporter.PresetType.Movie,
            )
        )
        for rel in _PREFERRED_RELATIVE:
            candidate = preset_dir / rel
            if candidate.is_file():
                return candidate
        found = sorted(preset_dir.rglob("*.xml"))
        if found:
            return found[0]
    except Exception:  # noqa: BLE001
        pass

    roots = _movie_preset_roots()
    by_name: dict[str, Path] = {}
    for root in roots:
        for xml in root.rglob("*.xml"):
            by_name.setdefault(xml.name, xml)
    for rel in _PREFERRED_RELATIVE:
        name = Path(rel).name
        if name in by_name:
            return by_name[name]
    for root in roots:
        found = sorted(root.rglob("*.xml"))
        if found:
            return found[0]

    raise RuntimeError(
        "No Flame Movie File export preset found. "
        "In Flame Media Export, open a Movie preset, Continue past the "
        "version warning, Save As to Shared/Project, then set "
        "flame_movie_preset in dgpy/state/ffmpeg_export.json"
    )


def _pick_exported_media(out_dir: Path) -> Path:
    files = [
        p
        for p in out_dir.rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in _MEDIA_EXT
    ]
    if not files:
        files = [
            p for p in out_dir.rglob("*") if p.is_file() and not p.name.startswith(".")
        ]
    if not files:
        raise RuntimeError(f"Flame export produced no files in {out_dir}")
    return max(files, key=lambda p: p.stat().st_size)


def export_intermediate_flame(clip, work_dir: Path, logger) -> Path:
    """Flame PyExporter → temp movie (sources, preset_xml, output_dir)."""
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
    _apply_exporter_quiet_flags(exporter)

    logger.info(
        "PyExporter.export sources=%s preset=%s out=%s",
        type(clip).__name__,
        preset_path,
        out_dir,
    )

    auto = _AutoContinueFlameDialogs()
    auto.start()
    try:
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
    finally:
        auto.stop()

    media = _pick_exported_media(out_dir)
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
        logger.warning("conflict=ask is not supported; using suffix")
        conflict = "suffix"

    if preset.video_codec and not _encoder_available(ff.path, preset.video_codec):
        raise RuntimeError(
            f"This ffmpeg build has no encoder '{preset.video_codec}'. "
            "Install/Update FFmpeg Runtime, or pick another preset."
        )

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
                intermediate = export_intermediate_flame(source.item, item_dir, logger)

                if preset.kind == "frames":
                    seq_pattern = final_out
                    seq_pattern.parent.mkdir(parents=True, exist_ok=True)
                    cmd = build_ffmpeg_cmd(ff.path, intermediate, seq_pattern, preset)
                else:
                    cmd = build_ffmpeg_cmd(ff.path, intermediate, final_out, preset)

                logger.info("ffmpeg: %s", " ".join(cmd))
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, check=False
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
