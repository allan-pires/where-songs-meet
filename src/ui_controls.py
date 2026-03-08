"""Reusable UI controls (e.g. Play/Stop button)."""

import tkinter as tk

from src import theme as _theme

_t = _theme
CARD = _t.CARD
FONT_FAMILY = _t.FONT_FAMILY
FG_DISABLED = _t.FG_DISABLED

# Play/Stop symbols (no Canvas — avoids Tk "bad argument 'N'" on some builds)
_CTRL_PLAY_SYMBOL = '\u25b6'   # ▶
_CTRL_STOP_SYMBOL = '\u25a0'   # ■

# Control button shape: enough height for 1080p so play/stop glyph isn't clipped
_CTRL_BTN_W = 56
_CTRL_BTN_H = 40
_CTRL_BTN_R = 6


def _rounded_rect_photo(w: int, h: int, color_hex: str, radius: int):
    """Return a PhotoImage of a rounded rectangle (Pillow). Kept for GC."""
    try:
        from PIL import Image, ImageDraw, ImageTk
        img = Image.new("RGB", (w, h), color_hex)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=color_hex, outline=color_hex)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


class ControlButton(tk.Frame):
    """Play or Stop control button: rounded rect image if Pillow available, else flat tk.Button."""

    def __init__(self, parent, kind: str, bg: str, hover_bg: str, fg: str, command, initial_state=tk.NORMAL, disabled_bg: str | None = None):
        assert kind in ('play', 'stop'), kind
        self._bg = bg
        self._hover_bg = hover_bg
        self._disabled_bg = disabled_bg if disabled_bg is not None else CARD
        self._command = command
        self._state = initial_state
        self._kind = kind
        text = _CTRL_PLAY_SYMBOL if kind == 'play' else _CTRL_STOP_SYMBOL
        super().__init__(parent, bg=CARD)
        # Fixed size so button doesn't shrink when state changes (e.g. play disabled while playing)
        self.pack_propagate(False)
        tk.Frame.config(self, width=_CTRL_BTN_W, height=_CTRL_BTN_H)
        # Rounded-rect images (keep refs so they aren't GC'd)
        self._img_normal = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, bg, _CTRL_BTN_R)
        self._img_hover = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, hover_bg, _CTRL_BTN_R)
        self._img_disabled = _rounded_rect_photo(_CTRL_BTN_W, _CTRL_BTN_H, self._disabled_bg, _CTRL_BTN_R)
        use_rounded = self._img_normal is not None
        show_disabled = initial_state == tk.DISABLED
        init_bg = self._disabled_bg if show_disabled else bg
        if use_rounded:
            self._btn = tk.Button(
                self, text=text, font=(FONT_FAMILY, 11), fg=fg,
                image=self._img_disabled if show_disabled else self._img_normal,
                compound='center',
                bg=init_bg,
                activebackground=init_bg, activeforeground=fg,
                highlightbackground=init_bg, highlightcolor=init_bg,
                relief='flat', bd=0, highlightthickness=0, padx=0, pady=0,
                cursor='hand2', command=command, state=initial_state,
                disabledforeground=FG_DISABLED, takefocus=0,
            )
        else:
            self._btn = tk.Button(
                self, text=text, font=(FONT_FAMILY, 12), fg=fg,
                bg=init_bg,
                activebackground=init_bg, activeforeground=fg,
                highlightbackground=init_bg, highlightcolor=init_bg,
                relief='flat', padx=18, pady=3, cursor='hand2',
                command=command, state=initial_state,
                disabledforeground=FG_DISABLED, takefocus=0,
            )
        self._use_rounded = use_rounded
        self._btn.pack()
        self._btn.bind('<Enter>', self._on_enter)
        self._btn.bind('<Leave>', self._on_leave)

    def _current_image(self):
        if self._btn['state'] == 'disabled':
            return self._img_disabled
        return self._img_normal

    def _apply_bg(self, color: str) -> None:
        """Set bg and matching border/active colors so no visible border mismatch."""
        self._btn.configure(
            bg=color, activebackground=color,
            highlightbackground=color, highlightcolor=color,
        )

    def _on_enter(self, e: tk.Event) -> None:
        if self._btn['state'] == 'normal':
            self._apply_bg(self._hover_bg)
            if self._use_rounded:
                self._btn.configure(image=self._img_hover)
        else:
            self._apply_bg(self._disabled_bg)
            if self._use_rounded:
                self._btn.configure(image=self._img_disabled)

    def _on_leave(self, e: tk.Event) -> None:
        color = self._disabled_bg if self._btn['state'] == 'disabled' else self._bg
        self._apply_bg(color)
        if self._use_rounded:
            self._btn.configure(image=self._current_image())

    def config(self, **kwargs) -> None:
        if 'state' in kwargs:
            self._btn.config(state=kwargs['state'])
        if 'bg' in kwargs:
            self._bg = kwargs['bg']
            self._apply_bg(self._bg)
        if self._use_rounded and ('state' in kwargs or 'bg' in kwargs):
            self._btn.configure(image=self._current_image())
        if 'state' in kwargs and kwargs['state'] == 'disabled':
            self._apply_bg(self._disabled_bg)

    def __getitem__(self, key: str):
        if key == 'state':
            return self._btn['state']
        raise KeyError(key)


__all__ = ["ControlButton"]
