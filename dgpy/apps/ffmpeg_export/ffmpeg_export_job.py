"""Export job: Flame intermediate → ffmpeg → destination."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ffmpeg_export_paths import output_path_for
from ffmpeg_export_presets import ExportPreset
from ffmpeg_export_selection import ExportSource

__version__ = "0.1.0"

ProgressCb = Callable[[int, int, str], None]  # done, total, message
CancelCb = Callable[[], bool]


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
    import os
    import sys

    import dgpy_paths

    runtime = dgpy_paths.dgpy_root() / "apps" / "ffmpeg_runtime"
    if runtime.is_dir() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))


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
        # image sequence / still: let ffmpeg pick from extension
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


def _export_intermediate_flame(clip, dest: Path, logger) -> None:
    """Best-effort Flame PyExporter → intermediate movie/file."""
    import flame

    dest.parent.mkdir(parents=True, exist_ok=True)
    exporter = flame.PyExporter()
    # Prefer foreground so we wait; attribute names vary by Flame version.
    for attr, value in (("foreground", True), ("wait_for_export", True)):
        if hasattr(exporter, attr):
            try:
                setattr(exporter, attr, value)
            except Exception:  # noqa: BLE001
                pass

    # API shapes differ; try common call patterns.
    errors: list[str] = []
    for kwargs in (
        {"clip": clip, "path": str(dest)},
        {},
    ):
        try:
            if kwargs:
                exporter.export(**kwargs)
            else:
                exporter.export(clip, str(dest))
            if dest.exists() and dest.stat().st_size > 0:
                return
        except TypeError as exc:
            errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            logger.warning("PyExporter attempt failed: %s", exc)

    raise RuntimeError(
        "Flame intermediate export failed. "
        "PyExporter preset/API needs real-machine confirmation. "
        + ("; ".join(errors[:3]) if errors else "No file written.")
    )


def run_export(
    sources: list[ExportSource],
    *,
    destination: Path,
    preset: ExportPreset,
    filename_pattern: str,
    keep_structure: bool,
    conflict: str = "suffix",  # suffix | skip (ask → suffix; avoid GUI in worker)
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
        # QMessageBox must not run inside QThread; use suffix for safety.
        logger.warning("conflict=ask is not supported in worker; using suffix")
        conflict = "suffix"

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
                intermediate = tmp_root / f"{index:04d}_{source.name}.mov"
                _export_intermediate_flame(source.item, intermediate, logger)

                if preset.kind == "frames":
                    seq_pattern = final_out
                    seq_pattern.parent.mkdir(parents=True, exist_ok=True)
                    cmd = build_ffmpeg_cmd(ff.path, intermediate, seq_pattern, preset)
                else:
                    cmd = build_ffmpeg_cmd(ff.path, intermediate, final_out, preset)

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
