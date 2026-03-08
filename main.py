"""Entry point: request admin (Windows), then run the GUI."""

import logging
import sys
import tkinter as tk

from lib import parse_midi, build_mcr_lines, export_mcr
from lib.admin import request_admin_and_restart
from lib.app import App
from lib.log_config import setup_logging


def main():
    setup_logging()
    log = logging.getLogger("lib.main")
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
