"""Per-song tempo/transpose persistence (no UI)."""

import json
import os


class SongSettings:
    """Load/save tempo and transpose per song key (file path or 'os:{sid}')."""

    def __init__(self, settings_dir: str = ""):
        self._dir = settings_dir or os.path.join(os.path.expanduser("~"), ".where_songs_meet")
        self._path = os.path.join(self._dir, "song_settings.json")
        self._data: dict[str, dict[str, float | int]] = {}
        self.load()

    @property
    def settings_dir(self) -> str:
        return self._dir

    def load(self) -> None:
        if not os.path.isfile(self._path):
            self._data = {}
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._data = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def save(self) -> None:
        if not self._dir:
            return
        try:
            os.makedirs(self._dir, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass

    def get(self, key: str) -> dict[str, float | int] | None:
        return self._data.get(key)

    def set(self, key: str, tempo: float, transpose: int) -> None:
        self._data[key] = {"tempo": tempo, "transpose": transpose}
        self.save()

    def delete(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self.save()

    def has(self, key: str) -> bool:
        return key in self._data
