"""Entry point: request admin (Windows), then run the GUI."""

import logging
import os
import sys
import tkinter as tk

from src import parse_midi, build_mcr_lines, export_mcr
from src.admin import request_admin_and_restart
from src.app import App
from src.log_config import setup_logging


def main():
    setup_logging()
    log = logging.getLogger("src.main")
    request_admin_and_restart()
    # Borderless (no title bar) by default; use --with-title-bar or WHERE_SONGS_MEET_TITLE_BAR=1 to show the title bar
    borderless = '--with-title-bar' not in sys.argv and os.environ.get('WHERE_SONGS_MEET_TITLE_BAR', '').strip().lower() not in ('1', 'true', 'yes')
    root = tk.Tk()
    try:
        App(root, borderless=borderless)
        root.mainloop()
    except Exception as e:
        log.exception("Startup error")
        root.destroy()
        from tkinter import messagebox
        messagebox.showerror('Startup error', str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
