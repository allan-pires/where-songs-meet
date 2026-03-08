"""Tests for src.file_favorites: FileFavorites add/remove/list/save."""

import os
import tempfile

import pytest

from src.file_favorites import FileFavorites


@pytest.fixture
def temp_config_dir(tmp_path):
    """A temporary directory used as config dir for FileFavorites."""
    return str(tmp_path)


@pytest.fixture
def file_fav(temp_config_dir):
    """FileFavorites instance using a temp dir."""
    return FileFavorites(temp_config_dir)


class TestFileFavorites:
    """Test FileFavorites persistence and API."""

    def test_init_empty(self, file_fav):
        assert file_fav.list_all() == []
        assert file_fav.fav_paths() == set()

    def test_add_and_list(self, file_fav, tmp_path):
        path1 = str(tmp_path / "song1.mid")
        path2 = str(tmp_path / "song2.mid")
        assert file_fav.add(path1) is True
        assert file_fav.add(path2) is True
        assert len(file_fav.list_all()) == 2
        assert path1 in file_fav.fav_paths()
        assert path2 in file_fav.fav_paths()

    def test_add_duplicate_returns_false(self, file_fav, tmp_path):
        path = str(tmp_path / "song.mid")
        assert file_fav.add(path) is True
        assert file_fav.add(path) is False
        assert len(file_fav.list_all()) == 1

    def test_remove(self, file_fav, tmp_path):
        path = str(tmp_path / "song.mid")
        file_fav.add(path)
        assert file_fav.remove(path) is True
        assert file_fav.fav_paths() == set()
        assert file_fav.remove(path) is False

    def test_persists_across_instances(self, temp_config_dir, tmp_path):
        path = str(tmp_path / "song.mid")
        fav1 = FileFavorites(temp_config_dir)
        fav1.add(path)
        fav2 = FileFavorites(temp_config_dir)
        assert path in fav2.fav_paths()
        assert fav2.list_all() == [os.path.normpath(path)]

    def test_normalizes_paths(self, file_fav, tmp_path):
        path = str(tmp_path / "song.mid")
        file_fav.add(path)
        # Same path with different separator or case should be considered same
        alt = path.replace(os.sep, "/") if os.sep != "/" else path
        assert file_fav.add(alt) is False
        assert len(file_fav.list_all()) == 1
