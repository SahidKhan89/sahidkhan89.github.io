#!/usr/bin/env python3
"""
generate_earnings_calendar_card.py — Render today's earnings calendar as a
branded card image.

Pulls the before-open / after-close earnings schedule from the StockScore
backend (same endpoint the Flutter app calls) and renders a two-column
logo-grid card (Before Open | After Close), matching the in-app share design.
Saves to images/earnings-calendar/<date>.png and writes a manifest for the
posting step (scripts/post_earnings_calendar.py).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) to render for a specific date,
e.g. for local testing.
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
from logos import load_logo_pil

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — PythonAnywhere's free-tier outbound proxy silently breaks the
# SavvyTrader calendar call, so /earnings only works reliably from a host with
# unrestricted egress. Override via BACKEND_URL if that changes.
BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT        = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT / "images" / "earnings-calendar"
MANIFEST    = Path(__file__).parent / "_earnings_calendar_manifest.json"

FALLBACK_BG = ss.C["card"]   # no-logo tile background — same navy card tone as everywhere else

MARGIN_X     = 48
DIVIDER_GAP  = 64            # total horizontal space the center divider sits in
COLS         = 3
TILE_SIZE    = 112
TILE_GAP_X   = 30            # horizontal gap between tiles — there's room to spare
ROW_PITCH_EXTRA = 70         # label height + gap between tile rows
LABEL_GAP    = 100           # gap between the section icon/label and its grid
HEADER_GAP   = 40            # gap between the page header and the section labels
MAX_PER_SIDE = 15            # matches the backend's own before_open/after_close cap;
                              # 5 rows still fits the fixed 1080x1350 canvas comfortably


def fetch_calendar(date_str: str) -> dict:
    r = requests.get(f"{BACKEND_URL}/earnings", params={"date": date_str}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error: {data['error']}")
        return {"before_open": [], "after_close": []}
    return data


def _col_group_width() -> int:
    return (ss.CW - 2 * MARGIN_X - DIVIDER_GAP) // 2


def _block_x0(col_x0: int, group_w: int) -> int:
    """Centers the fixed-width tile block (not each row individually) within
    its half of the canvas, so the section label and grid share one consistent
    left edge instead of hugging the column's outer margin.
    """
    content_w = COLS * TILE_SIZE + (COLS - 1) * TILE_GAP_X
    return col_x0 + (group_w - content_w) // 2


def _render_column(img, col_x0, group_w, y0, label: str, icon_fn, entries: list) -> int:
    x0 = _block_x0(col_x0, group_w)
    content_w = COLS * TILE_SIZE + (COLS - 1) * TILE_GAP_X

    draw = ImageDraw.Draw(img)
    icon_r  = 15
    icon_d  = icon_r * 2
    icon_gap = 14
    label_font = ss.font(True, 30)
    text_w = draw.textbbox((0, 0), label, font=label_font)[2]

    label_block_w = icon_d + icon_gap + text_w
    label_x0 = x0 + (content_w - label_block_w) // 2   # centered above the middle tile

    icon_cx = label_x0 + icon_r
    icon_fn(img, icon_cx, y0 + icon_r)
    draw.text((label_x0 + icon_d + icon_gap, y0), label, font=label_font, fill=ss.C["white"])
    y = y0 + LABEL_GAP

    if not entries:
        return ss.draw_empty_note(img, x0, y, "None scheduled")

    def render_item(img, item, x, y, size):
        logo = load_logo_pil(item["symbol"])
        return ss.draw_logo_tile(img, x, y, size, logo, item["symbol"], FALLBACK_BG)

    return ss.draw_tile_grid(img, entries[:MAX_PER_SIDE], x0, y, COLS, TILE_SIZE,
                              TILE_GAP_X, ROW_PITCH_EXTRA, render_item)


def render_card(human_date: str, before_open: list, after_close: list):
    img = ss.new_canvas()   # fixed 1080x1350 — same size as every other card type
    y0 = ss.draw_header(img, f"Earnings Calendar  ·  {human_date}", ss.load_brand_logo())
    y0 += HEADER_GAP

    group_w   = _col_group_width()
    left_x    = MARGIN_X
    right_x   = MARGIN_X + group_w + DIVIDER_GAP

    bottom_left  = _render_column(
        img, left_x, group_w, y0, "Before Open",
        lambda im, cx, cy: ss.draw_icon_sun(im, cx, cy, 15, (255, 179, 71)),
        before_open,
    )
    bottom_right = _render_column(
        img, right_x, group_w, y0, "After Close",
        lambda im, cx, cy: ss.draw_icon_moon(im, cx, cy, 15, (120, 170, 230), ss.C["bg"]),
        after_close,
    )
    content_bottom = max(bottom_left, bottom_right)

    divider_x = ss.CW // 2
    ImageDraw.Draw(img).line(
        [(divider_x, y0 - 4), (divider_x, content_bottom)], fill=ss.C["div"], width=2)

    ss.draw_footer(img)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, defaults to today (UTC)")
    args = parser.parse_args()

    date_str = args.date or os.environ.get("FORCE_DATE") or \
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
    human_date = ss.ordinal_date(datetime.strptime(date_str, "%Y-%m-%d"))

    print(f"Fetching earnings calendar for {date_str}...")
    data = fetch_calendar(date_str)
    before_open = data.get("before_open", [])
    after_close = data.get("after_close", [])

    if not before_open and not after_close:
        print("No earnings scheduled — nothing to render.")
        MANIFEST.write_text(json.dumps(None) + "\n")
        return

    print(f"  {len(before_open)} before open, {len(after_close)} after close")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"
    img = render_card(human_date, before_open, after_close)
    img.save(out_path)
    print(f"  chart saved → {out_path.relative_to(ROOT)}")

    manifest = {
        "date":         date_str,
        "human_date":   human_date,
        "before_open":  [e["symbol"] for e in before_open],
        "after_close":  [e["symbol"] for e in after_close],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
