"""Timewarp range from Flame TW setup (Speed / Timing bezier)."""

from __future__ import annotations

import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import dgpy_flame_attr

from segment_handle_clips_util import __version__, is_skip_tw  # noqa: F401

_TW_TYPE_HINTS = ("timewarp", "time warp", "tw")


@dataclass
class SourceRange:
    source_start: int
    source_end: int  # inclusive
    record_duration: int
    head: int
    tail: int
    speed: float | None
    tw_mode: str  # none | constant | variable
    notes: str = ""

    @property
    def source_frames(self) -> int:
        return max(1, abs(self.source_end - self.source_start) + 1)


@dataclass
class SkipTW:
    reason: str


@dataclass
class _Key:
    frame: float
    value: float
    rh_dx: float = 0.25
    rh_dy: float = 0.0
    lh_dx: float = -0.25
    lh_dy: float = 0.0
    curve_mode: str = "bezier"


@dataclass
class _TwSetup:
    retimer_mode: int | None = None  # 0 Speed, 1 Timing (Flame)
    speed_ratio: float | None = None  # 1.79 for 179% (channel / first key)
    speed_percent: float | None = None  # raw TW_Speed Value when present
    speed_keys: list[_Key] = field(default_factory=list)
    timing_keys: list[_Key] = field(default_factory=list)
    duration_keys: list[_Key] = field(default_factory=list)
    speed_timing_keys: list[_Key] = field(default_factory=list)


def frame_number(time_obj) -> int | None:
    val = float_number(time_obj)
    if val is None:
        return None
    return int(val)


def float_number(time_obj) -> float | None:
    if time_obj is None:
        return None
    if hasattr(time_obj, "get_value"):
        try:
            time_obj = time_obj.get_value()
        except Exception:  # noqa: BLE001
            pass
    if time_obj is None:
        return None
    if hasattr(time_obj, "frame"):
        try:
            frame_attr = time_obj.frame
            if hasattr(frame_attr, "get_value"):
                try:
                    return float(frame_attr.get_value())
                except Exception:  # noqa: BLE001
                    pass
            return float(frame_attr)
        except Exception:  # noqa: BLE001
            pass
    try:
        return float(time_obj)
    except Exception:  # noqa: BLE001
        return None


def record_duration_frames(segment) -> int | None:
    rec = frame_number(dgpy_flame_attr.attr_value(segment, "record_duration", None))
    if rec is not None and rec > 0:
        return rec
    rin = frame_number(dgpy_flame_attr.attr_value(segment, "record_in", None))
    rout = frame_number(dgpy_flame_attr.attr_value(segment, "record_out", None))
    if rin is not None and rout is not None:
        span = abs(rout - rin)
        return 1 if span == 0 else span + 1
    return None


def source_in_out(segment) -> tuple[float | None, float | None]:
    sin = float_number(dgpy_flame_attr.attr_value(segment, "source_in", None))
    sout = float_number(dgpy_flame_attr.attr_value(segment, "source_out", None))
    return sin, sout


def _effect_type(effect) -> str:
    typ = dgpy_flame_attr.attr_value(effect, "type", None)
    if typ is None:
        typ = getattr(effect, "type", None)
    return str(typ or "").strip()


def _is_timewarp_effect(effect) -> bool:
    text = _effect_type(effect).lower()
    return any(h in text for h in _TW_TYPE_HINTS)


def timewarp_effects(segment) -> list:
    effects = list(getattr(segment, "effects", None) or [])
    return [e for e in effects if _is_timewarp_effect(e)]


def _setup_text(effect, logger) -> str | None:
    save = getattr(effect, "save_setup", None)
    if not callable(save):
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="dgpy-tw-") as tmp:
            root = Path(tmp) / "tw"
            save(str(root))
            chunks: list[str] = []
            for f in Path(tmp).rglob("*"):
                if not f.is_file() or f.stat().st_size > 500_000:
                    continue
                try:
                    chunks.append(
                        f.read_text(encoding="utf-8", errors="replace")
                    )
                except Exception:  # noqa: BLE001
                    continue
            text = "\n".join(chunks) if chunks else None
            if text:
                logger.info("TW: save_setup ok (%s chars)", len(text))
            return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("TW: save_setup failed: %s", exc)
        return None


