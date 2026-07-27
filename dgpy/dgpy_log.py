"""Logging with [DG] prefix. UTF-8 file + console. Unique basename for Flame."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable

import dgpy_paths

_LOGGER_NAME = "dgpy"
_listeners: list[Callable[[str], None]] = []

__version__ = "0.3.5"


def add_listener(callback: Callable[[str], None]) -> None:
    if callback not in _listeners:
        _listeners.append(callback)


def remove_listener(callback: Callable[[str], None]) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


class _ListenerHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            return
        for cb in list(_listeners):
            try:
                cb(msg)
            except Exception:  # noqa: BLE001
                pass


def setup(log_file: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure once per process. Survives Flame Rescan module reloads."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # logging.getLogger is a process singleton; module-level flags reset on Rescan.
    if getattr(logger, "_dgpy_handlers_ready", False):
        return logger

    # Drop handlers left by a previous broken configure attempt.
    logger.handlers.clear()

    fmt = logging.Formatter("[DG] %(asctime)s %(levelname)s %(message)s", "%H:%M:%S")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_path = log_file or dgpy_paths.default_log_path()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(file_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as exc:
        logger.warning("Could not open log file %s: %s", file_path, exc)

    listener = _ListenerHandler()
    listener.setFormatter(fmt)
    logger.addHandler(listener)

    logger._dgpy_handlers_ready = True  # type: ignore[attr-defined]
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not getattr(logger, "_dgpy_handlers_ready", False):
        return setup()
    return logger
