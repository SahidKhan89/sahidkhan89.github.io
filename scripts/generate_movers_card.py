#!/usr/bin/env python3
"""
generate_movers_card.py — Render a "today's movers" card image.

Each run randomly picks ONE of three post types:
  - "movers"      — Day Gainers + Day Losers combined (two sections, like the
                     analyst-ratings card's Upgrades/Downgrades layout)
  - "most_active" — single list
  - "shorted"      — single list (most_shorted_stocks screener)

These are Yahoo Finance predefined screeners computed fresh from that day's
trading activity — unlike fundamental screeners (P/E, yield, growth), the
list genuinely changes run to run instead of repeating the same names. Saves
to images/movers/<date>.png and writes a manifest for the posting step
(scripts/post_movers.py).

Set FORCE_TYPE=movers|most_active|shorted (or pass --type) to pin a specific
post type, e.g. for local testing. Set FORCE_DATE=YYYY-MM-DD (or pass --date)
to label a specific date.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
from logos import load_logo_pil

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — see the same note in generate_ratings_card.py.
BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT        = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT / "images" / "movers"
MANIFEST    = Path(__file__).parent / "_movers_manifest.json"

POST_TYPES = ["movers", "most_active", "shorted"]

# NOTE: yfinance's live predefined-screener keys don't match what the backend's
# /available-screeners route documents — "most_active" is actually "most_actives"
# (plural), and "trending_tickers" isn't a valid key at all anymore (404).
# Swapped for "most_shorted_stocks", which is equally dynamic day to day.
SINGLE_LIST_SCREENER = {
    "most_active": ("Most Active", "most_actives"),
    "shorted":     ("Most Shorted", "most_shorted_stocks"),
}

COLS              = 3
MARGIN_X          = 40

CARD_H_SECTION    = 128  # gainers/losers — smaller since two sections share the canvas
MAX_ITEMS_SECTION = 9    # 3 rows each

CARD_H_SINGLE     = 160  # most active / most shorted — full canvas, one list
MAX_ITEMS_SINGLE  = 15   # 5 rows
SINGLE_GAP_Y      = 28   # more vertical breathing room between rows

CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥"}


def currency_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get((code or "").upper(), code or "")


def fetch_screener(screener_key: str) -> list:
    r = requests.get(f"{BACKEND_URL}/stock-screener",
                      params={"screener_criteria": screener_key}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error ({screener_key}): {data['error']}")
        return []
    return data.get("filtered_stocks", [])


def _fmt_lines(item: dict):
    price  = item.get("price")
    change = item.get("change")
    sym    = currency_symbol(item.get("currency"))

    price_str = f"{sym}{price:.2f}" if isinstance(price, (int, float)) else "N/A"
    if isinstance(change, (int, float)):
        sign  = "+" if change >= 0 else ""
        color = ss.C["green"] if change >= 0 else ss.C["red"]
        change_str = f"({sign}{change:.2f}%)"
    else:
        color, change_str = ss.C["grey"], ""

    return [
        (item.get("name") or "", 14, ss.C["grey"], False),
        (f"{price_str} {change_str}".strip(), 17, color, True),
    ]


def _render_item(img, item, cx, cy, w, h):
    symbol = item.get("symbol", "?")
    logo   = load_logo_pil(symbol)
    ss.draw_side_card(img, cx, cy, w, h, logo, symbol, _fmt_lines(item), fallback_bg=ss.C["card"])


def _render_section(img, x, y, label, color, stocks):
    y = ss.draw_section_header(img, x, y, label, color)
    if not stocks:
        return ss.draw_empty_note(img, x, y)
    card_w = ss.grid_card_width(COLS, margin_x=MARGIN_X)
    return ss.draw_grid(img, stocks[:MAX_ITEMS_SECTION], x, y, COLS, card_w, CARD_H_SECTION, _render_item)


def render_movers_combined(human_date: str, gainers: list, losers: list):
    img = ss.new_canvas()
    y = ss.draw_header(img, f"Gainers & Losers  ·  {human_date}", ss.load_brand_logo())
    y += 32
    y = _render_section(img, MARGIN_X, y, "GAINERS", ss.C["green"], gainers)
    y += 30
    y = _render_section(img, MARGIN_X, y, "LOSERS", ss.C["red"], losers)
    ss.draw_footer(img)
    return img


def render_single_list(title: str, human_date: str, stocks: list):
    img = ss.new_canvas()
    y = ss.draw_header(img, f"{title}  ·  {human_date}", ss.load_brand_logo())
    y += 32
    card_w = ss.grid_card_width(COLS, margin_x=MARGIN_X)
    items = stocks[:MAX_ITEMS_SINGLE]
    if items:
        ss.draw_grid(img, items, MARGIN_X, y, COLS, card_w, CARD_H_SINGLE, _render_item,
                     gap_y=SINGLE_GAP_Y)
    else:
        ss.draw_empty_note(img, MARGIN_X, y, "No data available")
    ss.draw_footer(img)
    return img, items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=POST_TYPES, help="pin a specific post type")
    parser.add_argument("--date", help="YYYY-MM-DD, defaults to the last market day")
    args = parser.parse_args()

    post_type = args.type or os.environ.get("FORCE_TYPE") or random.choice(POST_TYPES)

    date_str = args.date or os.environ.get("FORCE_DATE") or \
        ss.last_market_day(datetime.now(timezone.utc).date()).strftime("%Y-%m-%d")
    human_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")

    print(f"Selected post type: {post_type}")
    print(f"Fetching movers for {date_str}...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"

    if post_type == "movers":
        gainers = [s for s in fetch_screener("day_gainers") if s.get("symbol")]
        losers  = [s for s in fetch_screener("day_losers") if s.get("symbol")]
        if not gainers and not losers:
            print("No mover data — nothing to render.")
            MANIFEST.write_text(json.dumps(None) + "\n")
            return
        print(f"  {len(gainers)} gainers, {len(losers)} losers")
        img = render_movers_combined(human_date, gainers, losers)
        img.save(out_path)
        print(f"  chart saved → {out_path.relative_to(ROOT)}")
        manifest = {
            "date": date_str, "human_date": human_date, "post_type": post_type,
            "title": "Gainers & Losers",
            "gainers": [s["symbol"] for s in gainers[:MAX_ITEMS_SECTION]],
            "losers":  [s["symbol"] for s in losers[:MAX_ITEMS_SECTION]],
        }
    else:
        title, screener_key = SINGLE_LIST_SCREENER[post_type]
        stocks = [s for s in fetch_screener(screener_key) if s.get("symbol")]
        if not stocks:
            print("No mover data — nothing to render.")
            MANIFEST.write_text(json.dumps(None) + "\n")
            return
        print(f"  {len(stocks)} stocks found")
        img, items = render_single_list(title, human_date, stocks)
        img.save(out_path)
        print(f"  chart saved → {out_path.relative_to(ROOT)}")
        manifest = {
            "date": date_str, "human_date": human_date, "post_type": post_type,
            "title": title,
            "tickers": [s["symbol"] for s in items],
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