def _parse_keys_in_block(block: str) -> list[_Key]:
    keys: list[_Key] = []
    for m in re.finditer(r"(?is)<Key\b[^>]*>(.*?)</Key>", block):
        body = m.group(1)
        fm = re.search(r"(?is)<Frame>\s*([\-\d.]+)\s*</Frame>", body)
        vm = re.search(r"(?is)<Value>\s*([\-\d.]+)\s*</Value>", body)
        if not fm or not vm:
            continue
        def _f(pat: str, default: float) -> float:
            mm = re.search(pat, body)
            if not mm:
                return default
            try:
                return float(mm.group(1))
            except ValueError:
                return default

        cm = re.search(r"(?is)<CurveMode>\s*([^<]+)\s*</CurveMode>", body)
        keys.append(
            _Key(
                frame=float(fm.group(1)),
                value=float(vm.group(1)),
                rh_dx=_f(r"(?is)<RHandle_dX>\s*([\-\d.]+)\s*</RHandle_dX>", 0.25),
                rh_dy=_f(r"(?is)<RHandle_dY>\s*([\-\d.]+)\s*</RHandle_dY>", 0.0),
                lh_dx=_f(r"(?is)<LHandle_dX>\s*([\-\d.]+)\s*</LHandle_dX>", -0.25),
                lh_dy=_f(r"(?is)<LHandle_dY>\s*([\-\d.]+)\s*</LHandle_dY>", 0.0),
                curve_mode=(cm.group(1).strip().lower() if cm else "bezier"),
            )
        )
    keys.sort(key=lambda k: k.frame)
    return keys


def _channel_block(text: str, tag: str) -> str | None:
    m = re.search(rf"(?is)<{tag}>(.*?)</{tag}>", text)
    return m.group(1) if m else None


def parse_tw_setup(text: str) -> _TwSetup:
    out = _TwSetup()
    rm = re.search(r"(?is)<TW_RetimerMode>\s*(\d+)\s*</TW_RetimerMode>", text)
    if rm:
        out.retimer_mode = int(rm.group(1))

    speed_block = _channel_block(text, "TW_Speed")
    if speed_block:
        out.speed_keys = _parse_keys_in_block(speed_block)
        # Channel-level <Value> (before or beside keys); allow negative (reverse).
        sp = re.search(r"(?is)<Value>\s*([-\d.]+)\s*</Value>", speed_block)
        if sp:
            val = float(sp.group(1))
            if abs(val) > 1e-15:
                out.speed_percent = val
                out.speed_ratio = _as_speed_ratio(val)
        if out.speed_keys and (
            out.speed_ratio is None or abs(out.speed_ratio) < 1e-15
        ):
            val = out.speed_keys[0].value
            if abs(val) > 1e-15:
                out.speed_percent = val
                out.speed_ratio = _as_speed_ratio(val)

    # Flame often omits TW_Speed <Value> at default 100% (constant).
    # Do not treat negative speeds as "missing".
    if (
        out.retimer_mode == 0
        and not out.speed_keys
        and out.speed_ratio is None
    ):
        out.speed_percent = 100.0
        out.speed_ratio = 1.0

    for tag, attr in (
        ("TW_Timing", "timing_keys"),
        ("TW_DurationTiming", "duration_keys"),
        ("TW_SpeedTiming", "speed_timing_keys"),
    ):
        block = _channel_block(text, tag)
        if block:
            setattr(out, attr, _parse_keys_in_block(block))
    return out


def _bezier_x(t: float, x0: float, x1: float, x2: float, x3: float) -> float:
    u = 1.0 - t
    return (
        u * u * u * x0
        + 3 * u * u * t * x1
        + 3 * u * t * t * x2
        + t * t * t * x3
    )


def _bezier_y(t: float, y0: float, y1: float, y2: float, y3: float) -> float:
    return _bezier_x(t, y0, y1, y2, y3)


