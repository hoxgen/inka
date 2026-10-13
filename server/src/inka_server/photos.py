import hashlib
import random
from pathlib import Path

PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"})


def list_photos(photos_dir: Path) -> list[Path]:
    if not photos_dir.is_dir():
        return []
    photos = [
        p
        for p in photos_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in PHOTO_EXTENSIONS
    ]
    return sorted(photos, key=lambda p: p.name.casefold())


def order_photos(photos: list[Path], order: str) -> list[Path]:
    if order != "shuffle":
        return list(photos)
    seed = hashlib.sha256("\n".join(p.name for p in photos).encode()).hexdigest()
    shuffled = list(photos)
    random.Random(seed).shuffle(shuffled)
    return shuffled
