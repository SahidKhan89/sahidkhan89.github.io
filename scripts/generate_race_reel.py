#!/usr/bin/env python3
"""
generate_race_reel.py — "$1,000 race": a bar chart race of $1,000 invested in
each stock of a themed group (Magnificent 7, chipmakers, fast food...) plus
the S&P 500 for scale, with bars re-sorting as the years tick by and the
winner called out at the end.

Built from the same Yahoo weekly adjusted closes as the $1,000 reel (via
generate_investment_reel.fetch_weekly), so no market-cap history is needed —
every bar starts at $1,000 and the race is purely total return. Each bar is
coloured from its company logo.

Rotates through RACES (data/posted_race_reel.json); override with --race.

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
OUTPUT_DIR    = ROOT / "images" / "race-reel"
REEL_MANIFEST = Path(__file__).parent / "_race_reel_manifest.json"
TRACKING      = ROOT / "data" / "posted_race_reel.json"

# key -> (title, years, [(ticker, name), ...]). 5-7 members reads best at
# reel size; every member needs history for the full lookback.
RACES = {
    "mag7":     ("the Magnificent 7", 10, [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("GOOGL", "Google"),
                                           ("AMZN", "Amazon"), ("NVDA", "NVIDIA"), ("META", "Meta"),
                                           ("TSLA", "Tesla")]),
    "airlines": ("airlines", 10, [("DAL", "Delta"), ("UAL", "United"), ("AAL", "American"),
                                  ("LUV", "Southwest"), ("ALK", "Alaska Air")]),
    "sportswear": ("sportswear", 10, [("NKE", "Nike"), ("LULU", "Lululemon"), ("DECK", "Deckers (Hoka)"),
                                      ("CROX", "Crocs"), ("UAA", "Under Armour"), ("ADDYY", "Adidas")]),
    # No Wendy's: before its 2008 merger the WEN ticker's history is Triarc's,
    # so a 20-year "Wendy's" line would really be a different company.
    "food":     ("fast food", 20, [("MCD", "McDonald's"), ("SBUX", "Starbucks"), ("CMG", "Chipotle"),
                                   ("DPZ", "Domino's"), ("YUM", "Yum! Brands")]),
    "crypto":   ("crypto stocks", 5, [("COIN", "Coinbase"), ("MSTR", "Strategy"), ("HOOD", "Robinhood"),
                                      ("MARA", "MARA"), ("RIOT", "Riot")]),
    "oil":      ("oil majors", 10, [("XOM", "Exxon"), ("CVX", "Chevron"), ("SHEL", "Shell"),
                                    ("BP", "BP"), ("COP", "ConocoPhillips"), ("TTE", "TotalEnergies")]),
    "pharma":   ("big pharma", 10, [("LLY", "Eli Lilly"), ("NVO", "Novo Nordisk"), ("JNJ", "Johnson & Johnson"),
                                    ("PFE", "Pfizer"), ("MRK", "Merck"), ("ABBV", "AbbVie"), ("AZN", "AstraZeneca")]),
    "chips":    ("chipmakers", 10, [("NVDA", "NVIDIA"), ("AMD", "AMD"), ("INTC", "Intel"),
                                    ("AVGO", "Broadcom"), ("QCOM", "Qualcomm"), ("TSM", "TSMC"),
                                    ("MU", "Micron")]),
    "telecom":  ("telecom", 10, [("TMUS", "T-Mobile"), ("VZ", "Verizon"), ("T", "AT&T"),
                                 ("CMCSA", "Comcast"), ("CHTR", "Charter")]),
    "cars":     ("car makers", 10, [("TSLA", "Tesla"), ("F", "Ford"), ("GM", "GM"), ("TM", "Toyota"),
                                    ("HMC", "Honda"), ("RACE", "Ferrari")]),
    "retail":   ("retail giants", 20, [("WMT", "Walmart"), ("COST", "Costco"), ("TGT", "Target"),
                                       ("HD", "Home Depot"), ("AMZN", "Amazon"), ("LOW", "Lowe's")]),
    "gaming":   ("video games", 10, [("TTWO", "Take-Two"), ("NTDOY", "Nintendo"), ("SONY", "Sony"),
                                     ("NTES", "NetEase"), ("UBSFY", "Ubisoft")]),
    "ai":       ("AI stocks", 5, [("NVDA", "NVIDIA"), ("PLTR", "Palantir"), ("AMD", "AMD"),
                                  ("AVGO", "Broadcom"), ("SMCI", "Super Micro"), ("MSFT", "Microsoft")]),
    "defence":  ("defence", 10, [("LMT", "Lockheed Martin"), ("NOC", "Northrop Grumman"), ("RTX", "RTX"),
                                 ("GD", "General Dynamics"), ("LHX", "L3Harris"), ("BA", "Boeing")]),
    "drinks":   ("drinks", 10, [("KO", "Coca-Cola"), ("PEP", "PepsiCo"), ("MNST", "Monster"),
                                ("KDP", "Keurig Dr Pepper"), ("STZ", "Constellation"), ("BUD", "AB InBev")]),
    "luxury":   ("luxury", 10, [("RACE", "Ferrari"), ("LVMUY", "LVMH"), ("HESAY", "Hermès"),
                                ("TPR", "Tapestry"), ("RL", "Ralph Lauren"), ("CPRI", "Capri")]),
    "banks":    ("big banks", 20, [("JPM", "JPMorgan"), ("BAC", "Bank of America"), ("WFC", "Wells Fargo"),
                                   ("C", "Citigroup"), ("GS", "Goldman Sachs"), ("MS", "Morgan Stanley")]),
    "ecommerce": ("e-commerce", 10, [("AMZN", "Amazon"), ("SHOP", "Shopify"), ("MELI", "MercadoLibre"),
                                     ("EBAY", "eBay"), ("ETSY", "Etsy"), ("BABA", "Alibaba")]),
    "homebuilders": ("homebuilders", 10, [("DHI", "D.R. Horton"), ("LEN", "Lennar"), ("PHM", "PulteGroup"),
                                          ("NVR", "NVR"), ("TOL", "Toll Brothers")]),
    "media":    ("streaming & media", 5, [("NFLX", "Netflix"), ("DIS", "Disney"), ("SPOT", "Spotify"),
                                          ("ROKU", "Roku"), ("WBD", "Warner Bros"), ("CMCSA", "Comcast")]),
    "travel":   ("travel", 5, [("BKNG", "Booking"), ("ABNB", "Airbnb"), ("EXPE", "Expedia"),
                               ("MAR", "Marriott"), ("HLT", "Hilton")]),
    "payments": ("payments", 10, [("V", "Visa"), ("MA", "Mastercard"), ("PYPL", "PayPal"),
                                  ("AXP", "American Express"), ("XYZ", "Block")]),
    "software": ("software", 10, [("MSFT", "Microsoft"), ("ORCL", "Oracle"), ("CRM", "Salesforce"),
                                  ("ADBE", "Adobe"), ("NOW", "ServiceNow"), ("INTU", "Intuit")]),
    "techgiants": ("tech giants", 20, [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("AMZN", "Amazon"),
                                       ("GOOGL", "Google"), ("NVDA", "NVIDIA"), ("CSCO", "Cisco"), ("INTC", "Intel")]),
}
ROTATION_COOLDOWN = 16
BENCH = ("SPY", "S&P 500")

FPS = inv.FPS
REEL_W, REEL_H = inv.REEL_W, inv.REEL_H

HOOK_FADE_FRAMES = 8
HOOK_HOLD_FRAMES = 74
HOOK_OUT_FRAMES  = 8
RACE_FRAMES      = 720     # ~24s for the race — slow enough to read the numbers as they move
WINNER_FRAMES    = 14
CTA_FRAMES       = 12
END_HOLD_FRAMES  = 124     # winner + CTA ≈ 5s in all

BARS_Y0   = 470            # top of the first bar slot
SLOT_H    = 128
BAR_H     = 92
LOGO      = 76
BAR_X0    = 60 + LOGO + 18
BAR_MAX_W = 690            # leaves room for the value label after the longest bar
POS_EASE  = 0.3            # per-frame easing toward a bar's new rank slot (fast, so
                           # two bars trading places overlap only briefly)
SWAP_HYST = 0.04           # neighbours only swap once the lower one leads by 4% —
                           # neck-and-neck stocks otherwise trade places every week
                           # and the bars/labels pile on top of each other

FALLBACK_COLORS = [(56, 189, 248), (255, 179, 71), (167, 139, 250), (244, 114, 182),
                   (52, 211, 153), (251, 146, 60), (96, 165, 250)]


def logo_color(logo: Image.Image | None, i: int) -> tuple:
    """Mean colour of the logo's saturated pixels, brightened so the bar
    reads on the dark background; a palette colour if the logo is
    greyscale/black (Apple, Tesla...)."""
    if logo is not None:
        a = np.asarray(logo.convert("RGBA").resize((64, 64))).astype(float)
        rgb, alpha = a[..., :3], a[..., 3]
        mx, mn = rgb.max(-1), rgb.min(-1)
        mask = (alpha > 128) & ((mx - mn) / np.maximum(mx, 1) > 0.35) & (mx > 60)
        if mask.sum() >= 30:
            c = rgb[mask].mean(0)
            c = c * (230 / max(c.max(), 1))   # lift to a bright, saturated tone
            return tuple(int(v) for v in c)
    return FALLBACK_COLORS[i % len(FALLBACK_COLORS)]


def build_race(key: str, end: datetime) -> dict:
    title, years, members = RACES[key]
    start = end.replace(year=end.year - years)
    bts, bpx = inv.fetch_weekly(BENCH[0], start, end)
    series = []
    for ticker, name in members + [BENCH]:
        ts, px = (bts, bpx) if ticker == BENCH[0] else inv.fetch_weekly(ticker, start, end)
        if len(ts) < 20 or ts[0] - start.timestamp() > 45 * 86400:
            print(f"  {ticker}: history doesn't reach back {years}y — leaving it out")
            continue
        # A delisted/taken-private stock's history stops early; aligning it
        # would carry its last price forward as if it were today's value.
        if end.timestamp() - ts[-1] > 21 * 86400:
            print(f"  {ticker}: no recent prices (delisted?) — leaving it out")
            continue
        idx = np.clip(np.searchsorted(ts, bts, side="right") - 1, 0, len(ts) - 1)
        series.append({"ticker": ticker, "name": name, "values": inv.INVESTED * px[idx] / px[idx[0]],
                       "bench": ticker == BENCH[0]})
    if len([s for s in series if not s["bench"]]) < 4:
        raise RuntimeError(f"{key}: fewer than 4 members with full history")
    for s in series:
        s["final_value"] = round(float(s["values"][-1]), 2)
    winner = max((s for s in series if not s["bench"]), key=lambda s: s["final_value"])
    bench = next(s for s in series if s["bench"])
    return {"key": key, "title": title, "years": years, "series": series, "ts": bts,
            "winner": winner["ticker"], "winner_name": winner["name"],
            "winner_value": winner["final_value"],
            # The index beating every stock in the group is its own story.
            "index_won": bench["final_value"] > winner["final_value"]}


def rotation_order(history: list) -> list:
    recent = history[-ROTATION_COOLDOWN:]
    fresh = [k for k in RACES if k not in recent]
    last_used = {k: i for i, k in enumerate(history)}
    return fresh + sorted((k for k in RACES if k in recent), key=lambda k: last_used.get(k, -1))


# ── Overlays ────────────────────────────────────────────────────────────────────

def render_hook(race: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 1000), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, y = REEL_W / 2, 0
    d.text((cx, y), "$1,000 RACE", font=ss.font(True, 120), fill=ss.C["teal"], anchor="ma")
    y += 120 + 50
    d.text((cx, y), f"$1,000 in each of {race['title']},", font=ss.font(False, 48),
           fill=(214, 220, 228), anchor="ma")
    y += 48 + 18
    d.text((cx, y), f"{race['years']} years ago...", font=ss.font(True, 64), fill=ss.C["white"], anchor="ma")
    y += 64 + 50
    # Logo strip so the cover frame shows who's racing
    members = [s for s in race["series"] if not s["bench"]]
    size, gap = 96, 22
    x = (REEL_W - (len(members) * size + (len(members) - 1) * gap)) / 2
    for s in members:
        if s["logo"] is not None:
            lg = s["logo"].resize((size, size), Image.LANCZOS)
            lg.putalpha(ss._rounded_mask(size, size, int(size * 0.22)))
            overlay.paste(lg, (int(x), int(y)), lg)
        x += size + gap
    y += size + 60
    d.text((cx, y), "Who finishes first?", font=ss.font(True, 52), fill=ss.C["amber"], anchor="ma")
    y += 52 + 10
    return overlay.crop((0, 0, REEL_W, y))


def render_header(race: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.text((REEL_W / 2, 30), "$1,000 RACE", font=ss.font(True, 44), fill=ss.C["teal"], anchor="mm")
    d.text((REEL_W / 2, 88), f"{race['title'][0].upper()}{race['title'][1:]}  ·  {race['years']} years",
           font=ss.font(False, 36), fill=(214, 220, 228), anchor="mm")
    return overlay


def draw_bar(img: Image.Image, s: dict, y: float, length: float, value: float, highlight: bool) -> None:
    d = ImageDraw.Draw(img)
    cy = y + BAR_H / 2
    # logo (or a text tile for the S&P 500)
    if s["logo"] is not None:
        img.paste(s["logo_tile"], (60, int(cy - LOGO / 2)), s["logo_tile"])
    else:
        # The S&P 500 (or a stock with no logo available) gets a text tile.
        label = "S&P" if s["bench"] else s["ticker"][:4]
        d.rounded_rectangle([60, cy - LOGO / 2, 60 + LOGO, cy + LOGO / 2], radius=16, fill=ss.C["card"],
                            outline=s["color"], width=2)
        d.text((60 + LOGO / 2, cy), label, font=ss.font(True, 24 if len(label) <= 3 else 20),
               fill=s["color"], anchor="mm")
    col = s["color"]
    w = max(8.0, length)
    d.rounded_rectangle([BAR_X0, y, BAR_X0 + w, y + BAR_H], radius=14, fill=col)
    if highlight:
        d.rounded_rectangle([BAR_X0 - 4, y - 4, BAR_X0 + w + 4, y + BAR_H + 4], radius=18,
                            outline=ss.C["white"], width=4)
    # name inside the bar if it fits, else after it
    nf = ss.font(True, 32)
    name_w = inv._text_w(d, s["name"], nf)
    vf = ss.font(True, 34)
    if name_w + 36 < w:
        d.text((BAR_X0 + 18, cy), s["name"], font=nf, fill=ss.C["bg"], anchor="lm")
        d.text((BAR_X0 + w + 14, cy), inv.fmt_money(value), font=vf, fill=ss.C["white"], anchor="lm")
    else:
        d.text((BAR_X0 + w + 14, cy - 18), s["name"], font=ss.font(True, 26), fill=(214, 220, 228), anchor="lm")
        d.text((BAR_X0 + w + 14, cy + 18), inv.fmt_money(value), font=ss.font(True, 30),
               fill=ss.C["white"], anchor="lm")


def render_winner(race: dict) -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 170), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    bench = next(s for s in race["series"] if s["bench"])
    if race["index_won"]:
        d.text((REEL_W / 2, 45), "The S&P 500 beat them all", font=ss.font(True, 60),
               fill=ss.C["amber"], anchor="mm")
        d.text((REEL_W / 2, 110), f"Index: {inv.fmt_money(bench['final_value'])}  ·  Best stock: "
               f"{race['winner_name']} {inv.fmt_money(race['winner_value'])}  ·  Dividends reinvested",
               font=ss.font(False, 28), fill=(214, 220, 228), anchor="mm")
    else:
        d.text((REEL_W / 2, 45), f"{race['winner_name']} wins: {inv.fmt_money(race['winner_value'])}",
               font=ss.font(True, 60), fill=ss.C["green"], anchor="mm")
        d.text((REEL_W / 2, 110), f"Same $1,000 in the S&P 500: {inv.fmt_money(bench['final_value'])}  ·  "
               "Dividends reinvested", font=ss.font(False, 28), fill=(214, 220, 228), anchor="mm")
    return overlay


def render_cta() -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 70), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).text((REEL_W / 2, 35), "Which group should we race next?",
                                 font=ss.font(True, 40), fill=ss.C["teal"], anchor="mm")
    return overlay


# ── Frames ──────────────────────────────────────────────────────────────────────

def render_frames(race: dict, out_dir: Path) -> int:
    series, ts = race["series"], race["ts"]
    n = len(ts)
    for i, s in enumerate(series):
        s["logo"] = None if s["bench"] else load_logo_pil(s["ticker"])
        s["color"] = inv.BENCH_COLOR if s["bench"] else logo_color(s["logo"], i)
        if s["logo"] is not None:
            lt = s["logo"].resize((LOGO, LOGO), Image.LANCZOS)
            lt.putalpha(ss._rounded_mask(LOGO, LOGO, int(LOGO * 0.22)))
            s["logo_tile"] = lt

    base = ss._diagonal_gradient(REEL_W, REEL_H, ss.C["bg"], ss.C["bg2"]).convert("RGBA")
    footer = Image.new("RGBA", (REEL_W, REEL_H), (0, 0, 0, 0))
    ss.draw_footer(footer, ss.load_brand_logo())
    base.alpha_composite(footer)

    hook = render_hook(race)
    top, bot = inv.TOP_SAFE_PAD + 120, REEL_H - inv.FOOTER_ZONE
    hook_y = top + (bot - top - hook.height) // 2 - 40
    header = render_header(race)
    winner, cta = render_winner(race), render_cta()
    year_font = ss.font(True, 120)
    bars_bottom = BARS_Y0 + len(series) * SLOT_H
    WINNER_Y = bars_bottom + 10
    CTA_Y = WINNER_Y + winner.height + 10

    frame_idx = 0

    def save(img):
        nonlocal frame_idx
        img.convert("RGB").save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

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

    race_base = base.copy()
    race_base.paste(header, (0, 250), header)
    pos = {s["ticker"]: float(i) for i, s in enumerate(series)}   # smoothed rank slot per bar
    order = list(series)                                            # current displayed ranking
    # Bars scale to the current leader, eased so the axis doesn't jump when
    # the lead changes hands.
    scale_max = inv.INVESTED

    def race_frame(k: float, highlight: str | None = None, settle: bool = False):
        nonlocal scale_max, order
        kk = min(int(np.floor(k)), n - 1)
        frac = k - kk
        vals = {}
        for s in series:
            v = s["values"]
            vals[s["ticker"]] = float(v[kk] if kk >= n - 1 else v[kk] + (v[kk + 1] - v[kk]) * frac)
        if settle:
            order = sorted(series, key=lambda s: -vals[s["ticker"]])
        else:
            # Bubble passes with hysteresis: a bar only moves up past its
            # neighbour once it's clearly ahead, so order always matches the
            # bar lengths to within SWAP_HYST and never flickers.
            swapped = True
            while swapped:
                swapped = False
                for i in range(len(order) - 1):
                    if vals[order[i + 1]["ticker"]] > vals[order[i]["ticker"]] * (1 + SWAP_HYST):
                        order[i], order[i + 1] = order[i + 1], order[i]
                        swapped = True
        for rank, s in enumerate(order):
            p = pos[s["ticker"]]
            pos[s["ticker"]] = rank if settle else p + (rank - p) * POS_EASE
        target = max(vals.values())
        scale_max = target if settle else scale_max + (target - scale_max) * 0.25
        img = race_base.copy()
        # draw back-to-front so a bar overtaking slides over the one it passes
        for s in sorted(series, key=lambda s: -pos[s["ticker"]]):
            y = BARS_Y0 + pos[s["ticker"]] * SLOT_H
            length = vals[s["ticker"]] / max(scale_max, 1) * BAR_MAX_W
            draw_bar(img, s, y, length, vals[s["ticker"]], highlight == s["ticker"])
        d = ImageDraw.Draw(img)
        d.text((REEL_W - 60, bars_bottom - 30), datetime.fromtimestamp(ts[kk], timezone.utc).strftime("%Y"),
               font=year_font, fill=(*ss.C["grey"],), anchor="rs")
        return img

    for f in range(RACE_FRAMES):
        t = (f + 1) / RACE_FRAMES
        k = (inv.ease_in_out(t) * 0.25 + t * 0.75) * (n - 1)
        save(race_frame(k))

    final = race_frame(n - 1, highlight=BENCH[0] if race["index_won"] else race["winner"], settle=True)
    for f in range(WINNER_FRAMES):
        t = inv.ease_out_cubic((f + 1) / WINNER_FRAMES)
        img = final.copy()
        w = inv.with_alpha(winner, t)
        img.paste(w, (0, WINNER_Y + int(20 * (1 - t))), w)
        save(img)
    final.paste(winner, (0, WINNER_Y), winner)
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
    parser.add_argument("--race", choices=sorted(RACES), help="force a race instead of the rotation")
    parser.add_argument("--out", help="output mp4 path override")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    date_obj = (datetime.strptime(forced, "%Y-%m-%d").date() if forced
                else datetime.now(timezone.utc).date())
    date_str = date_obj.strftime("%Y-%m-%d")

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {}
    forced_race = args.race or os.environ.get("FORCE_RACE")
    to_try = [forced_race] if forced_race else rotation_order(tracking.get("races", []))[:4]
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    race = None
    for key in to_try:
        print(f"Building race '{key}'...")
        try:
            race = build_race(key, end)
            break
        except Exception as e:
            print(f"  {key}: {e} — trying the next one")
    if race is None:
        sys.exit(1)
    for s in sorted(race["series"], key=lambda s: -s["final_value"]):
        print(f"  {s['name']:18} {inv.fmt_money(s['final_value'])}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        n_frames = render_frames(race, Path(tmp))
        print(f"  rendered {n_frames} frames @ {FPS}fps (~{n_frames / FPS:.1f}s)")
        audio = reel_audio.encode_video(Path(tmp), out_path, FPS, n_frames, "race")
        print(f"  audio: {audio}")

    manifest = {"race": race["key"], "title": race["title"], "years": race["years"],
                "winner": race["winner"], "winner_name": race["winner_name"], "index_won": race["index_won"],
                "results": {s["ticker"]: s["final_value"] for s in race["series"]},
                "members": [{"ticker": s["ticker"], "name": s["name"]} for s in race["series"]],
                "date": date_str, "audio_credit": audio}
    REEL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  video saved -> {out_path}")


if __name__ == "__main__":
    main()
