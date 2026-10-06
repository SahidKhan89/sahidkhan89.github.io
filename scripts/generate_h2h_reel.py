#!/usr/bin/env python3
"""
generate_h2h_reel.py — "$1,000 in A vs $1,000 in B, N years ago — which won?"
as a vertical (1080x1920) Reel, posted by scripts/post_h2h_reel.py.

Sister format to generate_investment_reel.py (single stock vs the S&P 500),
and reuses its data fetching, chart drawing and audio/encode helpers so the
two stay visually consistent. Differences: both lines are full-weight in
their own colours (no area fill), two counters run side by side, and the
mid-chart beats are lead changes ("AMD takes the lead") rather than growth
milestones — rivalry is the hook, so who's ahead is the story.

Sequence: hook card (the question) -> both lines draw (lead-change toasts pop
as they happen) -> result cards with a WINNER tag fade in -> comment CTA ->
hold.

Rotates through MATCHUPS, skipping any used in the last ROTATION_COOLDOWN
posts (data/posted_h2h_reel.json); override with --pair NVDA-AMD / --years.

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
OUTPUT_DIR    = ROOT / "images" / "h2h-reel"
REEL_MANIFEST = Path(__file__).parent / "_h2h_reel_manifest.json"
TRACKING      = ROOT / "data" / "posted_h2h_reel.json"

# (ticker A, name A, ticker B, name B, lookback years) — direct rivals or
# same-category pairs people already have opinions about, which is what gets
# comments. Ordered to vary sector and outcome week to week (a blowout, then
# a close race, then an upset). 24 = ~6 months at one a week. Every pair was
# checked to have Yahoo history for both tickers over the full lookback.
MATCHUPS = [
    ("NVDA",  "NVIDIA",      "AMD",   "AMD",          10),
    ("KO",    "Coca-Cola",   "PEP",   "PepsiCo",      20),
    ("TSLA",  "Tesla",       "F",     "Ford",         10),
    ("AAPL",  "Apple",       "MSFT",  "Microsoft",    20),
    ("V",     "Visa",        "MA",    "Mastercard",   10),
    ("NFLX",  "Netflix",     "DIS",   "Disney",       20),
    ("LLY",   "Eli Lilly",   "PFE",   "Pfizer",       10),
    ("COST",  "Costco",      "WMT",   "Walmart",      20),
    ("GOOGL", "Google",      "META",  "Meta",         10),
    ("MCD",   "McDonald's",  "SBUX",  "Starbucks",    20),
    ("INTC",  "Intel",       "TSM",   "TSMC",         10),
    ("NKE",   "Nike",        "LULU",  "Lululemon",    10),
    ("HOOD",  "Robinhood",   "COIN",  "Coinbase",      5),
    ("HD",    "Home Depot",  "LOW",   "Lowe's",       20),
    ("UBER",  "Uber",        "LYFT",  "Lyft",          5),
    ("XOM",   "Exxon",       "CVX",   "Chevron",      10),
    ("AMZN",  "Amazon",      "BABA",  "Alibaba",      10),
    ("CAT",   "Caterpillar", "DE",    "Deere",        10),
    ("ORCL",  "Oracle",      "CRM",   "Salesforce",   10),
    ("T",     "AT&T",        "VZ",    "Verizon",      10),
    ("CRWD",  "CrowdStrike", "PANW",  "Palo Alto",     5),
    ("JPM",   "JPMorgan",    "BAC",   "Bank of America", 20),
    ("PLTR",  "Palantir",    "SNOW",  "Snowflake",     5),
    ("UPS",   "UPS",         "FDX",   "FedEx",        10),
]
ROTATION_COOLDOWN = 20

COOL = (56, 189, 248)    # sky blue
WARM = (255, 179, 71)    # amber (= ss.C["amber"])
# Brands whose logo file measures warm but whose brand reads blue (Walmart's
# logo is mostly the yellow spark).
FORCE_COOL = {"WMT"}

FPS = inv.FPS
REEL_W, REEL_H = inv.REEL_W, inv.REEL_H
HOOK_FADE_FRAMES = inv.HOOK_FADE_FRAMES
HOOK_HOLD_FRAMES = inv.HOOK_HOLD_FRAMES
HOOK_OUT_FRAMES  = inv.HOOK_OUT_FRAMES
CHART_FRAMES     = inv.CHART_FRAMES
CHART_HOLD_FRAMES = inv.CHART_HOLD_FRAMES
RESULT_FRAMES    = inv.RESULT_FRAMES
CTA_FRAMES       = inv.CTA_FRAMES
END_HOLD_FRAMES  = inv.END_HOLD_FRAMES
POP_FRAMES       = inv.POP_FRAMES

LEAD_MIN_HOLD    = 13   # weeks a new leader must stay ahead to count as a lead change...
LEAD_MIN_FRAMES  = 25   # ...raised to however many weeks this many frames of chart covers
                        # (~0.8s), so a toast is only shown for a lead that visibly held
TOAST_FRAMES     = 42   # ~1.4s on screen per lead-change toast
TOAST_FADE       = 6

COL_X = (270, 810)      # centres of the two counter columns


# ── Data ────────────────────────────────────────────────────────────────────────

def pair_key(m) -> str:
    return f"{m[0]}-{m[2]}"


def build_matchup(m, years: int, end: datetime) -> dict | None:
    a, name_a, b, name_b, _ = m
    start = end.replace(year=end.year - years)
    ta, pa = inv.fetch_weekly(a, start, end)
    tb, pb = inv.fetch_weekly(b, start, end)
    for sym, ts in ((a, ta), (b, tb)):
        if len(ts) < 20 or ts[0] - start.timestamp() > 45 * 86400:
            print(f"  {sym}: history doesn't reach back {years}y — skipping")
            return None
        if end.timestamp() - ts[-1] > 21 * 86400:
            print(f"  {sym}: no recent prices (delisted?) — skipping")
            return None
    tspy, pspy = inv.fetch_weekly(inv.BENCHMARK, start, end)

    def align(ts_other, px_other):
        idx = np.clip(np.searchsorted(ts_other, ta, side="right") - 1, 0, len(ts_other) - 1)
        return inv.INVESTED * px_other[idx] / px_other[idx[0]]

    va = inv.INVESTED * pa / pa[0]
    vb = align(tb, pb)
    vspy = align(tspy, pspy)
    span_years = (ta[-1] - ta[0]) / (365.25 * 86400)

    def side(ticker, name, v):
        final = float(v[-1])
        return {
            "ticker":      ticker,
            "name":        name,
            "final_value": round(final, 2),
            "pct_change":  round((final / inv.INVESTED - 1) * 100, 1),
            "cagr_pct":    round(((final / inv.INVESTED) ** (1 / span_years) - 1) * 100, 1),
        }

    sa, sb = side(a, name_a, va), side(b, name_b, vb)
    return {
        "a":           sa,
        "b":           sb,
        "winner":      a if sa["final_value"] >= sb["final_value"] else b,
        "years":       years,
        "start_date":  datetime.fromtimestamp(ta[0], timezone.utc).strftime("%Y-%m-%d"),
        "end_date":    datetime.fromtimestamp(ta[-1], timezone.utc).strftime("%Y-%m-%d"),
        "bench_final": round(float(vspy[-1]), 2),
        "_ts":         ta,
        "_va":         va,
        "_vb":         vb,
    }


def find_lead_changes(va: np.ndarray, vb: np.ndarray, min_hold: int = LEAD_MIN_HOLD) -> list:
    """[(index, 'a'|'b'), ...] where the lead changed hands. Hysteresis on the
    displayed leader: the trailing stock only "takes the lead" once it has
    stayed ahead for `min_hold` consecutive weeks (the toast is pinned to the
    week it first went ahead), so lines wobbling around each other don't
    produce a toast every other week. A lead change still in progress at the
    very end is always reported, so the toasts never contradict the result."""
    lead = (vb > va).astype(int)      # 0 = a ahead, 1 = b ahead
    n = len(lead)
    # Both start at $1,000, so the first few weeks' "leader" is noise —
    # whoever led most of the first min_hold weeks is the starting leader.
    cur = int(round(lead[:min(min_hold, n)].mean()))
    changes, run_start = [], None
    for i in range(n):
        if lead[i] == cur:
            run_start = None
            continue
        if run_start is None:
            run_start = i
        if i - run_start + 1 >= min_hold:
            cur = int(lead[i])
            changes.append((run_start, "ab"[cur]))
            run_start = None
    if lead[-1] != cur:
        changes.append((run_start if run_start is not None else n - 1, "ab"[int(lead[-1])]))
    return changes


def rotation_order(history: list) -> list:
    recent = history[-ROTATION_COOLDOWN:]
    fresh = [m for m in MATCHUPS if pair_key(m) not in recent]
    last_used = {k: i for i, k in enumerate(history)}
    return fresh + sorted((m for m in MATCHUPS if pair_key(m) in recent),
                          key=lambda m: last_used.get(pair_key(m), -1))


def logo_warmth(logo: Image.Image | None) -> float:
    """How red/orange/yellow a logo's saturated pixels are (-1 blue .. +1 red),
    ignoring transparent, grey and near-black pixels."""
    if logo is None:
        return 0.0
    a = np.asarray(logo.convert("RGBA").resize((64, 64))).astype(float)
    rgb, alpha = a[..., :3], a[..., 3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    mask = (alpha > 128) & ((mx - mn) / np.maximum(mx, 1) > 0.35) & (mx > 60)
    if mask.sum() < 30:
        return 0.0
    r, _, b = rgb[mask].T
    return float(np.mean(r - b) / 255)


def assign_colors(story: dict, logos: dict) -> dict:
    """Gives amber to the stock with the warmer brand and blue to the other, so
    Amazon isn't drawn blue against an orange Microsoft. Falls back to A=blue,
    B=amber when the two logos are too close to call."""
    wa, wb = (-1.0 if story[s]["ticker"] in FORCE_COOL else logo_warmth(logos[s]) for s in "ab")
    if wa - wb > 0.15:
        return {"a": WARM, "b": COOL}
    return {"a": COOL, "b": WARM}


# ── Overlays ────────────────────────────────────────────────────────────────────

def _paste_logo(overlay: Image.Image, logo: Image.Image | None, x: float, y: float, size: int) -> None:
    if logo is None:
        return
    lg = logo.resize((size, size), Image.LANCZOS)
    lg.putalpha(ss._rounded_mask(size, size, int(size * 0.22)))
    overlay.paste(lg, (int(x), int(y)), lg)


def _fit_font(draw, text: str, bold: bool, size: int, max_w: int):
    while size > 20:
        f = ss.font(bold, size)
        if inv._text_w(draw, text, f) <= max_w:
            return f
        size -= 2
    return ss.font(bold, size)


def render_hook_overlay(story: dict, logos: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 1000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx = REEL_W / 2
    y = 0

    draw.text((cx, y), "If you'd put $1,000 in", font=ss.font(False, 52),
               fill=(214, 220, 228), anchor="ma")
    y += 52 + 50

    logo_size = 110
    for i, (side, col) in enumerate(story["_colors"].items()):
        if i == 1:
            draw.text((cx, y), "vs", font=ss.font(True, 52), fill=ss.C["grey"], anchor="ma")
            y += 52 + 34
        s = story[side]
        nf = _fit_font(draw, s["name"], True, 84, REEL_W - 120 - logo_size - 24)
        nw = inv._text_w(draw, s["name"], nf)
        row_w = logo_size + 24 + nw
        x = cx - row_w / 2
        _paste_logo(overlay, logos[side], x, y, logo_size)
        draw.text((x + logo_size + 24, y + logo_size / 2), s["name"], font=nf, fill=col, anchor="lm")
        y += logo_size + 34

    y += 30
    draw.text((cx, y), f"{story['years']} years ago...", font=ss.font(True, 64),
               fill=ss.C["white"], anchor="ma")
    y += 64 + 60
    draw.text((cx, y), "who wins?", font=ss.font(True, 56), fill=ss.C["teal"], anchor="ma")
    y += 56 + 10
    return overlay.crop((0, 0, REEL_W, y))


def render_names_row(story: dict, logos: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    logo_size = 60
    for side, cx in zip("ab", COL_X):
        s = story[side]
        nf = _fit_font(draw, s["name"], True, 40, 440 - logo_size - 16)
        nw = inv._text_w(draw, s["name"], nf)
        x = cx - (logo_size + 16 + nw) / 2
        _paste_logo(overlay, logos[side], x, 10, logo_size)
        draw.text((x + logo_size + 16, 40), s["name"], font=nf, fill=ss.C["white"], anchor="lm")
    draw.text((REEL_W / 2, 40), "vs", font=ss.font(True, 32), fill=ss.C["grey"], anchor="mm")
    return overlay


def render_toast(name: str, color) -> Image.Image:
    text = f"{name} takes the lead"
    f = ss.font(True, 32)
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = inv._text_w(dummy, text, f) + 60
    h = 58
    overlay = Image.new("RGBA", (REEL_W, h + 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0 = (REEL_W - w) / 2
    draw.rounded_rectangle([x0, 0, x0 + w, h], radius=h / 2, fill=ss.C["card"],
                            outline=color, width=3)
    draw.text((REEL_W / 2, h / 2), text, font=f, fill=color, anchor="mm")
    return overlay


def render_result_overlay(story: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 260), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    pill_w, pill_h, gap, top = 450, 150, 40, 22
    x0 = (REEL_W - 2 * pill_w - gap) / 2

    for i, (side, col) in enumerate(story["_colors"].items()):
        s = story[side]
        x = x0 + i * (pill_w + gap)
        won = s["ticker"] == story["winner"]
        draw.rounded_rectangle([x, top, x + pill_w, top + pill_h], radius=26,
                                fill=ss.C["card"], outline=col, width=5 if won else 2)
        draw.text((x + pill_w / 2, top + 54), inv.fmt_money(s["final_value"]),
                   font=ss.font(True, 58), fill=col, anchor="mm")
        draw.text((x + pill_w / 2, top + 114), f"{s['pct_change']:+,.0f}%  ·  {s['cagr_pct']:+.1f}%/yr",
                   font=ss.font(False, 28), fill=(214, 220, 228), anchor="mm")
        if won:
            tf = ss.font(True, 24)
            tw = inv._text_w(draw, "WINNER", tf) + 36
            tx = x + (pill_w - tw) / 2
            draw.rounded_rectangle([tx, top - 20, tx + tw, top + 20], radius=20, fill=col)
            draw.text((tx + tw / 2, top), "WINNER", font=tf, fill=ss.C["bg"], anchor="mm")

    draw.text((REEL_W / 2, top + pill_h + 44),
               f"Same $1,000 in the S&P 500: {inv.fmt_money(story['bench_final'])}  ·  Dividends reinvested",
               font=ss.font(False, 24), fill=ss.C["grey"], anchor="mm")
    return overlay


def render_cta_overlay() -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 70), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text((REEL_W / 2, 35), "Which matchup next? Comment below",
               font=ss.font(True, 38), fill=ss.C["teal"], anchor="mm")
    return overlay


# ── Frames ──────────────────────────────────────────────────────────────────────

def render_frames(story: dict, out_dir: Path) -> int:
    logos = {"a": load_logo_pil(story["a"]["ticker"]), "b": load_logo_pil(story["b"]["ticker"])}
    va, vb, ts = story["_va"], story["_vb"], story["_ts"]
    n = len(va)

    base = ss._diagonal_gradient(REEL_W, REEL_H, ss.C["bg"], ss.C["bg2"]).convert("RGBA")
    footer_band = Image.new("RGBA", (REEL_W, REEL_H), (0, 0, 0, 0))
    ss.draw_footer(footer_band, ss.load_brand_logo())
    base.alpha_composite(footer_band)

    story["_colors"] = assign_colors(story, logos)
    ca, cb = story["_colors"]["a"], story["_colors"]["b"]
    hook = render_hook_overlay(story, logos)
    content_top = inv.TOP_SAFE_PAD + 120
    content_bot = REEL_H - inv.FOOTER_ZONE
    hook_y = content_top + (content_bot - content_top - hook.height) // 2 - 40

    names = render_names_row(story, logos)
    result = render_result_overlay(story)
    cta = render_cta_overlay()
    toasts = {side: render_toast(story[side]["name"], col)
              for side, col in story["_colors"].items()}

    # Same vertical rhythm as the single-stock reel; everything above ~y=1600
    # (the bottom of a Reel sits under Instagram's caption overlay).
    NAMES_Y  = 240
    VALUE_Y  = 385
    DATE_Y   = 470
    TOAST_Y  = 510
    RESULT_Y = inv.CHART_Y1 + 40
    CTA_Y    = RESULT_Y + result.height + 20

    value_fonts = {}
    date_font = ss.font(False, 34)
    frame_idx = 0

    def save(img):
        nonlocal frame_idx
        img.convert("RGB").save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    # 1. Hook card
    for f in range(HOOK_FADE_FRAMES):
        t = inv.ease_out_cubic((f + 1) / HOOK_FADE_FRAMES)
        img = base.copy()
        scale = 0.9 + 0.1 * t
        sw, sh = round(hook.width * scale), round(hook.height * scale)
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

    # 2. Race
    running_max = np.maximum.accumulate(np.maximum(va, vb))
    chart_base = base.copy()
    chart_base.paste(names, (0, NAMES_Y), names)

    def value_font(size):
        if size not in value_fonts:
            value_fonts[size] = ss.font(True, size)
        return value_fonts[size]

    def chart_frame(k, pops=(0.0, 0.0)):
        kk = min(int(np.floor(k)), n - 1)
        ymax = max(running_max[kk] * 1.12, inv.INVESTED * 1.6)
        layer = inv.render_chart_layer(va, vb, k, ymax, ca, (), bench_color=cb,
                                       bench_width=7, area_fill=False)
        img = chart_base.copy()
        img.paste(layer, (inv.CHART_X0, inv.CHART_Y0), layer)
        draw = ImageDraw.Draw(img)
        frac = k - kk
        for series, col, cx, pop in ((va, ca, COL_X[0], pops[0]), (vb, cb, COL_X[1], pops[1])):
            v = series[kk] if kk >= n - 1 else series[kk] + (series[kk + 1] - series[kk]) * frac
            text = inv.fmt_money(float(v))
            size = round(92 * (1 + 0.14 * pop))
            while size > 40 and inv._text_w(draw, text, value_font(size)) > 480:
                size -= 4
            draw.text((cx, VALUE_Y), text, font=value_font(size), fill=col, anchor="mm")
        when = datetime.fromtimestamp(ts[kk], timezone.utc).strftime("%b %Y")
        draw.text((REEL_W / 2, DATE_Y), when, font=date_font, fill=(183, 185, 191), anchor="mm")
        return img

    min_hold = max(LEAD_MIN_HOLD, int(np.ceil(n * LEAD_MIN_FRAMES / CHART_FRAMES)))
    changes = find_lead_changes(va, vb, min_hold)
    shown = []          # (start frame, side) of each toast
    seen = 0
    for f in range(CHART_FRAMES):
        t = (f + 1) / CHART_FRAMES
        k = (inv.ease_in_out(t) * 0.25 + t * 0.75) * (n - 1)
        while seen < len(changes) and changes[seen][0] <= k:
            shown.append((f, changes[seen][1]))
            seen += 1

        pops = [0.0, 0.0]
        toast = None
        if shown and f - shown[-1][0] < TOAST_FRAMES:
            age, side = f - shown[-1][0], shown[-1][1]
            pops["ab".index(side)] = inv.ease_out_cubic(max(0.0, 1 - age / POP_FRAMES))
            alpha = min(1.0, (age + 1) / TOAST_FADE, (TOAST_FRAMES - age) / TOAST_FADE)
            toast = inv.with_alpha(toasts[side], alpha)

        img = chart_frame(k, pops)
        if toast is not None:
            img.paste(toast, (0, TOAST_Y), toast)
        save(img)

    final = chart_frame(n - 1)
    for _ in range(CHART_HOLD_FRAMES):
        save(final)

    # 3. Result cards, then CTA
    for f in range(RESULT_FRAMES):
        t = inv.ease_out_cubic((f + 1) / RESULT_FRAMES)
        img = final.copy()
        faded = inv.with_alpha(result, t)
        img.paste(faded, (0, RESULT_Y + int(20 * (1 - t))), faded)
        save(img)
    final.paste(result, (0, RESULT_Y), result)
    for f in range(CTA_FRAMES):
        img = final.copy()
        faded = inv.with_alpha(cta, (f + 1) / CTA_FRAMES)
        img.paste(faded, (0, CTA_Y), faded)
        save(img)
    final.paste(cta, (0, CTA_Y), cta)
    for _ in range(END_HOLD_FRAMES):
        save(final)

    print(f"  lead changes: {len(changes)} (min hold {min_hold} weeks)")
    return frame_idx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD label override (defaults to today, UTC)")
    parser.add_argument("--pair", help="force a matchup, e.g. NVDA-AMD")
    parser.add_argument("--years", type=int, help="override the lookback period")
    parser.add_argument("--out", help="output mp4 path override")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    date_obj = (datetime.strptime(forced, "%Y-%m-%d").date() if forced
                else datetime.now(timezone.utc).date())
    date_str = date_obj.strftime("%Y-%m-%d")

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {}
    history = tracking.get("matchups", [])

    forced_pair = (args.pair or os.environ.get("FORCE_PAIR") or "").upper()
    if forced_pair:
        a, b = forced_pair.split("-", 1)
        known = {pair_key(m): m for m in MATCHUPS}
        names = {t: n for t, (n, _) in inv.CANDIDATES.items()}
        to_try = [known.get(forced_pair) or (a, names.get(a, a), b, names.get(b, b), 10)]
    else:
        to_try = rotation_order(history)[:5]
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    story = None
    for m in to_try:
        years = args.years or m[4]
        print(f"Building {m[0]} vs {m[2]} ({years}y) matchup...")
        try:
            story = build_matchup(m, years, end)
        except Exception as e:
            print(f"  {pair_key(m)}: fetch failed ({e}) — trying the next one")
        if story is not None:
            break
    if story is None:
        sys.exit(1)
    for s in (story["a"], story["b"]):
        print(f"  {s['ticker']}: $1,000 -> {inv.fmt_money(s['final_value'])} ({s['pct_change']:+,.1f}%)")
    print(f"  winner: {story['winner']}  (S&P 500: {inv.fmt_money(story['bench_final'])})")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        n_frames = render_frames(story, tmp_path)
        print(f"  rendered {n_frames} frames @ {FPS}fps (~{n_frames / FPS:.1f}s)")
        audio_credit = reel_audio.encode_video(tmp_path, out_path, FPS, n_frames, "h2h")
        print(f"  audio: {audio_credit}")

    manifest = {k: v for k, v in story.items() if not k.startswith("_")}
    manifest.update({"date": date_str, "pair": f"{story['a']['ticker']}-{story['b']['ticker']}",
                     "audio_credit": audio_credit})
    REEL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    try:
        shown_path = out_path.relative_to(ROOT)
    except ValueError:
        shown_path = out_path
    print(f"  video saved -> {shown_path}")


if __name__ == "__main__":
    main()
