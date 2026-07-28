"""Parse / patch Action setup text (Axis Specifics merge)."""

from __future__ import annotations

from pathlib import Path

__version__ = "0.3.2"


def extract_axis_specifics_with_surface_square(file_path: Path | str) -> str | None:
    """
    Extract Specifics block (through line before node End) from the first
    Node Axis that has a SurfaceSquare child.
    """
    path = Path(file_path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)
    except OSError:
        return None

    surface_square_numbers: set[int] = set()
    for i, line in enumerate(lines):
        if line.strip().startswith("Node SurfaceSquare"):
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip().startswith("Number "):
                    try:
                        surface_square_numbers.add(int(lines[j].strip().split()[1]))
                    except (ValueError, IndexError):
                        pass
                    break

    axis_nodes: list[dict] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("Node Axis"):
            axis_start = i
            axis_name = None
            axis_children: list[int] = []
            node_depth = 1
            for j in range(i + 1, len(lines)):
                child_stripped = lines[j].strip()
                if child_stripped.startswith("Name "):
                    axis_name = child_stripped.split(" ", 1)[1].strip()
                elif child_stripped.startswith("Child "):
                    try:
                        axis_children.append(int(child_stripped.split()[1]))
                    except (ValueError, IndexError):
                        pass
                elif child_stripped.startswith("Node "):
                    node_depth += 1
                elif child_stripped == "End":
                    end_indent = len(lines[j]) - len(lines[j].lstrip())
                    if end_indent == 0:
                        node_depth -= 1
                        if node_depth == 0:
                            if any(c in surface_square_numbers for c in axis_children):
                                axis_nodes.append(
                                    {
                                        "name": axis_name,
                                        "start": axis_start,
                                        "end": j,
                                    }
                                )
                            i = j
                            break
        i += 1

    for axis_info in axis_nodes:
        specifics_start = None
        for i in range(axis_info["start"], axis_info["end"] + 1):
            if lines[i].strip() == "Specifics":
                specifics_start = i
                break
        if specifics_start is not None:
            return "".join(lines[specifics_start : axis_info["end"]])
    return None


def replace_axis_specifics(content: str, axis_name: str, new_specifics: str) -> str:
    """Replace Specifics of Named Axis (e.g. axis1) with new_specifics text."""
    lines = content.splitlines(True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("Node Axis"):
            node_start = i
            axis_found = False
            specifics_start = None
            axis_end = None
            node_depth = 1
            j = i + 1
            while j < len(lines):
                current = lines[j]
                current_stripped = current.strip()
                if current_stripped.startswith("Name "):
                    name_value = current_stripped.split(" ", 1)[1].strip()
                    if name_value == axis_name:
                        axis_found = True
                elif (
                    current_stripped == "Specifics"
                    and axis_found
                    and specifics_start is None
                ):
                    specifics_start = j
                elif current_stripped.startswith("Node "):
                    node_depth += 1
                elif current_stripped == "End":
                    end_indent = len(current) - len(current.lstrip())
                    if end_indent == 0:
                        node_depth -= 1
                        if node_depth == 0:
                            axis_end = j
                            break
                j += 1

            if axis_found and specifics_start is not None and axis_end is not None:
                result.extend(lines[node_start:specifics_start])
                result.append(new_specifics)
                result.append(lines[axis_end])
                i = axis_end + 1
                continue

        result.append(line)
        i += 1
    return "".join(result)


def find_saved_action_file(save_root: Path) -> Path | None:
    """Locate Flame save_setup output (_action.action or a single .action file)."""
    candidates = [
        save_root / "_action.action",
        save_root / "temp.action" / "_action.action",
    ]
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    if save_root.is_file() and save_root.suffix == ".action":
        return save_root
    if save_root.is_dir():
        nested = sorted(save_root.rglob("*.action"))
        for path in nested:
            if path.name.startswith("."):
                continue
            if path.stat().st_size > 0:
                return path
    return None


def merge_template_with_saved(
    template_path: Path,
    saved_action_file: Path,
    output_path: Path,
    *,
    axis_name: str = "axis1",
) -> Path:
    """Copy template, replace axis Specifics from saved setup, write output_path."""
    specifics = extract_axis_specifics_with_surface_square(saved_action_file)
    if not specifics:
        raise RuntimeError(
            f"No SurfaceSquare-parent Axis Specifics in:\n{saved_action_file}"
        )
    content = template_path.read_text(encoding="utf-8", errors="replace")
    merged = replace_axis_specifics(content, axis_name, specifics)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(merged, encoding="utf-8")
    return output_path


def _iter_named_axis_ranges(lines: list[str], axis_name: str):
    """Yield (node_start, node_end_inclusive) for Node Axis with Name axis_name."""
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith("Node Axis"):
            i += 1
            continue
        node_start = i
        found_name = False
        node_depth = 1
        j = i + 1
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped.startswith("Name "):
                name_value = stripped.split(" ", 1)[1].strip()
                if name_value == axis_name:
                    found_name = True
            elif stripped.startswith("Node "):
                node_depth += 1
            elif stripped == "End":
                end_indent = len(lines[j]) - len(lines[j].lstrip())
                if end_indent == 0:
                    node_depth -= 1
                    if node_depth == 0:
                        if found_name:
                            yield node_start, j
                        i = j
                        break
            j += 1
        else:
            break
        i += 1


def _swap_max_min_in_expression_line(line: str) -> str:
    if "Expression" not in line:
        return line
    if "max(" not in line and "min(" not in line:
        return line
    text = line.replace("max(", "__TEMP_MAX__")
    text = text.replace("min(", "max(")
    text = text.replace("__TEMP_MAX__", "min(")
    return text


def toggle_axis_rsz_fit_expressions(content: str) -> tuple[str, int]:
    """
    Swap max(↔min( only on Expression lines inside Name axis_rsz.
    Returns (new_content, number_of_lines_changed).
    """
    lines = content.splitlines(True)
    changed = 0
    for start, end in _iter_named_axis_ranges(lines, "axis_rsz"):
        for i in range(start, end + 1):
            if "Expression" not in lines[i]:
                continue
            new_line = _swap_max_min_in_expression_line(lines[i])
            if new_line != lines[i]:
                lines[i] = new_line
                changed += 1
    return "".join(lines), changed


def strip_axis_rsz_expressions(content: str) -> tuple[str, int]:
    """
    Drop lines containing Expression inside Name axis_rsz blocks.
    Returns (new_content, number_of_lines_removed).
    """
    lines = content.splitlines(True)
    drop: set[int] = set()
    for start, end in _iter_named_axis_ranges(lines, "axis_rsz"):
        for i in range(start, end + 1):
            if "Expression" in lines[i]:
                drop.add(i)
    if not drop:
        return content, 0
    out = [line for i, line in enumerate(lines) if i not in drop]
    return "".join(out), len(drop)


def patch_saved_setup(
    saved_action_file: Path,
    output_path: Path,
    *,
    mode: str,
) -> tuple[Path, int]:
    """mode: 'toggle_fit' | 'strip_expr'. Returns (output_path, change_count)."""
    content = saved_action_file.read_text(encoding="utf-8", errors="replace")
    if mode == "toggle_fit":
        new_content, count = toggle_axis_rsz_fit_expressions(content)
    elif mode == "strip_expr":
        new_content, count = strip_axis_rsz_expressions(content)
    else:
        raise ValueError(f"Unknown patch mode: {mode}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content, encoding="utf-8")
    return output_path, count
