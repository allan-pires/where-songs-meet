"""Shared UI helpers (tooltips, etc.)."""

import tkinter as tk

__all__ = ["bind_tooltip"]


def bind_tooltip(btn: tk.Widget, status_widget: tk.Widget, hint: str) -> None:
    """Bind Enter/Leave so status_widget shows hint on hover and clears on leave."""
    btn.bind('<Enter>', lambda e: status_widget.config(text=hint))
    btn.bind('<Leave>', lambda e: status_widget.config(text=''))
