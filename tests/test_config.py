"""Tests for src.config: config directory path."""

import os

import pytest

from src.config import DEFAULT_CONFIG_DIR_NAME, get_config_dir


class TestGetConfigDir:
    """Test get_config_dir behavior."""

    def test_empty_uses_default_under_home(self):
        path = get_config_dir("")
        assert path.endswith(DEFAULT_CONFIG_DIR_NAME)
        assert os.path.expanduser("~") in path

    def test_non_empty_returns_unchanged(self):
        custom = "/custom/config/dir"
        assert get_config_dir(custom) == custom

    def test_default_config_dir_name(self):
        assert DEFAULT_CONFIG_DIR_NAME == ".where_songs_meet"
