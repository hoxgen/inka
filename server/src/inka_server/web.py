import hashlib
import io
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps

from .humanize import ago_cs, at_cs, battery_percent
from .library import load_hidden, set_hidden, visible_photos
from .photos import list_photos, order_photos
from .schedule import DEBUG_DURATION_S
from .dither import LABELS as DITHER_LABELS, METHODS as DITHER_METHODS
from .render import _write_atomic, color_stats, preview_cached, preview_png, source_png
from .settings import PANEL_COLORS, Settings, load_settings, save_settings, settings_from_dict
from .state import load_state, save_state
from .uploads import save_upload

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["urlname"] = lambda n: quote(n)
templates.env.filters["stem"] = lambda n: n.rsplit(".", 1)[0]
# Verze statických souborů podle obsahu: po nasazení si prohlížeč nenechá starý JS/CSS.
templates.env.globals["asset_v"] = hashlib.sha256(
    b"".join(p.read_bytes() for p in sorted((HERE / "static").iterdir()))
).hexdigest()[:10]
router = APIRouter()

INTERVALS = [(900, "15 min"), (3600, "1 h"), (10800, "3 h"), (21600, "6 h"), (43200, "12 h"), (86400, "24 h")]
TONE_KEYS = ("brightness", "contrast", "saturation", "gamma", "warmth", "tint")
DITHER_NUM_KEYS = ("dither_strength", "grain")


def _guard(request: Request) -> None:
    # Přes Cloudflare tunel smí jen /api/v1/frame; webové rozhraní je jen pro Tailscale.
    if "cf-connecting-ip" in request.headers:
        raise HTTPException(status_code=404)
    # CSRF: změny smí poslat jen stránka z téhož původu.
    if request.method != "GET" and request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403)


def _ctx(request: Request):
    return request.app.state.cfg, request.app.state.clock, request.app.state.lock


def _photo_or_404(request: Request, name: str) -> Path:
    cfg, _, _ = _ctx(request)
    for p in list_photos(cfg.photos_dir):
        if p.name == name:
            return p
    raise HTTPException(status_code=404)


def _palette(s: Settings) -> list[tuple[int, int, int]]:
    return [s.palette[n] for n, _ in PANEL_COLORS]


