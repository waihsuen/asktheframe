# displayBuses.py
import os
import sys
import logging
import math
from functools import lru_cache
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Optional, TypedDict
import requests
from requests.adapters import HTTPAdapter, Retry
from PIL import Image, ImageDraw, ImageFont

# ---------- constants / configuration ----------
ASIA_SG = ZoneInfo("Asia/Singapore")
WIDTH, HEIGHT = 800, 480

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PIC_DIR = os.path.join(BASE_DIR, "images")
FONT_DIR = os.path.join(BASE_DIR, "libraries", "fonts")

if os.path.exists(FONT_DIR):
    sys.path.append(FONT_DIR)

# Layout metrics (override via ENV if you want to tweak without code changes)
PILL_H = int(os.getenv("PILL_H", "48"))
PILL_MAX_W = int(os.getenv("PILL_MAX_W", "300"))
PILL_TEXT_NUDGE_X = int(os.getenv("PILL_TEXT_NUDGE_X", "0"))
PILL_TEXT_NUDGE_Y = int(os.getenv("PILL_TEXT_NUDGE_Y", "0"))
COL_MARGIN = int(os.getenv("COL_MARGIN", "24"))
COL_GAP = int(os.getenv("COL_GAP", "18"))
BADGE_D = int(os.getenv("BADGE_D", "64"))
BADGE_TEXT_NUDGE_X = int(os.getenv("BADGE_TEXT_NUDGE_X", "0"))
BADGE_TEXT_NUDGE_Y = int(os.getenv("BADGE_TEXT_NUDGE_Y", "-4"))
ETA_GAP_FROM_BADGE = int(os.getenv("ETA_GAP_FROM_BADGE", "24"))
L1_NUDGE_X = int(os.getenv("L1_NUDGE_X", "0"))
L1_NUDGE_Y = int(os.getenv("L1_NUDGE_Y", "-6"))
L2_L3_NUDGE_X = int(os.getenv("L2_L3_NUDGE_X", "4"))
L2_NUDGE_Y = int(os.getenv("L2_NUDGE_Y", "36"))
L3_NUDGE_Y = int(os.getenv("L3_NUDGE_Y", "64"))
ROW_ADVANCE = int(os.getenv("ROW_ADVANCE", "140"))
TOP_Y = int(os.getenv("TOP_Y", "64"))
API_URL = os.getenv("API_URL", "")


