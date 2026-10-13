from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .storage import read_json, write_json_atomic


@dataclass
class DeviceState:
    offset: int = 0
    last_seen: str | None = None
    battery_mv: int | None = None
    battery_pct: int | None = None
    charging: bool | None = None
    temp_c: float | None = None
    usb: bool | None = None  # rámeček napájený z USB
    fw: str | None = None
    wake: str | None = None
    current_photo: str | None = None
    debug_until: float | None = None  # ladicí režim aktivní do (epoch s)
    pinned: str | None = None  # „Další na řadě“ z webu; použije se při nejbližším dotazu rámečku


def load_state(data_dir: Path) -> DeviceState:
    data = read_json(data_dir / "state.json") or {}
    known = {f.name for f in fields(DeviceState)}
    st = DeviceState(**{k: v for k, v in data.items() if k in known})
    if not isinstance(st.offset, int):
        st.offset = 0
    return st


def save_state(data_dir: Path, st: DeviceState) -> None:
    write_json_atomic(data_dir / "state.json", asdict(st))
