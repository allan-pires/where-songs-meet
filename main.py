"""Entry point: request admin (Windows), then run the GUI."""

import logging
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
    root = tk.Tk()
    try:
        App(root)
        root.mainloop()
    except Exception as e:
        log.exception("Startup error")
        root.destroy()
        from tkinter import messagebox
        messagebox.showerror('Startup error', str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
