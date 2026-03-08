"""Render emoji as color images for icon buttons (Pillow + Segoe UI Emoji with embedded_color)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tkinter import PhotoImage

# Size in pixels for icon buttons (single dimension; we render square)
ICON_SIZE = 30
ICON_SIZE_SMALL = 20
ICON_SIZE_LARGE = 38

# Windows Segoe UI Emoji (color emoji font)
def _emoji_font_path() -> str | None:
    windir = os.environ.get("WINDIR", "C:\\Windows")
    path = os.path.join(windir, "Fonts", "seguiemj.ttf")
    return path if os.path.isfile(path) else None


_cache: dict[tuple[str, int], "PhotoImage"] = {}


def get_icon_image(emoji_char: str, size: int = ICON_SIZE) -> "PhotoImage | None":
    """Render emoji as a color PhotoImage using Segoe UI Emoji (Windows). Returns None if unavailable."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk
    except ImportError:
        return None

    font_path = _emoji_font_path()
    if not font_path:
        return None

    key = (emoji_char, size)
    if key in _cache:
        return _cache[key]

    try:
        font_size = max(8, int(size * 72 / 96))
        font = ImageFont.truetype(font_path, font_size)
    except OSError:
        return None

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((size / 2, size / 2), emoji_char, font=font, anchor="mm", embedded_color=True)
    photo = ImageTk.PhotoImage(img)
    _cache[key] = photo
    return photo


def get_all_theme_icons(size: int = ICON_SIZE) -> dict[str, "PhotoImage"]:
    """Return a dict of icon_name -> PhotoImage for all theme icons. Missing icons are omitted."""
    from src.theme import (
        ICON_ADD_LIST,
        ICON_ADD_TO_PLAYLIST,
        ICON_BROWSER,
        ICON_CLEAR,
        ICON_CONNECT,
        ICON_DISCONNECT,
        ICON_DOWNLOAD,
        ICON_FAV,
        ICON_FAV_OFF,
        ICON_FOLDER,
        ICON_HOST,
        ICON_LOG,
        ICON_PLAY,
        ICON_RELOAD,
        ICON_REMOVE,
        ICON_SAVE,
        ICON_SEARCH,
        ICON_STOP,
        ICON_STOP_HOST,
        ICON_UPDATE,
    )
    names_and_chars = [
        ("PLAY", ICON_PLAY),
        ("STOP", ICON_STOP),
        ("STOP_HOST", ICON_STOP_HOST),
        ("FOLDER", ICON_FOLDER),
        ("ADD_LIST", ICON_ADD_LIST),
        ("ADD_TO_PLAYLIST", ICON_ADD_TO_PLAYLIST),
        ("FAV", ICON_FAV),
        ("FAV_OFF", ICON_FAV_OFF),
        ("SEARCH", ICON_SEARCH),
        ("RELOAD", ICON_RELOAD),
        ("BROWSER", ICON_BROWSER),
        ("REMOVE", ICON_REMOVE),
        ("CLEAR", ICON_CLEAR),
        ("HOST", ICON_HOST),
        ("CONNECT", ICON_CONNECT),
        ("DISCONNECT", ICON_DISCONNECT),
        ("DOWNLOAD", ICON_DOWNLOAD),
        ("SAVE", ICON_SAVE),
        ("UPDATE", ICON_UPDATE),
        ("LOG", ICON_LOG),
    ]
    result: dict[str, "PhotoImage"] = {}
    for name, char in names_and_chars:
        photo = get_icon_image(char, size)
        if photo is not None:
            result[name] = photo
    return result
