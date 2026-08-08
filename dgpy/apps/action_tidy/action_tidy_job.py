"""Apply Clean Up / Toggle Fit / Strip Expressions via TimelineFX load_setup."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from action_tidy_merge import (
    find_saved_action_file,
    merge_template_with_saved,
    patch_saved_setup,
)
from action_tidy_selection import segment_label

__version__ = "0.3.4"

TEMPLATE_CLEAN = "cleanup.action"
TEMPLATE_FIT = "cleanup_fit.action"


class TemplateKind:
    __slots__ = ("id", "label", "filename")

    def __init__(self, id: str, label: str, filename: str) -> None:
        self.id = id
        self.label = label
        self.filename = filename


TEMPLATES = (
    TemplateKind(id="clean", label="Clean Up Action", filename=TEMPLATE_CLEAN),
    TemplateKind(id="fit", label="Clean Up Action (Fit)", filename=TEMPLATE_FIT),
)


def setups_dir() -> Path:
    return Path(__file__).resolve().parent / "setups"


def find_template(template_id: str) -> TemplateKind | None:
    for item in TEMPLATES:
        if item.id == template_id:
            return item
    return None


def template_path(kind: TemplateKind) -> Path:
    path = setups_dir() / kind.filename
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(
            f"Action template missing:\n{path}\n\n"
            "Place Flame Action setups under apps/action_tidy/setups/."
        )
    return path


def _action_effects(segment) -> list:
    effects = list(getattr(segment, "effects", None) or [])
    out = []
    for effect in effects:
        typ = getattr(effect, "type", None)
        if typ is not None and hasattr(typ, "get_value"):
            try:
                typ = typ.get_value()
            except Exception:  # noqa: BLE001
                pass
        if str(typ) == "Action":
            out.append(effect)
    return out


def _get_existing_action(segment):
    existing = _action_effects(segment)
    if not existing:
        return None
    return existing[0]


def _create_action(segment):
    create = getattr(segment, "create_effect", None)
    if create is None:
        raise RuntimeError("segment.create_effect is unavailable")
    return create("Action")


class JobResult:
    def __init__(self) -> None:
        self.ok = 0
        self.failed = 0
        self.skipped = 0
        self.messages: list[str] = []


def _save_action_text(action, temp_dir: Path) -> Path:
    save_root = temp_dir / "temp.action"
    if save_root.exists():
        shutil.rmtree(save_root, ignore_errors=True)
    action.save_setup(str(save_root))
    saved = find_saved_action_file(save_root)
    if saved is None:
        raise RuntimeError(f"save_setup produced no .action under {save_root}")
    return saved


def _apply_existing(
    segment, action, kind: TemplateKind, *, temp_dir: Path, logger
) -> None:
    tmpl = template_path(kind)
    saved = _save_action_text(action, temp_dir)
    out = temp_dir / f"merged_{kind.id}.action"
    merge_template_with_saved(tmpl, saved, out)
    logger.info(
        "load_setup(merged) segment=%s template=%s saved=%s out=%s",
        segment_label(segment),
        kind.id,
        saved,
        out,
    )
    action.load_setup(str(out))


def _apply_new(segment, kind: TemplateKind, *, logger) -> None:
    tmpl = template_path(kind)
    action = _create_action(segment)
    logger.info(
        "load_setup(template) segment=%s template=%s path=%s",
        segment_label(segment),
        kind.id,
        tmpl,
    )
    action.load_setup(str(tmpl))


def apply_template(segment, kind: TemplateKind, *, temp_dir: Path, logger) -> None:
    existing = _get_existing_action(segment)
    if existing is not None:
        if len(_action_effects(segment)) > 1:
            logger.info(
                "Clean Up Action: %s has multiple Action FX; using first",
                segment_label(segment),
            )
        _apply_existing(segment, existing, kind, temp_dir=temp_dir, logger=logger)
    else:
        _apply_new(segment, kind, logger=logger)


def run_cleanup(segments: list, *, template_id: str) -> JobResult:
    import dgpy_flame_util
    import dgpy_log

    logger = dgpy_log.setup()
    dgpy_flame_util.ensure_timeline_tab(logger=logger, label="Action Tidy")
    kind = find_template(template_id)
    if kind is None:
        raise RuntimeError(f"Unknown template: {template_id}")
    template_path(kind)

    result = JobResult()
    temp_dir = Path(tempfile.mkdtemp(prefix="dgpy_action_tidy_"))
    try:
        for segment in segments:
            label = segment_label(segment)
            try:
                apply_template(segment, kind, temp_dir=temp_dir, logger=logger)
                result.ok += 1
                result.messages.append(f"OK: {label}")
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.messages.append(f"FAIL {label}: {exc}")
                logger.exception("Clean Up Action failed for %s", label)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return result


def _run_patch(segments: list, *, mode: str, prefix: str) -> JobResult:
    import dgpy_flame_util
    import dgpy_log

    logger = dgpy_log.setup()
    dgpy_flame_util.ensure_timeline_tab(logger=logger, label="Action Tidy")
    result = JobResult()
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        for segment in segments:
            label = segment_label(segment)
            action = _get_existing_action(segment)
            if action is None:
                result.skipped += 1
                result.messages.append(f"SKIP {label}: no Action")
                continue
            try:
                saved = _save_action_text(action, temp_dir)
                out = temp_dir / f"{mode}.action"
                _, count = patch_saved_setup(saved, out, mode=mode)
                if count <= 0:
                    result.skipped += 1
                    result.messages.append(f"SKIP {label}: no matching Expression")
                    continue
                logger.info(
                    "load_setup(%s) segment=%s changes=%s out=%s",
                    mode,
                    label,
                    count,
                    out,
                )
                action.load_setup(str(out))
                result.ok += 1
                result.messages.append(f"OK: {label} ({count})")
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.messages.append(f"FAIL {label}: {exc}")
                logger.exception("%s failed for %s", mode, label)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return result


def run_toggle_fit(segments: list) -> JobResult:
    return _run_patch(
        segments, mode="toggle_fit", prefix="dgpy_action_tidy_toggle_"
    )


def run_strip_expressions(segments: list) -> JobResult:
    return _run_patch(
        segments, mode="strip_expr", prefix="dgpy_action_tidy_strip_"
    )
