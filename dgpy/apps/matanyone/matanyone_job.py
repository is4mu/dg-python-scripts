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

__version__ = "0.2.1"

ProgressCb = Callable[[str], None]
StepCb = Callable[[int, int, str], None]
MAX_SIZE = 1080

JOB_STEPS: list[tuple[str, int]] = [
    ("Prepare work dir", 1),
    ("Export source", 3),
    ("Prepare mask", 2),
    ("MatAnyone infer", 8),
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
    mask_source: str  # "flame" | "sam2"
    mask_path: Path | None = None
    sam_points: list[tuple[float, float]] = field(default_factory=list)
    sam_points_provider: Callable[[Path], list[tuple[float, float]] | None] | None = None
    output_kind: str = "alpha_sequence"  # alpha_sequence | alpha_movie
    write_foreground: bool = False
    import_to_flame: bool = True
    import_destination: Any | None = None
    work_dir: Path | None = None


@dataclass
class JobResult:
    ok: bool = False
    message: str = ""
    work_dir: Path | None = None
    alpha_path: Path | None = None
    foreground_path: Path | None = None
    imported: bool = False
    cancelled: bool = False


class JobCancelled(Exception):
    """Raised when the operator cancels a running job."""


def job_step_count() -> int:
    return len(JOB_STEPS)


def job_step_label(index: int) -> str:
    if 0 <= index < len(JOB_STEPS):
        return JOB_STEPS[index][0]
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
    try:
        for line in proc.stdout:
            _check_cancel(cancel)
            text = line.rstrip()
            if text:
                log(text)
        code = proc.wait()
    finally:
        if holder is not None:
            holder.set(None)
    _check_cancel(cancel)
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {' '.join(cmd)}")


def extract_first_frame(
    video: Path,
    still: Path,
    *,
    python: str,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    still.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import sys\n"
        "import cv2\n"
        "cap=cv2.VideoCapture(sys.argv[1])\n"
        "ok,frame=cap.read()\n"
        "cap.release()\n"
        "if not ok: raise SystemExit('failed to read frame')\n"
        "cv2.imwrite(sys.argv[2], frame)\n"
    )
    log(f"Extract first frame → {still}")
    _run_streaming(
        [python, "-c", code, str(video), str(still)],
        log=log,
        cancel=cancel,
        holder=holder,
    )
    if not still.is_file():
        raise RuntimeError("First-frame extract produced no file")
    return still


def run_sam_mask(
    *,
    python: str,
    sam_script: Path,
    image: Path,
    points: list[tuple[float, float]],
    out_mask: Path,
    log: ProgressCb,
    cancel: threading.Event | None = None,
    holder: _ProcHolder | None = None,
) -> Path:
    if not points:
        raise RuntimeError("SAM2 mode needs at least one foreground point")
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
    ]
    try:
        _run_streaming(cmd, log=log, cancel=cancel, holder=holder)
    except RuntimeError as exc:
        raise RuntimeError(
            "SAM mask failed (experimental). Use Flame mask, or install "
            "SAM/SAM2 + checkpoint into the MatAnyone runtime.\n"
            f"{exc}"
        ) from exc
    if not out_mask.is_file():
        raise RuntimeError("SAM mask produced no file")
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


