"""Comp CG Clips: stack clips into one Action and set blend modes by name."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import dgpy_batch_prefs
import dgpy_flame_attr
import dgpy_flame_types
import dgpy_log

__version__ = "1.0.4"

_NODE_UNIT = 150
_BATCH_NAME = "comp_cg"

# SurfaceSquare Specifics Blending — calibrated from BlendMode.action
# (Blend, Multiply, Add, Screen, Overlay)
_BLEND_INT = {
    "Blend": 0,
    "Multiply": 2,
    "Add": 5,
    "Screen": 7,
    "Overlay": 20,
}

# (tokens, mode) — first match wins; casefold substring
_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("multiply", "multi", "mult"), "Multiply"),
    (("screen",), "Screen"),
    (("overlay",), "Overlay"),
    (("add", "plus"), "Add"),
)

_SURFACE_BLENDING_RE = re.compile(r"^(\t\tBlending )\d+(\s*)$")


def mode_from_clip_name(name: str) -> str:
    folded = name.casefold()
    for tokens, mode in _NAME_RULES:
        if any(tok in folded for tok in tokens):
            return mode
    return "Blend"


def blending_int(mode: str) -> int:
    return _BLEND_INT.get(mode, _BLEND_INT["Blend"])


def _sort_clips_by_name(clips: list) -> list:
    return sorted(clips, key=lambda c: dgpy_flame_attr.clip_name(c).casefold())


def _set_xy(node, x: int, y: int, logger, label: str) -> None:
    try:
        node.pos_x = int(x)
        node.pos_y = int(y)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Comp CG: could not set %s pos: %s", label, exc)


def _node_type(node) -> str:
    return str(getattr(node, "type", "") or "")


def _is_clip_schematic_node(node) -> bool:
    typ = _node_type(node)
    if typ in ("Action", "Resize", "Render") or "Action" in typ:
        return False
    if "Clip" in typ or typ in ("", "clip"):
        return True
    return typ.lower() in ("clip", "sequence", "pyclip", "pysequence")


def _clip_nodes_after_copy(batch, before_ids: set[int]) -> list:
    nodes = list(getattr(batch, "nodes", None) or [])
    added = [n for n in nodes if id(n) not in before_ids]
    clips = [n for n in added if _is_clip_schematic_node(n)]
    return clips if clips else added


def _connect(batch, src, dst, logger, label: str) -> bool:
    attempts = (
        ("Default", None),
        ("Result", None),
        ("Default", "Front"),
        ("Result", "Front"),
    )
    for out_sock, in_sock in attempts:
        try:
            if in_sock is None:
                batch.connect_nodes(src, out_sock, dst)
            else:
                batch.connect_nodes(src, out_sock, dst, in_sock)
            return True
        except TypeError:
            try:
                batch.connect_nodes(src, out_sock, dst)
                return True
            except Exception:  # noqa: BLE001
                continue
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Comp CG connect %s %s/%s: %s", label, out_sock, in_sock, exc
            )
    logger.warning("Comp CG: connect failed (%s)", label)
    return False


def find_saved_action_file(save_root: Path) -> Path | None:
    """Locate Batch save_node_setup or TimelineFX save_setup output."""
    if save_root.is_file() and save_root.stat().st_size > 0:
        return save_root
    candidates = [
        save_root / "comp_cg.action",
        save_root / "comp_cg.action_node",
        save_root / "_action.action",
        save_root / "temp.action" / "_action.action",
    ]
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    if save_root.is_dir():
        patterns = ("*.action", "*.action_node")
        found: list[Path] = []
        for pattern in patterns:
            found.extend(save_root.rglob(pattern))
        for path in sorted(found, key=lambda p: p.name.lower()):
            if path.name.startswith("."):
                continue
            # Skip our patched output if present
            if path.name == "comp_cg_blended.action":
                continue
            if path.stat().st_size > 0:
                return path
    return None


def _resolve_setup_io(action) -> tuple[object | None, object | None, str, str]:
    """Batch Action → save_node_setup; TimelineFX Action → save_setup."""
    save_fn = None
    save_name = ""
    for name in ("save_node_setup", "save_setup"):
        fn = getattr(action, name, None)
        if callable(fn):
            save_fn = fn
            save_name = name
            break
    load_fn = None
    load_name = ""
    for name in ("load_node_setup", "load_setup"):
        fn = getattr(action, name, None)
        if callable(fn):
            load_fn = fn
            load_name = name
            break
    return save_fn, load_fn, save_name, load_name


def apply_blending_to_setup(text: str, modes: list[str]) -> tuple[str, int]:
    """Rewrite SurfaceSquare ``Blending N`` lines in file order.

    Returns (new_text, number_of_replacements).
    """
    values = [blending_int(m) for m in modes]
    idx = 0
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        # Preserve newline style via keepends; match without trailing newline
        bare = line[:-1] if line.endswith("\n") else line
        if bare.endswith("\r"):
            bare = bare[:-1]
        m = _SURFACE_BLENDING_RE.match(bare)
        if m and idx < len(values):
            nl = "\n" if line.endswith("\n") else ""
            if line.endswith("\r\n"):
                nl = "\r\n"
            elif line.endswith("\r"):
                nl = "\r"
            out_lines.append(f"{m.group(1)}{values[idx]}{m.group(2)}{nl}")
            idx += 1
        else:
            out_lines.append(line)
    return "".join(out_lines), idx


def _patch_action_blending(action, clip_names: list[str], logger) -> bool:
    # Clip[0] → Action Back (background). Flame Mode is always Blend there;
    # SurfaceSquare Blending fields exist only for add_media layers (clips[1:]).
    if clip_names:
        logger.info(
            "Comp CG: %s → Back (Blend only; no Blending field)",
            clip_names[0],
        )
    layer_names = clip_names[1:]
    modes = [mode_from_clip_name(n) for n in layer_names]
    for name, mode in zip(layer_names, modes):
        logger.info(
            "Comp CG: %s → %s (Blending %s)",
            name,
            mode,
            blending_int(mode),
        )
    if not modes:
        logger.info("Comp CG: no media layers to blend-patch")
        return True

    save_fn, load_fn, save_name, load_name = _resolve_setup_io(action)
    if save_fn is None or load_fn is None:
        logger.warning(
            "Comp CG: Action has no callable setup IO "
            "(tried save_node_setup/save_setup, "
            "load_node_setup/load_setup); save=%r load=%r",
            getattr(action, "save_node_setup", "∅"),
            getattr(action, "load_node_setup", "∅"),
        )
        return False

    save_root = Path(tempfile.mkdtemp(prefix="dgpy_comp_cg_"))
    try:
        # Batch save_node_setup expects a file path (extension optional).
        # TimelineFX save_setup often writes a directory + _action.action.
        setup_stem = save_root / "comp_cg"
        logger.info("Comp CG: %s → %s", save_name, setup_stem)
        try:
            save_fn(str(setup_stem))
        except TypeError:
            save_fn(str(save_root))
        saved = find_saved_action_file(save_root)
        if saved is None and setup_stem.is_file():
            saved = setup_stem
        if saved is None:
            # Common Flame extensions when stem has no suffix
            for suffix in (".action", ".action_node"):
                cand = Path(str(setup_stem) + suffix)
                if cand.is_file() and cand.stat().st_size > 0:
                    saved = cand
                    break
        if saved is None:
            listing = sorted(p.name for p in save_root.iterdir()) if save_root.is_dir() else []
            logger.warning(
                "Comp CG: %s produced no setup file under %s (listing=%s)",
                save_name,
                save_root,
                listing,
            )
            return False
        text = saved.read_text(encoding="utf-8", errors="replace")
        new_text, n = apply_blending_to_setup(text, modes)
        if n < len(modes):
            logger.warning(
                "Comp CG: Blending fields %s < media layers %s (partial apply)",
                n,
                len(modes),
            )
        if n == 0:
            logger.warning(
                "Comp CG: no SurfaceSquare Blending lines in %s",
                saved.name,
            )
            return False
        out = save_root / "comp_cg_blended.action"
        out.write_text(new_text, encoding="utf-8")
        logger.info("Comp CG: %s ← %s (fields=%s)", load_name, out.name, n)
        load_fn(str(out))
        logger.info("Comp CG: blend patch ok via %s/%s", save_name, load_name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Comp CG: blend patch failed: %s", exc)
        return False
    finally:
        shutil.rmtree(save_root, ignore_errors=True)


def run_comp_cg(selection) -> None:
    import flame

    logger = dgpy_log.setup()
    clips = dgpy_flame_types.get_clips(selection, logger=logger)
    if len(clips) < 2:
        logger.info("Comp CG: need 2+ clips (got %s)", len(clips))
        return

    clips = _sort_clips_by_name(clips)
    names = [dgpy_flame_attr.clip_name(c) for c in clips]
    nb_reels = dgpy_batch_prefs.schematic_reel_count()
    shelves = dgpy_batch_prefs.shelf_reel_names()
    logger.info(
        "Comp CG: clips=%s nb_reels=%s names=%s",
        len(clips),
        nb_reels,
        names,
    )

    try:
        flame.set_current_tab("Batch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Comp CG: set_current_tab failed: %s", exc)

    create = flame.batch.create_batch_group
    try:
        batch = create(_BATCH_NAME, nb_reels=nb_reels, shelf_reels=shelves)
    except TypeError:
        logger.info("Comp CG: shelf_reels unsupported; nb_reels=%s only", nb_reels)
        batch = create(_BATCH_NAME, nb_reels=nb_reels)

    reels = list(getattr(batch, "reels", None) or [])
    if not reels:
        logger.warning("Comp CG: batch has no schematic reels")
        return

    before_ids = {id(n) for n in (getattr(batch, "nodes", None) or [])}
    try:
        flame.media_panel.copy(clips, reels[0])
    except TypeError:
        for clip in clips:
            flame.media_panel.copy(clip, reels[0])

    clip_nodes = _clip_nodes_after_copy(batch, before_ids)
    if len(clip_nodes) < 2:
        logger.warning(
            "Comp CG: need 2+ clip nodes after copy (got %s)",
            len(clip_nodes),
        )
        return

    if len(clip_nodes) != len(clips):
        logger.warning(
            "Comp CG: clip/node mismatch clips=%s nodes=%s",
            len(clips),
            len(clip_nodes),
        )
        n = min(len(clips), len(clip_nodes))
        clips = clips[:n]
        clip_nodes = clip_nodes[:n]
        names = names[:n]

    action = None
    for index, (clip, node) in enumerate(zip(clips, clip_nodes)):
        nx, ny = dgpy_flame_attr.node_xy(node)
        try:
            if index == 0:
                action = batch.create_node("Action")
                _connect(batch, node, action, logger, f"{dgpy_flame_attr.clip_name(clip)}→Action")
                _set_xy(action, nx + (_NODE_UNIT * 2), ny, logger, "Action")
            else:
                if action is None:
                    logger.warning("Comp CG: Action missing; skip %s", dgpy_flame_attr.clip_name(clip))
                    continue
                media = action.add_media()
                _connect(batch, node, media, logger, f"{dgpy_flame_attr.clip_name(clip)}→Media")
                _set_xy(media, nx + _NODE_UNIT, ny, logger, "Media")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Comp CG: wire failed for %s: %s",
                dgpy_flame_attr.clip_name(clip),
                exc,
            )

    try:
        batch.frame_all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Comp CG frame_all: %s", exc)

    if action is None:
        logger.warning("Comp CG: no Action created")
        return

    _patch_action_blending(action, names, logger)
    logger.info("Comp CG: done clips=%s", len(clips))
