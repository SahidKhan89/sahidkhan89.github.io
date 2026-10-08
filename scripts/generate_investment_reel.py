#!/usr/bin/env python3
"""
generate_investment_reel.py — "What $1,000 invested in X years ago is worth
today" as a vertical (1080x1920) Reel, posted by
scripts/post_investment_reel.py.

Unlike the daily data reels (sector heatmap, VIX gauge) this is evergreen,
hook-led content: the opening frame poses the question, the chart then draws
the growth of $1,000 week by week (with the S&P 500 alongside for scale) while
the dollar value counts up, and it ends on the final number plus a
"which stock next?" prompt to drive comments.

Sequence: hook card -> line chart draws left-to-right (y-axis rescales as the
value grows, counter + date tick in lockstep) -> result badges fade in ->
comment CTA fades in -> hold.

Prices are Yahoo Finance weekly adjusted closes (dividends/splits folded in,
so it's a total-return figure). The ticker is picked by rotating through
CANDIDATES, skipping any used in the last ROTATION_COOLDOWN posts (tracked in
data/posted_investment_reel.json); override with --ticker / --years.

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
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
import reel_audio
from logos import load_logo_pil

ROOT          = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT / "images" / "investment-reel"
REEL_MANIFEST = Path(__file__).parent / "_investment_reel_manifest.json"
TRACKING      = ROOT / "data" / "posted_investment_reel.json"

# ticker -> (display name, lookback years). Ordered so big winners alternate
# with laggards/blow-ups (PTON, SNAP, ZM...) and steady compounders — the
# "$1,000 in Peloton is now $57" stories are as shareable as the 100x ones,
# and mixing them keeps the feed from reading like hype. Every entry was
# checked to have Yahoo history covering its full lookback period.
CANDIDATES = {
    "NVDA":  ("NVIDIA",              10),
    "PTON":  ("Peloton",              5),
    "AAPL":  ("Apple",               20),
    "INTC":  ("Intel",               10),
    "MNST":  ("Monster Beverage",    20),
    "PYPL":  ("PayPal",              10),
    "MU":    ("Micron",              10),
    "NKE":   ("Nike",                10),
    "COST":  ("Costco",              20),
    "SNAP":  ("Snap",                 5),
    "PANW":  ("Palo Alto Networks",  10),
    "DIS":   ("Disney",              10),
    "AMZN":  ("Amazon",              20),
    "ZM":    ("Zoom",                 5),
    "DPZ":   ("Domino's",            20),
    "BA":    ("Boeing",              10),
    "ASML":  ("ASML",                10),
    "MRNA":  ("Moderna",              5),
    "NFLX":  ("Netflix",             20),
    "BABA":  ("Alibaba",             10),
    "CAT":   ("Caterpillar",         10),
    "VZ":    ("Verizon",             10),
    "META":  ("Meta",                10),
    "F":     ("Ford",                10),
    "LLY":   ("Eli Lilly",           10),
    "LULU":  ("Lululemon",           10),
    "TSM":   ("TSMC",                10),
    "T":     ("AT&T",                10),
    "MSFT":  ("Microsoft",           10),
    "RBLX":  ("Roblox",               5),
    "HD":    ("Home Depot",          20),
    "PFE":   ("Pfizer",              10),
    "AVGO":  ("Broadcom",            10),
    "ABNB":  ("Airbnb",               5),
    "JPM":   ("JPMorgan",            20),
    "ADBE":  ("Adobe",               10),
    "GOOGL": ("Google",              10),
    "SBUX":  ("Starbucks",           10),
    "CRWD":  ("CrowdStrike",          5),
    "SHOP":  ("Shopify",              5),
    "NOW":   ("ServiceNow",          10),
    "UNH":   ("UnitedHealth",        10),
    "PLTR":  ("Palantir",             5),
    "SNOW":  ("Snowflake",            5),
    "DE":    ("Deere",               10),
    "XOM":   ("Exxon Mobil",         10),
    "SMCI":  ("Super Micro",          5),
    "CRM":   ("Salesforce",          10),
    "GS":    ("Goldman Sachs",       10),
    "TGT":   ("Target",              10),
    "COIN":  ("Coinbase",             5),
    "KO":    ("Coca-Cola",           20),
    "HOOD":  ("Robinhood",            5),
    "PEP":   ("PepsiCo",             20),
    "MA":    ("Mastercard",          10),
    "GE":    ("GE Aerospace",        10),
    "TSLA":  ("Tesla",               10),
    "CSCO":  ("Cisco",               20),
    "AXP":   ("American Express",    10),
    "IBM":   ("IBM",                 20),
    "AMD":   ("AMD",                 10),
    "QCOM":  ("Qualcomm",            10),
    "ORCL":  ("Oracle",              10),
    "CMG":   ("Chipotle",            10),
    "NET":   ("Cloudflare",           5),
    "LMT":   ("Lockheed Martin",     10),
    "TXN":   ("Texas Instruments",   10),
    "JNJ":   ("Johnson & Johnson",   20),
    "V":     ("Visa",                10),
    "PG":    ("Procter & Gamble",    20),
    "ISRG":  ("Intuitive Surgical",  10),
    "BRK-B": ("Berkshire Hathaway",  20),
    "WMT":   ("Walmart",             20),
    "UBER":  ("Uber",                 5),
    "MCD":   ("McDonald's",          20),
    "SPOT":  ("Spotify",              5),
}
ROTATION_COOLDOWN = 30   # don't repeat a ticker within its last N posts
BENCHMARK = "SPY"        # S&P 500 total-return proxy (dividends included)
INVESTED  = 1000.0

FPS            = 30
REEL_W, REEL_H = 1080, 1920
FOOTER_ZONE    = 90    # matches draw_footer's fixed offset from img.height
TOP_SAFE_PAD   = 100   # same as the sector heatmap / VIX reels (proven on the live grid)

HOOK_FADE_FRAMES   = 8    # short pop-in — the question should be readable almost from frame 0
HOOK_HOLD_FRAMES   = 74   # ~2.5s — long enough to read, and the cover-frame grab lands here
HOOK_OUT_FRAMES    = 8
CHART_FRAMES       = 450  # ~15s for the line to draw the full period — 10-20 years needs
                          # this long to follow the counter without feeling rushed
CHART_HOLD_FRAMES  = 10
RESULT_FRAMES      = 14
CTA_FRAMES         = 14
END_HOLD_FRAMES    = 112  # ~3.7s holding on the finished frame — result + CTA section is
                          # 5s in all; any longer and people scroll before the CTA lands
# Total 690 frames = 23s (shared by the head-to-head reel). Was 18s; the
# chart was lengthened because it felt rushed — check average watch time in
# Insights before going longer.
POP_FRAMES         = 12   # counter 'pop' when a milestone is crossed

# Chart geometry (final-frame coordinates)
CHART_X0, CHART_X1 = 70, 1010
CHART_Y0, CHART_Y1 = 590, 1180
HEAD_PAD = 24   # keeps the head dot (and its glow) inside the chart's right edge
SS = 2   # supersample factor for the chart layer (PIL lines aren't antialiased)

BENCH_COLOR = (150, 163, 184)

# Growth multiples pinned to the line as they're crossed ("2x", "10x"...), plus
# drawdown marks for losers — data-driven beats, so the longer chart draw has
# something happening on screen rather than just a line creeping right.
GAIN_MILESTONES = [2, 5, 10, 20, 50, 100, 200, 500, 1000]
LOSS_MILESTONES = [0.5, 0.25]


# ── Data ────────────────────────────────────────────────────────────────────────

def fetch_weekly(symbol: str, start: datetime, end: datetime) -> tuple:
    """Weekly adjusted closes between start and end -> (unix timestamps, prices)."""
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"period1": int(start.timestamp()), "period2": int(end.timestamp()),
                "interval": "1wk", "events": "div,split"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts  = np.array(res["timestamp"], dtype=float)
    adj = np.array([np.nan if v is None else v
                    for v in res["indicators"]["adjclose"][0]["adjclose"]], dtype=float)
    keep = ~np.isnan(adj)
    return ts[keep], adj[keep]


def build_story(ticker: str, years: int, end: datetime) -> dict | None:
    start = end.replace(year=end.year - years)
    ts, px = fetch_weekly(ticker, start, end)
    if len(ts) < 20 or ts[0] - start.timestamp() > 45 * 86400:
        print(f"  {ticker}: history doesn't reach back {years}y — skipping")
        return None
    if end.timestamp() - ts[-1] > 21 * 86400:
        print(f"  {ticker}: no recent prices (delisted?) — skipping")
        return None
    bts, bpx = fetch_weekly(BENCHMARK, start, end)

    values = INVESTED * px / px[0]
    # Align the benchmark onto the ticker's weekly timestamps (last close at or before each).
    idx = np.clip(np.searchsorted(bts, ts, side="right") - 1, 0, len(bts) - 1)
    bench = INVESTED * bpx[idx] / bpx[idx[0]]

    final, bench_final = float(values[-1]), float(bench[-1])
    span_years = (ts[-1] - ts[0]) / (365.25 * 86400)
    cagr = (final / INVESTED) ** (1 / span_years) - 1
    return {
        "ticker":      ticker,
        "name":        CANDIDATES.get(ticker, (ticker, years))[0],
        "years":       years,
        "start_date":  datetime.fromtimestamp(ts[0], timezone.utc).strftime("%Y-%m-%d"),
        "end_date":    datetime.fromtimestamp(ts[-1], timezone.utc).strftime("%Y-%m-%d"),
        "final_value": round(final, 2),
        "pct_change":  round((final / INVESTED - 1) * 100, 1),
        "cagr_pct":    round(cagr * 100, 1),
        "bench_final": round(bench_final, 2),
        "_ts":         ts,
        "_values":     values,
        "_bench":      bench,
    }


def rotation_order(history: list) -> list:
    """Candidates in the order to try: list order, skipping anything used in
    the last ROTATION_COOLDOWN posts, then the cooled-down ones least-recent
    first — so a failed fetch just falls through to the next ticker."""
    recent = history[-ROTATION_COOLDOWN:]
    fresh = [t for t in CANDIDATES if t not in recent]
    last_used = {t: i for i, t in enumerate(history)}
    return fresh + sorted((t for t in CANDIDATES if t in recent),
                          key=lambda t: last_used.get(t, -1))


# ── Formatting ──────────────────────────────────────────────────────────────────

def fmt_money(v: float) -> str:
    return f"${v:,.0f}"


def fmt_axis(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def nice_step(ymax: float) -> float:
    raw = ymax / 4
    mag = 10 ** np.floor(np.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def find_milestones(values: np.ndarray) -> list:
    """[(first index crossing the level, label), ...] in time order."""
    out = []
    for m in GAIN_MILESTONES:
        hit = np.nonzero(values >= INVESTED * m)[0]
        if len(hit):
            out.append((int(hit[0]), f"{m}x"))
    for m in LOSS_MILESTONES:
        hit = np.nonzero(values <= INVESTED * m)[0]
        if len(hit):
            out.append((int(hit[0]), f"-{(1 - m) * 100:.0f}%"))
    return sorted(out)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def with_alpha(overlay: Image.Image, a: float) -> Image.Image:
    if a >= 1.0:
        return overlay
    out = overlay.copy()
    out.putalpha(overlay.split()[3].point(lambda v: int(v * a)))
    return out


# ── Static overlays ─────────────────────────────────────────────────────────────

def _text_w(draw, text, fnt) -> int:
    b = draw.textbbox((0, 0), text, font=fnt)
    return b[2] - b[0]


def render_hook_overlay(story: dict, logo: Image.Image | None) -> Image.Image:
    """'If you invested $1,000 in [logo] NVIDIA 10 years ago... what would it
    be worth today?' — the cover frame and the scroll-stopper."""
    overlay = Image.new("RGBA", (REEL_W, 900), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx = REEL_W / 2
    y = 0

    draw.text((cx, y), "If you'd invested", font=ss.font(False, 54),
               fill=(214, 220, 228), anchor="ma")
    y += 54 + 30
    draw.text((cx, y), "$1,000", font=ss.font(True, 190), fill=ss.C["teal"], anchor="ma")
    y += 190 + 50

    name_font = ss.font(True, 84)
    logo_size = 120
    in_font = ss.font(False, 54)
    in_w = _text_w(draw, "in", in_font)
    name_w = _text_w(draw, story["name"], name_font)
    row_w = in_w + 28 + (logo_size + 24 if logo is not None else 0) + name_w
    x = cx - row_w / 2
    row_cy = y + logo_size / 2
    draw.text((x, row_cy), "in", font=in_font, fill=(214, 220, 228), anchor="lm")
    x += in_w + 28
    if logo is not None:
        lg = logo.resize((logo_size, logo_size), Image.LANCZOS)
        lg.putalpha(ss._rounded_mask(logo_size, logo_size, int(logo_size * 0.22)))
        overlay.paste(lg, (int(x), int(y)), lg)
        x += logo_size + 24
    draw.text((x, row_cy), story["name"], font=name_font, fill=ss.C["white"], anchor="lm")
    y += logo_size + 50

    draw.text((cx, y), f"{story['years']} years ago...", font=ss.font(True, 64),
               fill=ss.C["white"], anchor="ma")
    y += 64 + 70
    draw.text((cx, y), "what would it be worth today?", font=ss.font(False, 46),
               fill=ss.C["amber"], anchor="ma")
    y += 46 + 10
    return overlay.crop((0, 0, REEL_W, y))


SERIES_TITLE_Y = TOP_SAFE_PAD + 5   # fills the band above the title row


def render_series_title(label: str, question: str) -> Image.Image:
    """Persistent two-line title for the chart phase of every reel: a teal
    tracked-caps series label (same eyebrow style as the image cards'
    draw_header) over a question that stays up until the result answers it,
    so anyone who joins after the hook card still knows what they're watching.
    Shared by the $1,000, head-to-head, guess and race reels."""
    overlay = Image.new("RGBA", (REEL_W, 115), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lf = ss.font(True, 30)
    text = label.upper()
    tracking = 4
    lw = sum(draw.textbbox((0, 0), ch, font=lf)[2] + tracking for ch in text) - tracking
    ss._draw_tracked_text(draw, ((REEL_W - lw) // 2, 0), text, lf, ss.C["teal"], tracking=tracking)
    size = 58
    qf = ss.font(True, size)
    while _text_w(draw, question, qf) > REEL_W - 120 and size > 38:
        size -= 2
        qf = ss.font(True, size)
    draw.text((REEL_W / 2, 78), question, font=qf, fill=ss.C["white"], anchor="mm")
    return overlay


def render_title_row(story: dict, logo: Image.Image | None) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 90), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    logo_size = 72
    title = f"{story['name']}"
    sub = f"${story['ticker']}"
    tf, sf = ss.font(True, 48), ss.font(False, 36)
    tw, sw = _text_w(draw, title, tf), _text_w(draw, sub, sf)
    row_w = (logo_size + 22 if logo is not None else 0) + tw + 18 + sw
    x = (REEL_W - row_w) / 2
    if logo is not None:
        lg = logo.resize((logo_size, logo_size), Image.LANCZOS)
        lg.putalpha(ss._rounded_mask(logo_size, logo_size, int(logo_size * 0.22)))
        overlay.paste(lg, (int(x), 9), lg)
        x += logo_size + 22
    draw.text((x, 45), title, font=tf, fill=ss.C["white"], anchor="lm")
    x += tw + 18
    draw.text((x, 47), sub, font=sf, fill=ss.C["grey"], anchor="lm")
    return overlay


def render_result_overlay(story: dict) -> Image.Image:
    """Two stat pills: total return, and the same $1,000 in the S&P 500."""
    overlay = Image.new("RGBA", (REEL_W, 250), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    up = story["final_value"] >= INVESTED
    color = ss.C["green"] if up else ss.C["red"]

    pill_w, pill_h, gap = 450, 150, 40
    x0 = (REEL_W - 2 * pill_w - gap) / 2
    pills = [
        (f"{story['pct_change']:+,.0f}%", f"{story['cagr_pct']:+.1f}% a year", color),
        (fmt_money(story["bench_final"]), "same $1,000 in the S&P 500", BENCH_COLOR),
    ]
    for i, (big, small, col) in enumerate(pills):
        x = x0 + i * (pill_w + gap)
        draw.rounded_rectangle([x, 0, x + pill_w, pill_h], radius=26,
                                fill=ss.C["card"], outline=col, width=3)
        draw.text((x + pill_w / 2, 52), big, font=ss.font(True, 58), fill=col, anchor="mm")
        draw.text((x + pill_w / 2, 112), small, font=ss.font(False, 28),
                   fill=(214, 220, 228), anchor="mm")

    draw.text((REEL_W / 2, pill_h + 46),
               "Dividends reinvested · Past performance isn't a guarantee",
               font=ss.font(False, 24), fill=ss.C["grey"], anchor="mm")
    return overlay


def render_cta_overlay() -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 70), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text((REEL_W / 2, 35), "Which stock should we do next? Comment below",
               font=ss.font(True, 38), fill=ss.C["teal"], anchor="mm")
    return overlay


# ── Chart ───────────────────────────────────────────────────────────────────────

def render_chart_layer(values: np.ndarray, bench: np.ndarray, k: float, ymax: float,
                        line_color, milestones: list = (), bench_color=BENCH_COLOR,
                        bench_width: int = 4, area_fill: bool = True) -> Image.Image:
    """Chart drawn up to (fractional) index k, at SS-x supersampling, returned
    downsampled to final size as RGBA. The y-axis runs 0..ymax. `bench` is the
    secondary line — the S&P 500 here, the rival stock in the head-to-head reel
    (generate_h2h_reel.py), which styles it as a full-weight line with no fill."""
    w, h = (CHART_X1 - CHART_X0), (CHART_Y1 - CHART_Y0)
    W, H = w * SS, h * SS
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    n = len(values)

    # Gridlines + axis labels
    step = nice_step(ymax)
    lbl_font = ss.font(False, 22 * SS)
    g = step
    while g < ymax * 0.98:
        gy = H - g / ymax * H
        draw.line([(0, gy), (W, gy)], fill=(*ss.C["div"], 255), width=2 * SS)
        draw.text((6 * SS, gy - 6 * SS), fmt_axis(g), font=lbl_font,
                   fill=(*ss.C["grey"], 255), anchor="ld")
        g += step
    draw.line([(0, H - SS), (W, H - SS)], fill=(*ss.C["div"], 255), width=2 * SS)

    def pts(series):
        kk = int(np.floor(k))
        xs = np.arange(kk + 1) / (n - 1) * (W - HEAD_PAD * SS)
        ys = H - series[:kk + 1] / ymax * H
        out = list(zip(xs.tolist(), ys.tolist()))
        if kk < n - 1:
            frac = k - kk
            xv = (kk + frac) / (n - 1) * (W - HEAD_PAD * SS)
            yv = series[kk] + (series[kk + 1] - series[kk]) * frac
            out.append((xv, H - yv / ymax * H))
        return out

    tp, bp = pts(values), pts(bench)

    # Area fill under the ticker line
    if area_fill and len(tp) >= 2:
        fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(fill).polygon(tp + [(tp[-1][0], H), (0, H)], fill=(*line_color, 46))
        layer = Image.alpha_composite(layer, fill)
        draw = ImageDraw.Draw(layer)

    # $1,000 starting line
    sy = H - INVESTED / ymax * H
    for x in range(0, W, 24 * SS):
        draw.line([(x, sy), (x + 12 * SS, sy)], fill=(*ss.C["grey"], 160), width=2 * SS)

    if len(bp) >= 2:
        draw.line(bp, fill=(*bench_color, 255), width=bench_width * SS, joint="curve")
    if len(tp) >= 2:
        draw.line(tp, fill=(*line_color, 255), width=7 * SS, joint="curve")

    # Milestone markers crossed so far. Newest first, and any marker that would
    # collide with a newer one is dropped — once the y-axis has zoomed out, the
    # early 2x/5x marks bunch up near the baseline and only the latest survive.
    xscale = (W - HEAD_PAD * SS) / (n - 1)
    mfont = ss.font(True, 26 * SS)
    kept = []
    for idx, label in reversed([m for m in milestones if m[0] <= k]):
        mx, my = idx * xscale, H - values[idx] / ymax * H
        if any(abs(mx - kx) < 120 * SS and abs(my - ky) < 70 * SS for kx, ky in kept):
            continue
        kept.append((mx, my))
        tb = draw.textbbox((0, 0), label, font=mfont)
        pw, ph = tb[2] - tb[0] + 28 * SS, tb[3] - tb[1] + 18 * SS
        py = my - 30 * SS - ph if my - 30 * SS - ph > 0 else my + 30 * SS
        px = min(max(mx - pw / 2, 0), W - pw)
        draw.line([(mx, my), (mx, py + ph if py < my else py)], fill=(*ss.C["white"], 120), width=2 * SS)
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=ph / 2,
                               fill=(*ss.C["card"], 235), outline=(*line_color, 255), width=2 * SS)
        draw.text((px + pw / 2, py + ph / 2), label, font=mfont, fill=(*ss.C["white"], 255), anchor="mm")
        draw.ellipse([mx - 7 * SS, my - 7 * SS, mx + 7 * SS, my + 7 * SS],
                     fill=(*ss.C["white"], 255), outline=(*line_color, 255), width=3 * SS)

    # Head dots
    bench_r = 7 if bench_width < 7 else 11
    for (hx, hy), col, r in ((bp[-1], bench_color, bench_r), (tp[-1], line_color, 11)):
        draw.ellipse([hx - (r + 8) * SS, hy - (r + 8) * SS, hx + (r + 8) * SS, hy + (r + 8) * SS],
                     fill=(*col, 60))
        draw.ellipse([hx - r * SS, hy - r * SS, hx + r * SS, hy + r * SS], fill=(*col, 255))

    return layer.resize((w, h), Image.LANCZOS)


def render_chart_legend(story: dict, line_color) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    f = ss.font(False, 28)
    items = [(story["name"], line_color), ("S&P 500", BENCH_COLOR)]
    widths = [40 + 14 + _text_w(draw, t, f) for t, _ in items]
    x = (REEL_W - sum(widths) - 50) / 2
    for (t, col), wi in zip(items, widths):
        draw.line([(x, 25), (x + 40, 25)], fill=col, width=6)
        draw.text((x + 54, 25), t, font=f, fill=(214, 220, 228), anchor="lm")
        x += wi + 50
    return overlay


# ── Frames ──────────────────────────────────────────────────────────────────────

def render_frames(story: dict, out_dir: Path) -> int:
    logo = load_logo_pil(story["ticker"])
    values, bench, ts = story["_values"], story["_bench"], story["_ts"]
    n = len(values)
    up = story["final_value"] >= INVESTED
    line_color = ss.C["green"] if up else ss.C["red"]

    bg = ss._diagonal_gradient(REEL_W, REEL_H, ss.C["bg"], ss.C["bg2"])
    footer_band = Image.new("RGBA", (REEL_W, REEL_H), (0, 0, 0, 0))
    ss.draw_footer(footer_band, ss.load_brand_logo())

    base = bg.copy()
    base.paste(footer_band, (0, 0), footer_band)

    hook = render_hook_overlay(story, logo)
    # No date on this reel — it's evergreen. The chart phase gets a series
    # title instead (render_series_title), below the top safe-zone pad.
    content_top = TOP_SAFE_PAD + 120
    content_bot = REEL_H - FOOTER_ZONE
    hook_y = content_top + (content_bot - content_top - hook.height) // 2 - 40

    title_row = render_title_row(story, logo)
    legend = render_chart_legend(story, line_color)
    result = render_result_overlay(story)
    cta = render_cta_overlay()

    # Everything sits above ~y=1600: the bottom of a Reel is covered by
    # Instagram's caption/username overlay.
    TITLE_Y   = 255
    VALUE_Y   = 420   # center of the big counter
    DATE_Y    = 515
    LEGEND_Y  = CHART_Y1 + 18
    RESULT_Y  = LEGEND_Y + 80
    CTA_Y     = RESULT_Y + result.height + 30

    value_fonts = {}
    milestones = find_milestones(values)
    date_font = ss.font(False, 36)
    frame_idx = 0

    def save(img):
        nonlocal frame_idx
        img.convert("RGB").save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    # 1. Hook card
    for f in range(HOOK_FADE_FRAMES):
        t = ease_out_cubic((f + 1) / HOOK_FADE_FRAMES)
        img = base.copy()
        scale = 0.9 + 0.1 * t
        sw, sh = round(hook.width * scale), round(hook.height * scale)
        scaled = with_alpha(hook.resize((sw, sh), Image.LANCZOS), 0.3 + 0.7 * t)
        img.paste(scaled, ((REEL_W - sw) // 2, hook_y + (hook.height - sh) // 2), scaled)
        save(img)
    for _ in range(HOOK_HOLD_FRAMES):
        img = base.copy()
        img.paste(hook, (0, hook_y), hook)
        save(img)
    for f in range(HOOK_OUT_FRAMES):
        img = base.copy()
        faded = with_alpha(hook, 1 - (f + 1) / HOOK_OUT_FRAMES)
        img.paste(faded, (0, hook_y - int(30 * (f + 1) / HOOK_OUT_FRAMES)), faded)
        save(img)

    # 2. Chart draws — the y-axis tracks the running max so the line always
    # fills the frame (a slow "zoom out" as the value grows), never starting
    # as a flat line crushed against the baseline by a huge final value.
    running_max = np.maximum.accumulate(np.maximum(values, bench))
    chart_base = base.copy()
    series_title = render_series_title(f"$1,000 · {story['years']} years ago",
                                       f"Did {story['name']} beat the market?")
    chart_base.paste(series_title, (0, SERIES_TITLE_Y), series_title)
    chart_base.paste(title_row, (0, TITLE_Y), title_row)
    chart_base.paste(legend, (0, LEGEND_Y), legend)

    def draw_counter(img, val, ts_val, pop=0.0):
        draw = ImageDraw.Draw(img)
        col = ss.C["green"] if val >= INVESTED else ss.C["red"]
        size = round(150 * (1 + 0.14 * pop))
        if size not in value_fonts:
            value_fonts[size] = ss.font(True, size)
        draw.text((REEL_W / 2, VALUE_Y), fmt_money(val), font=value_fonts[size],
                   fill=col, anchor="mm")
        when = datetime.fromtimestamp(ts_val, timezone.utc).strftime("%b %Y")
        draw.text((REEL_W / 2, DATE_Y), when, font=date_font, fill=(183, 185, 191), anchor="mm")

    def chart_frame(k, pop=0.0):
        kk = min(int(np.floor(k)), n - 1)
        ymax = max(running_max[kk] * 1.12, INVESTED * 1.6)
        layer = render_chart_layer(values, bench, k, ymax, line_color, milestones)
        img = chart_base.copy()
        img.paste(layer, (CHART_X0, CHART_Y0), layer)
        frac = k - kk
        val = values[kk] if kk >= n - 1 else values[kk] + (values[kk + 1] - values[kk]) * frac
        draw_counter(img, float(val), ts[kk], pop)
        return img

    crossed, last_pop = 0, -POP_FRAMES
    for f in range(CHART_FRAMES):
        t = (f + 1) / CHART_FRAMES
        k = (ease_in_out(t) * 0.25 + t * 0.75) * (n - 1)   # mostly constant speed, soft start/stop
        now_crossed = sum(1 for idx, _ in milestones if idx <= k)
        if now_crossed > crossed:
            crossed, last_pop = now_crossed, f
        pop = max(0.0, 1 - (f - last_pop) / POP_FRAMES)
        save(chart_frame(k, ease_out_cubic(pop)))

    final = chart_frame(n - 1)
    for _ in range(CHART_HOLD_FRAMES):
        save(final)

    # 3. Result pills, then CTA
    for f in range(RESULT_FRAMES):
        t = ease_out_cubic((f + 1) / RESULT_FRAMES)
        img = final.copy()
        faded = with_alpha(result, t)
        img.paste(faded, (0, RESULT_Y + int(20 * (1 - t))), faded)
        save(img)
    final.paste(result, (0, RESULT_Y), result)
    for f in range(CTA_FRAMES):
        img = final.copy()
        faded = with_alpha(cta, (f + 1) / CTA_FRAMES)
        img.paste(faded, (0, CTA_Y), faded)
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
    history = tracking.get("tickers", [])

    forced_ticker = (args.ticker or os.environ.get("FORCE_TICKER") or "").upper()
    to_try = [forced_ticker] if forced_ticker else rotation_order(history)[:5]
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    story = None
    for ticker in to_try:
        years = args.years or CANDIDATES.get(ticker, (ticker, 10))[1]
        print(f"Building $1,000-in-{ticker} ({years}y) story...")
        try:
            story = build_story(ticker, years, end)
        except Exception as e:
            print(f"  {ticker}: fetch failed ({e}) — trying the next one")
        if story is not None:
            break
    if story is None:
        sys.exit(1)
    print(f"  $1,000 -> {fmt_money(story['final_value'])} ({story['pct_change']:+,.1f}%, "
          f"{story['cagr_pct']:+.1f}%/yr) vs S&P 500 {fmt_money(story['bench_final'])}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        n_frames = render_frames(story, tmp_path)
        print(f"  rendered {n_frames} frames @ {FPS}fps (~{n_frames / FPS:.1f}s)")
        audio_credit = reel_audio.encode_video(tmp_path, out_path, FPS, n_frames, "investment")
        print(f"  audio: {audio_credit}")

    manifest = {k: v for k, v in story.items() if not k.startswith("_")}
    manifest.update({"date": date_str, "audio_credit": audio_credit})
    REEL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    try:
        shown_path = out_path.relative_to(ROOT)
    except ValueError:
        shown_path = out_path
    print(f"  video saved -> {shown_path}")


if __name__ == "__main__":
    main()
