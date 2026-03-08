"""Application config directory and paths (single source of truth)."""

import os

__all__ = ["DEFAULT_CONFIG_DIR_NAME", "get_config_dir"]

# Default config directory name under user home (e.g. ~/.where_songs_meet).
DEFAULT_CONFIG_DIR_NAME = ".where_songs_meet"


def get_config_dir(settings_dir: str = "") -> str:
    """Return the config directory path. Uses settings_dir if non-empty, else ~/DEFAULT_CONFIG_DIR_NAME."""
    if settings_dir:
        return settings_dir
    return os.path.join(os.path.expanduser("~"), DEFAULT_CONFIG_DIR_NAME)
