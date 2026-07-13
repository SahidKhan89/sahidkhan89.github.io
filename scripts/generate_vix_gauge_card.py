#!/usr/bin/env python3
"""
generate_vix_gauge_card.py — Render the current VIX level as a branded
"fear gauge" speedometer card image.

Pulls the live ^VIX quote from the StockScore backend's /market-ticker
endpoint (same feed that drives the Flutter app's scrolling market ticker
banner — see routes/market_ticker.py in the stock_score backend repo) and
renders a semicircle gauge with a smooth colour gradient across five bands
(Calm / Normal / Elevated / Panic / Extreme), a needle at the current
reading, and the price + day change below it. Saves to
images/vix-gauge/<date>.png and writes a manifest for the posting step
(scripts/post_vix_gauge.py).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) to label a specific date, e.g.
for local testing — the underlying reading is always whatever the backend
currently has cached (it doesn't accept a date param, it's a live quote).
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — see the same note in generate_ratings_card.py / generate_dividends_card.py.
BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT        = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT / "images" / "vix-gauge"
MANIFEST    = Path(__file__).parent / "_vix_gauge_manifest.json"

VMIN, VMAX = 0, 60   # gauge scale — VIX readings above 60 are vanishingly rare (2008/2020 spikes);
                     # values beyond this just pin the needle at max rather than clipping the read

EXTREME = (196, 32, 64)   # deeper crimson than C["red"] — a distinct "beyond panic" tier

# (band floor, band ceiling, colour, label) — ascending, covering VMIN..VMAX.
# These are a widely-cited market-commentary convention (VIX's long-run
# average sits ~19-20), not an official CBOE-defined banding.
ZONES = [
    (0,  12, ss.C["teal"],  "Calm"),
    (12, 20, ss.C["green"], "Normal"),
    (20, 30, ss.C["amber"], "Elevated"),
    (30, 40, ss.C["red"],   "Panic"),
    (40, 60, EXTREME,       "Extreme"),
]
BOUNDARIES = sorted({z[0] for z in ZONES} | {ZONES[-1][1]})   # 0,12,20,30,40,60
GRADIENT_STOPS = [(z[0], z[2]) for z in ZONES] + [(ZONES[-1][1], ZONES[-1][2])]

CX, R        = ss.CW // 2, 430   # gauge pivot x, outer radius
ARC_WIDTH    = 84
NEEDLE_LEN   = R - 70
NEEDLE_BASE_W = 24
HUB_R        = 26

SS           = 3     # supersampling factor — PIL's ImageDraw has no anti-aliasing,
                     # so arcs/ticks/needle are drawn this many times larger, then
                     # downscaled with LANCZOS to get smooth edges instead of jagged ones
TILE_MARGIN_X = 110   # local-tile clearance either side of the pivot, for boundary labels
TILE_MARGIN_TOP = 110 # clearance above the arc's topmost point, for the top boundary label
TILE_MARGIN_BOT = 40   # clearance below the pivot, for the hub


def fetch_vix() -> dict | None:
    r = requests.get(f"{BACKEND_URL}/market-ticker", timeout=20)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error: {data['error']}")
        return None
    for item in data.get("items", []):
        if item.get("symbol") == "^VIX":
            return item
    return None


def _value_to_angle(value: float) -> float:
    f = max(0.0, min(1.0, (value - VMIN) / (VMAX - VMIN)))
    return 180 + f * 180


def _zone_for(value: float):
    for lo, hi, color, label in ZONES:
        if value < hi or hi == VMAX:
            return color, label
    return ZONES[-1][2], ZONES[-1][3]


def _polar(cx, cy, radius, angle_deg):
    rad = math.radians(angle_deg)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def _lerp_color(c0, c1, t):
    return tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))


def _gradient_color(value: float):
    for (v0, c0), (v1, c1) in zip(GRADIENT_STOPS, GRADIENT_STOPS[1:]):
        if value <= v1:
            t = 0.0 if v1 == v0 else (value - v0) / (v1 - v0)
            return _lerp_color(c0, c1, t)
    return GRADIENT_STOPS[-1][1]


def _draw_needle(draw, cx, cy, angle_deg, length, base_w, color):
    rad  = math.radians(angle_deg)
    perp = rad + math.pi / 2
    tip  = (cx + length * math.cos(rad), cy + length * math.sin(rad))
    b1 = (cx + base_w * math.cos(perp), cy + base_w * math.sin(perp))
    b2 = (cx - base_w * math.cos(perp), cy - base_w * math.sin(perp))
    draw.polygon([tip, b1, b2], fill=color)


def _draw_gradient_arc(draw, bbox, steps: int = 140):
    for i in range(steps):
        v0 = VMIN + (VMAX - VMIN) * i / steps
        v1 = VMIN + (VMAX - VMIN) * (i + 1) / steps
        a0 = _value_to_angle(v0)
        a1 = _value_to_angle(v1) + 0.75   # slight overlap — hides seams between slices
        color = _gradient_color((v0 + v1) / 2)
        draw.arc(bbox, a0, a1, fill=color, width=ARC_WIDTH)


def render_gauge_tile(value: float):
    """Draws the arc/ticks/needle/hub at SS-times resolution on a transparent
    tile, then downsamples with LANCZOS for anti-aliased edges — PIL's
    ImageDraw has no anti-aliasing of its own, so at native resolution
    diagonal ticks and the needle come out visibly jagged.

    Returns (tile, pivot_x, pivot_y, zone_color, zone_label). pivot_x/y are
    the tile-local coordinates of the gauge's pivot, so the caller can paste
    the tile aligned to wherever the pivot needs to land on the main canvas.
    """
    tile_w = (R + TILE_MARGIN_X) * 2
    tile_h = R + TILE_MARGIN_TOP + TILE_MARGIN_BOT
    pivot_x, pivot_y = tile_w / 2, tile_h - TILE_MARGIN_BOT

    hi = Image.new("RGBA", (tile_w * SS, tile_h * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hi)
    cx, cy = pivot_x * SS, pivot_y * SS
    r      = R * SS
    half_w = (ARC_WIDTH * SS) / 2
    bbox   = [cx - r, cy - r, cx + r, cy + r]

    for i in range(140):
        v0 = VMIN + (VMAX - VMIN) * i / 140
        v1 = VMIN + (VMAX - VMIN) * (i + 1) / 140
        a0 = _value_to_angle(v0)
        a1 = _value_to_angle(v1) + 0.75   # slight overlap — hides seams between slices
        draw.arc(bbox, a0, a1, fill=_gradient_color((v0 + v1) / 2), width=int(half_w * 2))

    # boundary value labels — no tick lines (they read as visual noise against
    # the gradient at this thickness); the numbers alone plus the legend below
    # are enough to place the needle on the scale
    label_font = ss.font(True, 26 * SS)
    for v in BOUNDARIES:
        ang = _value_to_angle(v)
        tx, ty = _polar(cx, cy, r + half_w + 2 * SS, ang)
        draw.text((tx, ty), str(v), font=label_font, fill=ss.C["white"], anchor="mm")

    zone_color, zone_label = _zone_for(value)
    angle = _value_to_angle(value)
    _draw_needle(draw, cx, cy, angle, NEEDLE_LEN * SS, NEEDLE_BASE_W * SS, ss.C["white"])

    # two-tone hub — dark outer ring + light bolt-like centre, echoing a
    # real gauge's metal pivot rather than a flat disc
    hub_r = HUB_R * SS
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
                 fill=ss.C["card"], outline=ss.C["bg"], width=3 * SS)
    inner_r = hub_r * 0.5
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                 fill=ss.C["white"])

    tile = hi.resize((tile_w, tile_h), Image.LANCZOS)
    return tile, pivot_x, pivot_y, zone_color, zone_label


def _draw_zone_legend(img, draw, y):
    margin  = 60
    w_total = ss.CW - 2 * margin
    seg_w   = w_total / len(ZONES)
    bar_h   = 18
    for i, (lo, hi, color, label) in enumerate(ZONES):
        x = margin + i * seg_w
        cx = x + (seg_w - 10) / 2
        draw.rounded_rectangle([x, y, x + seg_w - 10, y + bar_h], radius=6, fill=color)
        draw.text((cx, y + bar_h + 20), label, font=ss.font(True, 21), fill=color, anchor="mm")
        range_text = f"{lo}–{hi}" if hi != VMAX else f"{lo}+"
        draw.text((cx, y + bar_h + 46), range_text, font=ss.font(False, 16), fill=ss.C["grey"], anchor="mm")
    return y + bar_h + 66


def render_card(human_date: str, price: float, change_pct: float):
    img  = ss.new_canvas()
    draw = ImageDraw.Draw(img)
    y0   = ss.draw_header(img, f"VIX Fear Gauge  ·  {human_date}", ss.load_brand_logo())

    title_font = ss.font(True, 32)
    draw.text((ss.CW / 2, y0 + 45), "Market Volatility Index", font=title_font,
               fill=ss.C["white"], anchor="mm")

    gauge_top = y0 + 180
    cy = gauge_top + R
    tile, pivot_x, pivot_y, zone_color, zone_label = render_gauge_tile(price)
    img.paste(tile, (int(CX - pivot_x), int(cy - pivot_y)), tile)

    value_y = cy + 85
    draw.text((ss.CW / 2, value_y), f"{price:.2f}", font=ss.font(True, 112),
               fill=ss.C["white"], anchor="mm")

    # inverted vs. a normal price move — for VIX, down is calmer (good/green)
    # and up is more fear (bad/red), the opposite of a stock ticking up
    sign = "+" if change_pct >= 0 else ""
    change_color = ss.C["red"] if change_pct >= 0 else ss.C["green"]
    draw.text((ss.CW / 2, value_y + 78), f"{sign}{change_pct:.2f}%", font=ss.font(True, 30),
               fill=change_color, anchor="mm")

    badge_y = value_y + 150
    badge_font = ss.font(True, 32)
    badge_text = zone_label.upper()
    tb = draw.textbbox((0, 0), badge_text, font=badge_font)
    pad_x, pad_y = 30, 16
    bw, bh = (tb[2] - tb[0]) + pad_x * 2, (tb[3] - tb[1]) + pad_y * 2
    bx0 = ss.CW / 2 - bw / 2
    by0 = badge_y - bh / 2
    draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=bh / 2,
                            outline=zone_color, width=3, fill=ss.C["card"])
    draw.text((ss.CW / 2, badge_y), badge_text, font=badge_font, fill=zone_color, anchor="mm")

    _draw_zone_legend(img, draw, badge_y + 80)

    ss.draw_footer(img)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD label override, defaults to the last market day")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    if forced:
        date_obj = datetime.strptime(forced, "%Y-%m-%d").date()
    else:
        date_obj = ss.last_market_day(datetime.now(timezone.utc).date())
    date_str   = date_obj.strftime("%Y-%m-%d")
    human_date = date_obj.strftime("%a %d %b")

    print("Fetching VIX reading...")
    vix = fetch_vix()

    if not vix:
        print("No VIX reading available — nothing to render.")
        MANIFEST.write_text(json.dumps(None) + "\n")
        return

    price      = vix["price"]
    change_pct = vix.get("change_pct", 0.0)
    print(f"  VIX {price:.2f} ({change_pct:+.2f}%)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"
    img = render_card(human_date, price, change_pct)
    img.save(out_path)
    print(f"  chart saved → {out_path.relative_to(ROOT)}")

    _, zone_label = _zone_for(price)
    manifest = {
        "date":         date_str,
        "human_date":   human_date,
        "price":        price,
        "change_pct":   change_pct,
        "zone_label":   zone_label,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
