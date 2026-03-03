"""Check for updates via GitHub releases and open/download latest."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser
import zipfile

log = logging.getLogger("midi_to_macro.updater")

from midi_to_macro.version import (
    GITHUB_RELEASES_API,
    GITHUB_RELEASES_PAGE,
    __version__ as current_version,
)


# Headers sent on every request (including after redirects) so GitHub/CDN returns the binary
_DOWNLOAD_HEADERS = {
    "Accept": "application/octet-stream",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-add our headers when following redirects so the asset CDN gets Accept and User-Agent."""

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        new_req = super().redirect_request(req, fp, code, msg, hdrs, newurl)
        if new_req is not None:
            for key, value in _DOWNLOAD_HEADERS.items():
                new_req.add_header(key, value)
        return new_req


def _ssl_context():
    """SSL context with CA bundle so HTTPS works in frozen builds and strict environments."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _build_download_opener():
    return urllib.request.build_opener(
        _RedirectHandler,
        urllib.request.HTTPSHandler(context=_ssl_context()),
    )


def _parse_version(s: str) -> tuple[int, ...]:
    """Convert version string to comparable tuple (e.g. '1.2.3' -> (1, 2, 3))."""
    s = re.sub(r"[^0-9.].*$", "", s.strip())
    parts = s.split(".")[:4]
    return tuple(int(p) if p.isdigit() else 0 for p in parts)


def check_for_updates(timeout: float = 10.0) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """
    Fetch latest release from GitHub. Returns (latest_version, html_url, body, download_url, error_message).
    On success error_message is None. On error returns (None, None, None, None, error_message).
    """
    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_API,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "midi-to-macro-updater",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (None, None, None, None, "No releases found. Publish a release on GitHub or check the repo in version.py.")
        return (None, None, None, None, f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return (None, None, None, None, str(e.reason) if e.reason else "Connection error")
    except (OSError, ValueError) as e:
        return (None, None, None, None, str(e))

    try:
        release = json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        return (None, None, None, None, f"Invalid response: {e}")

    tag = release.get("tag_name") or ""
    # Strip leading 'v' if present
    latest_version = tag.lstrip("v").strip() or None
    html_url = release.get("html_url") or GITHUB_RELEASES_PAGE
    body = (release.get("body") or "").strip() or None
    download_url = None
    assets = release.get("assets") or []
    # Prefer .exe for "Download and run"; fall back to .zip then any asset
    for a in assets:
        url = a.get("browser_download_url")
        name = (a.get("name") or "").lower()
        if url and name.endswith(".exe"):
            download_url = url
            break
    if not download_url:
        for a in assets:
            url = a.get("browser_download_url")
            name = (a.get("name") or "").lower()
            if url and name.endswith(".zip"):
                download_url = url
                break
    if not download_url:
        for a in assets:
            url = a.get("browser_download_url")
            if url:
                download_url = url
                break

    return (latest_version, html_url, body, download_url, None)


def is_newer(latest: str, current: str = current_version) -> bool:
    """Return True if latest > current."""
    return _parse_version(latest) > _parse_version(current)


def open_releases_page() -> None:
    """Open the GitHub releases page in the default browser."""
    webbrowser.open(GITHUB_RELEASES_PAGE)


def open_release_page(url: str) -> None:
    """Open a specific release URL in the default browser."""
    webbrowser.open(url)


def download_update(
    download_url: str,
    timeout: float = 60.0,
    save_dir: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Download the update. Returns (path, error_message). On success path is set and error_message is None.
    On failure path is None and error_message describes the error (and is logged).
    - If URL is .zip and save_dir is set: download zip, extract to save_dir/where-songs-meet/,
      return path to save_dir/where-songs-meet/where-songs-meet.exe (runs with DLLs beside it, no "Failed to load Python DLL").
    - If URL is .exe and save_dir is set: save exe there, return its path.
    - If save_dir is None: save to temp and return path (caller runs or cleans up).
    """
    if not download_url:
        msg = "No download URL provided"
        log.warning("download_update: %s", msg)
        return (None, msg)

    opener = _build_download_opener()
    req = urllib.request.Request(download_url, headers=_DOWNLOAD_HEADERS)
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.reason}"
        log.warning("download_update: %s", msg, exc_info=True)
        return (None, msg)
    except urllib.error.URLError as e:
        msg = str(e.reason) if e.reason else "Connection error"
        log.warning("download_update: %s", msg, exc_info=True)
        return (None, msg)
    except (OSError, ValueError) as e:
        msg = str(e)
        log.warning("download_update: %s", msg, exc_info=True)
        return (None, msg)

    if not data:
        msg = "Download returned no data"
        log.warning("download_update: %s", msg)
        return (None, msg)

    filename = download_url.split("/")[-1].split("?")[0] or "update"

    if filename.lower().endswith(".zip") and save_dir:
        # Extract onedir bundle so exe runs from a folder with all DLLs
        os.makedirs(save_dir, exist_ok=True)
        zip_path = os.path.join(save_dir, filename)
        try:
            with open(zip_path, "wb") as f:
                f.write(data)
            extract_dir = os.path.join(save_dir, "where-songs-meet")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(os.path.dirname(extract_dir))
            exe_path = os.path.join(extract_dir, "where-songs-meet.exe")
            try:
                os.remove(zip_path)
            except OSError:
                pass
            if os.path.isfile(exe_path):
                return (exe_path, None)
            msg = "Extracted zip did not contain where-songs-meet.exe"
            log.warning("download_update: %s", msg)
            return (None, msg)
        except (OSError, zipfile.BadZipFile) as e:
            msg = str(e)
            log.warning("download_update: extract failed: %s", msg, exc_info=True)
            return (None, msg)

    if not filename.endswith(".exe") and not filename.endswith(".msi"):
        filename = filename + ".exe"

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, filename)
        # Avoid overwriting the running executable (Windows locks it and the write would fail)
        if getattr(sys, "frozen", False):
            try:
                if os.path.abspath(path) == os.path.abspath(sys.executable):
                    base, ext = os.path.splitext(filename)
                    filename = base + "-new" + ext
                    path = os.path.join(save_dir, filename)
            except OSError:
                pass
        try:
            with open(path, "wb") as f:
                f.write(data)
            return (path, None)
        except OSError as e:
            msg = str(e)
            log.warning("download_update: save failed: %s", msg, exc_info=True)
            return (None, msg)

    fd, path = tempfile.mkstemp(suffix="_" + filename)
    try:
        with open(fd, "wb") as f:
            f.write(data)
        return (path, None)
    except OSError as e:
        msg = str(e)
        log.warning("download_update: temp write failed: %s", msg, exc_info=True)
        return (None, msg)
