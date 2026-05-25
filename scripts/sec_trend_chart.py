#!/usr/bin/env python3
"""
sec_trend_chart.py — Multi-quarter earnings trend chart for social media.

Pulls 6-8 quarters of revenue, gross profit and net income directly from
SEC EDGAR XBRL. No analyst estimates needed.

Usage:
    python sec_trend_chart.py NVDA
    python sec_trend_chart.py AAPL --quarters 6
    python sec_trend_chart.py MSFT --output chart.png
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D
from PIL import Image, ImageDraw

# ── Brand palette ──────────────────────────────────────────────────────────────
C = {
    "bg":      "#07101f",
    "card":    "#0d1829",
    "hdr_l":   "#14d1c3",
    "hdr_r":   "#0097a7",
    "teal":    "#14d1c3",
    "green":   "#3de07a",
    "red":     "#ff4d6d",
    "amber":   "#ffb347",
    "white":   "#ffffff",
    "grey":    "#6e7f96",
    "div":     "#1a2640",
    "rev_bar": "#14d1c3",
    "ni_bar":  "#3de07a",
}
FIGW, FIGH, DPI = 10.8, 13.5, 100   # 1080×1350 — Instagram feed 4:5
LOGO_DIR = Path(__file__).parent.parent / "logos"  # repo-root/logos/

SEC = "https://data.sec.gov"
UA  = {"User-Agent": "StockScore App sahidkhan@live.co.uk"}

TAGS = {
    "revenue":      ["RevenueFromContractWithCustomerExcludingAssessedTax",
                     "Revenues", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "net_income":   ["NetIncomeLoss"],
}

# ── SEC EDGAR helpers ──────────────────────────────────────────────────────────

def get_cik(ticker: str) -> tuple[str, str]:
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=UA, timeout=15)
    r.raise_for_status()
    for e in r.json().values():
        if e["ticker"].upper() == ticker.upper():
            return str(e["cik_str"]).zfill(10), e["title"]
    raise ValueError(f"Ticker '{ticker}' not found")


def fetch_facts(cik: str) -> dict:
    r = requests.get(f"{SEC}/api/xbrl/companyfacts/CIK{cik}.json",
                     headers=UA, timeout=30)
    r.raise_for_status()
    return r.json().get("facts", {}).get("us-gaap", {})


def get_quarterly_values(facts: dict, tags: list) -> list:
    """Return all single-quarter USD entries sorted chronologically.

    Q1/Q2/Q3 come directly from 10-Q filings (75–105 day spans).
    Q4 is derived as annual (10-K) minus Q1+Q2+Q3, because most companies
    do not file a separate 10-Q for Q4 — only the 10-K annual total.
    """
    qtrs   = {}   # end_date_str → {end, val}
    annual = {}   # (fy_start_str, fy_end_str) → {fy_start, fy_end, val}

    for tag in tags:
        if tag not in facts:
            continue
        for e in facts[tag].get("units", {}).get("USD", []):
            if "start" not in e or "end" not in e:
                continue
            try:
                start_dt = datetime.strptime(e["start"], "%Y-%m-%d")
                end_dt   = datetime.strptime(e["end"],   "%Y-%m-%d")
                days     = (end_dt - start_dt).days
            except ValueError:
                continue

            form = e.get("form", "")
            if form == "10-Q" and 75 <= days <= 105:
                key = e["end"]
                if key not in qtrs:
                    qtrs[key] = {"end": end_dt, "val": e["val"]}
            elif form == "10-K" and 340 <= days <= 380:
                key = (e["start"], e["end"])
                if key not in annual:
                    annual[key] = {"fy_start": start_dt, "fy_end": end_dt,
                                   "fy_end_str": e["end"], "val": e["val"]}

    # Derive Q4 = annual − (Q1 + Q2 + Q3) for each fiscal year
    for fy in annual.values():
        q4_end_str = fy["fy_end_str"]
        if q4_end_str in qtrs:
            continue   # Q4 already present (rare edge case)
        in_fy = [v for v in qtrs.values()
                 if fy["fy_start"] < v["end"] < fy["fy_end"]]
        if len(in_fy) == 3:
            q4_val = fy["val"] - sum(q["val"] for q in in_fy)
            qtrs[q4_end_str] = {"end": fy["fy_end"], "val": q4_val}

    return sorted(qtrs.values(), key=lambda x: x["end"])


def build_trend(facts: dict, n: int = 8) -> list:
    """Return last n quarters with revenue, gross_profit, net_income."""
    def to_map(rows):
        return {r["end"].strftime("%Y-%m-%d"): r["val"] for r in rows}

    rev_rows   = get_quarterly_values(facts, TAGS["revenue"])
    gross_rows = get_quarterly_values(facts, TAGS["gross_profit"])
    ni_rows    = get_quarterly_values(facts, TAGS["net_income"])

    gross_map = to_map(gross_rows)
    ni_map    = to_map(ni_rows)

    quarters = []
    for r in rev_rows[-n:]:
        key = r["end"].strftime("%Y-%m-%d")
        quarters.append({
            "end":          r["end"],
            "key":          key,
            "label":        quarter_label(key),
            "revenue":      r["val"],
            "gross_profit": gross_map.get(key),
            "net_income":   ni_map.get(key),
        })
    return quarters


# ── Formatting ─────────────────────────────────────────────────────────────────

def quarter_label(period: str) -> str:
    try:
        dt = datetime.strptime(period, "%Y-%m-%d")
        q  = (dt.month - 1) // 3 + 1
        return f"Q{q}\n'{str(dt.year)[2:]}"
    except ValueError:
        return period


def fmt_b(v, dec=1):
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return fr"\${v/1e9:.{dec}f}B"
    if abs(v) >= 1e6:
        return fr"\${v/1e6:.0f}M"
    return fr"\${v:,.0f}"


def fmt_money(v) -> str:
    """Plain-text money formatter for captions (no LaTeX escaping)."""
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return f"${v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"


def pct_chg(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev) * 100


def yoy_str(pct):
    if pct is None:
        return "N/A", None
    s = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
    return s, pct >= 0


# ── Logo helpers ───────────────────────────────────────────────────────────────

def rounded_image(img_arr: np.ndarray, radius_frac: float = 0.20) -> np.ndarray:
    """Mask corners of an RGBA image array to produce a rounded square."""
    arr = img_arr.copy()
    h, w = arr.shape[:2]
    r    = int(min(h, w) * radius_frac)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    mask_arr = np.array(mask)
    if arr.shape[2] == 4:
        arr[:, :, 3] = np.minimum(arr[:, :, 3], mask_arr)
    else:
        arr = np.dstack([arr[:, :, :3], mask_arr])
    return arr


def load_logo(ticker: str):
    for nm in [f"{ticker}.png", f"{ticker}.jpg", f"{ticker}.F.png"]:
        p = LOGO_DIR / nm
        if p.exists():
            return np.asarray(Image.open(p).convert("RGBA"))
    return None


def load_brand_logo():
    # Check project root first, then logos/ subdirectory
    candidates = (
        [LOGO_DIR.parent / nm for nm in ["app_logo.png", "brand_logo.png"]]
        + [LOGO_DIR / nm for nm in ["app_logo.png", "brand_logo.png",
                                     "app_icon.png", "stockscore_logo.png"]]
    )
    for p in candidates:
        if p.exists():
            img = np.asarray(Image.open(p).convert("RGBA"))
            return rounded_image(img, radius_frac=0.22)
    return None


# ── Drawing helpers ────────────────────────────────────────────────────────────

def hdr_grad(ax):
    cmap = mcolors.LinearSegmentedColormap.from_list("h", [C["hdr_l"], C["hdr_r"]])
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1),
              aspect="auto", extent=[0, 1, 0, 1], cmap=cmap, zorder=0)


def pill(ax, x, y, w, h, color, alpha=1.0, zorder=3, r=None):
    if r is None:
        r = min(h * 0.42, w * 0.08)
    ax.add_patch(FancyBboxPatch(
        (x + r, y + r), max(w - 2 * r, 0.001), h - 2 * r,
        boxstyle=f"round,pad={r}",
        facecolor=color, edgecolor="none",
        alpha=alpha, zorder=zorder, clip_on=False,
    ))


# ── Pillow post-processing: rounded header card ────────────────────────────────

def apply_rounded_header(filepath: str, corner_r: int = 20):
    """Round only the top corners of the header card; bottom edge is straight."""
    img  = Image.open(filepath).convert("RGB")
    w, h = img.size

    hdr_h   = round(h * 0.128)
    card_xl = round(w * 0.025)
    card_xr = w - card_xl
    card_yt = round(hdr_h * 0.09)
    card_yb = hdr_h - 1   # card ends at last header row — never bleeds below

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    # Rounded rect (all 4 corners), then fill the bottom band to make bottom straight.
    draw.rounded_rectangle([card_xl, card_yt, card_xr, card_yb],
                            radius=corner_r, fill=255)
    draw.rectangle([card_xl, card_yb - corner_r, card_xr, card_yb], fill=255)
    # Preserve everything below the header boundary (company strip, chart, footer).
    draw.rectangle([0, hdr_h, w, h], fill=255)

    bg_rgb = tuple(int(C["bg"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    bg_img = Image.new("RGB", (w, h), bg_rgb)
    Image.composite(img, bg_img, mask).save(filepath)


# ── Main figure ────────────────────────────────────────────────────────────────

def build_figure(quarters: list, company: str, ticker: str,
                 co_logo=None, br_logo=None):

    latest = quarters[-1]
    rev    = latest["revenue"]
    ni     = latest["net_income"]
    gp     = latest["gross_profit"]

    yoy_q   = quarters[-5] if len(quarters) >= 5 else None
    rev_yoy = pct_chg(rev, yoy_q["revenue"]    if yoy_q else None)
    ni_yoy  = pct_chg(ni,  yoy_q["net_income"] if yoy_q else None)
    gm_pct  = (gp / rev * 100) if (gp and rev) else None
    nm_pct  = (ni / rev * 100) if (ni and rev) else None

    fig = plt.figure(figsize=(FIGW, FIGH), facecolor=C["bg"])

    # Layout (bottom → top, 1080×1350):
    # 0.000–0.050  footer
    # 0.095–0.532  chart axes     (raised: bigger gap from footer, closer to legend)
    # 0.537–0.555  legend strip   (lowered: bigger gap from stats above)
    # 0.583–0.760  stats strip
    # 0.760–0.868  company strip
    # 0.872–1.000  header (gradient fills full strip; corners rounded in post-processing)

    # ── Header ────────────────────────────────────────────────────────────────
    ax_h = fig.add_axes([0, 0.872, 1, 0.128])
    ax_h.patch.set_visible(False)          # transparent — figure bg shows through gaps
    ax_h.set_xlim(0, 1); ax_h.set_ylim(0, 1); ax_h.axis("off")
    hdr_grad(ax_h)

    # Tighter line spacing: both texts closer together vertically
    ax_h.text(0.055, 0.63, "StockScore.co.uk", color="white",
              fontsize=28, fontweight="bold", va="center", zorder=1)
    ax_h.text(0.055, 0.30, "Quarterly Earnings Trend", color="white",
              fontsize=15, alpha=0.90, va="center", zorder=1)

    # Brand logo — right side of card, square with equal ~12 px padding top/bottom/right.
    # Card bounds (pixels): top=16, bottom=152, right=1053 → logo = 112×112 px,
    # placed at x=929–1041, y=28–140 → figure fractions below.
    if br_logo is not None:
        bax = fig.add_axes([0.860, 0.896, 0.104, 0.083])
        bax.imshow(br_logo)
        bax.axis("off")

    # ── Company strip ─────────────────────────────────────────────────────────
    # Extra top padding gives breathing room below the header card.
    ax_c = fig.add_axes([0, 0.760, 1, 0.112])
    ax_c.patch.set_visible(False)
    ax_c.set_xlim(0, 1); ax_c.set_ylim(0, 1); ax_c.axis("off")

    tx = 0.07
    if co_logo is not None:
        la = fig.add_axes([0.04, 0.778, 0.140, 0.086])
        la.imshow(co_logo); la.axis("off")
        tx = 0.25

    name_d = company.title() if len(company) <= 28 else company.title()[:26] + "..."
    # Tighter gap between name and ticker: name at 0.68, ticker at 0.32
    ax_c.text(tx, 0.68, name_d, color=C["white"],
              fontsize=22, fontweight="bold", va="center")
    ax_c.text(tx, 0.30, f"${ticker}", color=C["grey"], fontsize=14, va="center")
    ax_c.plot([0.04, 0.96], [0.06, 0.06], color=C["div"], lw=1.5)

    # ── Stats strip — 3 cards ─────────────────────────────────────────────────
    ax_s = fig.add_axes([0, 0.583, 1, 0.177])
    ax_s.patch.set_visible(False)
    ax_s.set_xlim(0, 1); ax_s.set_ylim(0, 1); ax_s.axis("off")

    card_w = 0.272
    pad_l  = 0.048
    gap    = (1 - 2 * pad_l - 3 * card_w) / 2
    CARD_R = 0.030   # fixed corner radius for cards (more prominent rounding)

    stat_defs = [
        ("Revenue",    fmt_b(rev),  rev_yoy, "YoY"),
        ("Net Income", fmt_b(ni),   ni_yoy,  "YoY"),
        ("Net Margin", f"{nm_pct:.1f}%" if nm_pct is not None else "N/A",
                                    gm_pct,  "GM"),
    ]

    for i, (name, val_str, aux_val, aux_lbl) in enumerate(stat_defs):
        cx = pad_l + i * (card_w + gap)
        pill(ax_s, cx, 0.06, card_w, 0.88, C["card"], zorder=1, r=CARD_R)
        ax_s.text(cx + card_w / 2, 0.84, name, color=C["grey"],
                  fontsize=11, ha="center", va="center", zorder=3)
        ax_s.text(cx + card_w / 2, 0.54, val_str, color=C["white"],
                  fontsize=19, fontweight="bold", ha="center", va="center", zorder=3)
        if aux_lbl == "YoY" and aux_val is not None:
            s, pos = yoy_str(aux_val)
            col   = C["green"] if pos else C["red"]
            arrow = "▲" if pos else "▼"
            ax_s.text(cx + card_w / 2, 0.22, f"{arrow} {s} YoY",
                      color=col, fontsize=11, ha="center", va="center",
                      fontweight="bold", zorder=3)
        elif aux_lbl == "GM" and aux_val is not None:
            ax_s.text(cx + card_w / 2, 0.22, f"GM {aux_val:.1f}%",
                      color=C["teal"], fontsize=11, ha="center", va="center", zorder=3)

    # ── Legend strip — each item centred under its matching stat box ──────────
    LEG_LEFT  = 0.09
    LEG_WIDTH = 0.82
    ax_leg = fig.add_axes([LEG_LEFT, 0.537, LEG_WIDTH, 0.018])
    ax_leg.patch.set_visible(False)
    ax_leg.set_xlim(0, 1); ax_leg.set_ylim(0, 1); ax_leg.axis("off")

    # box_centers are in figure space (ax_s spans full width); convert to ax_leg space.
    _gap = (1 - 2 * pad_l - 3 * card_w) / 2
    box_centers = [pad_l + i * (card_w + _gap) + card_w / 2 for i in range(3)]
    leg_centers = [(bc - LEG_LEFT) / LEG_WIDTH for bc in box_centers]

    # hw = half-group width in ax_leg coordinate space (icon + gap + text)
    leg_items = [
        (C["rev_bar"], "s", "Revenue",      0.038),
        (C["ni_bar"],  "s", "Net Income",   0.048),
        (C["amber"],   "o", "Net Margin %", 0.058),
    ]
    for i, (col, mrk, lbl, hw) in enumerate(leg_items):
        cx = leg_centers[i]
        ax_leg.plot(cx - hw, 0.50, marker=mrk, color=col, markersize=9,
                    linestyle="none", zorder=3,
                    markeredgecolor=C["bg"] if mrk == "o" else col,
                    markeredgewidth=1.5 if mrk == "o" else 0)
        ax_leg.text(cx - hw + 0.022, 0.50, lbl, color=C["grey"],
                    fontsize=10.5, va="center", ha="left", zorder=3)

    # ── Bar chart ─────────────────────────────────────────────────────────────
    ax = fig.add_axes([0.11, 0.095, 0.83, 0.437])
    ax.set_facecolor(C["bg"])
    for spine in ax.spines.values():
        spine.set_visible(False)

    n   = len(quarters)
    x   = np.arange(n)
    BW  = 0.30
    OFF = 0.17

    revenues    = np.array([q["revenue"]   or 0.0 for q in quarters])
    net_incomes = np.array([q["net_income"] or 0.0 for q in quarters])
    margins     = [
        (q["net_income"] / q["revenue"] * 100)
        if (q["net_income"] is not None and q["revenue"])
        else None
        for q in quarters
    ]

    rev_alphas = [0.40] * (n - 1) + [0.92]
    ni_alphas  = [0.45] * (n - 1) + [0.94]

    rev_bars = ax.bar(x - OFF, revenues,    BW, zorder=3)
    ni_bars  = ax.bar(x + OFF, net_incomes, BW, zorder=3)

    for bar, a in zip(rev_bars, rev_alphas):
        bar.set_facecolor(C["rev_bar"]); bar.set_alpha(a)
    for bar, a in zip(ni_bars, ni_alphas):
        bar.set_facecolor(C["ni_bar"]); bar.set_alpha(a)

    def bar_label(axis, xpos, val, color):
        if val:
            if val >= 0:
                axis.text(xpos, val * 1.02, fmt_b(val, dec=1),
                          color=color, fontsize=11, fontweight="bold",
                          ha="center", va="bottom", zorder=5)
            else:
                axis.text(xpos, val * 1.05, fmt_b(val, dec=1),
                          color=color, fontsize=11, fontweight="bold",
                          ha="center", va="top", zorder=5)

    bar_label(ax, (n - 1) - OFF, revenues[-1],    C["teal"])
    bar_label(ax, (n - 1) + OFF, net_incomes[-1], C["green"])

    # Net margin line — skip quarters with extreme margins (beyond ±200%)
    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    for spine in ax2.spines.values():
        spine.set_visible(False)
    ax2.yaxis.set_visible(False)

    valid = [(xi, m) for xi, m in zip(x, margins)
             if m is not None and -200 <= m <= 200]
    if valid:
        mx, my = zip(*valid)
        ax2.plot(mx, my, color=C["amber"], lw=2.5, zorder=5,
                 marker="o", markersize=8,
                 markerfacecolor=C["amber"],
                 markeredgecolor=C["bg"], markeredgewidth=1.8)
        my_range     = (max(my) - min(my)) or max(abs(m) for m in my) or 10
        label_offset = max(my_range * 0.12, 3)
        for xi, mi in zip(mx, my):
            offset = label_offset if mi >= 0 else -label_offset
            va     = "bottom" if mi >= 0 else "top"
            ax2.text(xi, mi + offset, f"{mi:.0f}%",
                     color=C["amber"], fontsize=8.5,
                     ha="center", va=va, zorder=6)
        pad = my_range * 0.5
        ax2.set_ylim(min(my) - pad, max(my) + pad * 4)

    # Y axis — extend below zero when net income dips negative
    max_rev      = revenues.max() if len(revenues) else 1
    min_ni       = net_incomes.min()
    y_bottom     = min(0.0, min_ni * 1.3)
    use_billions = max_rev >= 1e9
    if use_billions and max_rev < 10e9:
        fmt_fn = lambda v, _: f"${v/1e9:.1f}B"
    elif use_billions:
        fmt_fn = lambda v, _: f"${v/1e9:.0f}B"
    else:
        fmt_fn = lambda v, _: f"${v/1e6:.0f}M"
    ax.set_ylim(y_bottom, max_rev * 1.45)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_fn))
    ax.tick_params(axis="y", colors=C["grey"], labelsize=11, length=0)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True, color=C["div"], lw=0.7, zorder=0)
    ax.set_axisbelow(True)

    labels = [q["label"] for q in quarters]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11.5, fontweight="bold",
                       color=C["grey"], linespacing=1.3)
    ax.get_xticklabels()[-1].set_color(C["teal"])

    # ── Footer ────────────────────────────────────────────────────────────────
    ax_f = fig.add_axes([0, 0, 1, 0.050])
    ax_f.patch.set_visible(False)
    ax_f.set_xlim(0, 1); ax_f.set_ylim(0, 1); ax_f.axis("off")
    ax_f.plot([0.04, 0.96], [0.88, 0.88], color=C["div"], lw=1.2)
    ax_f.text(0.5, 0.36, "@StockScoreUK  ·  Source: SEC EDGAR",
              color=C["grey"], fontsize=14, ha="center", va="center")

    return fig


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Multi-quarter earnings trend chart from SEC EDGAR")
    parser.add_argument("ticker")
    parser.add_argument("--quarters", type=int, default=8,
                        help="Number of quarters to plot (default 8)")
    parser.add_argument("--output")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    out    = args.output or f"{ticker}_trend.png"

    print(f"\n[1/4] Looking up {ticker} ...")
    cik, company = get_cik(ticker)
    print(f"      {company}  (CIK {cik})")

    print("[2/4] Fetching EDGAR XBRL facts ...")
    facts = fetch_facts(cik)

    print(f"[3/4] Building {args.quarters}-quarter trend ...")
    quarters = build_trend(facts, args.quarters)
    if len(quarters) < 2:
        print("ERROR: fewer than 2 quarters found — check the ticker.")
        sys.exit(1)

    print(f"      Found {len(quarters)} quarters:")
    for q in quarters:
        ql = q["label"].replace("\n", " ")
        print(f"      {ql:10s}  Rev {fmt_b(q['revenue']):>10s}   "
              f"NI {fmt_b(q['net_income']):>10s}")

    print("[4/4] Drawing chart ...")
    co_logo = load_logo(ticker)
    br_logo = load_brand_logo()
    fig = build_figure(quarters, company, ticker, co_logo, br_logo)
    fig.savefig(out, dpi=DPI, facecolor=C["bg"])
    plt.close(fig)

    print("      Applying rounded header ...")
    apply_rounded_header(out)

    print(f"\n      Saved → {out}\n")


if __name__ == "__main__":
    main()
