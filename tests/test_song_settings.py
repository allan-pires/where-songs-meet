"""Tests for src.song_settings: SongSettings get/set/delete/has and persistence."""

import json
import os

import pytest

from src.song_settings import SongSettings


@pytest.fixture
def temp_config_dir(tmp_path):
    """A temporary directory used as config dir for SongSettings."""
    return str(tmp_path)


@pytest.fixture
def song_settings(temp_config_dir):
    """SongSettings instance using a temp dir."""
    return SongSettings(temp_config_dir)


class TestSongSettings:
    """Test SongSettings API and persistence."""

    def test_settings_dir_property(self, song_settings, temp_config_dir):
        assert song_settings.settings_dir == temp_config_dir

    def test_get_missing_returns_none(self, song_settings):
        assert song_settings.get("missing_key") is None

    def test_set_and_get(self, song_settings):
        song_settings.set("file:/path/to.mid", 1.2, 3)
        data = song_settings.get("file:/path/to.mid")
        assert data is not None
        assert data["tempo"] == 1.2
        assert data["transpose"] == 3

    def test_has(self, song_settings):
        assert song_settings.has("key1") is False
        song_settings.set("key1", 1.0, 0)
        assert song_settings.has("key1") is True

    def test_delete(self, song_settings):
        song_settings.set("key1", 1.0, 0)
        song_settings.delete("key1")
        assert song_settings.get("key1") is None
        assert song_settings.has("key1") is False

    def test_persists_across_instances(self, temp_config_dir):
        s1 = SongSettings(temp_config_dir)
        s1.set("os:123", 0.8, -2)
        s2 = SongSettings(temp_config_dir)
        data = s2.get("os:123")
        assert data is not None
        assert data["tempo"] == 0.8
        assert data["transpose"] == -2

    def test_save_format(self, temp_config_dir):
        s = SongSettings(temp_config_dir)
        s.set("key", 1.5, 5)
        path = os.path.join(temp_config_dir, "song_settings.json")
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"key": {"tempo": 1.5, "transpose": 5}}
