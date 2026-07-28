"""Apply Clean Up Action templates via TimelineFX load_setup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from action_tidy_selection import segment_label

__version__ = "0.1.0"

TEMPLATE_CLEAN = "cleanup.action"
TEMPLATE_FIT = "cleanup_fit.action"


@dataclass(frozen=True)
class TemplateKind:
    id: str
    label: str
    filename: str


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


def _get_or_create_action(segment, logger):
    existing = _action_effects(segment)
    if existing:
        if len(existing) > 1 and logger is not None:
            logger.info(
                "Clean Up Action: %s has %s Action FX; using first",
                segment_label(segment),
                len(existing),
            )
        return existing[0]
    create = getattr(segment, "create_effect", None)
    if create is None:
        raise RuntimeError("segment.create_effect is unavailable")
    return create("Action")


@dataclass
class JobResult:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    messages: list[str] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []


def apply_template(segment, kind: TemplateKind, *, logger) -> None:
    path = template_path(kind)
    action = _get_or_create_action(segment, logger)
    logger.info(
        "load_setup segment=%s template=%s path=%s",
        segment_label(segment),
        kind.id,
        path,
    )
    action.load_setup(str(path))


def run_cleanup(segments: list, *, template_id: str) -> JobResult:
    import dgpy_log

    logger = dgpy_log.setup()
    kind = find_template(template_id)
    if kind is None:
        raise RuntimeError(f"Unknown template: {template_id}")
    # Validate template exists once
    template_path(kind)

    result = JobResult()
    for segment in segments:
        label = segment_label(segment)
        try:
            apply_template(segment, kind, logger=logger)
            result.ok += 1
            result.messages.append(f"OK: {label}")
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.messages.append(f"FAIL {label}: {exc}")
            logger.exception("Clean Up Action failed for %s", label)
    return result
