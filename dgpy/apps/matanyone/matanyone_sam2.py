"""SAM2 resident-worker client and mask-edit helpers for MatAnyone (v0.10)."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui

__version__ = "0.10.0"

MAX_OBJECTS = 8

_RUNTIME_APP = Path(__file__).resolve().parent.parent / "matanyone_runtime"
_WORKER = _RUNTIME_APP / "sam2_worker.py"


def _ensure_runtime_paths() -> Any:
    runtime_app = str(_RUNTIME_APP)
    if runtime_app not in sys.path:
        sys.path.insert(0, runtime_app)
    import matanyone_runtime_paths as rpaths

    return rpaths


def worker_script_path() -> Path:
    if _WORKER.is_file():
        return _WORKER
    # Deployed layout may copy worker next to runtime helpers.
    rpaths = _ensure_runtime_paths()
    candidate = rpaths.runtime_root() / "sam2_worker.py"
    if candidate.is_file():
        return candidate
    return _WORKER


@dataclass
class SamObject:
    """One object slot: points + optional SAM base / paint edit masks."""

    name: str
    points: list[tuple[float, float, int]] = field(default_factory=list)
    base_mask_path: Path | None = None
    edit_mask_path: Path | None = None


class Sam2Worker:
    """Client for the long-lived ``sam2_worker.py`` subprocess."""

    def __init__(
        self,
        *,
        python: str | None = None,
        worker: Path | None = None,
        cwd: Path | None = None,
        response_timeout_s: float = 120.0,
    ) -> None:
        rpaths = _ensure_runtime_paths()
        self._python = python or rpaths.resolve_python()
        self._worker = Path(worker) if worker else worker_script_path()
        self._cwd = Path(cwd) if cwd else rpaths.sam2_repo_dir()
        self._timeout = float(response_timeout_s)
        self._lock = threading.Lock()
        self._proc = None
        self._next_id = 1
        self._stderr_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        import subprocess

        with self._lock:
            if self.is_running:
                return
            if not self._python:
                raise RuntimeError("runtime python missing")
            if not self._worker.is_file():
                raise RuntimeError(f"SAM2 worker missing: {self._worker}")
            self._cwd.mkdir(parents=True, exist_ok=True)
            self._proc = subprocess.Popen(
                [str(self._python), str(self._worker)],
                cwd=str(self._cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                name="sam2-worker-stderr",
                daemon=True,
            )
            self._stderr_thread.start()
            ready = self._read_line_unlocked(timeout=self._timeout)
            if not isinstance(ready, dict) or not ready.get("ok") or not ready.get(
                "ready"
            ):
                self._kill_unlocked()
                raise RuntimeError(f"SAM2 worker failed to start: {ready!r}")

    def close(self) -> None:
        with self._lock:
            if not self.is_running:
                self._proc = None
                return
            try:
                self._send_unlocked({"op": "shutdown"}, expect_reply=True)
            except Exception:  # noqa: BLE001
                pass
            self._kill_unlocked()

    def init_model(self, checkpoint: str | Path, config: str) -> None:
        self._call(
            {
                "op": "init",
                "checkpoint": str(checkpoint),
                "config": str(config),
            }
        )

    def set_image(self, path: str | Path) -> None:
        self._call({"op": "set_image", "path": str(path)})

    def predict(
        self,
        points: list[tuple[float, float, int]],
        out: Path,
    ) -> Path:
        if not points:
            raise ValueError("predict needs at least one point")
        if not any(int(p[2]) == 1 for p in points):
            raise ValueError("predict needs at least one positive point (label=1)")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "op": "predict",
            "points": [{"x": float(x), "y": float(y), "label": int(lab)} for x, y, lab in points],
            "out": str(out),
        }
        resp = self._call(payload)
        result = Path(str(resp.get("out") or out))
        if not result.is_file():
            raise RuntimeError(f"SAM2 predict did not write {result}")
        return result

    def switch_model(self, checkpoint: str | Path, config: str) -> None:
        self._call(
            {
                "op": "switch_model",
                "checkpoint": str(checkpoint),
                "config": str(config),
            }
        )

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self.is_running:
                raise RuntimeError("SAM2 worker is not running")
            return self._send_unlocked(body, expect_reply=True)

    def _send_unlocked(
        self,
        body: dict[str, Any],
        *,
        expect_reply: bool,
    ) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdin is not None
        req_id = self._next_id
        self._next_id += 1
        msg = {"id": req_id, **body}
        self._proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
        self._proc.stdin.flush()
        if not expect_reply:
            return {}
        resp = self._read_line_unlocked(timeout=self._timeout)
        if not isinstance(resp, dict):
            raise RuntimeError(f"SAM2 worker bad response: {resp!r}")
        if resp.get("id") != req_id:
            raise RuntimeError(
                f"SAM2 worker id mismatch: expected {req_id}, got {resp.get('id')}"
            )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error") or "SAM2 worker error"))
        return resp

    def _read_line_unlocked(self, *, timeout: float) -> Any:
        import select

        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        # Prefer select when available (POSIX). Fallback: blocking readline.
        if hasattr(select, "select"):
            ready, _, _ = select.select([stdout], [], [], timeout)
            if not ready:
                raise TimeoutError(f"SAM2 worker timed out after {timeout}s")
        line = stdout.readline()
        if not line:
            code = self._proc.poll()
            raise RuntimeError(f"SAM2 worker exited unexpectedly (code={code})")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"SAM2 worker invalid JSON: {line!r}") from exc

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                text = line.rstrip()
                if text:
                    print(f"[sam2_worker] {text}", flush=True)
        except Exception:  # noqa: BLE001
            pass

    def _kill_unlocked(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def brush_edit_qimage(
    img: QtGui.QImage,
    x: float,
    y: float,
    radius: float,
    add: bool,
) -> None:
    """Mutate a mask QImage in place: Add=white, Erase=black."""
    painter = QtGui.QPainter(img)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    color = QtGui.QColor(255, 255, 255) if add else QtGui.QColor(0, 0, 0)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QBrush(color))
    r = float(radius)
    painter.drawEllipse(QtCore.QPointF(float(x), float(y)), r, r)
    painter.end()


def or_qimages(images: list[QtGui.QImage]) -> QtGui.QImage:
    """OR-combine binary / grayscale masks into one Format_Grayscale8 image."""
    if not images:
        raise ValueError("or_qimages requires at least one image")
    first = images[0].convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    w, h = first.width(), first.height()
    out = QtGui.QImage(w, h, QtGui.QImage.Format.Format_Grayscale8)
    out.fill(0)
    painter = QtGui.QPainter(out)
    painter.setCompositionMode(
        QtGui.QPainter.CompositionMode.CompositionMode_Lighten
    )
    for img in images:
        g = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
        if g.width() != w or g.height() != h:
            g = g.scaled(
                w,
                h,
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.FastTransformation,
            )
        painter.drawImage(0, 0, g)
    painter.end()
    return out


def save_qimage_l(img: QtGui.QImage, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    g = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    if not g.save(str(path), "PNG"):
        raise RuntimeError(f"failed to save mask PNG: {path}")
    return path


def load_qimage_l(path: Path | str) -> QtGui.QImage:
    path = Path(path)
    img = QtGui.QImage(str(path))
    if img.isNull():
        raise RuntimeError(f"failed to load mask PNG: {path}")
    return img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
