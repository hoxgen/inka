import time
from datetime import datetime
from zoneinfo import ZoneInfo


def ago_cs(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return "právě teď"
    if s < 3600:
        return f"před {s // 60} min"
    if s < 86400:
        return f"před {s // 3600} h"
    days = s // 86400
    return "před 1 dnem" if days == 1 else f"před {days} dny"


def battery_percent(mv: int | None) -> int | None:
    if mv is None:
        return None
    return max(0, min(100, round((mv - 3300) * 100 / 850)))


def at_cs(ts: float, tz: str, now: float | None = None) -> str:
    zone = ZoneInfo(tz)
    when = datetime.fromtimestamp(ts, zone)
    today = datetime.fromtimestamp(time.time() if now is None else now, zone).date()
    if when.date() == today:
        return when.strftime("%H:%M")
    return f"{when.day}. {when.month}. {when:%H:%M}"
