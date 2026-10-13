from pathlib import Path

from .photos import list_photos
from .storage import read_json, write_json_atomic

FILE = "library.json"


def load_hidden(data_dir: Path) -> set[str]:
    hidden = (read_json(data_dir / FILE) or {}).get("hidden")
    if not isinstance(hidden, list):
        return set()
    return {h for h in hidden if isinstance(h, str)}


def set_hidden(data_dir: Path, name: str, hidden: bool) -> None:
    names = load_hidden(data_dir)
    if hidden:
        names.add(name)
    else:
        names.discard(name)
    write_json_atomic(data_dir / FILE, {"hidden": sorted(names)})


def visible_photos(photos_dir: Path, data_dir: Path) -> list[Path]:
    hidden = load_hidden(data_dir)
    return [p for p in list_photos(photos_dir) if p.name not in hidden]
