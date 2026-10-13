import hashlib
import hmac
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request, Response

from .library import visible_photos
from .photos import order_photos
from .render import render_cached
from .schedule import DEBUG_SLEEP_S, LIGHT_MAX_SLEEP_S, sleep_seconds, slot_index
from .settings import load_settings
from .state import load_state, save_state

log = logging.getLogger("inka_server")


@dataclass
class Config:
    photos_dir: Path
    data_dir: Path
    device_token: str
    tz: str = "Europe/Prague"


def _authorized(request: Request, token: str) -> bool:
    header = request.headers.get("authorization", "")
    expected = f"Bearer {token}"
    return hmac.compare_digest(header.encode(), expected.encode())


def _float_in(value: str | None, lo: float, hi: float) -> float | None:
    try:
        f = float(value) if value is not None else None
    except ValueError:
        return None
    return f if f is not None and math.isfinite(f) and lo <= f <= hi else None


def _bool_or_none(value: str | None) -> bool | None:
    return {"1": True, "0": False}.get(value)


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def create_app(cfg: Config, clock: Callable[[], float] = time.time) -> FastAPI:
    app = FastAPI(title="inka", docs_url=None, redoc_url=None, openapi_url=None)
    cache_dir = cfg.data_dir / "cache"
    app.state.cfg = cfg
    app.state.clock = clock
    app.state.lock = threading.Lock()

    @app.get("/api/v1/frame")
    def frame(request: Request) -> Response:
        if not _authorized(request, cfg.device_token):
            return Response(status_code=401)

        with app.state.lock:
            now = clock()
            settings = load_settings(cfg.data_dir)
            state = load_state(cfg.data_dir)
            q = request.query_params
            wake = q.get("wake")
            if wake == "button" and not state.pinned:
                state.offset += 1
            state.last_seen = datetime.fromtimestamp(now, timezone.utc).isoformat()
            state.battery_mv = _int_or_none(q.get("battery_mv"))
            pct = _int_or_none(q.get("battery_pct"))
            state.battery_pct = None if pct is None else max(0, min(100, pct))
            state.charging = _bool_or_none(q.get("charging"))
            state.temp_c = _float_in(q.get("temp_c"), -40, 85)
            state.usb = _bool_or_none(q.get("usb"))
            # Automaticky: z USB lehký spánek, z baterie hluboký. Bez hlášení (starší firmware) bezpečně lehký.
            mode = settings.sleep_mode
            if mode == "auto":
                mode = "deep" if state.usb is False else "light"
            state.fw = q.get("fw")
            state.wake = wake

            if state.debug_until is not None and now >= state.debug_until:
                state.debug_until = None
            if state.debug_until is not None:
                sleep = DEBUG_SLEEP_S
            else:
                sleep = sleep_seconds(now, settings.interval_s)
                if mode == "light":
                    sleep = min(sleep, LIGHT_MAX_SLEEP_S)
            headers = {
                "X-Inka-Sleep-Seconds": str(sleep),
                "X-Inka-Sleep-Mode": mode,
                # firmware podle toho kreslí štítek OFF do pravého dolního rohu pohledu
                "X-Inka-View": f"{settings.orientation};{'rot180' if settings.rotate_180 else 'rot0'}",
                "X-Inka-Interval-Seconds": str(settings.interval_s),
                "Cache-Control": "no-store",
            }

            photos = order_photos(visible_photos(cfg.photos_dir, cfg.data_dir), settings.order)
            body = None
            names = [p.name for p in photos]
            if state.pinned in names:
                # Připíchnutá fotka platí pro aktuální slot, ať se rámeček ozve kdykoli.
                state.offset = (names.index(state.pinned) - int(now // settings.interval_s)) % len(names)
            state.pinned = None
            if photos:
                start = slot_index(now, settings.interval_s, len(photos), state.offset)
                for k in range(len(photos)):
                    photo = photos[(start + k) % len(photos)]
                    try:
                        body = render_cached(photo, settings, cache_dir)
                    except Exception as exc:  # poškozená nebo nedokončená fotka
                        log.warning("skipping %s: %s", photo.name, exc)
                        continue
                    state.current_photo = photo.name
                    break

            save_state(cfg.data_dir, state)
        if body is None:
            log.info("frame: no photo, wake=%s battery=%s", wake, state.battery_mv)
            return Response(status_code=204, headers=headers)

        etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
        headers["ETag"] = etag
        if request.headers.get("if-none-match") == etag:
            log.info("frame: 304 %s wake=%s", state.current_photo, wake)
            return Response(status_code=304, headers=headers)
        log.info("frame: 200 %s wake=%s battery=%s", state.current_photo, wake, state.battery_mv)
        return Response(content=body, media_type="application/octet-stream", headers=headers)

    from fastapi.staticfiles import StaticFiles

    from . import web

    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app
