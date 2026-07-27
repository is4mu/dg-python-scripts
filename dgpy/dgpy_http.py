"""HTTPS (and file) fetch helpers. stdlib only."""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from pathlib import Path

__version__ = "0.3.2"

_TIMEOUT_SEC = 30


def fetch_bytes(url: str, timeout: int = _TIMEOUT_SEC) -> bytes:
    """Fetch URL contents. Supports https:// and file:// and plain local paths.

    For GitHub Contents API URLs, sends Accept: application/vnd.github.raw so the
    response body is the file bytes (not the JSON metadata envelope).
    """
    if url.startswith("file://"):
        path = Path(url[7:])
        return path.read_bytes()
    if not url.startswith(("http://", "https://")):
        path = Path(url)
        if path.exists():
            return path.read_bytes()

    headers = {
        "User-Agent": "DG-Script-Manager/0.3",
        # raw.githubusercontent.com CDN can serve stale branch tips for ~5 minutes.
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if "api.github.com" in url and "/contents/" in url:
        headers["Accept"] = "application/vnd.github.raw"

    req = urllib.request.Request(url, headers=headers, method="GET")
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def download_to(url: str, dest: Path, timeout: int = _TIMEOUT_SEC) -> None:
    data = fetch_bytes(url, timeout=timeout)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
