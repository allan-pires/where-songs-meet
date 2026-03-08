"""File tab favorites persistence (full paths to MIDI files)."""

import json
import os

from src.config import get_config_dir


class FileFavorites:
    """Load/save list of full paths to favorited MIDI files."""

    def __init__(self, settings_dir: str = ""):
        self._dir = get_config_dir(settings_dir)
        self._path = os.path.join(self._dir, "file_favorites.json")
        self._paths: list[str] = []
        self.load()

    def load(self) -> None:
        self._paths = []
        if not self._path or not os.path.isfile(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("favorites"), list):
                for item in data["favorites"]:
                    if isinstance(item, dict) and isinstance(item.get("path"), str):
                        self._paths.append(os.path.normpath(item["path"]))
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if not self._dir:
            return
        try:
            os.makedirs(self._dir, exist_ok=True)
            data = {"favorites": [{"path": p} for p in self._paths]}
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def list_all(self) -> list[str]:
        return list(self._paths)

    def add(self, path: str) -> bool:
        norm = os.path.normpath(path)
        if norm in self.fav_paths():
            return False
        self._paths.append(norm)
        self.save()
        return True

    def remove(self, path: str) -> bool:
        norm = os.path.normpath(path)
        before = len(self._paths)
        self._paths = [p for p in self._paths if p != norm]
        if len(self._paths) < before:
            self.save()
            return True
        return False

    def fav_paths(self) -> set[str]:
        return set(self._paths)