def _eval_segment_fixed(k0: _Key, k1: _Key, x: float) -> float:
    x0, y0 = k0.frame, k0.value
    x3, y3 = k1.frame, k1.value
    if abs(x3 - x0) < 1e-12:
        return y0
    if k0.curve_mode == "linear":
        t = (x - x0) / (x3 - x0)
        return y0 + (y3 - y0) * t

    x1 = x0 + k0.rh_dx
    y1 = y0 + k0.rh_dy
    x2 = x3 + k1.lh_dx
    y2 = y3 + k1.lh_dy

    lo, hi = 0.0, 1.0
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if _bezier_x(mid, x0, x1, x2, x3) < x:
            lo = mid
        else:
            hi = mid
    t = 0.5 * (lo + hi)
    return _bezier_y(t, y0, y1, y2, y3)


def eval_timing(keys: list[_Key], x: float) -> float:
    """Evaluate Timing channel at TW-local frame x (extrapolate outside)."""
    if not keys:
        raise ValueError("no timing keys")
    if len(keys) == 1:
        return keys[0].value
    if x <= keys[0].frame:
        # Left of first key: use LEFT handle tangent (into the past)
        k0, k1 = keys[0], keys[1]
        if abs(k0.lh_dx) > 1e-9:
            slope = k0.lh_dy / k0.lh_dx
        elif abs(k0.rh_dx) > 1e-9:
            slope = k0.rh_dy / k0.rh_dx
        else:
            slope = (k1.value - k0.value) / (k1.frame - k0.frame)
        return k0.value + slope * (x - k0.frame)
    if x >= keys[-1].frame:
        # Right of last key: use RIGHT handle tangent (into the future)
        k0, k1 = keys[-2], keys[-1]
        if abs(k1.rh_dx) > 1e-9:
            slope = k1.rh_dy / k1.rh_dx
        elif abs(k1.lh_dx) > 1e-9:
            slope = k1.lh_dy / k1.lh_dx
        else:
            slope = (k1.value - k0.value) / (k1.frame - k0.frame)
        return k1.value + slope * (x - k1.frame)
    for i in range(len(keys) - 1):
        if keys[i].frame <= x <= keys[i + 1].frame:
            return _eval_segment_fixed(keys[i], keys[i + 1], x)
    return keys[-1].value


def _is_timing_mode(setup: _TwSetup) -> bool:
    if setup.retimer_mode == 1:
        return True
    if setup.retimer_mode == 0:
        return False
    # Heuristic: multiple Timing keys with non-constant slope → Timing
    keys = setup.timing_keys
    if len(keys) >= 2:
        slopes = []
        for i in range(len(keys) - 1):
            dx = keys[i + 1].frame - keys[i].frame
            if dx:
                slopes.append((keys[i + 1].value - keys[i].value) / dx)
        if slopes and (max(slopes) - min(slopes)) > 0.05:
            return True
        # bezier handles with meaningful dy → Timing
        if any(abs(k.rh_dy) > 1e-6 or abs(k.lh_dy) > 1e-6 for k in keys):
            return True
    return False


def _speed_timing_in(setup: _TwSetup) -> float | None:
    """Speed-mode Timing IN (first key value from setup only)."""
    for keys in (setup.speed_timing_keys, setup.timing_keys):
        if keys:
            return keys[0].value
    return None


def _as_speed_ratio(val: float) -> float:
    """Flame stores Speed as percent (179 / -100) or occasionally as ratio."""
    if abs(val) > 10:
        return val / 100.0
    return val


def _speed_ratio_at(
    keys: list[_Key],
    constant: float | None,
    x: float,
) -> float:
    """Piecewise-constant Speed (left-key hold), matching CurveOrder=constant."""
    if not keys:
        if constant is None or abs(constant) < 1e-15:
            raise ValueError("no speed")
        return float(constant)
    if x < keys[0].frame:
        return _as_speed_ratio(keys[0].value)
    for i in range(len(keys) - 1):
        if keys[i].frame <= x < keys[i + 1].frame:
            return _as_speed_ratio(keys[i].value)
    return _as_speed_ratio(keys[-1].value)


