"""Tests for src.playlist: Playlist add/remove/advance/current_item."""

import pytest

from src.playlist import Playlist


class TestPlaylist:
    """Test Playlist state and API."""

    def test_init_empty(self):
        pl = Playlist()
        assert len(pl) == 0
        assert pl.current_item() is None
        assert pl.current_index() == 0

    def test_add_file(self):
        pl = Playlist()
        pl.add_file("/path/to.mid")
        assert len(pl) == 1
        assert pl.current_item() == ("file", "/path/to.mid")

    def test_add_os(self):
        pl = Playlist()
        pl.add_os("sid123", "My Song")
        assert len(pl) == 1
        assert pl.current_item() == ("os", "sid123", "My Song")

    def test_advance(self):
        pl = Playlist()
        pl.add_file("a.mid")
        pl.add_file("b.mid")
        assert pl.current_index() == 0
        assert pl.advance() is True
        assert pl.current_index() == 1
        assert pl.current_item() == ("file", "b.mid")
        assert pl.advance() is False
        assert pl.current_index() == 1

    def test_reset_to_start(self):
        pl = Playlist()
        pl.add_file("a.mid")
        pl.add_file("b.mid")
        pl.advance()
        pl.reset_to_start()
        assert pl.current_index() == 0

    def test_remove_indices(self):
        pl = Playlist()
        pl.add_file("a.mid")
        pl.add_file("b.mid")
        pl.add_file("c.mid")
        pl.remove_indices([1])
        assert len(pl) == 2
        assert pl.items() == [("file", "a.mid"), ("file", "c.mid")]

    def test_remove_indices_adjusts_current_index(self):
        pl = Playlist()
        pl.add_file("a.mid")
        pl.add_file("b.mid")
        pl.advance()
        pl.remove_indices([1])
        assert pl.current_index() == 0
        assert pl.current_item() == ("file", "a.mid")

    def test_clear(self):
        pl = Playlist()
        pl.add_file("a.mid")
        pl.add_os("1", "Title")
        pl.clear()
        assert len(pl) == 0
        assert pl.current_index() == 0
        assert pl.current_item() is None

    def test_items_returns_copy(self):
        pl = Playlist()
        pl.add_file("a.mid")
        items = pl.items()
        items.append(("file", "b.mid"))
        assert len(pl) == 1
