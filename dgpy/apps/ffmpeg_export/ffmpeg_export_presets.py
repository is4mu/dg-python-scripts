"""Built-in export presets (v1). User presets: state/export_presets.json."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import dgpy_paths

__version__ = "0.1.0"


@dataclass
class ExportPreset:
    id: str
    label: str
    kind: str = "movie"  # movie | still | frames | audio
    container: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_channels: str = "source"  # source | 2 | 1 | none
    crf: int | None = 18
    video_bitrate: str = ""  # e.g. 8M — used when crf is None
    audio_bitrate: str = "192k"
    pix_fmt: str = "yuv420p"
    scale: str = "source"  # source | WxH
    fps: str = "source"
    summary: str = ""
    builtin: bool = True
    extra_ffmpeg: list[str] = field(default_factory=list)

    def short_summary(self) -> str:
        if self.summary:
            return self.summary
        if self.kind == "still":
            return f"Still · {self.container.upper()}"
        if self.kind == "frames":
            return f"Frames · {self.container.upper()} sequence"
        if self.kind == "audio":
            return f"Audio · {self.audio_codec} · {self.container}"
        rate = f"CRF {self.crf}" if self.crf is not None else (self.video_bitrate or "bitrate?")
        audio = "no audio" if self.audio_channels == "none" else self.audio_codec
        return (
            f"{self.container.upper()} · {self.video_codec} · {rate} · "
            f"{audio} · Size {self.scale} · FPS {self.fps}"
        )


def _builtins() -> list[ExportPreset]:
    return [
        ExportPreset(
            id="review_h264_hq",
            label="Review — H.264 HQ (MP4)",
            container="mp4",
            video_codec="libx264",
            audio_codec="aac",
            crf=18,
            summary="MP4 · H.264 High · AAC stereo · Source size/fps",
        ),
        ExportPreset(
            id="review_h264_small",
            label="Review — H.264 Small (MP4)",
            container="mp4",
            video_codec="libx264",
            audio_codec="aac",
            crf=28,
            summary="MP4 · H.264 Small · AAC stereo",
        ),
        ExportPreset(
            id="delivery_h265",
            label="Delivery — H.265 (MP4)",
            container="mp4",
            video_codec="libx265",
            audio_codec="aac",
            crf=22,
            pix_fmt="yuv420p",
            summary="MP4 · H.265 · AAC stereo",
        ),
        ExportPreset(
            id="web_vp9",
            label="Web — VP9 (WebM)",
            container="webm",
            video_codec="libvpx-vp9",
            audio_codec="libopus",
            crf=32,
            audio_bitrate="128k",
            summary="WebM · VP9 · Opus",
        ),
        ExportPreset(
            id="audio_wav",
            label="Audio — WAV",
            kind="audio",
            container="wav",
            video_codec="",
            audio_codec="pcm_s24le",
            audio_channels="source",
            crf=None,
            summary="WAV · PCM 24-bit",
        ),
        ExportPreset(
            id="still_png",
            label="Still — PNG",
            kind="still",
            container="png",
            video_codec="",
            audio_codec="",
            audio_channels="none",
            crf=None,
            summary="Single frame · PNG",
        ),
        ExportPreset(
            id="still_jpeg",
            label="Still — JPEG",
            kind="still",
            container="jpg",
            video_codec="",
            audio_codec="",
            audio_channels="none",
            crf=None,
            summary="Single frame · JPEG",
        ),
        ExportPreset(
            id="frames_png",
            label="Frames — PNG sequence",
            kind="frames",
            container="png",
            video_codec="",
            audio_codec="",
            audio_channels="none",
            crf=None,
            summary="Image sequence · PNG",
        ),
    ]


def user_presets_path(root: Path | None = None) -> Path:
    return dgpy_paths.state_dir(root) / "export_presets.json"


def load_user_presets(root: Path | None = None) -> list[ExportPreset]:
    path = user_presets_path(root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("presets") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    out: list[ExportPreset] = []
    for entry in items:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        try:
            out.append(
                ExportPreset(
                    id=str(entry["id"]),
                    label=str(entry.get("label") or entry["id"]),
                    kind=str(entry.get("kind") or "movie"),
                    container=str(entry.get("container") or "mp4"),
                    video_codec=str(entry.get("video_codec") or ""),
                    audio_codec=str(entry.get("audio_codec") or ""),
                    audio_channels=str(entry.get("audio_channels") or "source"),
                    crf=entry.get("crf"),
                    video_bitrate=str(entry.get("video_bitrate") or ""),
                    audio_bitrate=str(entry.get("audio_bitrate") or "192k"),
                    pix_fmt=str(entry.get("pix_fmt") or "yuv420p"),
                    scale=str(entry.get("scale") or "source"),
                    fps=str(entry.get("fps") or "source"),
                    summary=str(entry.get("summary") or ""),
                    builtin=False,
                    extra_ffmpeg=list(entry.get("extra_ffmpeg") or []),
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    return out


def save_user_preset(preset: ExportPreset, root: Path | None = None) -> None:
    """Insert or replace a user preset (never overwrites builtin ids on disk as builtin)."""
    path = user_presets_path(root)
    existing = {p.id: p for p in load_user_presets(root)}
    copy = deepcopy(preset)
    copy.builtin = False
    if copy.id.startswith("builtin:") or any(b.id == copy.id for b in _builtins()):
        copy.id = f"user_{copy.id}"
    existing[copy.id] = copy
    payload = {
        "presets": [asdict(p) for p in existing.values()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def all_presets(root: Path | None = None) -> list[ExportPreset]:
    return _builtins() + load_user_presets(root)


def find_preset(preset_id: str, root: Path | None = None) -> ExportPreset | None:
    for p in all_presets(root):
        if p.id == preset_id:
            return deepcopy(p)
    return None


def default_preset(root: Path | None = None) -> ExportPreset:
    presets = all_presets(root)
    return deepcopy(presets[0]) if presets else ExportPreset(id="empty", label="Empty")