def _apply_min_abs_ratio(ratio: float, min_abs: float) -> float:
    """Floor |ratio| to min_abs, preserving sign (for reverse Speed)."""
    if min_abs <= 0:
        return ratio
    if abs(ratio) >= min_abs - 1e-15:
        return ratio
    if abs(ratio) < 1e-15:
        return float(min_abs)
    return math.copysign(min_abs, ratio)


def integrate_speed(
    keys: list[_Key],
    constant: float | None,
    x0: float,
    x1: float,
    *,
    min_ratio: float = 0.0,
) -> float:
    """∫ speed_ratio(t) dt over [x0, x1).

    min_ratio: minimum |speed| per sample (e.g. 1.0 for handles so slow
    forward/reverse still reserves handle frames). Sign is preserved.
    """
    if x1 <= x0 + 1e-15:
        return 0.0
    floor_r = max(0.0, float(min_ratio))

    def sample(x: float) -> float:
        return _apply_min_abs_ratio(
            _speed_ratio_at(keys, constant, x), floor_r
        )

    if not keys:
        if constant is None or abs(constant) < 1e-15:
            raise ValueError("no speed")
        return _apply_min_abs_ratio(float(constant), floor_r) * (x1 - x0)

    total = 0.0
    f = math.floor(x0 + 1e-12)
    while f < x1 - 1e-12:
        a = max(x0, float(f))
        b = min(x1, float(f + 1))
        if b > a:
            total += sample(a) * (b - a)
        f += 1
    return total


def _clamp_keep(start: int, end: int) -> tuple[int, int]:
    """Keep IN minimum is Flame FirstFrame (1); ensure inclusive end ≥ start."""
    start = max(1, int(start))
    end = max(1, int(end))
    if end < start:
        end = start
    return start, end


def _range_from_speed_integral(
    *,
    tin: float,
    rec_dur: int,
    head: int,
    tail: int,
    speed_keys: list[_Key],
    speed_const: float | None,
    t0: float,
    tw_mode: str,
    notes: str,
    logger,
) -> SourceRange | SkipTW:
    """Timing IN + ∫speed over body; handles with min |ratio|=1; floor/ceil; clamp≥1.

    Reverse (negative) speed: source runs backward; keep is min..max of the path.
    """
    h = max(0, int(head))
    t = max(0, int(tail))
    t1 = t0 + float(rec_dur)
    try:
        body = integrate_speed(speed_keys, speed_const, t0, t1)
        head_src = integrate_speed(
            speed_keys, speed_const, t0 - float(h), t0, min_ratio=1.0
        )
        tail_src = integrate_speed(
            speed_keys, speed_const, t1, t1 + float(t), min_ratio=1.0
        )
    except ValueError:
        return SkipTW("setup missing Speed")

    tout = tin + body
    # Path endpoints (order depends on speed sign).
    a_f = tin - head_src
    b_f = tout + tail_src
    reversed_speed = a_f > b_f + 1e-15
    lo_f, hi_f = (a_f, b_f) if a_f <= b_f else (b_f, a_f)
    start = int(math.floor(lo_f + 1e-9))
    end = int(math.ceil(hi_f - 1e-9))
    # Reverse (-Speed): front handle is 1F short after floor/ceil — pad keep OUT.
    if reversed_speed:
        end += 1
        logger.info(
            "TW: reverse Speed — keep OUT +1 → end=%s (front handle pad)",
            end,
        )
    start, end = _clamp_keep(start, end)

    rep = speed_const
    if speed_keys:
        ratios = [_as_speed_ratio(k.value) for k in speed_keys]
        rep = sum(ratios) / len(ratios)
    sk = len(speed_keys)
    logger.info(
        "TW: Speed ∫body=%.4g head=%.4g tail=%.4g "
        "IN=%.4g OUT=%.4g keys=%s handles=%s/%s → [%.4g..%.4g] → [%s..%s] "
        "(floor/ceil, handles min|ratio|=1, clamp≥1%s) mode=%s",
        body,
        head_src,
        tail_src,
        tin,
        tout,
        sk,
        h,
        t,
        lo_f,
        hi_f,
        start,
        end,
        ", reverse OUT+1" if reversed_speed else "",
        tw_mode,
    )
    return SourceRange(
        source_start=start,
        source_end=end,
        record_duration=rec_dur,
        head=h,
        tail=t,
        speed=rep,
        tw_mode=tw_mode,
        notes=notes
        or (
            f"setup ∫speed body={body:g} IN={tin:g} OUT={tout:g} "
            f"speed_keys={sk}"
        ),
    )


