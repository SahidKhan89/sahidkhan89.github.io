#!/usr/bin/env python3
"""
generate_guess_reel.py — "Guess the stock": an unlabelled $1,000-growth chart
draws (with the S&P 500 for scale), two hints pop in along the way, a 3-2-1
countdown runs, then the logo and name are revealed. Built for comments —
"Did you get it?" — which is what these accounts are short on.

Reuses generate_investment_reel.py's data fetch, chart drawing and overlays so
it matches the $1,000 reel visually; the line is drawn in a neutral colour
until the reveal so the up/down colour isn't itself a clue.

Rotates through MYSTERIES, skipping any used in the last ROTATION_COOLDOWN
posts (data/posted_guess_reel.json); override with --ticker / --years.

Requires ffmpeg on PATH (invoked via subprocess — not a pip dependency).
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
import reel_audio
import generate_investment_reel as inv
from logos import load_logo_pil

ROOT          = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT / "images" / "guess-reel"
REEL_MANIFEST = Path(__file__).parent / "_guess_reel_manifest.json"
TRACKING      = ROOT / "data" / "posted_guess_reel.json"

# ticker -> (display name, years, hint). Household names only — a guessing
# game needs stocks people have a shot at. The hint is the category the
# company is best known for; the second hint (ticker's first letter) is
# derived, so there's nothing else to keep accurate.
MYSTERIES = {
    "NVDA":  ("NVIDIA",        10, "Semiconductors"),
    "PTON":  ("Peloton",        5, "Home fitness"),
    "COST":  ("Costco",        20, "Retail"),
    "NFLX":  ("Netflix",       20, "Streaming"),
    "INTC":  ("Intel",         10, "Semiconductors"),
    "MCD":   ("McDonald's",    20, "Restaurants"),
    "TSLA":  ("Tesla",         10, "Electric vehicles"),
    "SNAP":  ("Snap",           5, "Social media"),
    "AAPL":  ("Apple",         20, "Consumer tech"),
    "NKE":   ("Nike",          10, "Sportswear"),
    "LLY":   ("Eli Lilly",     10, "Pharmaceuticals"),
    "ZM":    ("Zoom",           5, "Video calls"),
    "DPZ":   ("Domino's",      20, "Restaurants"),
    "DIS":   ("Disney",        10, "Entertainment"),
    "AMD":   ("AMD",           10, "Semiconductors"),
    "PFE":   ("Pfizer",        10, "Pharmaceuticals"),
    "MNST":  ("Monster Beverage", 20, "Energy drinks"),
    "BA":    ("Boeing",        10, "Aerospace"),
    "META":  ("Meta",          10, "Social media"),
    "SBUX":  ("Starbucks",     10, "Coffee chains"),
    "PLTR":  ("Palantir",       5, "Software"),
    "LULU":  ("Lululemon",     10, "Sportswear"),
    "AMZN":  ("Amazon",        20, "E-commerce"),
    "F":     ("Ford",          10, "Car makers"),
    "CMG":   ("Chipotle",      10, "Restaurants"),
    "COIN":  ("Coinbase",       5, "Crypto"),
    "MSFT":  ("Microsoft",     10, "Software"),
    "UBER":  ("Uber",           5, "Ride-hailing"),
    "KO":    ("Coca-Cola",     20, "Soft drinks"),
    "SPOT":  ("Spotify",        5, "Music streaming"),
}
ROTATION_COOLDOWN = 20

FPS = inv.FPS
REEL_W, REEL_H = inv.REEL_W, inv.REEL_H

HOOK_FADE_FRAMES   = 8
HOOK_HOLD_FRAMES   = 74     # ~2.5s
HOOK_OUT_FRAMES    = 8
CHART_FRAMES       = 390    # ~13s
CHART_HOLD_FRAMES  = 8
COUNT_FRAMES       = 20     # per countdown number (3, 2, 1) — ~2s total
REVEAL_FRAMES      = 14
CTA_FRAMES         = 12
END_HOLD_FRAMES    = 110    # reveal + result + CTA ≈ 5s in all
HINT_FRAMES        = 75     # ~2.5s on screen per hint
HINT_AT            = (0.30, 0.62)   # fraction of the chart draw where each hint pops

MYSTERY_COLOR = (0, 210, 190)      # ss.C["teal"] — neutral until the reveal


def rotation_order(history: list) -> list:
    recent = history[-ROTATION_COOLDOWN:]
    fresh = [t for t in MYSTERIES if t not in recent]
    last_used = {t: i for i, t in enumerate(history)}
    return fresh + sorted((t for t in MYSTERIES if t in recent), key=lambda t: last_used.get(t, -1))


# ── Overlays ────────────────────────────────────────────────────────────────────

def render_hook(story: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 900), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, y = REEL_W / 2, 0
    draw.text((cx, y), "GUESS", font=ss.font(True, 150), fill=ss.C["teal"], anchor="ma")
    y += 150 + 10
    draw.text((cx, y), "THE STOCK", font=ss.font(True, 110), fill=ss.C["white"], anchor="ma")
    y += 110 + 70
    draw.text((cx, y), f"$1,000 invested {story['years']} years ago...", font=ss.font(False, 48),
              fill=(214, 220, 228), anchor="ma")
    y += 48 + 50
    draw.text((cx, y), "Can you name it before the reveal?", font=ss.font(True, 46),
              fill=ss.C["amber"], anchor="ma")
    y += 46 + 10
    return overlay.crop((0, 0, REEL_W, y))


def mystery_tile(size: int) -> Image.Image:
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22),
                        fill=ss.C["card"], outline=MYSTERY_COLOR, width=3)
    d.text((size / 2, size / 2 + 2), "?", font=ss.font(True, int(size * 0.62)),
           fill=MYSTERY_COLOR, anchor="mm")
    return tile


def render_title_row(name: str, ticker: str | None, logo: Image.Image | None) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 90), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = 72
    tf, sf = ss.font(True, 48), ss.font(False, 36)
    sub = f"${ticker}" if ticker else ""
    tw = inv._text_w(draw, name, tf)
    sw = inv._text_w(draw, sub, sf) if sub else 0
    x = (REEL_W - (size + 22 + tw + (18 + sw if sub else 0))) / 2
    if logo is not None:
        lg = logo.resize((size, size), Image.LANCZOS)
        lg.putalpha(ss._rounded_mask(size, size, int(size * 0.22)))
    else:
        lg = mystery_tile(size)
    overlay.paste(lg, (int(x), 9), lg)
    x += size + 22
    draw.text((x, 45), name, font=tf, fill=ss.C["white"], anchor="lm")
    if sub:
        draw.text((x + tw + 18, 47), sub, font=sf, fill=ss.C["grey"], anchor="lm")
    return overlay


def render_hint(n: int, text: str) -> Image.Image:
    label = f"Hint {n}:  {text}"
    f = ss.font(True, 34)
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w, h = inv._text_w(dummy, label, f) + 64, 62
    overlay = Image.new("RGBA", (REEL_W, h + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    x0 = (REEL_W - w) / 2
    d.rounded_rectangle([x0, 0, x0 + w, h], radius=h / 2, fill=ss.C["card"],
                        outline=ss.C["amber"], width=3)
    d.text((REEL_W / 2, h / 2), label, font=f, fill=ss.C["amber"], anchor="mm")
    return overlay


def render_countdown(n: int, scale: float) -> Image.Image:
    size = 420
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([10, 10, size - 10, size - 10], fill=(*ss.C["card"], 235), outline=MYSTERY_COLOR, width=8)
    d.text((size / 2, size / 2 + 6), str(n), font=ss.font(True, 260), fill=ss.C["white"], anchor="mm")
    s = max(1, int(size * scale))
    return overlay.resize((s, s), Image.LANCZOS)


def render_result(story: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    up = story["final_value"] >= inv.INVESTED
    col = ss.C["green"] if up else ss.C["red"]
    d.text((REEL_W / 2, 40), f"$1,000  →  {inv.fmt_money(story['final_value'])}",
           font=ss.font(True, 64), fill=col, anchor="mm")
    d.text((REEL_W / 2, 110), f"{story['pct_change']:+,.0f}% over {story['years']} years  ·  "
           f"S&P 500: {inv.fmt_money(story['bench_final'])}",
           font=ss.font(False, 32), fill=(214, 220, 228), anchor="mm")
    d.text((REEL_W / 2, 170), "Dividends reinvested · Past performance isn't a guarantee",
           font=ss.font(False, 24), fill=ss.C["grey"], anchor="mm")
    return overlay


def render_cta() -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 70), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).text((REEL_W / 2, 35), "Did you get it? Comment your guess",
                                 font=ss.font(True, 40), fill=ss.C["teal"], anchor="mm")
    return overlay


# ── Frames ──────────────────────────────────────────────────────────────────────

def render_frames(story: dict, out_dir: Path) -> int:
    ticker, name, hint = story["ticker"], story["name"], story["hint"]
    logo = load_logo_pil(ticker)
    values, bench, ts = story["_values"], story["_bench"], story["_ts"]
    n = len(values)
    up = story["final_value"] >= inv.INVESTED
    reveal_color = ss.C["green"] if up else ss.C["red"]

    base = ss._diagonal_gradient(REEL_W, REEL_H, ss.C["bg"], ss.C["bg2"]).convert("RGBA")
    footer = Image.new("RGBA", (REEL_W, REEL_H), (0, 0, 0, 0))
    ss.draw_footer(footer, ss.load_brand_logo())
    base.alpha_composite(footer)

    hook = render_hook(story)
    top, bot = inv.TOP_SAFE_PAD + 120, REEL_H - inv.FOOTER_ZONE
    hook_y = top + (bot - top - hook.height) // 2 - 40

    TITLE_Y, VALUE_Y, DATE_Y, HINT_Y = 255, 420, 515, 550
    RESULT_Y = inv.CHART_Y1 + 40
    CTA_Y = RESULT_Y + 240

    mystery_row = render_title_row("Mystery stock", None, None)
    reveal_row  = render_title_row(name, ticker, logo)
    hints = [render_hint(1, hint), render_hint(2, f"Ticker starts with \"{ticker[0]}\"")]
    result, cta = render_result(story), render_cta()
    milestones = inv.find_milestones(values)
    running_max = np.maximum.accumulate(np.maximum(values, bench))
    value_font, date_font = ss.font(True, 150), ss.font(False, 36)

    frame_idx = 0

    def save(img):
        nonlocal frame_idx
        img.convert("RGB").save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    # 1. Hook
    for f in range(HOOK_FADE_FRAMES):
        t = inv.ease_out_cubic((f + 1) / HOOK_FADE_FRAMES)
        img = base.copy()
        sw, sh = round(hook.width * (0.9 + 0.1 * t)), round(hook.height * (0.9 + 0.1 * t))
        scaled = inv.with_alpha(hook.resize((sw, sh), Image.LANCZOS), 0.3 + 0.7 * t)
        img.paste(scaled, ((REEL_W - sw) // 2, hook_y + (hook.height - sh) // 2), scaled)
        save(img)
    for _ in range(HOOK_HOLD_FRAMES):
        img = base.copy()
        img.paste(hook, (0, hook_y), hook)
        save(img)
    for f in range(HOOK_OUT_FRAMES):
        img = base.copy()
        faded = inv.with_alpha(hook, 1 - (f + 1) / HOOK_OUT_FRAMES)
        img.paste(faded, (0, hook_y - int(30 * (f + 1) / HOOK_OUT_FRAMES)), faded)
        save(img)

    # 2. Mystery chart (neutral colour), hints along the way
    def chart_frame(k, row, color):
        kk = min(int(np.floor(k)), n - 1)
        ymax = max(running_max[kk] * 1.12, inv.INVESTED * 1.6)
        layer = inv.render_chart_layer(values, bench, k, ymax, color, milestones)
        img = base.copy()
        img.paste(row, (0, TITLE_Y), row)
        img.paste(layer, (inv.CHART_X0, inv.CHART_Y0), layer)
        d = ImageDraw.Draw(img)
        frac = k - kk
        val = values[kk] if kk >= n - 1 else values[kk] + (values[kk + 1] - values[kk]) * frac
        d.text((REEL_W / 2, VALUE_Y), inv.fmt_money(float(val)), font=value_font, fill=color, anchor="mm")
        d.text((REEL_W / 2, DATE_Y), datetime.fromtimestamp(ts[kk], timezone.utc).strftime("%b %Y"),
               font=date_font, fill=(183, 185, 191), anchor="mm")
        return img

    hint_start = [int(h * CHART_FRAMES) for h in HINT_AT]
    for f in range(CHART_FRAMES):
        t = (f + 1) / CHART_FRAMES
        k = (inv.ease_in_out(t) * 0.25 + t * 0.75) * (n - 1)
        img = chart_frame(k, mystery_row, MYSTERY_COLOR)
        for i, hs in enumerate(hint_start):
            age = f - hs
            if 0 <= age < HINT_FRAMES:
                a = min(1.0, (age + 1) / 6, (HINT_FRAMES - age) / 6)
                h = inv.with_alpha(hints[i], a)
                img.paste(h, (0, HINT_Y), h)
        save(img)

    mystery_final = chart_frame(n - 1, mystery_row, MYSTERY_COLOR)
    for _ in range(CHART_HOLD_FRAMES):
        save(mystery_final)

    # 3. Countdown over a dimmed chart
    dim = mystery_final.copy()
    dim.alpha_composite(Image.new("RGBA", dim.size, (*ss.C["bg"], 150)))
    cy = (inv.CHART_Y0 + inv.CHART_Y1) // 2
    for num in (3, 2, 1):
        for f in range(COUNT_FRAMES):
            scale = 0.7 + 0.3 * inv.ease_out_cubic(min(1.0, (f + 1) / 8))
            c = render_countdown(num, scale)
            img = dim.copy()
            img.paste(c, ((REEL_W - c.width) // 2, cy - c.height // 2), c)
            save(img)

    # 4. Reveal: logo + name, line recoloured up/down, then result + CTA
    final = chart_frame(n - 1, reveal_row, reveal_color)
    for f in range(REVEAL_FRAMES):
        t = inv.ease_out_cubic((f + 1) / REVEAL_FRAMES)
        img = Image.blend(dim.convert("RGB"), final.convert("RGB"), t).convert("RGBA")
        r = inv.with_alpha(result, t)
        img.paste(r, (0, RESULT_Y + int(20 * (1 - t))), r)
        save(img)
    final.paste(result, (0, RESULT_Y), result)
    for f in range(CTA_FRAMES):
        img = final.copy()
        c = inv.with_alpha(cta, (f + 1) / CTA_FRAMES)
        img.paste(c, (0, CTA_Y), c)
        save(img)
    final.paste(cta, (0, CTA_Y), cta)
    for _ in range(END_HOLD_FRAMES):
        save(final)
    return frame_idx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD label override (defaults to today, UTC)")
    parser.add_argument("--ticker", help="force a ticker instead of the rotation")
    parser.add_argument("--years", type=int, help="override the lookback period")
    parser.add_argument("--out", help="output mp4 path override")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    date_obj = (datetime.strptime(forced, "%Y-%m-%d").date() if forced
                else datetime.now(timezone.utc).date())
    date_str = date_obj.strftime("%Y-%m-%d")

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {}
    forced_ticker = (args.ticker or os.environ.get("FORCE_TICKER") or "").upper()
    to_try = [forced_ticker] if forced_ticker else rotation_order(tracking.get("tickers", []))[:5]
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    story = None
    for ticker in to_try:
        name, years, hint = MYSTERIES.get(ticker, (inv.CANDIDATES.get(ticker, (ticker,))[0], 10, "Stocks"))
        years = args.years or years
        print(f"Building guess-the-stock for {ticker} ({years}y)...")
        try:
            story = inv.build_story(ticker, years, datetime(end.year, end.month, end.day, tzinfo=timezone.utc))
        except Exception as e:
            print(f"  {ticker}: fetch failed ({e}) — trying the next one")
        if story is not None:
            story.update({"name": name, "hint": hint})
            break
    if story is None:
        sys.exit(1)
    print(f"  $1,000 -> {inv.fmt_money(story['final_value'])} ({story['pct_change']:+,.1f}%)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        n_frames = render_frames(story, Path(tmp))
        print(f"  rendered {n_frames} frames @ {FPS}fps (~{n_frames / FPS:.1f}s)")
        audio = reel_audio.encode_video(Path(tmp), out_path, FPS, n_frames, "guess")
        print(f"  audio: {audio}")

    manifest = {k: v for k, v in story.items() if not k.startswith("_")}
    manifest.update({"date": date_str, "audio_credit": audio})
    REEL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  video saved -> {out_path}")


if __name__ == "__main__":
    main()
