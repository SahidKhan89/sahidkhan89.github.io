#!/usr/bin/env python3
"""
generate_dividends_card.py — Render an upcoming ex-dividend calendar as a
branded card image.

Pulls the ex-dividend calendar from the StockScore backend (same endpoint the
Flutter app calls) for the next market day (skips weekends), so followers have
lead time to buy in before the ex-dividend date. Saves to
images/dividends/<target-date>.png and writes a manifest for the posting step
(scripts/post_dividends.py).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) to render a specific target date
directly (bypasses the market-day lookahead), e.g. for local testing.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
from logos import load_logo_pil

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — PythonAnywhere's free-tier outbound proxy blocks api.divvydiary.com
# (403 from its allowlist), so /dividends only works from a host with unrestricted
# egress. Override via BACKEND_URL if that changes.
BACKEND_URL  = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT         = Path(__file__).parent.parent
OUTPUT_DIR   = ROOT / "images" / "dividends"
MANIFEST     = Path(__file__).parent / "_dividends_manifest.json"
MARKET_DAYS_AHEAD = 1   # next trading day — weekends don't count


def next_market_day(from_date, n: int = 1):
    d = from_date
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:   # Mon-Fri
            added += 1
    return d

COLS      = 3   # matches the analyst-ratings card layout/sizing
CARD_H    = 160
MARGIN_X  = 40
MAX_ITEMS = 15  # 5 rows

CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥"}


def currency_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get((code or "").upper(), code or "")


def fmt_pay_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date[:10], "%Y-%m-%d").strftime("%b %d")
    except (TypeError, ValueError):
        return iso_date or ""


def fetch_dividends(date_str_compact: str) -> list:
    r = requests.get(f"{BACKEND_URL}/dividends", params={"date": date_str_compact}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error: {data['error']}")
        return []
    return data.get("dividends", [])


def render_card(human_date: str, dividends: list):
    img = ss.new_canvas()   # fixed 1080x1350 — same size as every other card type
    y = ss.draw_header(img, f"Ex-Dividend  ·  {human_date}", ss.load_brand_logo())

    y += 32
    card_w = ss.grid_card_width(COLS, margin_x=MARGIN_X)

    def render_item(img, item, cx, cy, w, h):
        ticker = item.get("ticker") or item.get("symbol") or "?"
        logo   = load_logo_pil(ticker)
        sym    = currency_symbol(item.get("currency"))
        amount = item.get("amount")
        amount_str = f"{sym}{amount:.2f}" if isinstance(amount, (int, float)) else "N/A"
        pay_str    = fmt_pay_date(item.get("payDate"))
        lines = [
            (pay_str, 20, ss.C["grey"], False),
            (amount_str, 24, ss.C["teal"], True),
        ]
        ss.draw_side_card(img, cx, cy, w, h, logo, ticker, lines, fallback_bg=ss.C["bg"],
                          logo_cap=100, title_size=32)

    items = [d for d in dividends if d.get("ticker")][:MAX_ITEMS]
    if items:
        y = ss.draw_grid(img, items, MARGIN_X, y, COLS, card_w, CARD_H, render_item, gap_y=28)
    else:
        y = ss.draw_empty_note(img, MARGIN_X, y, "None scheduled")

    ss.draw_footer(img)
    return img, items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD target ex-div date, bypasses the lookahead")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    if forced:
        target_date = datetime.strptime(forced, "%Y-%m-%d").date()
    else:
        target_date = next_market_day(datetime.now(timezone.utc).date(), MARKET_DAYS_AHEAD)

    date_str        = target_date.strftime("%Y-%m-%d")
    date_compact    = target_date.strftime("%Y%m%d")
    human_date      = target_date.strftime("%a %d %b")

    print(f"Fetching ex-dividend calendar for {date_str} (compact {date_compact})...")
    dividends = fetch_dividends(date_compact)

    if not dividends:
        print("No dividends found — nothing to render.")
        MANIFEST.write_text(json.dumps(None) + "\n")
        return

    print(f"  {len(dividends)} dividends found")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"
    img, items = render_card(human_date, dividends)
    img.save(out_path)
    print(f"  chart saved → {out_path.relative_to(ROOT)}")

    manifest = {
        "date":       date_str,
        "human_date": human_date,
        "tickers":    [d["ticker"] for d in items],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