def range_from_setup(
    setup: _TwSetup,
    *,
    rec_dur: int,
    head: int,
    tail: int,
    logger,
) -> SourceRange | SkipTW:
    """
    Keep range from TW setup only (no segment source_in/out fallback).

    Speed: Timing IN + ∫speed over body/handles (DurationTiming Values unused).
    Timing: evaluate Timing bezier over handle window.
    """
    h = max(0, int(head))
    t = max(0, int(tail))

    if _is_timing_mode(setup):
        keys = setup.timing_keys
        if len(keys) < 2:
            keys = setup.duration_keys
        if len(keys) < 1:
            return SkipTW("timing mode but no Timing keys in setup")
        x0 = keys[0].frame - h
        x1 = keys[-1].frame + t
        s0 = eval_timing(keys, float(x0))
        s1 = eval_timing(keys, float(x1) + 1.0 - 1e-9)
        lo_f, hi_f = (s0, s1) if s0 <= s1 else (s1, s0)
        start = int(math.floor(lo_f + 1e-9))
        end = int(math.ceil(hi_f - 1e-9))
        start, end = _clamp_keep(start, end)
        logger.info(
            "TW: Timing mode setup keys=%s eval x[%.3g..%.3g+1) → "
            "src[%.4g..%.4g] → [%s..%s] (floor/ceil, clamp≥1)",
            len(keys),
            x0,
            x1,
            lo_f,
            hi_f,
            start,
            end,
        )
        return SourceRange(
            source_start=start,
            source_end=end,
            record_duration=rec_dur,
            head=h,
            tail=t,
            speed=setup.speed_ratio,
            tw_mode="variable",
            notes=f"timing bezier x[{x0:g}..{x1:g}]",
        )

    # Speed retimer — integrate speed curve (not DurationTiming Values)
    speed_const = setup.speed_ratio
    if (not setup.speed_keys) and (
        speed_const is None or abs(speed_const) < 1e-15
    ):
        return SkipTW("setup missing Speed")

    tin = _speed_timing_in(setup)
    if tin is None:
        return SkipTW("setup missing Timing IN")

    # Timeline local origin: first timing / speed-timing key frame, else 1
    t0 = 1.0
    for keys in (setup.speed_timing_keys, setup.timing_keys, setup.speed_keys):
        if keys:
            t0 = float(keys[0].frame)
            break

    return _range_from_speed_integral(
        tin=float(tin),
        rec_dur=rec_dur,
        head=h,
        tail=t,
        speed_keys=setup.speed_keys,
        speed_const=speed_const,
        t0=t0,
        tw_mode="constant",
        notes="",
        logger=logger,
    )


def _fmt_key_channel(tag: str, keys: list[_Key]) -> list[str]:
    if not keys:
        return [f"  {tag}: (none)"]
    lines = [f"  {tag}: keys={len(keys)}"]
    for i, k in enumerate(keys):
        lines.append(
            f"    [{i}] Frame={k.frame:g} Value={k.value:g} "
            f"Curve={k.curve_mode} "
            f"LHandle({k.lh_dx:g},{k.lh_dy:g}) "
            f"RHandle({k.rh_dx:g},{k.rh_dy:g})"
        )
    return lines