def _float(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@router.get("/", response_class=HTMLResponse)
def gallery(request: Request):
    _guard(request)
    cfg, clock, _ = _ctx(request)
    now = clock()
    s = load_settings(cfg.data_dir)
    st = load_state(cfg.data_dir)
    hidden = load_hidden(cfg.data_dir)
    visible = order_photos(visible_photos(cfg.photos_dir, cfg.data_dir), s.order)
    ordered = visible + [p for p in list_photos(cfg.photos_dir) if p.name in hidden]
    photos = [
        {"name": p.name, "index": i + 1, "hidden": p.name in hidden, "current": p.name == st.current_photo}
        for i, p in enumerate(ordered)
    ]
    status = None
    if st.last_seen:
        seen = datetime.fromisoformat(st.last_seen).timestamp()
        next_at = (int(now // s.interval_s) + 1) * s.interval_s
        status = {
            "seen_ago": ago_cs(now - seen),
            "battery": st.battery_pct if st.battery_pct is not None else battery_percent(st.battery_mv),
            "charging": st.charging,
            "usb": st.usb,
            "temp": f"{st.temp_c:.1f}".replace(".", ",") if st.temp_c is not None else None,
            "fw": st.fw,
            "next_at": at_cs(next_at, cfg.tz, now=now),
        }
    names = {p.name for p in ordered}
    debug_active = st.debug_until is not None and now < st.debug_until
    return templates.TemplateResponse(
        request,
        "gallery.html",
        {
            "debug_until": at_cs(st.debug_until, cfg.tz, now=now) if debug_active else None,
            "photos": photos,
            "current": st.current_photo if st.current_photo in names else None,
            "current_hidden": st.current_photo in hidden,
            "pinned": st.pinned if st.pinned in names else None,
            "all_hidden": bool(ordered) and not visible,
            "status": status,
            "counts": {"total": len(ordered), "hidden": len(hidden & names)},
            "aspect": "5 / 3" if s.orientation == "landscape" else "3 / 5",
            "palette": _palette(s),
            "interval_label": dict(INTERVALS).get(s.interval_s, f"{s.interval_s // 60} min"),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, saved: int = 0):
    _guard(request)
    cfg, _, _ = _ctx(request)
    s = load_settings(cfg.data_dir)
    st = load_state(cfg.data_dir)
    names = [p.name for p in visible_photos(cfg.photos_dir, cfg.data_dir)]
    sample = st.current_photo if st.current_photo in names else (names[0] if names else None)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "s": s, "saved": bool(saved), "sample": sample, "intervals": INTERVALS, "palette": _palette(s),
            "dithers": [(m, DITHER_LABELS[m]) for m in DITHER_METHODS],
        },
    )


@router.post("/settings")
async def settings_save(request: Request):
    _guard(request)
    cfg, _, lock = _ctx(request)
    form = await request.form()
    current = load_settings(cfg.data_dir)
    interval = _float(form.get("interval_s"))
    data = {
        "interval_s": int(interval) if interval is not None else 3600,
        "order": form.get("order"),
        "orientation": form.get("orientation"),
        "rotate_180": form.get("rotate_180") == "on",
        "sleep_mode": form.get("sleep_mode"),
        "palette": {k: list(v) for k, v in current.palette.items()},
    }
    for key in TONE_KEYS:
        data[key] = _float(form.get(key))
    # dithering: z formuláře, jinak ponechat uložené (starší formuláře pole nemají)
    data["dither"] = form.get("dither") or current.dither
    for key in DITHER_NUM_KEYS:
        value = _float(form.get(key))
        data[key] = value if value is not None else getattr(current, key)
    with lock:
        save_settings(cfg.data_dir, settings_from_dict(data))
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/upload")
async def upload(request: Request, files: list[UploadFile] = File(...)):
    _guard(request)
    cfg, _, _ = _ctx(request)
    saved, errors = [], []
    for f in files:
        try:
            saved.append(save_upload(cfg.photos_dir, f.filename or "foto", await f.read()).name)
        except ValueError as exc:
            errors.append(str(exc))
    return JSONResponse({"saved": saved, "errors": errors})


def _set_hidden(request: Request, name: str, hidden: bool):
    _guard(request)
    cfg, _, lock = _ctx(request)
    photo = _photo_or_404(request, name)
    with lock:
        set_hidden(cfg.data_dir, photo.name, hidden)
    return RedirectResponse(f"/#p-{quote(photo.name)}", status_code=303)


@router.post("/photo/{name}/hide")
def hide(request: Request, name: str):
    return _set_hidden(request, name, True)


@router.post("/photo/{name}/show")
def show(request: Request, name: str):
    return _set_hidden(request, name, False)


@router.post("/photo/{name}/next")
def make_next(request: Request, name: str):
    _guard(request)
    cfg, _, lock = _ctx(request)
    photo = _photo_or_404(request, name)
    with lock:
        st = load_state(cfg.data_dir)
        st.pinned = photo.name
        save_state(cfg.data_dir, st)
    return RedirectResponse(f"/#p-{quote(photo.name)}", status_code=303)


def _settings_with_overrides(request: Request, s: Settings) -> tuple[Settings, bool]:
    """Nastavení s hodnotami tónu a orientace z query (živý náhled); druhá hodnota říká, zda se něco změnilo."""
    q = request.query_params
    overrides = {k: _float(q[k]) for k in TONE_KEYS + DITHER_NUM_KEYS if k in q}
    for key in ("orientation", "dither"):
        if key in q:
            overrides[key] = q[key]
    if not overrides:
        return s, False
    d = {**s.__dict__, "palette": {k: list(v) for k, v in s.palette.items()}, **overrides}
    return settings_from_dict(d), True


def _safe_next(value) -> str:
    # Jen místní cesta; nikdy jiný původ (open redirect).
    return value if isinstance(value, str) and value.startswith("/") and not value.startswith("//") else "/"


@router.post("/debug")
async def debug_mode(request: Request):
    _guard(request)
    cfg, clock, lock = _ctx(request)
    form = await request.form()
    with lock:
        st = load_state(cfg.data_dir)
        st.debug_until = clock() + DEBUG_DURATION_S if form.get("on") == "1" else None
        save_state(cfg.data_dir, st)
    return RedirectResponse(_safe_next(form.get("next")), status_code=303)


@router.post("/photo/{name}/show-now")
async def show_now(request: Request, name: str):
    _guard(request)
    cfg, clock, lock = _ctx(request)
    photo = _photo_or_404(request, name)
    form = await request.form()
    with lock:
        st = load_state(cfg.data_dir)
        st.pinned = photo.name
        st.debug_until = max(st.debug_until or 0, clock() + DEBUG_DURATION_S)
        save_state(cfg.data_dir, st)
    return RedirectResponse(_safe_next(form.get("next") or f"/#p-{quote(photo.name)}"), status_code=303)


@router.get("/photo/{name}/preview.png")
def preview(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    s, overridden = _settings_with_overrides(request, load_settings(cfg.data_dir))
    if overridden:
        body, cache = preview_png(photo, s), "no-store"
    else:
        body, cache = preview_cached(photo, s, cfg.data_dir / "cache"), "private, max-age=60"
    return Response(body, media_type="image/png", headers={"Cache-Control": cache})


@router.get("/photo/{name}/source.png")
def source(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    s, overridden = _settings_with_overrides(request, load_settings(cfg.data_dir))
    tone = request.query_params.get("tone") == "1"
    cache = "no-store" if overridden or tone else "private, max-age=60"
    return Response(source_png(photo, s, tone), media_type="image/png", headers={"Cache-Control": cache})


@router.get("/photo/{name}/stats.json")
def stats(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    s, _ = _settings_with_overrides(request, load_settings(cfg.data_dir))
    return JSONResponse(color_stats(photo, s), headers={"Cache-Control": "no-store"})


@router.post("/settings/tone")
async def save_tone(request: Request):
    _guard(request)
    cfg, _, lock = _ctx(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    with lock:
        current = load_settings(cfg.data_dir)
        d = {**current.__dict__, "palette": {k: list(v) for k, v in current.palette.items()}}
        for key in TONE_KEYS + DITHER_NUM_KEYS:
            if key in body:
                d[key] = _float(body[key])
        if "dither" in body:
            d["dither"] = body["dither"]
        save_settings(cfg.data_dir, settings_from_dict(d))
    return JSONResponse({"saved": True})


@router.get("/photo/{name}/compare", response_class=HTMLResponse)
def compare(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    saved = load_settings(cfg.data_dir)
    s, _ = _settings_with_overrides(request, saved)  # neuložené posuvníky přenesené z předchozí fotky
    hidden = load_hidden(cfg.data_dir)
    visible = order_photos(visible_photos(cfg.photos_dir, cfg.data_dir), s.order)
    ordered = [p.name for p in visible + [p for p in list_photos(cfg.photos_dir) if p.name in hidden]]
    i = ordered.index(photo.name)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "name": photo.name,
            "position": i + 1,
            "total": len(ordered),
            "prev": ordered[i - 1],
            "next": ordered[(i + 1) % len(ordered)],
            "hidden": photo.name in hidden,
            "s": s,
            "saved": saved,
            "w": 800 if s.orientation == "landscape" else 480,
            "h": 480 if s.orientation == "landscape" else 800,
            "palette": _palette(s),
            "palette_named": [(n, s.palette[n]) for n, _ in PANEL_COLORS],
            "dithers": [(m, DITHER_LABELS[m]) for m in DITHER_METHODS],
        },
    )


@router.get("/photo/{name}/variants", response_class=HTMLResponse)
def variants(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    s = load_settings(cfg.data_dir)
    # neuložené hodnoty tónu a síly z porovnání se přenesou do všech variant
    keep = {k: v for k, v in request.query_params.items() if k in TONE_KEYS + DITHER_NUM_KEYS}
    extra = "".join(f"&{k}={quote(v)}" for k, v in keep.items())
    return templates.TemplateResponse(
        request,
        "variants.html",
        {
            "name": photo.name,
            "w": 800 if s.orientation == "landscape" else 480,
            "h": 480 if s.orientation == "landscape" else 800,
            "variants": [(m, DITHER_LABELS[m], m == s.dither) for m in DITHER_METHODS],
            "extra": extra,
            "back": f"/photo/{quote(photo.name)}/compare" + (f"?{extra[1:]}" if extra else ""),
            "palette": _palette(s),
        },
    )


@router.get("/navod", response_class=HTMLResponse)
def guide(request: Request):
    _guard(request)
    cfg, _, _ = _ctx(request)
    return templates.TemplateResponse(request, "guide.html", {"palette": _palette(load_settings(cfg.data_dir))})


@router.get("/photo/{name}/original.jpg")
def original(request: Request, name: str):
    _guard(request)
    cfg, _, _ = _ctx(request)
    photo = _photo_or_404(request, name)
    digest = hashlib.sha256(photo.read_bytes()).hexdigest()[:16]
    target = cfg.data_dir / "cache" / f"orig-{digest}.jpg"
    if not target.is_file():
        with Image.open(photo) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
        _write_atomic(target, buf.getvalue())
    return Response(target.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
