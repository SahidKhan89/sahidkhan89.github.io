#!/usr/bin/env python3
"""
generate_sector_heatmap_card.py — Render today's S&P sector performance as a
branded treemap heatmap card image.

Pulls day % change for all 11 S&P sectors plus their sub-industries from the
StockScore backend (ETF proxies, same endpoint the Flutter app's heatmap
share page uses) and renders a nested, color-graded treemap with a legend —
matching the look of lib/heatmap_share_page.dart. Saves to
images/sector-heatmap/<date>.png and writes a manifest for the posting step
(scripts/post_sector_heatmap.py).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) to label a specific date, e.g. for
local testing — the underlying data is always whatever the backend currently
has cached (it doesn't accept a date param).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — see the same note in generate_ratings_card.py / generate_dividends_card.py.
BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT        = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT / "images" / "sector-heatmap"
MANIFEST    = Path(__file__).parent / "_sector_heatmap_manifest.json"

OUTER_COLS   = 3
OUTER_MARGIN = 40
OUTER_GAP    = 16
HEADER_H     = 42
CELL_ROW_H   = 74
CELL_GAP     = 4
BLOCK_GAP_Y  = 16

NEUTRAL          = (70, 70, 70)   # true grey "no signal" — distinct from the brand navy
HEAT_CAP         = 3.0            # |% change| at which color saturation maxes out
BLEND_MAX_CELL   = 0.85
BLEND_MAX_HEADER = 0.35

LEGEND_STOPS = [-3, -2, -1, 0, 1, 2, 3]
LEGEND_LABELS = ["≤-3%", "-2%", "-1%", "0%", "+1%", "+2%", "≥+3%"]

# The backend's labels are pre-abbreviated for a narrower widget — expand
# them back out where our bigger cells have room, falling back to the short
# form only where the full name genuinely won't fit.
FULL_NAME = {
    "Cons. Discr.": "Consumer Discretionary",
    "Cons. Staples": "Consumer Staples",
    "Comm. Svcs": "Communication Services",
    "Semis": "Semiconductors",
    "Med Dev": "Medical Devices",
    "Mgd Care": "Managed Care",
    "Cap Mkts": "Capital Markets",
    "Homebldrs": "Homebuilders",
    "E-Comm": "E-Commerce",
    "Oil Svcs": "Oil Services",
    "Clean Enrg": "Clean Energy",
    "Construct": "Construction",
}


def _best_label(draw, short: str, fnt, max_w: int, max_lines: int = 1) -> list:
    """Prefers the full-length name, wrapped up to `max_lines`, but only if it
    fits without ellipsizing — otherwise falls back to the short label.
    """
    full  = FULL_NAME.get(short, short)
    lines = ss.wrap_text(draw, full, fnt, max_w, max_lines)
    if "…" not in "".join(lines):
        return lines
    return ss.wrap_text(draw, short, fnt, max_w, max_lines)


def fetch_heatmap() -> list:
    r = requests.get(f"{BACKEND_URL}/sector-heatmap", timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error: {data['error']}")
        return []
    return data.get("sectors", [])


def _heat_color(pct: float, blend_max: float):
    t      = max(-1.0, min(1.0, pct / HEAT_CAP))
    target = ss.C["green"] if t >= 0 else ss.C["red"]
    blend  = min(abs(t), 1.0) * blend_max
    return tuple(int(NEUTRAL[i] + (target[i] - NEUTRAL[i]) * blend) for i in range(3))


def _sector_block_height(n_industries: int) -> int:
    rows = (n_industries + 1) // 2
    return HEADER_H + CELL_GAP + rows * CELL_ROW_H + (rows - 1) * CELL_GAP


def _draw_cell(draw, x, y, w, h, name, pct):
    color = _heat_color(pct, BLEND_MAX_CELL)
    draw.rectangle([x, y, x + w, y + h], fill=color)
    cx = x + w / 2

    name_font = ss.font(False, 14)
    lines     = _best_label(draw, name, name_font, w - 10, max_lines=2)
    line_h    = 17
    start_y   = y + h * 0.30 - (len(lines) - 1) * line_h / 2
    for i, line in enumerate(lines):
        draw.text((cx, start_y + i * line_h), line, font=name_font,
                   fill=(235, 238, 242), anchor="mm")

    sign = "+" if pct >= 0 else ""
    draw.text((cx, y + h * 0.76), f"{sign}{pct:.2f}%", font=ss.font(True, 18),
               fill=ss.C["white"], anchor="mm")


def _draw_sector_block(img, draw, x, y, w, sector: dict):
    name = sector["sector"]
    pct  = sector.get("change_pct", 0.0)
    industries = sector.get("industries", [])

    header_color = _heat_color(pct, BLEND_MAX_HEADER)
    draw.rectangle([x, y, x + w, y + HEADER_H], fill=header_color)
    sign = "+" if pct >= 0 else ""
    pct_str     = f"{sign}{pct:.2f}%"
    header_font = ss.font(True, 19)
    avail_w     = w - 16

    full_text  = f"{FULL_NAME.get(name, name)}  {pct_str}"
    short_text = f"{name}  {pct_str}"
    if draw.textbbox((0, 0), full_text, font=header_font)[2] <= avail_w:
        header_text = full_text
    elif draw.textbbox((0, 0), short_text, font=header_font)[2] <= avail_w:
        header_text = short_text
    else:
        header_text = ss.ellipsize(draw, short_text, header_font, avail_w)
    draw.text((x + w / 2, y + HEADER_H / 2), header_text, font=header_font,
               fill=ss.C["white"], anchor="mm")

    n = len(industries)
    cell_w = (w - CELL_GAP) / 2
    cy = y + HEADER_H + CELL_GAP
    for i, ind in enumerate(industries):
        full_width = (i == n - 1 and n % 2 == 1)
        row = i // 2
        cell_y = cy + row * (CELL_ROW_H + CELL_GAP)
        if full_width:
            _draw_cell(draw, x, cell_y, w, CELL_ROW_H, ind["name"], ind.get("change_pct", 0.0))
        else:
            col = i % 2
            cell_x = x + col * (cell_w + CELL_GAP)
            _draw_cell(draw, cell_x, cell_y, cell_w, CELL_ROW_H, ind["name"], ind.get("change_pct", 0.0))


def _draw_legend(img, draw, y):
    w_total = ss.CW - 2 * OUTER_MARGIN
    seg_w   = w_total / len(LEGEND_STOPS)
    bar_h   = 16
    for i, stop in enumerate(LEGEND_STOPS):
        x = OUTER_MARGIN + i * seg_w
        draw.rectangle([x, y, x + seg_w - 3, y + bar_h], fill=_heat_color(stop, BLEND_MAX_CELL))
        draw.text((x + seg_w / 2, y + bar_h + 14), LEGEND_LABELS[i], font=ss.font(False, 15),
                   fill=ss.C["grey"], anchor="mm")
    return y + bar_h + 28


def render_card(human_date: str, sectors: list):
    img  = ss.new_canvas()
    draw = ImageDraw.Draw(img)
    y0   = ss.draw_header(img, f"Sector Heatmap  ·  {human_date}", ss.load_brand_logo())
    y0  += 30

    outer_col_w = (ss.CW - 2 * OUTER_MARGIN - (OUTER_COLS - 1) * OUTER_GAP) / OUTER_COLS
    col_x = [OUTER_MARGIN + i * (outer_col_w + OUTER_GAP) for i in range(OUTER_COLS)]
    col_heights = [0] * OUTER_COLS

    for sector in sectors:
        block_h = _sector_block_height(len(sector.get("industries", [])))
        col = min(range(OUTER_COLS), key=lambda i: col_heights[i])
        x = col_x[col]
        y = y0 + col_heights[col]
        _draw_sector_block(img, draw, x, y, outer_col_w, sector)
        col_heights[col] += block_h + BLOCK_GAP_Y

    content_bottom = y0 + max(col_heights)
    legend_bottom  = _draw_legend(img, draw, content_bottom + 14)

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

    print(f"Fetching sector heatmap (labeling as {date_str})...")
    sectors = fetch_heatmap()

    if not sectors:
        print("No sector data — nothing to render.")
        MANIFEST.write_text(json.dumps(None) + "\n")
        return

    print(f"  {len(sectors)} sectors found")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"
    img = render_card(human_date, sectors)
    img.save(out_path)
    print(f"  chart saved → {out_path.relative_to(ROOT)}")

    manifest = {
        "date":       date_str,
        "human_date": human_date,
        "sectors":    [{"name": s["sector"], "change_pct": s["change_pct"]} for s in sectors],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