def format_setup_detail(
    setup: _TwSetup,
    *,
    save_chars: int,
    effect_type: str = "",
) -> list[str]:
    """Human-readable lines of what was parsed from save_setup."""
    mode_label = {
        0: "Speed",
        1: "Timing",
    }.get(
        setup.retimer_mode if setup.retimer_mode is not None else -1,
        "unset → heuristic",
    )
    lines = [
        f"  save_setup: ok ({save_chars} chars)",
        f"  effect type: {effect_type or '?'}",
        f"  TW_RetimerMode: {setup.retimer_mode} ({mode_label})",
    ]
    if setup.speed_percent is not None and setup.speed_ratio is not None:
        lines.append(
            f"  TW_Speed: {setup.speed_percent:g} → ratio {setup.speed_ratio:g}"
        )
    elif setup.speed_ratio is not None:
        lines.append(f"  TW_Speed: ratio {setup.speed_ratio:g}")
    else:
        lines.append("  TW_Speed: (missing channel value)")
    lines.extend(_fmt_key_channel("TW_Speed keys", setup.speed_keys))
    lines.extend(_fmt_key_channel("TW_Timing", setup.timing_keys))
    lines.extend(_fmt_key_channel("TW_DurationTiming", setup.duration_keys))
    lines.extend(_fmt_key_channel("TW_SpeedTiming", setup.speed_timing_keys))
    judged = "Timing" if _is_timing_mode(setup) else "Speed"
    lines.append(f"  judged mode: {judged}")
    return lines


def probe_source_range(
    segment,
    *,
    head: int,
    tail: int,
    logger,
) -> tuple[SourceRange | SkipTW, list[str], str | None]:
    """
    Compute keep range; return (range_or_skip, parse_detail_lines, raw_setup).
    raw_setup is unedited save_setup text (or None).
    """
    rec_dur = record_duration_frames(segment)
    if rec_dur is None or rec_dur < 1:
        return (
            SkipTW("no record_duration"),
            ["  setup: (n/a — no record_duration)"],
            None,
        )

    sin, _sout = source_in_out(segment)
    effects = timewarp_effects(segment)

    if not effects:
        detail = ["  setup: (none — treat as Speed 100%)"]
        if sin is None:
            return SkipTW("no source_in"), detail, None
        # Same formula as constant 100% Speed: IN=source_in, body=rec×1.
        rng = _range_from_speed_integral(
            tin=float(sin),
            rec_dur=rec_dur,
            head=head,
            tail=tail,
            speed_keys=[],
            speed_const=1.0,
            t0=1.0,
            tw_mode="none",
            notes=f"no TW (as 100% speed) IN={float(sin):g}",
            logger=logger,
        )
        if is_skip_tw(rng):
            detail.append(f"  keep: SKIP — {rng.reason}")
        else:
            detail.append(
                f"  keep derived: {rng.notes} → "
                f"[{rng.source_start}..{rng.source_end}] ({rng.source_frames} F)"
            )
        return rng, detail, None

    if len(effects) > 1:
        logger.warning(
            "TW: %s Timewarp effects — using first only", len(effects)
        )

    text = _setup_text(effects[0], logger)
    if not text:
        return (
            SkipTW("timewarp save_setup failed"),
            ["  save_setup: failed"],
            None,
        )

    setup = parse_tw_setup(text)
    detail = format_setup_detail(
        setup,
        save_chars=len(text),
        effect_type=_effect_type(effects[0]),
    )
    logger.info(
        "TW: setup retimer=%s speed=%s timing_keys=%s duration_keys=%s "
        "(keep from setup only)",
        setup.retimer_mode,
        setup.speed_ratio,
        len(setup.timing_keys),
        len(setup.duration_keys),
    )
    rng = range_from_setup(
        setup,
        rec_dur=rec_dur,
        head=head,
        tail=tail,
        logger=logger,
    )
    if is_skip_tw(rng):
        detail.append(f"  keep: SKIP — {rng.reason}")
    else:
        detail.append(
            f"  keep derived: {rng.notes} → "
            f"[{rng.source_start}..{rng.source_end}] ({rng.source_frames} F)"
        )
    return rng, detail, text