# ---------- font helpers (cached) ----------
@lru_cache(maxsize=None)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=None)
def _load_font_cached(libdir: str, size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates: List[str] = []
    if mono:
        candidates += [os.path.join(libdir, "Roboto_Mono", "static", "RobotoMono-Regular.ttf")]
    elif bold:
        candidates += [os.path.join(libdir, "Roboto", "static", "Roboto-Bold.ttf")]
    # fallbacks
    candidates += [
        os.path.join(libdir, "Roboto", "static", "Roboto-VariableFont_wdth,wght.ttf"),
        os.path.join(libdir, "Roboto", "static", "Roboto-Regular.ttf"),
        os.path.join(libdir, "OpenSans-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            return _font(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _load_font(libdir: str, size: int) -> ImageFont.FreeTypeFont:
    return _load_font_cached(libdir, size, bold=False, mono=False)


def _load_font_bold(libdir: str, size: int) -> ImageFont.FreeTypeFont:
    return _load_font_cached(libdir, size, bold=True, mono=False)


def _load_font_mono(libdir: str, size: int) -> ImageFont.FreeTypeFont:
    return _load_font_cached(libdir, size, bold=False, mono=True)


# ---------- formatting helpers ----------
def _fmt_eta(v: Optional[int]) -> str:
    if v is None:
        return "—"
    if v < 1:
        return "Arriving"
    unit = "min" if v == 1 else "mins"
    return f"{v} {unit}"


def _clamp_minutes_floor(delta_minutes: Optional[float]) -> Optional[int]:
    if delta_minutes is None:
        return None
    try:
        return max(0, math.floor(delta_minutes))
    except Exception:
        return None


def fmt_all_etas(etas: List[Optional[int]]) -> Tuple[str, str, str]:
    """Return (l1, l2, l3) strings with zero-padding applied to l2/l3 only."""
    v1 = etas[0] if len(etas) > 0 else None
    v2 = etas[1] if len(etas) > 1 else None
    v3 = etas[2] if len(etas) > 2 else None

    l1 = _fmt_eta(v1)
    if isinstance(v2, int) and v2 >= 1:
        unit = "min" if v2 == 1 else "mins"
        l2 = f"{v2:02} {unit}"
    else:
        l2 = _fmt_eta(v2)

    if isinstance(v3, int) and v3 >= 1:
        unit = "min" if v3 == 1 else "mins"
        l3 = f"{v3:02} {unit}"
    else:
        l3 = _fmt_eta(v3)

    return l1, l2, l3


def draw_centered_text(draw: ImageDraw.ImageDraw, cx: int, cy: int, text: str, font: ImageFont.FreeTypeFont, *, fill: int = 0, nudge_x: int = 0, nudge_y: int = 0) -> None:
    """Center text on (cx, cy) and allow pixel nudges."""
    tb = draw.textbbox((0, 0), text, font=font)
    w = tb[2] - tb[0]
    h = tb[3] - tb[1]
    x = int(cx - w / 2 + nudge_x)
    y = int(cy - h / 2 + nudge_y)
    draw.text((x, y), text, font=font, fill=fill)


# ---------- drawing ----------
def render_stop_column(draw: ImageDraw.ImageDraw, stop_name: str, routes: List[Tuple[str, List[int]]], col_w: int, x0: int, top_y: int = TOP_Y) -> None:
    if not routes:
        return  # nothing to draw for this stop

    # Stop-name pill
    pill_h = PILL_H
    pill_w = min(col_w - 12, PILL_MAX_W)
    pill_x = x0 + (col_w - pill_w) // 2
    pill_y = top_y
    title_font = _load_font(FONT_DIR, 22)

    # draw pill
    draw.rounded_rectangle((pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), radius=12, fill=0)

    # center of pill
    cx = pill_x + pill_w // 2
    cy = pill_y + pill_h // 2
    draw_centered_text(draw, cx, cy, stop_name, title_font, fill=255, nudge_x=PILL_TEXT_NUDGE_X, nudge_y=PILL_TEXT_NUDGE_Y)

    # route rows
    y = top_y + pill_h + 48
    badge_font = _load_font_bold(FONT_DIR, 24)
    eta_big = _load_font_bold(FONT_DIR, 32)
    eta_small = _load_font_mono(FONT_DIR, 24)

    for svc, etas in routes[:2]:  # only draw up to 2 actual services
        # circular route badge
        d = BADGE_D
        cx = x0 + 8 + d // 2
        cy = y + d // 2
        draw.ellipse((cx - d // 2, cy - d // 2, cx + d // 2, cy + d // 2), fill=0)

        rb = draw.textbbox((0, 0), svc, font=badge_font)
        text_w = rb[2] - rb[0]
        text_h = rb[3] - rb[1]
        draw.text((cx - text_w / 2 + BADGE_TEXT_NUDGE_X, cy - text_h / 2 + BADGE_TEXT_NUDGE_Y), svc, font=badge_font, fill=255)

        text_x = x0 + 8 + d + ETA_GAP_FROM_BADGE

        # Format ETAs (l2/l3 zero-padded)
        l1, l2, l3 = fmt_all_etas(etas)

        # draw l1 (main ETA)
        y_l1 = y + L1_NUDGE_Y
        draw.text((text_x + L1_NUDGE_X, y_l1), l1, font=eta_big, fill=0)

        # l2 / l3
        if l2 != "—":
            draw.text((text_x + L2_L3_NUDGE_X, y_l1 + L2_NUDGE_Y), l2, font=eta_small, fill=0)
        if l3 != "—":
            draw.text((text_x + L2_L3_NUDGE_X, y_l1 + L3_NUDGE_Y), l3, font=eta_small, fill=0)

        y += ROW_ADVANCE


class StopPayload(TypedDict):
    name: str
    routes: List[Tuple[str, List[int]]]


def render_bus_screen(epd, stops_payload: List[StopPayload]) -> Image.Image:
    """Build a 1-bit image using three stop columns."""
    img = Image.new("1", (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(img)

    # background
    # draw.rectangle((0, 0, epd.width, epd.height), fill=255)

    col_w = (epd.width - 2 * COL_MARGIN - 2 * COL_GAP) // 3
    for i in range(3):
        x0 = COL_MARGIN + i * (col_w + COL_GAP)
        stop = stops_payload[i] if i < len(stops_payload) else {"name": "—", "routes": []}
        render_stop_column(draw, stop.get("name", "—"), stop.get("routes", []), col_w, x0, top_y=TOP_Y)
    return img


# ---------- API (session + retry) ----------
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
    ),
)


def get_bus_arrival(bus_stop_code: str) -> List[Tuple[str, List[int]]]:
    api_key = os.getenv("API_KEY")
    if not api_key:
        logging.error("Missing API_KEY")
        return []

    url = f"{API_URL}/busarrival?BusStopCode={bus_stop_code}"
    headers = {"x-api-key": api_key, "accept": "application/json"}

    try:
        r = _session.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logging.error(f"[get_bus_arrival] Network/API error: {e}")
        return []
    except ValueError:
        logging.error("[get_bus_arrival] Invalid JSON")
        return []

    services = data.get("Services", [])
    now = datetime.now(ASIA_SG)
    out: List[Tuple[str, List[Optional[int]]]] = []

    for svc in services:
        svc_no = svc.get("ServiceNo", "?")
        etas: List[Optional[int]] = []
        for key in ("NextBus", "NextBus2", "NextBus3"):
            item = svc.get(key) or {}
            eta = item.get("EstimatedArrival")
            if not eta:
                etas.append(None)
                continue
            try:
                eta_dt = datetime.strptime(eta, "%Y-%m-%dT%H:%M:%S%z")
                diff_min = (eta_dt - now).total_seconds() / 60.0
                etas.append(_clamp_minutes_floor(diff_min))
            except Exception:
                etas.append(None)

        clean = [e for e in etas if e is not None]
        if clean:
            # keep only first three values (already)
            out.append((svc_no, clean[:3]))

    out.sort(key=lambda t: (t[1][0] if t[1] else 9999))
    # Type: List[Tuple[str, List[int]]] – cast by filtering None above
    return [(svc, list(map(int, mins))) for svc, mins in out]  # type: ignore[return-value]


# ---------- main entry ----------
def show_bus_arrivals(epd) -> None:
    # names
    name_a = os.getenv("STOP_NAME_A", "Stop A")
    name_b = os.getenv("STOP_NAME_B", "Stop B")
    name_c = os.getenv("STOP_NAME_C", "Stop C")
    # codes
    code_a = os.getenv("STOP_CODE_A")
    code_b = os.getenv("STOP_CODE_B")
    code_c = os.getenv("STOP_CODE_C")

    if not (code_a or code_b or code_c):
        logging.error("Missing STOP_CODE_A/B/C")
        return

    route_a = get_bus_arrival(code_a) if code_a else []
    route_b = get_bus_arrival(code_b) if code_b else []
    route_c = get_bus_arrival(code_c) if code_c else []

    # If everything is empty, skip the EPD update to avoid unnecessary refresh
    if not (route_a or route_b or route_c):
        logging.info("No route info — skipping render")
        return

    stops_payload: List[StopPayload] = [
        {"name": name_a, "routes": route_a},
        {"name": name_b, "routes": route_b},
        {"name": name_c, "routes": route_c},
    ]

    logging.debug("Stops payload: %s", stops_payload)

    img = render_bus_screen(epd, stops_payload)
    epd.display(epd.getbuffer(img))
