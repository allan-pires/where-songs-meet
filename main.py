"""Entry point: request admin (Windows), then run the GUI."""

import logging
import sys
import tkinter as tk

from where_songs_meet import parse_midi, build_mcr_lines, export_mcr
from where_songs_meet.admin import request_admin_and_restart
from where_songs_meet.app import App
from where_songs_meet.log_config import setup_logging


def main():
    setup_logging()
    log = logging.getLogger("where_songs_meet.main")
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