def run_job(
    opts: JobOptions,
    *,
    logger,
    progress: ProgressCb | None = None,
    step: StepCb | None = None,
    cancel: threading.Event | None = None,
    proc_holder: _ProcHolder | None = None,
) -> JobResult:
    def log(msg: str) -> None:
        logger.info("[matanyone] %s", msg)
        if progress:
            progress(msg)

    def set_step(index: int, label: str | None = None) -> None:
        if step:
            step(index, len(JOB_STEPS), label or job_step_label(index))

    holder = proc_holder or _ProcHolder()

    # Import runtime helpers from sibling package.
    runtime_app = Path(dgpy_paths.apps_dir()) / "matanyone_runtime"
    if str(runtime_app) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(runtime_app))
    import matanyone_runtime_paths as rpaths

    if not rpaths.is_ready():
        return JobResult(
            ok=False,
            message=(
                "MatAnyone runtime is not set up.\n"
                "Use DGpy → MatAnyone Runtime Setup…"
            ),
        )

    python = rpaths.resolve_python()
    infer = rpaths.inference_script()
    if not python or not infer:
        return JobResult(ok=False, message="Runtime READY but python/script missing.")

    work = opts.work_dir or default_work_dir()
    try:
        set_step(0)
        _check_cancel(cancel)
        work.mkdir(parents=True, exist_ok=True)
        (work / "options.json").write_text(
            json.dumps(
                {
                    "mask_source": opts.mask_source,
                    "output_kind": opts.output_kind,
                    "write_foreground": opts.write_foreground,
                    "import_to_flame": opts.import_to_flame,
                    "max_size": MAX_SIZE,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        set_step(1)
        log("Exporting source…")
        _check_cancel(cancel)
        video = export_clip_mp4(opts.clip, work / "source", logger=logger)

        set_step(2)
        _check_cancel(cancel)
        mask_path = opts.mask_path
        if opts.mask_source == "sam2":
            log("Preparing SAM2 mask (experimental)…")
            still = work / "first_frame.png"
            extract_first_frame(
                video,
                still,
                python=python,
                log=log,
                cancel=cancel,
                holder=holder,
            )
            points = list(opts.sam_points)
            if not points and opts.sam_points_provider is not None:
                # Point UI must run on the Qt main thread.
                provided = _call_on_main_thread(
                    lambda: opts.sam_points_provider(still)
                )
                if not provided:
                    return JobResult(
                        ok=False,
                        message="SAM2 cancelled (no points).",
                        work_dir=work,
                    )
                points = list(provided)
            sam = rpaths.sam_script()
            if sam is None:
                raise RuntimeError(
                    "SAM helper missing in runtime. "
                    "Use Flame mask, or finish SAM setup later."
                )
            mask_path = work / "mask.png"
            run_sam_mask(
                python=python,
                sam_script=sam,
                image=still,
                points=points,
                out_mask=mask_path,
                log=log,
                cancel=cancel,
                holder=holder,
            )
        else:
            if mask_path is None or not Path(mask_path).is_file():
                raise RuntimeError("Flame mask PNG/EXR path is required")
            mask_path = Path(mask_path)
            log(f"Using Flame mask: {mask_path}")

        set_step(3)
        out_dir = work / "out"
        save_image = opts.output_kind == "alpha_sequence"
        log("Running MatAnyone (max_size=1080 short side)…")
        _check_cancel(cancel)
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

        pha_mov, fgr_mov, pha_dir = _find_outputs(out_dir)
        alpha: Path | None = None
        import_candidates: list[str] = []
        if opts.output_kind == "alpha_sequence":
            if pha_dir is None and pha_mov is None:
                raise RuntimeError("Alpha sequence folder (pha/) not found")
            if pha_dir is not None:
                alpha = pha_dir
                patterned = sequence_pattern(pha_dir)
                if patterned:
                    import_candidates.append(patterned)
            if pha_mov is not None:
                if alpha is None:
                    alpha = pha_mov
                import_candidates.append(str(pha_mov))
        else:
            if pha_mov is None:
                raise RuntimeError("Alpha movie (*_pha.mp4) not found")
            alpha = pha_mov
            import_candidates.append(str(pha_mov))

        fgr_path = fgr_mov if opts.write_foreground else None
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
                )

        set_step(5)
        return JobResult(
            ok=True,
            message="Done" if imported or not opts.import_to_flame else "Done (not imported)",
            work_dir=work,
            alpha_path=alpha,
            foreground_path=fgr_path,
            imported=imported,
        )
    except JobCancelled:
        log("Cancelled.")
        return JobResult(
            ok=False,
            message="Cancelled.",
            work_dir=work,
            cancelled=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("MatAnyone job failed")
        return JobResult(ok=False, message=str(exc), work_dir=work)
