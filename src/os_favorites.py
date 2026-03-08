"""Online Sequencer favorites persistence (no UI)."""

import json
import os


# Legacy config dir names (e.g. from older app names); checked if primary path has no file.
_LEGACY_CONFIG_DIRS = (".midi_to_macro", ".where_songs_meet")


def _user_config_dir(settings_dir: str) -> str:
    return settings_dir or os.path.join(os.path.expanduser("~"), ".where_songs_meet")


class OsFavorites:
    """Load/save list of (sequence_id, title) for onlinesequencer.net."""

    def __init__(self, settings_dir: str = ""):
        self._dir = _user_config_dir(settings_dir)
        self._path = os.path.join(self._dir, "os_favorites.json")
        self._list: list[tuple[str, str]] = []
        self.load()

    def load(self) -> None:
        self._list = []
        # Try primary path first
        if self._path and os.path.isfile(self._path):
            self._load_from_path(self._path)
            return
        # Fallback: load from legacy config dirs (e.g. .midi_to_macro) and migrate
        base = os.path.expanduser("~")
        for legacy_dir in _LEGACY_CONFIG_DIRS:
            if legacy_dir == os.path.basename(self._dir):
                continue
            legacy_path = os.path.join(base, legacy_dir, "os_favorites.json")
            if os.path.isfile(legacy_path):
                self._load_from_path(legacy_path)
                if self._list:
                    self.save()
                return

    def _load_from_path(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("favorites"), list):
                for item in data["favorites"]:
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("id"), str)
                        and isinstance(item.get("title"), str)
                    ):
                        self._list.append((item["id"], item["title"]))
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if not self._dir:
            return
        try:
            os.makedirs(self._dir, exist_ok=True)
            data = {"favorites": [{"id": sid, "title": title} for sid, title in self._list]}
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def list_all(self) -> list[tuple[str, str]]:
        return list(self._list)

    def add(self, sid: str, title: str) -> bool:
        if sid in self.fav_ids():
            return False
        self._list.append((sid, title))
        self.save()
        return True

    def remove(self, sid: str) -> bool:
        before = len(self._list)
        self._list = [(s, t) for s, t in self._list if s != sid]
        if len(self._list) < before:
            self.save()
            return True
        return False

    def fav_ids(self) -> set[str]:
        return {sid for sid, _ in self._list}
