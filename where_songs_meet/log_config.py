"""Configure application logging to a file and stderr."""

import logging
import os
import sys

# Set by setup_logging(); used by UI to open the log file.
LOG_FILE_PATH: str | None = None


def setup_logging() -> None:
    """Configure root logger: file in temp dir + stderr at INFO."""
    root = logging.getLogger("where_songs_meet")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    global LOG_FILE_PATH
    log_path = None
    try:
        log_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "WhereSongsMeet")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "app.log")
        LOG_FILE_PATH = log_path
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass

    eh = logging.StreamHandler(sys.stderr)
    eh.setLevel(logging.INFO)
    eh.setFormatter(fmt)
    root.addHandler(eh)

    root.info("Logging started; file: %s", log_path or "(none)")
