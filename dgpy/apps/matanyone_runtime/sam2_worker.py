#!/usr/bin/env python3
"""Long-lived SAM2 image-predictor worker (stdin/stdout JSON lines).

Runs inside the MatAnyone runtime venv. No Flame imports.
Protocol: one JSON object per line on stdin; one JSON response per line on stdout.
Logs go to stderr. On start emits {"ok":true,"ready":true} then waits.

Heavy deps (numpy/torch/PIL) load only when executed as __main__ so Flame's
hook scanner can import this file without error (it lives under apps/).
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# Populated by _ensure_ml() before _Session is used as a worker.
np: Any = None
torch: Any = None
Image: Any = None


def _ensure_ml() -> None:
    """Import ML stack once (runtime venv only — not Flame's Python)."""
    global np, torch, Image
    if np is not None:
        return
    import numpy as _np
    import torch as _torch
    from PIL import Image as _Image

    np = _np
    torch = _torch
    Image = _Image


def _unshadow_sam2_package() -> None:
    """Drop this script's directory from sys.path.

    The helper lives under …/dgpy_runtimes/matanyone/ or the apps package.
    A clone folder named ``sam2`` beside it would otherwise win on
    sys.path[0] and shadow the installed ``sam2`` package.
    """
    script_dir = str(Path(__file__).resolve().parent)
    while script_dir in sys.path:
        sys.path.remove(script_dir)
    cwd = os.getcwd()
    if cwd == script_dir or Path(cwd).name in ("sam2", "sam2_src"):
        while "" in sys.path:
            sys.path.remove("")
        if cwd in sys.path:
            sys.path.remove(cwd)


def _reply(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _err(req_id: Any, message: str) -> None:
    _reply({"id": req_id, "ok": False, "error": message})


class _Session:
    def __init__(self) -> None:
        _ensure_ml()
        self.predictor = None
        self._image = None
        self._image_path: str | None = None
        self._ckpt: str | None = None
        self._config: str | None = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

    def init_model(self, checkpoint: str, config: str) -> None:
        _ensure_ml()
        _unshadow_sam2_package()
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        ckpt = Path(checkpoint)
        if not ckpt.is_file():
            raise FileNotFoundError(f"checkpoint missing: {checkpoint}")
        print(
            f"SAM2 worker init device={self._device} ckpt={checkpoint} "
            f"config={config}",
            file=sys.stderr,
            flush=True,
        )
        self.predictor = SAM2ImagePredictor(
            build_sam2(config, str(ckpt), device=self._device)
        )
        self._ckpt = str(ckpt)
        self._config = config
        self._image = None
        self._image_path = None

    def set_image(self, path: str) -> None:
        _ensure_ml()
        if self.predictor is None:
            raise RuntimeError("model not initialized; send init first")
        image = np.array(Image.open(path).convert("RGB"))
        with torch.inference_mode():
            self.predictor.set_image(image)
        self._image = image
        self._image_path = path

    def predict(self, points: list[dict], out: str) -> str:
        _ensure_ml()
        if self.predictor is None:
            raise RuntimeError("model not initialized; send init first")
        if self._image is None:
            raise RuntimeError("image not set; send set_image first")
        if not points:
            raise ValueError("predict needs at least one point")
        coords: list[tuple[float, float]] = []
        labels: list[int] = []
        for p in points:
            x = float(p["x"])
            y = float(p["y"])
            label = int(p.get("label", 1))
            if label not in (0, 1):
                raise ValueError(f"label must be 0 or 1, got {label}")
            coords.append((x, y))
            labels.append(label)
        if 1 not in labels:
            raise ValueError("predict needs at least one positive point (label=1)")
        point_coords = np.array(coords, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)
        with torch.inference_mode():
            masks, scores, _ = self.predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                multimask_output=True,
            )
        mask = masks[int(np.argmax(scores))]
        binary = (mask > 0.5).astype(np.uint8) * 255
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.ascontiguousarray(binary), mode="L").save(out_path)
        return str(out_path)


def _handle(session: _Session, msg: dict[str, Any]) -> None:
    req_id = msg.get("id")
    op = str(msg.get("op") or "").strip()
    try:
        if op == "init":
            session.init_model(str(msg["checkpoint"]), str(msg["config"]))
            _reply({"id": req_id, "ok": True})
        elif op == "set_image":
            session.set_image(str(msg["path"]))
            _reply({"id": req_id, "ok": True})
        elif op == "predict":
            points = msg.get("points") or []
            if not isinstance(points, list):
                raise TypeError("points must be a list")
            out = session.predict(points, str(msg["out"]))
            _reply({"id": req_id, "ok": True, "out": out})
        elif op == "shutdown":
            _reply({"id": req_id, "ok": True})
            raise SystemExit(0)
        else:
            _err(req_id, f"unknown op: {op!r}")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        _err(req_id, str(exc))


def main() -> int:
    _ensure_ml()
    _unshadow_sam2_package()
    _reply({"ok": True, "ready": True})
    session = _Session()
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError as exc:
            _err(None, f"invalid JSON: {exc}")
            continue
        if not isinstance(msg, dict):
            _err(None, "message must be a JSON object")
            continue
        _handle(session, msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
