"""MatAnyone job: export → (optional SAM) → infer → import.

Heavy subprocess work streams logs and respects cancel. Flame API calls
(export / import) are marshalled to the Qt main thread when needed.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import dgpy_paths

__version__ = "0.9.1"

ProgressCb = Callable[[str], None]
StepCb = Callable[[int, int, str], None]
MAX_SIZE = 1080

JOB_STEPS: list[tuple[str, int]] = [
    ("Prepare work dir", 1),
    ("Export source", 3),
    ("Prepare mask", 2),
    ("MatAnyone 2 infer", 8),
    ("Import to Flame", 2),
    ("Done", 1),
]

EXPORT_STEPS: list[tuple[str, int]] = [
    ("Prepare work dir", 1),
    ("Export source", 4),
    ("Extract first frame", 2),
    ("Done", 1),
]

INFER_STEPS: list[tuple[str, int]] = [
    ("Prepare", 1),
    ("Forward MatAnyone", 6),
    ("Backward MatAnyone", 6),
    ("Join + upscale", 3),
    ("Import to Flame", 2),
    ("Done", 1),
]

_WARN_FLAGS = (
    "warn_on_mixed_colour_space",
    "warn_on_link_unsupported",
    "warn_on_no_media",
    "warn_on_pending_render",
    "warn_on_reimport_unsupported",
    "warn_on_unlinked",
    "warn_on_unrendered",
)


@dataclass
class JobOptions:
    clip: Any
    mask_source: str = "flame"  # "flame" | "sam2"
    mask_path: Path | None = None
    sam_points: list[tuple[float, float]] = field(default_factory=list)
    sam_points_provider: Callable[[Path], list[tuple[float, float]] | None] | None = None
    output_kind: str = "alpha_sequence"  # alpha_sequence | alpha_movie
    write_foreground: bool = False
    import_to_flame: bool = True
    import_destination: Any | None = None
    work_dir: Path | None = None
    phase: str = "full"  # export | infer | full
    source_video: Path | None = None
    result_basename: str = "clip"  # sanitized source name without _Alpha
    ref_frame_index: int = 0  # mask applies to this frame; bidirectional when > 0


@dataclass
class JobResult:
    ok: bool = False
    message: str = ""
    work_dir: Path | None = None
    alpha_path: Path | None = None
    foreground_path: Path | None = None
    imported: bool = False
    cancelled: bool = False
    video_path: Path | None = None
    still_path: Path | None = None


class JobCancelled(Exception):
    """Raised when the operator cancels a running job."""


def _steps_for(phase: str) -> list[tuple[str, int]]:
    if phase == "export":
        return EXPORT_STEPS
    if phase == "infer":
        return INFER_STEPS
    return JOB_STEPS


def job_step_count(phase: str = "full") -> int:
    return len(_steps_for(phase))


def job_step_label(index: int, phase: str = "full") -> str:
    steps = _steps_for(phase)
    if 0 <= index < len(steps):
        return steps[index][0]
    return ""


def default_work_dir(job_id: str | None = None) -> Path:
    jid = job_id or time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    return Path("/tmp") / "dgpy_matanyone" / jid


def _preset_xml() -> Path:
    return Path(__file__).resolve().parent / "presets" / "intermediate_mp4.xml"


def _apply_exporter_quiet_flags(exporter) -> None:
    for name in _WARN_FLAGS:
        if hasattr(exporter, name):
            try:
                setattr(exporter, name, False)
            except Exception:  # noqa: BLE001
                pass


_MAIN_INVOKER: Any = None


def _main_invoker():
    """Lazy singleton QObject living on the Qt GUI thread."""
    global _MAIN_INVOKER
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        return None

    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    if _MAIN_INVOKER is not None:
        return _MAIN_INVOKER

    class _Invoker(QtCore.QObject):
        @QtCore.Slot()
        def _run(self) -> None:
            try:
                self._result = self._fn()
                self._error = None
            except Exception as exc:  # noqa: BLE001
                self._result = None
                self._error = exc

    inv = _Invoker()
    inv.moveToThread(app.thread())
    inv._fn = None
    inv._result = None
    inv._error = None
    _MAIN_INVOKER = inv
    return inv


def _call_on_main_thread(fn: Callable[[], Any]) -> Any:
    """Run Flame API / modal UI work on the Qt GUI thread when needed."""
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        return fn()

    app = QtWidgets.QApplication.instance()
    if app is None:
        return fn()
    if QtCore.QThread.currentThread() == app.thread():
        return fn()

    invoker = _main_invoker()
    if invoker is None:
        return fn()
    invoker._fn = fn
    invoker._result = None
    invoker._error = None
    QtCore.QMetaObject.invokeMethod(
        invoker,
        "_run",
        QtCore.Qt.ConnectionType.BlockingQueuedConnection,
    )
    if invoker._error is not None:
        raise invoker._error
    return invoker._result


def export_clip_mp4(clip, out_dir: Path, *, logger) -> Path:
    """Export clip to MP4 via PyExporter; return path to produced movie."""
    import flame

    out_dir.mkdir(parents=True, exist_ok=True)
    preset = _preset_xml()
    if not preset.is_file():
        raise RuntimeError(f"Export preset missing: {preset}")

    def _do() -> Path:
        before = {p.resolve() for p in out_dir.rglob("*") if p.is_file()}
        exporter = flame.PyExporter()
        exporter.foreground = True
        if hasattr(exporter, "export_between_marks"):
            exporter.export_between_marks = False
        if hasattr(exporter, "use_top_video_track"):
            exporter.use_top_video_track = True
        _apply_exporter_quiet_flags(exporter)

        sources = [clip]
        try:
            exporter.export(sources, str(preset), str(out_dir))
        except TypeError:
            exporter.export(clip, str(preset), str(out_dir))

        after = [p for p in out_dir.rglob("*") if p.is_file()]
        new_files = [p for p in after if p.resolve() not in before]
        movies = [
            p
            for p in (new_files or after)
            if p.suffix.lower() in {".mp4", ".mov", ".mxf", ".avi"}
        ]
        if not movies:
            raise RuntimeError(f"No movie produced in {out_dir}")
        movies.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        logger.info("MatAnyone exported: %s", movies[0])
        return movies[0]

    return _call_on_main_thread(_do)


class _ProcHolder:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def set(self, proc: subprocess.Popen | None) -> None:
        with self._lock:
            self.proc = proc

    def kill(self) -> None:
        with self._lock:
            proc = self.proc
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise JobCancelled("Cancelled by user")


def _run_streaming(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
    tail: int = 40,
) -> None:
    log("$ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    if holder is not None:
        holder.set(proc)
    assert proc.stdout is not None
    recent: list[str] = []
    try:
        for line in proc.stdout:
            _check_cancel(cancel)
            text = line.rstrip()
            if text:
                log(text)
                recent.append(text)
                if len(recent) > tail:
                    recent = recent[-tail:]
        code = proc.wait()
    finally:
        if holder is not None:
            holder.set(None)
    _check_cancel(cancel)
    if code != 0:
        detail = "\n".join(recent[-tail:]) if recent else "(no output)"
        raise RuntimeError(
            f"Command failed ({code}): {' '.join(cmd)}\n\n--- output ---\n{detail}"
        )


def extract_first_frame(
    video: Path,
    still: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    """Write first frame PNG. Prefer ffmpeg (avoids OpenCV in the pipeline)."""
    return extract_frame_at(
        video,
        0,
        still,
        python=python,
        log=log,
        cancel=cancel,
        holder=holder,
    )


def probe_frame_count(video: Path, *, python: str | None = None) -> int:
    """Best-effort frame count for the intermediate export video."""
    import shutil

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_packets",
                "-show_entries",
                "stream=nb_read_packets",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            raw = (proc.stdout or "").strip().splitlines()
            if raw:
                try:
                    n = int(raw[0].strip().split(",")[0])
                    if n > 0:
                        return n
                except ValueError:
                    pass
        proc2 = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc2.returncode == 0:
            raw = (proc2.stdout or "").strip()
            if raw.isdigit() and int(raw) > 0:
                return int(raw)

    if not python:
        raise RuntimeError(f"Could not probe frame count for {video}")
    code = (
        "import sys,cv2\n"
        "cap=cv2.VideoCapture(sys.argv[1])\n"
        "n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()\n"
        "if n<1: raise SystemExit('bad frame count')\n"
        "print(n)\n"
    )
    proc = subprocess.run(
        [python, "-c", code, str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Could not probe frame count for {video}: "
            f"{(proc.stderr or proc.stdout or '').strip()}"
        )
    return int((proc.stdout or "").strip())


def extract_frame_at(
    video: Path,
    frame_index: int,
    still: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    """Write PNG for frame_index (0-based) from video."""
    import shutil

    if frame_index < 0:
        raise RuntimeError(f"Invalid frame index: {frame_index}")
    still.parent.mkdir(parents=True, exist_ok=True)
    log(f"Extract frame {frame_index} → {still}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                f"select=eq(n\\,{frame_index})",
                "-vsync",
                "vfr",
                "-frames:v",
                "1",
                str(still),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    else:
        code = (
            "import sys,cv2\n"
            "cap=cv2.VideoCapture(sys.argv[1]); idx=int(sys.argv[2])\n"
            "cap.set(cv2.CAP_PROP_POS_FRAMES, idx)\n"
            "ok,frame=cap.read(); cap.release()\n"
            "if not ok: raise SystemExit('failed to read frame')\n"
            "cv2.imwrite(sys.argv[3], frame)\n"
        )
        _run_streaming(
            [python, "-c", code, str(video), str(frame_index), str(still)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not still.is_file():
        raise RuntimeError(f"Frame extract produced no file (index={frame_index})")
    return still


def _which_ffmpeg() -> str | None:
    import shutil

    return shutil.which("ffmpeg")


def _opencv_video_tool(
    python: str,
    code: str,
    args: list[str],
    *,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    """Run a small OpenCV helper in the MatAnyone runtime venv."""
    _run_streaming(
        [python, "-c", code, *args],
        log=log,
        cancel=cancel,
        holder=holder,
    )


_CV_FORWARD = (
    "import sys,cv2\n"
    "src,dst,start=sys.argv[1],sys.argv[2],int(sys.argv[3])\n"
    "cap=cv2.VideoCapture(src)\n"
    "if not cap.isOpened(): raise SystemExit('open failed')\n"
    "fps=cap.get(cv2.CAP_PROP_FPS) or 24.0\n"
    "w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
    "cap.set(cv2.CAP_PROP_POS_FRAMES, start)\n"
    "fourcc=cv2.VideoWriter_fourcc(*'mp4v')\n"
    "wr=cv2.VideoWriter(dst,fourcc,fps,(w,h),True)\n"
    "if not wr.isOpened(): raise SystemExit('writer open failed')\n"
    "n=0\n"
    "while True:\n"
    "    ok,frame=cap.read()\n"
    "    if not ok: break\n"
    "    wr.write(frame); n+=1\n"
    "cap.release(); wr.release()\n"
    "if n<1: raise SystemExit('no frames written')\n"
    "print(f'wrote {n} frames')\n"
)

_CV_BACKWARD_IN = (
    "import sys,cv2\n"
    "src,dst,end=sys.argv[1],sys.argv[2],int(sys.argv[3])\n"
    "cap=cv2.VideoCapture(src)\n"
    "if not cap.isOpened(): raise SystemExit('open failed')\n"
    "fps=cap.get(cv2.CAP_PROP_FPS) or 24.0\n"
    "w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
    "frames=[]\n"
    "for i in range(end+1):\n"
    "    cap.set(cv2.CAP_PROP_POS_FRAMES, i)\n"
    "    ok,frame=cap.read()\n"
    "    if not ok: raise SystemExit(f'read failed at {i}')\n"
    "    frames.append(frame)\n"
    "cap.release()\n"
    "frames.reverse()\n"
    "fourcc=cv2.VideoWriter_fourcc(*'mp4v')\n"
    "wr=cv2.VideoWriter(dst,fourcc,fps,(w,h),True)\n"
    "if not wr.isOpened(): raise SystemExit('writer open failed')\n"
    "for frame in frames: wr.write(frame)\n"
    "wr.release()\n"
    "print(f'wrote {len(frames)} frames')\n"
)

_CV_REVERSE = (
    "import sys,cv2\n"
    "src,dst=sys.argv[1],sys.argv[2]\n"
    "cap=cv2.VideoCapture(src)\n"
    "if not cap.isOpened(): raise SystemExit('open failed')\n"
    "fps=cap.get(cv2.CAP_PROP_FPS) or 24.0\n"
    "w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
    "frames=[]\n"
    "while True:\n"
    "    ok,frame=cap.read()\n"
    "    if not ok: break\n"
    "    frames.append(frame)\n"
    "cap.release()\n"
    "if not frames: raise SystemExit('no frames')\n"
    "frames.reverse()\n"
    "fourcc=cv2.VideoWriter_fourcc(*'mp4v')\n"
    "wr=cv2.VideoWriter(dst,fourcc,fps,(w,h),True)\n"
    "if not wr.isOpened(): raise SystemExit('writer open failed')\n"
    "for frame in frames: wr.write(frame)\n"
    "wr.release()\n"
    "print(f'reversed {len(frames)} frames')\n"
)

_CV_JOIN = (
    "import sys,cv2\n"
    "a,b,dst,n=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])\n"
    "ca=cv2.VideoCapture(a); cb=cv2.VideoCapture(b)\n"
    "if not ca.isOpened() or not cb.isOpened(): raise SystemExit('open failed')\n"
    "fps=ca.get(cv2.CAP_PROP_FPS) or cb.get(cv2.CAP_PROP_FPS) or 24.0\n"
    "w=int(ca.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(ca.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
    "fourcc=cv2.VideoWriter_fourcc(*'mp4v')\n"
    "wr=cv2.VideoWriter(dst,fourcc,fps,(w,h),True)\n"
    "if not wr.isOpened(): raise SystemExit('writer open failed')\n"
    "count=0\n"
    "for i in range(n):\n"
    "    ok,frame=ca.read()\n"
    "    if not ok: raise SystemExit(f'bwd short at {i}')\n"
    "    if frame.shape[1]!=w or frame.shape[0]!=h:\n"
    "        frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_LANCZOS4)\n"
    "    wr.write(frame); count+=1\n"
    "ca.release()\n"
    "while True:\n"
    "    ok,frame=cb.read()\n"
    "    if not ok: break\n"
    "    if frame.shape[1]!=w or frame.shape[0]!=h:\n"
    "        frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_LANCZOS4)\n"
    "    wr.write(frame); count+=1\n"
    "cb.release(); wr.release()\n"
    "if count<1: raise SystemExit('no frames joined')\n"
    "print(f'joined {count} frames')\n"
)


def make_forward_segment(
    video: Path,
    ref_index: int,
    out_mp4: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    """Write MP4 of frames ref_index…end (frame 0 of result = ref)."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    log(f"Build forward segment from frame {ref_index} → {out_mp4.name}")
    ffmpeg = _which_ffmpeg()
    if ffmpeg:
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                f"select='gte(n\\,{ref_index})',setpts=N/FRAME_RATE/TB",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(out_mp4),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    else:
        log("ffmpeg not found; using OpenCV for forward segment")
        _opencv_video_tool(
            python,
            _CV_FORWARD,
            [str(video), str(out_mp4), str(ref_index)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not out_mp4.is_file():
        raise RuntimeError("Forward segment missing")
    return out_mp4


def make_backward_input_segment(
    video: Path,
    ref_index: int,
    out_mp4: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    """Write MP4 of frames ref…0 in reverse (frame 0 of result = ref)."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    log(f"Build backward-input segment (reverse 0…{ref_index}) → {out_mp4.name}")
    ffmpeg = _which_ffmpeg()
    if ffmpeg:
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                f"select='lte(n\\,{ref_index})',setpts=N/FRAME_RATE/TB,reverse",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(out_mp4),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    else:
        log("ffmpeg not found; using OpenCV for backward-input segment")
        _opencv_video_tool(
            python,
            _CV_BACKWARD_IN,
            [str(video), str(out_mp4), str(ref_index)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not out_mp4.is_file():
        raise RuntimeError("Backward input segment missing")
    return out_mp4


def _reverse_movie(
    src: Path,
    dest: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"Reverse movie {src.name} → {dest.name}")
    ffmpeg = _which_ffmpeg()
    if ffmpeg:
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-vf",
                "reverse",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    else:
        log("ffmpeg not found; using OpenCV to reverse movie")
        _opencv_video_tool(
            python,
            _CV_REVERSE,
            [str(src), str(dest)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not dest.is_file():
        raise RuntimeError(f"Reverse movie failed: {dest}")
    return dest


def _list_seq_frames(seq_dir: Path) -> list[Path]:
    frames = sorted(seq_dir.glob("*.png"))
    if not frames:
        frames = sorted(seq_dir.glob("*.exr"))
    return frames


def _reverse_sequence_dir(
    src_dir: Path,
    dest_dir: Path,
    *,
    log: ProgressCb,
) -> Path:
    frames = _list_seq_frames(src_dir)
    if not frames:
        raise RuntimeError(f"No frames to reverse in {src_dir}")
    if dest_dir.exists():
        import shutil

        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f"Reverse sequence ({len(frames)} frames) → {dest_dir.name}")
    width = max(4, len(str(len(frames) - 1)))
    suffix = frames[0].suffix
    for i, frame in enumerate(reversed(frames)):
        target = dest_dir / f"{i:0{width}d}{suffix}"
        target.write_bytes(frame.read_bytes())
    return dest_dir


def reverse_matanyone_outputs(
    src_out: Path,
    dest_out: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    """Time-reverse pha/fgr movies and pha/ sequence under a MatAnyone out dir."""
    import shutil

    if dest_out.exists():
        shutil.rmtree(dest_out)
    dest_out.mkdir(parents=True, exist_ok=True)
    pha_mov, fgr_mov, pha_dir = _find_outputs(src_out)
    if pha_dir is not None:
        _reverse_sequence_dir(pha_dir, dest_out / "pha", log=log)
    if pha_mov is not None:
        tmp = dest_out / f".{pha_mov.name}.rev.mp4"
        _reverse_movie(
            pha_mov, tmp, python=python, log=log, cancel=cancel, holder=holder
        )
        final = dest_out / pha_mov.name
        if final.exists():
            final.unlink()
        tmp.rename(final)
    if fgr_mov is not None:
        tmp = dest_out / f".{fgr_mov.name}.rev.mp4"
        _reverse_movie(
            fgr_mov, tmp, python=python, log=log, cancel=cancel, holder=holder
        )
        final = dest_out / fgr_mov.name
        if final.exists():
            final.unlink()
        tmp.rename(final)


def _join_sequence_dirs(
    bwd_dir: Path,
    fwd_dir: Path,
    *,
    ref_index: int,
    dest_dir: Path,
    log: ProgressCb,
) -> Path:
    bwd = _list_seq_frames(bwd_dir)
    fwd = _list_seq_frames(fwd_dir)
    if not bwd or not fwd:
        raise RuntimeError("Join sequence: missing frames")
    head = bwd[:ref_index]
    combined = head + fwd
    if dest_dir.exists():
        import shutil

        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    width = max(4, len(str(max(len(combined) - 1, 0))))
    suffix = combined[0].suffix
    log(f"Join sequence: {len(head)} (bwd) + {len(fwd)} (fwd) → {len(combined)}")
    for i, frame in enumerate(combined):
        (dest_dir / f"{i:0{width}d}{suffix}").write_bytes(frame.read_bytes())
    return dest_dir


def _join_movies(
    bwd_mov: Path,
    fwd_mov: Path,
    *,
    ref_index: int,
    dest: Path,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    """Concat first ref_index frames of bwd with all of fwd."""
    import shutil

    dest.parent.mkdir(parents=True, exist_ok=True)
    if ref_index <= 0:
        shutil.copy2(fwd_mov, dest)
        return dest
    log(f"Join movies: bwd[0…{ref_index - 1}] + fwd")
    ffmpeg = _which_ffmpeg()
    if ffmpeg:
        part_a = dest.with_name(f".{dest.stem}_a{dest.suffix}")
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(bwd_mov),
                "-vf",
                f"select='lt(n\\,{ref_index})',setpts=N/FRAME_RATE/TB",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(part_a),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(part_a),
                "-i",
                str(fwd_mov),
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
        try:
            part_a.unlink()
        except OSError:
            pass
    else:
        log("ffmpeg not found; using OpenCV to join movies")
        _opencv_video_tool(
            python,
            _CV_JOIN,
            [str(bwd_mov), str(fwd_mov), str(dest), str(ref_index)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not dest.is_file():
        raise RuntimeError("Joined movie missing")
    return dest


def join_matanyone_outputs(
    bwd_out: Path,
    fwd_out: Path,
    *,
    ref_index: int,
    dest_out: Path,
    write_foreground: bool,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    """Join reversed-backward + forward into dest_out (pha / *_pha / *_fgr)."""
    import shutil

    if dest_out.exists():
        shutil.rmtree(dest_out)
    dest_out.mkdir(parents=True, exist_ok=True)
    b_pha, b_fgr, b_dir = _find_outputs(bwd_out)
    f_pha, f_fgr, f_dir = _find_outputs(fwd_out)

    if b_dir is not None and f_dir is not None:
        _join_sequence_dirs(
            b_dir, f_dir, ref_index=ref_index, dest_dir=dest_out / "pha", log=log
        )
    if b_pha is not None and f_pha is not None:
        _join_movies(
            b_pha,
            f_pha,
            ref_index=ref_index,
            dest=dest_out / "clip_pha.mp4",
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )
    elif f_pha is not None and ref_index == 0:
        shutil.copy2(f_pha, dest_out / f_pha.name)

    if write_foreground and b_fgr is not None and f_fgr is not None:
        _join_movies(
            b_fgr,
            f_fgr,
            ref_index=ref_index,
            dest=dest_out / "clip_fgr.mp4",
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )
    elif write_foreground and f_fgr is not None and ref_index == 0:
        shutil.copy2(f_fgr, dest_out / f_fgr.name)


def run_sam_mask(
    *,
    python: str,
    sam_script: Path,
    image: Path,
    points: list[tuple[float, float]],
    out_mask: Path,
    checkpoint: Path,
    config: str,
    cwd: Path | None = None,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    if not points:
        raise RuntimeError("SAM2 mode needs at least one foreground point")
    # Refresh helper so path-unshadow fix applies without full SAM2 reinstall.
    try:
        import matanyone_runtime_setup as rsetup

        rsetup._write_sam_helper(sam_script)
    except Exception as exc:  # noqa: BLE001
        log(f"Warning: could not refresh SAM2 helper: {exc}")
    pts = ";".join(f"{x},{y}" for x, y in points)
    out_mask.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        python,
        str(sam_script),
        "--image",
        str(image),
        "--points",
        pts,
        "--out",
        str(out_mask),
        "--checkpoint",
        str(checkpoint),
        "--config",
        config,
    ]
    try:
        # cwd must NOT be the runtime root (parent of a clone named sam2/).
        # Prefer an unrelated work dir; None uses Flame's cwd.
        _run_streaming(cmd, cwd=cwd, log=log, cancel=cancel, holder=holder)
    except RuntimeError as exc:
        raise RuntimeError(
            "SAM2 mask failed. Use Flame mask, or re-run "
            "DGpy → MatAnyone → SAM2 Setup…\n"
            f"{exc}"
        ) from exc
    if not out_mask.is_file():
        raise RuntimeError("SAM2 mask produced no file")
    return out_mask


def run_matanyone(
    *,
    python: str,
    inference_script: Path,
    source: Path,
    mask: Path,
    out_dir: Path,
    save_image: bool,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        python,
        str(inference_script),
        "-i",
        str(source),
        "-m",
        str(mask),
        "-o",
        str(out_dir),
        "--max_size",
        str(MAX_SIZE),
    ]
    if save_image:
        # inference_matanyone2.py (argparse) uses underscores;
        # the `matanyone2` Typer CLI uses hyphens — we call the .py script.
        cmd.append("--save_image")
    _run_streaming(
        cmd,
        cwd=inference_script.parent,
        log=log,
        cancel=cancel,
        holder=holder,
    )


def _find_outputs(out_dir: Path) -> tuple[Path | None, Path | None, Path | None]:
    """Return (alpha_movie, fgr_movie, alpha_seq_dir)."""
    pha_mov = None
    fgr_mov = None
    pha_dir = None
    for path in sorted(out_dir.rglob("*")):
        name = path.name.lower()
        if path.is_file() and name.endswith("_pha.mp4"):
            pha_mov = path
        elif path.is_file() and name.endswith("_fgr.mp4"):
            fgr_mov = path
        elif path.is_dir() and path.name == "pha":
            pha_dir = path
    return pha_mov, fgr_mov, pha_dir


def _probe_size_ffprobe(path: Path) -> tuple[int, int] | None:
    import shutil

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    parts = line[0].strip().split("x")
    if len(parts) != 2:
        return None
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if w < 1 or h < 1:
        return None
    return w, h


def _probe_size_opencv(path: Path, *, python: str) -> tuple[int, int]:
    code = (
        "import sys\n"
        "import cv2\n"
        "p=sys.argv[1]\n"
        "img=cv2.imread(p, cv2.IMREAD_UNCHANGED)\n"
        "if img is not None:\n"
        "    h,w=img.shape[:2]; print(f'{w}x{h}'); raise SystemExit(0)\n"
        "cap=cv2.VideoCapture(p)\n"
        "w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n"
        "cap.release()\n"
        "if w<1 or h<1: raise SystemExit('probe failed')\n"
        "print(f'{w}x{h}')\n"
    )
    proc = subprocess.run(
        [python, "-c", code, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Failed to probe size for {path}: {detail}")
    parts = (proc.stdout or "").strip().split("x")
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected probe output for {path}: {proc.stdout!r}")
    return int(parts[0]), int(parts[1])


def probe_media_size(path: Path, *, python: str) -> tuple[int, int]:
    """Return (width, height) of an image or video on disk."""
    sized = _probe_size_ffprobe(path)
    if sized is not None:
        return sized
    return _probe_size_opencv(path, python=python)


def _first_sequence_frame(seq_dir: Path) -> Path | None:
    frames = sorted(seq_dir.glob("*.png"))
    if not frames:
        frames = sorted(seq_dir.glob("*.exr"))
    return frames[0] if frames else None


def _resize_sequence_lanczos(
    seq_dir: Path,
    *,
    target_w: int,
    target_h: int,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    first = _first_sequence_frame(seq_dir)
    if first is None:
        raise RuntimeError(f"No frames to resize in {seq_dir}")
    cur_w, cur_h = probe_media_size(first, python=python)
    if (cur_w, cur_h) == (target_w, target_h):
        log(f"Sequence already {target_w}x{target_h}; skip resize")
        return
    log(f"Resizing sequence {cur_w}x{cur_h} → {target_w}x{target_h} (lanczos)")
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "import cv2\n"
        "d=Path(sys.argv[1]); tw,th=int(sys.argv[2]),int(sys.argv[3])\n"
        "exts={'.png','.exr'}\n"
        "n=0\n"
        "for p in sorted(d.iterdir()):\n"
        "    if not p.is_file() or p.suffix.lower() not in exts: continue\n"
        "    img=cv2.imread(str(p), cv2.IMREAD_UNCHANGED)\n"
        "    if img is None: raise SystemExit(f'read failed: {p}')\n"
        "    out=cv2.resize(img,(tw,th),interpolation=cv2.INTER_LANCZOS4)\n"
        "    if not cv2.imwrite(str(p), out): raise SystemExit(f'write failed: {p}')\n"
        "    n+=1\n"
        "print(f'resized {n} frames')\n"
    )
    _run_streaming(
        [python, "-c", code, str(seq_dir), str(target_w), str(target_h)],
        log=log,
        cancel=cancel,
        holder=holder,
    )


def _resize_movie_lanczos(
    movie: Path,
    *,
    target_w: int,
    target_h: int,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> None:
    cur_w, cur_h = probe_media_size(movie, python=python)
    if (cur_w, cur_h) == (target_w, target_h):
        log(f"Movie already {target_w}x{target_h}; skip resize ({movie.name})")
        return
    log(f"Resizing movie {cur_w}x{cur_h} → {target_w}x{target_h} (lanczos): {movie.name}")
    import shutil

    tmp = movie.with_name(f".{movie.stem}_upscale{movie.suffix}")
    if tmp.exists():
        tmp.unlink()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        _run_streaming(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(movie),
                "-vf",
                f"scale={target_w}:{target_h}:flags=lanczos",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(tmp),
            ],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    else:
        code = (
            "import sys\n"
            "import cv2\n"
            "src,dst,tw,th=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4])\n"
            "cap=cv2.VideoCapture(src)\n"
            "fps=cap.get(cv2.CAP_PROP_FPS) or 24.0\n"
            "fourcc=cv2.VideoWriter_fourcc(*'mp4v')\n"
            "writer=cv2.VideoWriter(dst, fourcc, fps, (tw,th), True)\n"
            "if not writer.isOpened(): raise SystemExit('VideoWriter open failed')\n"
            "while True:\n"
            "    ok,frame=cap.read()\n"
            "    if not ok: break\n"
            "    writer.write(cv2.resize(frame,(tw,th),interpolation=cv2.INTER_LANCZOS4))\n"
            "cap.release(); writer.release()\n"
        )
        _run_streaming(
            [python, "-c", code, str(movie), str(tmp), str(target_w), str(target_h)],
            log=log,
            cancel=cancel,
            holder=holder,
        )
    if not tmp.is_file():
        raise RuntimeError(f"Upscale produced no file: {tmp}")
    movie.unlink()
    tmp.rename(movie)


def restore_outputs_to_source_size(
    *,
    out_dir: Path,
    source_video: Path,
    output_kind: str,
    write_foreground: bool,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> tuple[int, int]:
    """Upscale MatAnyone outputs to intermediate export WxH (lanczos). Return target size."""
    target_w, target_h = probe_media_size(source_video, python=python)
    log(f"Source (export) size: {target_w}x{target_h}")
    pha_mov, fgr_mov, pha_dir = _find_outputs(out_dir)

    if output_kind == "alpha_sequence":
        if pha_dir is not None:
            _resize_sequence_lanczos(
                pha_dir,
                target_w=target_w,
                target_h=target_h,
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
        if pha_mov is not None:
            _resize_movie_lanczos(
                pha_mov,
                target_w=target_w,
                target_h=target_h,
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
    else:
        if pha_mov is None:
            raise RuntimeError("Alpha movie (*_pha.mp4) not found for resize")
        _resize_movie_lanczos(
            pha_mov,
            target_w=target_w,
            target_h=target_h,
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )

    if write_foreground and fgr_mov is not None:
        _resize_movie_lanczos(
            fgr_mov,
            target_w=target_w,
            target_h=target_h,
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )
    return target_w, target_h


def sequence_pattern(pha_dir: Path) -> str | None:
    """Build Flame-style sequence path from pha/0000.png …"""
    frames = sorted(pha_dir.glob("*.png"))
    if not frames:
        frames = sorted(pha_dir.glob("*.exr"))
    if not frames:
        return None
    first = frames[0].name
    m = re.match(r"^(.*?)(\d+)(\.[^.]+)$", first)
    if not m:
        return str(frames[0])
    prefix, digits, suffix = m.group(1), m.group(2), m.group(3)
    width = len(digits)
    start = int(digits)
    last = frames[-1].name
    m2 = re.match(r"^(.*?)(\d+)(\.[^.]+)$", last)
    end = int(m2.group(2)) if m2 else start
    return str(pha_dir / f"{prefix}[{start:0{width}d}-{end:0{width}d}]{suffix}")


def _rename_movie(src: Path, stem: str) -> Path:
    dest = src.with_name(f"{stem}{src.suffix}")
    if dest.resolve() == src.resolve():
        return src
    if dest.exists():
        dest.unlink()
    src.rename(dest)
    return dest


def _rename_sequence_dir(pha_dir: Path, stem: str) -> Path:
    """Rename pha/ → stem/ and frames to stem.####.ext for Flame-friendly names."""
    parent = pha_dir.parent
    dest_dir = parent / stem
    if dest_dir.resolve() != pha_dir.resolve():
        if dest_dir.exists():
            raise RuntimeError(f"Rename target already exists: {dest_dir}")
        pha_dir.rename(dest_dir)
    else:
        dest_dir = pha_dir
    frames = sorted(
        [p for p in dest_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".exr"}]
    )
    for frame in frames:
        m = re.match(r"^(.*?)(\d+)(\.[^.]+)$", frame.name)
        if not m:
            continue
        digits, suffix = m.group(2), m.group(3)
        new_name = f"{stem}.{digits}{suffix}"
        target = frame.with_name(new_name)
        if target.resolve() == frame.resolve():
            continue
        if target.exists():
            target.unlink()
        frame.rename(target)
    return dest_dir


def prepare_named_outputs(
    *,
    out_dir: Path,
    output_kind: str,
    write_foreground: bool,
    basename: str,
    log: ProgressCb,
) -> tuple[Path | None, Path | None, list[str]]:
    """Rename MatAnyone outputs to <basename>_Alpha / _Foreground. Return paths + import list."""
    pha_mov, fgr_mov, pha_dir = _find_outputs(out_dir)
    alpha_stem = f"{basename}_Alpha"
    fgr_stem = f"{basename}_Foreground"
    alpha: Path | None = None
    import_candidates: list[str] = []

    if output_kind == "alpha_sequence":
        if pha_dir is None and pha_mov is None:
            raise RuntimeError("Alpha sequence folder (pha/) not found")
        if pha_dir is not None:
            alpha = _rename_sequence_dir(pha_dir, alpha_stem)
            log(f"Renamed sequence → {alpha}")
            patterned = sequence_pattern(alpha)
            if patterned:
                import_candidates.append(patterned)
        if pha_mov is not None:
            mov = _rename_movie(pha_mov, alpha_stem)
            if alpha is None:
                alpha = mov
            import_candidates.append(str(mov))
            log(f"Renamed alpha movie → {mov}")
    else:
        if pha_mov is None:
            raise RuntimeError("Alpha movie (*_pha.mp4) not found")
        alpha = _rename_movie(pha_mov, alpha_stem)
        import_candidates.append(str(alpha))
        log(f"Renamed alpha movie → {alpha}")

    fgr_path: Path | None = None
    if write_foreground and fgr_mov is not None:
        fgr_path = _rename_movie(fgr_mov, fgr_stem)
        log(f"Renamed foreground → {fgr_path}")

    return alpha, fgr_path, import_candidates


def import_path(path_str: str, destination) -> None:
    import flame

    def _do() -> None:
        dest = destination
        if dest is None:
            desktop = flame.project.current_project.current_workspace.desktop
            reel_groups = getattr(desktop, "reel_groups", None) or []
            if not reel_groups:
                raise RuntimeError("No desktop reel group for import")
            reels = getattr(reel_groups[0], "reels", None) or []
            if not reels:
                raise RuntimeError("No desktop reel for import")
            dest = reels[0]
        try:
            flame.import_clips([path_str], dest)
        except TypeError:
            flame.import_clips(path_str, dest)

    _call_on_main_thread(_do)


def gpu_vram_warning() -> str | None:
    """Return a warning string if Flame appears to hold a lot of VRAM."""
    smi = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if smi.returncode != 0:
        return None
    flame_mb = 0
    for line in smi.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name = parts[1].lower()
        try:
            mb = int(parts[2])
        except ValueError:
            continue
        if "flame" in name or "flicicw" in name:
            flame_mb += mb
    if flame_mb >= 6000:
        return (
            f"Flame-related processes appear to use ~{flame_mb} MiB GPU memory. "
            "MatAnyone may OOM while Flame is open. Continue anyway?"
        )
    return None


def _runtime_import():
    runtime_app = Path(dgpy_paths.apps_dir()) / "matanyone_runtime"
    if str(runtime_app) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(runtime_app))
    import matanyone_runtime_paths as rpaths

    return rpaths


def run_export(
    opts: JobOptions,
    *,
    logger,
    progress: ProgressCb | None = None,
    step: StepCb | None = None,
    cancel: threading.Event | None = None,
    proc_holder: _ProcHolder | None = None,
) -> JobResult:
    """PyExporter + first-frame extract. Opens mask UI afterward."""
    phase = "export"
    steps = EXPORT_STEPS

    def log(msg: str) -> None:
        logger.info("[matanyone] %s", msg)
        if progress:
            progress(msg)

    def set_step(index: int, label: str | None = None) -> None:
        if step:
            step(index, len(steps), label or job_step_label(index, phase))

    holder = proc_holder or _ProcHolder()
    rpaths = _runtime_import()
    if not rpaths.is_ready():
        return JobResult(
            ok=False,
            message=(
                "MatAnyone 2 runtime is not set up.\n"
                "Use DGpy → MatAnyone → Runtime Setup… first."
            ),
        )
    python = rpaths.resolve_python()
    if not python:
        return JobResult(ok=False, message="Runtime READY but python missing.")

    work = opts.work_dir or default_work_dir()
    try:
        set_step(0)
        _check_cancel(cancel)
        work.mkdir(parents=True, exist_ok=True)
        set_step(1)
        log("Exporting source…")
        _check_cancel(cancel)
        video = export_clip_mp4(opts.clip, work / "source", logger=logger)
        set_step(2)
        still = work / "first_frame.png"
        log(f"Extract first frame → {still}")
        extract_first_frame(
            video,
            still,
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )
        set_step(3)
        return JobResult(
            ok=True,
            message="Export done",
            work_dir=work,
            video_path=video,
            still_path=still,
        )
    except JobCancelled:
        log("Cancelled.")
        return JobResult(ok=False, message="Cancelled.", work_dir=work, cancelled=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MatAnyone export failed")
        return JobResult(ok=False, message=str(exc), work_dir=work)


def run_infer(
    opts: JobOptions,
    *,
    logger,
    progress: ProgressCb | None = None,
    step: StepCb | None = None,
    cancel: threading.Event | None = None,
    proc_holder: _ProcHolder | None = None,
) -> JobResult:
    """MatAnyone 2 infer + optional import. Mask must already exist."""
    phase = "infer"
    steps = INFER_STEPS

    def log(msg: str) -> None:
        logger.info("[matanyone] %s", msg)
        if progress:
            progress(msg)

    def set_step(index: int, label: str | None = None) -> None:
        if step:
            step(index, len(steps), label or job_step_label(index, phase))

    holder = proc_holder or _ProcHolder()
    rpaths = _runtime_import()
    if not rpaths.is_ready():
        return JobResult(
            ok=False,
            message=(
                "MatAnyone 2 runtime is not set up.\n"
                "Use DGpy → MatAnyone → Runtime Setup… first."
            ),
        )
    python = rpaths.resolve_python()
    infer = rpaths.inference_script()
    if not python or not infer:
        return JobResult(ok=False, message="Runtime READY but python/script missing.")

    work = opts.work_dir or default_work_dir()
    video = opts.source_video
    mask_path = opts.mask_path
    try:
        set_step(0)
        _check_cancel(cancel)
        if video is None or not Path(video).is_file():
            raise RuntimeError("Exported source video missing")
        if mask_path is None or not Path(mask_path).is_file():
            raise RuntimeError("Mask image missing")
        video = Path(video)
        mask_path = Path(mask_path)
        work.mkdir(parents=True, exist_ok=True)
        (work / "options.json").write_text(
            json.dumps(
                {
                    "mask_source": opts.mask_source,
                    "output_kind": opts.output_kind,
                    "write_foreground": opts.write_foreground,
                    "import_to_flame": opts.import_to_flame,
                    "result_basename": opts.result_basename,
                    "ref_frame_index": opts.ref_frame_index,
                    "max_size": MAX_SIZE,
                    "mask_path": str(mask_path),
                    "source_video": str(video),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        ref_n = max(0, int(opts.ref_frame_index or 0))
        out_dir = work / "out"
        save_image = opts.output_kind == "alpha_sequence"
        seg = work / "seg"

        set_step(1)
        _check_cancel(cancel)
        if ref_n == 0:
            log("Running MatAnyone 2 forward (ref=0, full clip)…")
            run_matanyone(
                python=python,
                inference_script=infer,
                source=video,
                mask=mask_path,
                out_dir=out_dir,
                save_image=save_image,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            set_step(2, "Backward skipped (ref=0)")
            log("Backward pass skipped (reference frame 0).")
        else:
            fwd_mp4 = make_forward_segment(
                video,
                ref_n,
                seg / "forward.mp4",
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            log(f"Running MatAnyone 2 forward from frame {ref_n}…")
            run_matanyone(
                python=python,
                inference_script=infer,
                source=fwd_mp4,
                mask=mask_path,
                out_dir=work / "out_fwd",
                save_image=save_image,
                log=log,
                cancel=cancel,
                holder=holder,
            )

            set_step(2)
            _check_cancel(cancel)
            bwd_in = make_backward_input_segment(
                video,
                ref_n,
                seg / "backward_in.mp4",
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            log(f"Running MatAnyone 2 backward (reverse 0…{ref_n})…")
            run_matanyone(
                python=python,
                inference_script=infer,
                source=bwd_in,
                mask=mask_path,
                out_dir=work / "out_bwd_raw",
                save_image=save_image,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            reverse_matanyone_outputs(
                work / "out_bwd_raw",
                work / "out_bwd",
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            set_step(3)
            _check_cancel(cancel)
            log("Joining backward + forward mattes…")
            join_matanyone_outputs(
                work / "out_bwd",
                work / "out_fwd",
                ref_index=ref_n,
                dest_out=out_dir,
                write_foreground=opts.write_foreground,
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )

        set_step(3)
        _check_cancel(cancel)
        restore_outputs_to_source_size(
            out_dir=out_dir,
            source_video=video,
            output_kind=opts.output_kind,
            write_foreground=opts.write_foreground,
            python=python,
            log=log,
            cancel=cancel,
            holder=holder,
        )

        basename = (opts.result_basename or "clip").strip() or "clip"
        alpha, fgr_path, import_candidates = prepare_named_outputs(
            out_dir=out_dir,
            output_kind=opts.output_kind,
            write_foreground=opts.write_foreground,
            basename=basename,
            log=log,
        )
        imported = False
        import_errors: list[str] = []

        set_step(4)
        _check_cancel(cancel)
        if opts.import_to_flame and import_candidates:
            last_err: Exception | None = None
            for target in import_candidates:
                try:
                    log(f"Importing {target}")
                    import_path(target, opts.import_destination)
                    imported = True
                    if fgr_path is not None:
                        import_path(str(fgr_path), opts.import_destination)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    import_errors.append(f"{target}: {exc}")
                    log(f"Import failed, trying next candidate: {exc}")
            if not imported and last_err is not None:
                detail = "\n".join(import_errors)
                set_step(5)
                return JobResult(
                    ok=True,
                    message=(
                        "Matte finished but Flame import failed.\n"
                        f"Files are on disk under:\n{out_dir}\n\n{detail}"
                    ),
                    work_dir=work,
                    alpha_path=alpha,
                    foreground_path=fgr_path,
                    imported=False,
                    video_path=video,
                )

        set_step(5)
        return JobResult(
            ok=True,
            message="Done" if imported or not opts.import_to_flame else "Done (not imported)",
            work_dir=work,
            alpha_path=alpha,
            foreground_path=fgr_path,
            imported=imported,
            video_path=video,
        )
    except JobCancelled:
        log("Cancelled.")
        return JobResult(
            ok=False,
            message="Cancelled.",
            work_dir=work,
            cancelled=True,
            video_path=video if isinstance(video, Path) else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("MatAnyone infer failed")
        return JobResult(ok=False, message=str(exc), work_dir=work)


def run_job(
    opts: JobOptions,
    *,
    logger,
    progress: ProgressCb | None = None,
    step: StepCb | None = None,
    cancel: threading.Event | None = None,
    proc_holder: _ProcHolder | None = None,
) -> JobResult:
    if opts.phase == "export":
        return run_export(
            opts,
            logger=logger,
            progress=progress,
            step=step,
            cancel=cancel,
            proc_holder=proc_holder,
        )
    if opts.phase == "infer":
        return run_infer(
            opts,
            logger=logger,
            progress=progress,
            step=step,
            cancel=cancel,
            proc_holder=proc_holder,
        )
    # Legacy full path no longer used by the UI; keep a clear error.
    return JobResult(
        ok=False,
        message="Internal error: unsupported job phase. Use export or infer.",
    )
