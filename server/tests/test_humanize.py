from datetime import datetime
from zoneinfo import ZoneInfo

from inka_server.humanize import ago_cs, at_cs, battery_percent


def test_ago_cs():
    assert ago_cs(5) == "právě teď"
    assert ago_cs(4 * 60) == "před 4 min"
    assert ago_cs(2 * 3600 + 10) == "před 2 h"
    assert ago_cs(26 * 3600) == "před 1 dnem"
    assert ago_cs(3 * 86400) == "před 3 dny"


def test_battery_percent():
    assert battery_percent(None) is None
    assert battery_percent(3300) == 0
    assert battery_percent(4150) == 100
    assert battery_percent(4300) == 100
    assert battery_percent(3725) == 50


def test_at_cs_today_and_other_day():
    tz = "Europe/Prague"
    now = datetime(2026, 10, 12, 13, 0, tzinfo=ZoneInfo(tz)).timestamp()
    assert at_cs(now + 3600, tz, now=now) == "14:00"
    assert at_cs(now + 86400, tz, now=now) == "13. 10. 13:00"
