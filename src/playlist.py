"""Playlist state: ordered list of file paths or OS (sid, title) (no UI)."""

# Item: ('file', path: str) or ('os', sid: str, title: str)
PlaylistItem = tuple[str, ...]


class Playlist:
    """Mutable playlist with current index for playback."""

    def __init__(self) -> None:
        self._items: list[PlaylistItem] = []
        self._index = 0

    def items(self) -> list[PlaylistItem]:
        return list(self._items)

    def add_file(self, path: str) -> None:
        self._items.append(("file", path))

    def add_os(self, sid: str, title: str) -> None:
        self._items.append(("os", sid, title))

    def remove_indices(self, indices: list[int]) -> None:
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self._items):
                self._items.pop(i)
        if self._index >= len(self._items):
            self._index = max(0, len(self._items) - 1)

    def clear(self) -> None:
        self._items.clear()
        self._index = 0

    def current_index(self) -> int:
        return self._index

    def current_item(self) -> PlaylistItem | None:
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return None

    def advance(self) -> bool:
        """Move to next item. Returns True if there is a next item."""
        if self._index + 1 < len(self._items):
            self._index += 1
            return True
        return False

    def reset_to_start(self) -> None:
        self._index = 0

    def __len__(self) -> int:
        return len(self._items)
