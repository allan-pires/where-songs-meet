"""Tests for src.ui_helpers: bind_tooltip."""

import tkinter as tk

import pytest

from src.ui_helpers import bind_tooltip


class TestBindTooltip:
    """Test bind_tooltip attaches Enter/Leave bindings."""

    def test_bind_tooltip_registers_enter_and_leave(self):
        """bind_tooltip adds <Enter> and <Leave> bindings to the widget."""
        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("Tk not available or broken (e.g. headless)")
        root.withdraw()
        try:
            btn = tk.Button(root, text="X")
            status = tk.Label(root, text="")
            bind_tooltip(btn, status, "Hint text")
            # Check bindings were registered (format is widget-specific)
            bindings = btn.bind()
            assert "<Enter>" in bindings
            assert "<Leave>" in bindings
        finally:
            root.destroy()
