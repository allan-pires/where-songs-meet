"""Tests for src.os_favorites: OsFavorites add/remove/list/save and legacy migration."""

import json
import os

import pytest

from src.os_favorites import OsFavorites


@pytest.fixture
def temp_config_dir(tmp_path):
    """A temporary directory used as config dir for OsFavorites."""
    return str(tmp_path)


@pytest.fixture
def os_fav(temp_config_dir):
    """OsFavorites instance using a temp dir."""
    return OsFavorites(temp_config_dir)


class TestOsFavorites:
    """Test OsFavorites persistence and API."""

    def test_init_empty(self, os_fav):
        assert os_fav.list_all() == []
        assert os_fav.fav_ids() == set()

    def test_add_and_list(self, os_fav):
        assert os_fav.add("sid1", "Title One") is True
        assert os_fav.add("sid2", "Title Two") is True
        assert len(os_fav.list_all()) == 2
        assert "sid1" in os_fav.fav_ids()
        assert "sid2" in os_fav.fav_ids()
        assert os_fav.list_all() == [("sid1", "Title One"), ("sid2", "Title Two")]

    def test_add_duplicate_returns_false(self, os_fav):
        assert os_fav.add("sid1", "Title") is True
        assert os_fav.add("sid1", "Other Title") is False
        assert len(os_fav.list_all()) == 1

    def test_remove(self, os_fav):
        os_fav.add("sid1", "Title")
        assert os_fav.remove("sid1") is True
        assert os_fav.fav_ids() == set()
        assert os_fav.remove("sid1") is False

    def test_persists_across_instances(self, temp_config_dir):
        fav1 = OsFavorites(temp_config_dir)
        fav1.add("abc", "My Sequence")
        fav2 = OsFavorites(temp_config_dir)
        assert "abc" in fav2.fav_ids()
        assert fav2.list_all() == [("abc", "My Sequence")]

    def test_save_format(self, temp_config_dir):
        fav = OsFavorites(temp_config_dir)
        fav.add("id1", "Title 1")
        path = os.path.join(temp_config_dir, "os_favorites.json")
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"favorites": [{"id": "id1", "title": "Title 1"}]}
