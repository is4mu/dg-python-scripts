"""Minimal semver compare for package versions."""

from __future__ import annotations

import re

__version__ = "0.3.0"

_SEMVER_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


def parse(version: str) -> tuple[int, int, int, tuple]:
    text = (version or "").strip()
    match = _SEMVER_RE.match(text)
    if not match:
        return (0, 0, 0, (text,))
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    pre = match.group("pre")
    # No pre-release sorts after pre-release of same numbers? Spec: plain > pre
    pre_key: tuple = (0,) if pre is None else (1, pre)
    return (major, minor, patch, pre_key)


def cmp(a: str, b: str) -> int:
    pa, pb = parse(a), parse(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def gt(a: str, b: str) -> bool:
    return cmp(a, b) > 0


def eq(a: str, b: str) -> bool:
    return cmp(a, b) == 0
