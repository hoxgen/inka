import io
import os
import re
import tempfile
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from .photos import PHOTO_EXTENSIONS

register_heif_opener()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_BAD = re.compile(r"[\x00-\x1f\x7f/\\:]")


def safe_name(filename: str) -> str:
    base = re.split(r"[/\\]", filename)[-1]
    base = _BAD.sub("", base).lstrip(". ").strip()
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    stem = stem.strip()[:100] or "foto"
    return f"{stem}.{ext.lower()}" if ext else stem


def _unique(photos_dir: Path, name: str) -> Path:
    stem, dot, ext = name.rpartition(".")
    candidate = photos_dir / name
    n = 2
    while candidate.exists():
        candidate = photos_dir / f"{stem}-{n}{dot}{ext}"
        n += 1
    return candidate


def save_upload(photos_dir: Path, filename: str, data: bytes) -> Path:
    name = safe_name(filename)
    if Path(name).suffix.lower() not in PHOTO_EXTENSIONS:
        raise ValueError(f"nepodporovaný typ souboru: {filename}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"soubor je větší než 50 MB: {filename}")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception as exc:
        raise ValueError(f"soubor není čitelný obrázek: {filename}") from exc
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = _unique(photos_dir, name)
    fd, tmp = tempfile.mkstemp(dir=photos_dir, prefix=".upload.")
    try:
        # mkstemp vytváří 0600; Syncthing může běžet pod jiným uživatelem.
        umask = os.umask(0)
        os.umask(umask)
        os.fchmod(fd, 0o666 & ~umask)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.link(tmp, target)  # selže, pokud cíl mezitím vznikl → žádné přepsání
    finally:
        os.unlink(tmp)
    return target
