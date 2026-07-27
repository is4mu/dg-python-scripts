"""Minimal PySide6 helpers. Unique basename for Flame."""

from __future__ import annotations

from PySide6 import QtWidgets

__version__ = "0.3.3"


def info(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    QtWidgets.QMessageBox.information(parent, title, message)


def warning(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    QtWidgets.QMessageBox.warning(parent, title, message)


def error(parent: QtWidgets.QWidget | None, title: str, message: str) -> None:
    QtWidgets.QMessageBox.critical(parent, title, message)


def confirm(
    parent: QtWidgets.QWidget | None, title: str, message: str
) -> bool:
    reply = QtWidgets.QMessageBox.question(
        parent,
        title,
        message,
        QtWidgets.QMessageBox.StandardButton.Yes
        | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    return reply == QtWidgets.QMessageBox.StandardButton.Yes
