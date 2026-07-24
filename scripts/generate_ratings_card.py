#!/usr/bin/env python3
"""
generate_ratings_card.py — Render today's analyst upgrade/downgrade actions
as a branded card image.

Pulls upgrades/downgrades from the StockScore backend (same endpoint the
Flutter app calls) and renders a grid card. Saves to images/ratings/<date>.png
and writes a manifest for the posting step (scripts/post_ratings.py).

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

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
from logos import load_logo_pil

# NOTE: defaults to the Koyeb deployment, not the PythonAnywhere one used elsewhere
# in this repo — PythonAnywhere's free-tier outbound proxy blocks benzinga.com
# (403 from its allowlist), so /upgrades-downgrades only works from a host with
# unrestricted egress. Override via BACKEND_URL if that changes.
BACKEND_URL = os.environ.get("BACKEND_URL", "https://disturbed-melly-skhan89-05036d6c.koyeb.app")
ROOT        = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT / "images" / "ratings"
MANIFEST    = Path(__file__).parent / "_ratings_manifest.json"

COLS      = 3   # wider cards, up to 3 rows — fills the canvas better than 4x2
CARD_H    = 160
MARGIN_X  = 40
MAX_UPGRADES   = 9   # 3 rows
MAX_DOWNGRADES = 6   # 2 rows — downgrades are typically fewer


def fetch_ratings(date_str: str) -> dict:
    r = requests.get(f"{BACKEND_URL}/upgrades-downgrades", params={"date": date_str}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"  backend error: {data['error']}")
        return {"upgrades": [], "downgrades": []}
    return data


def _fmt_pt(v: float) -> str:
    return f"${v:.0f}" if v == int(v) else f"${v:.2f}"


def _pt_line(entry: dict):
    try:
        pt_current = float(entry["pt_current"])
    except (KeyError, TypeError, ValueError):
        return None
    pct = entry.get("pt_pct_change")
    try:
        pct_val = float(pct) if pct is not None else None
    except ValueError:
        pct_val = None

    text  = _fmt_pt(pt_current)
    color = ss.C["white"]
    if pct_val is not None:
        text  += f" ({pct_val:+.0f}%)"
        color  = ss.C["green"] if pct_val > 0 else (ss.C["red"] if pct_val < 0 else ss.C["grey"])
    return text, color


def _render_section(img, x, y, label, color, entries, max_items):
    y = ss.draw_section_header(img, x, y, label, color)
    if not entries:
        return ss.draw_empty_note(img, x, y)

    card_w = ss.grid_card_width(COLS, margin_x=MARGIN_X)

    def render_item(img, item, cx, cy, w, h):
        logo  = load_logo_pil(item["ticker"])
        lines = [(item.get("analyst") or "", 18, ss.C["grey"], False)]
        pt_line = _pt_line(item)
        if pt_line:
            text, pt_color = pt_line
            lines.append((text, 21, pt_color, True))
        ss.draw_side_card(img, cx, cy, w, h, logo, item["ticker"], lines,
                          fallback_bg=ss.C["bg"])

    return ss.draw_grid(img, entries[:max_items], x, y, COLS, card_w, CARD_H, render_item)


def render_card(human_date: str, upgrades: list, downgrades: list):
    img = ss.new_canvas()   # fixed 1080x1350 — same size as every other card type
    y = ss.draw_header(img, f"Analyst Ratings  ·  {human_date}", ss.load_brand_logo())

    y += 32
    y = _render_section(img, MARGIN_X, y, "UPGRADES", ss.C["green"], upgrades, MAX_UPGRADES)
    y += 30
    y = _render_section(img, MARGIN_X, y, "DOWNGRADES", ss.C["red"], downgrades, MAX_DOWNGRADES)

    ss.draw_footer(img)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, defaults to today (UTC)")
    args = parser.parse_args()

    date_str = args.date or os.environ.get("FORCE_DATE") or \
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
    human_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")

    print(f"Fetching analyst rating changes for {date_str}...")
    data = fetch_ratings(date_str)
    upgrades   = data.get("upgrades", [])
    downgrades = data.get("downgrades", [])

    if not upgrades and not downgrades:
        print("No rating changes found — nothing to render.")
        MANIFEST.write_text(json.dumps(None) + "\n")
        return

    print(f"  {len(upgrades)} upgrades, {len(downgrades)} downgrades")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}.png"
    img = render_card(human_date, upgrades, downgrades)
    img.save(out_path)
    print(f"  chart saved → {out_path.relative_to(ROOT)}")

    def _detail(e: dict) -> dict:
        return {
            "ticker":        e["ticker"],
            "analyst":       e.get("analyst"),
            "pt_current":    e.get("pt_current"),
            "pt_pct_change": e.get("pt_pct_change"),
        }

    manifest = {
        "date":       date_str,
        "human_date": human_date,
        "upgrades":   [_detail(e) for e in upgrades],
        "downgrades": [_detail(e) for e in downgrades],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
