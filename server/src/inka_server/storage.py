import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        log.warning("ignoring %s: top level is not an object", path)
        return None
    return data


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            # ensure_ascii: názvy souborů mohou obsahovat surrogate escape (neplatné UTF-8)
            json.dump(data, f, indent=2, ensure_ascii=True)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
