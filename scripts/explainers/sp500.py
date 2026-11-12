#!/usr/bin/env python3
"""Explainer reel: "What actually is the S&P 500?".

Narration: stories/SP500-*.mp3 (ElevenLabs). Output: stories/out/sp500.mp4

  python3 scripts/explainers/sp500.py --still 3,20,40   # preview frames
  python3 scripts/explainers/sp500.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("SP500-*.mp3"))

LINES = [
    ("hook", "Most professional"),
    ("hook", "So what actually"),
    ("basket", "It's a list"),
    ("basket", "Apple Microsoft"),
    ("weight", "But they don't"),
    ("weight", "The bigger the"),
    ("swap", "And the list"),
    ("swap", "When companies shrink"),
    ("fund", "You can't buy"),
    ("fund", "But you can buy"),
    ("fund", "One purchase"),
    ("history", "Historically"),
    ("history", "But not in"),
    ("history", "In 2008"),
    ("bet", "Warren Buffett"),
    ("bet", "He won"),
    ("end", "Follow for more"),
]

BASKET = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
          "JPM", "LLY", "V", "WMT", "XOM", "MA", "COST", "NFLX"]


def scene_hook(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    fade = 1 - prog(t, L[1] - 0.2, 0.4)
    if fade > 0:
        x0, x1, ybase = 150, 900, 940
        n = 40
        def path(end_rise, wob, ph):
            return [(lerp(x0, x1, i/(n-1)), ybase - end_rise*(i/(n-1))**1.3 - wob*math.sin(i*0.55 + ph)*(i/(n-1)))
                    for i in range(n)]
        u = eo(prog(t, 0.1, 2.2))
        p.line([(x0 - 20, ybase + 20), (x1 + 20, ybase + 20)], mix((70, 90, 130), fade), 3)
        for k, (rise, wob, ph) in enumerate([(230, 30, 0), (170, 40, 2), (120, 35, 4)]):
            partial(p, path(rise, wob, ph), u, mix((110, 125, 150), fade), 5)
        partial(p, path(400, 26, 1), u, mix(C["teal"], fade), 9)
        if u > 0.95:
            p.text(x1 - 10, ybase - 455, "S&P 500", F(36, "heavy"), mix(C["teal"], fade), anchor="rm")
            p.text(x1 + 6, ybase - 225, "the pros", F(30, "bold"), mix((150, 163, 184), fade), anchor="lm")
    for i, x in enumerate((230, 380, 530)):
        person(p, x, GROUND, 0.72 * back(prog(t, 0.2 + i*0.12, 0.4)), body=(70, 84, 120),
               mood="worried" if t > 2.0 else "smile", look=1, tie=True, blink=blinking(t, i))
    u = prog(t, w("S&P") - 0.15, 0.5)
    sprite_text(img, 540, 640, "S&P 500?", F(140, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])


def scene_basket(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    # 500 squares — one per company
    gfade = 1 - prog(t, L[1] - 0.3, 0.4)
    if gfade > 0:
        sprite_text(img, 540, 455, "~500 of America's biggest companies", F(38, "heavy"), C["white"],
                    a=prog(t, 0.2, 0.4) * gfade)
        t0 = w("500") - 0.3
        for i in range(500):
            r, c = divmod(i, 25)
            u = prog(t, t0 + (r + c) * 0.035, 0.25)
            if u <= 0: continue
            x, y = 180 + c*30, 520 + r*30
            sz = 12 * back(u)
            shade = [C["teal"], (0, 170, 160), (60, 230, 210)][(i * 7) % 3]
            p.rect(x - sz, y - sz, x + sz, y + sz, mix(shade, gfade))
    # the big four, then into the basket
    if t > L[1] - 0.3:
        bt = w("basket") - 0.3
        drop = eio(prog(t, bt, 0.6))
        bu = back(prog(t, bt - 0.3, 0.5))
        basket(p, 540, 1060, bu)
        # extra logos already sitting in the basket
        for k, tk in enumerate(BASKET[4:12]):
            eu = back(prog(t, bt + 0.4 + k*0.06, 0.35))
            if eu > 0.02:
                paste_layer(img, ticker_logo(tk, 70), 360 + k*52, 930 - (k % 2)*30, scale=eu)
        for k, tk in enumerate(BASKET[:4]):
            u = back(prog(t, w(["apple", "microsoft", "nvidia", "amazon"][k]) - 0.15, 0.4))
            if u <= 0.02: continue
            sx, sy = 195 + k*230, 620
            ex, ey = 400 + k*95, 900 - (k % 2)*25
            x, y = lerp(sx, ex, drop), lerp(sy, ey, drop) - 120*math.sin(math.pi*drop)
            paste_layer(img, ticker_logo(tk, 170), x, y, scale=u * lerp(1, 0.6, drop))


def scene_weight(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    ticks = ["NVDA", "MSFT", "AAPL", "AMZN", "GOOGL"]
    big = [210, 185, 175, 130, 95]
    m = eio(prog(t, w("same") - 0.2, 0.7))
    sizes = [lerp(130, b, m) for b in big]
    total = sum(sizes) + 22*4
    x = 540 - total/2
    j_big, j_small = w("moves") - 0.1, w("moves") + 1.0
    for i, (tk, s) in enumerate(zip(ticks, sizes)):
        u = back(prog(t, 0.05 + i*0.08, 0.4))
        cx = x + s/2; x += s + 22
        jump = 0
        if i == 0: jump = 70*math.sin(math.pi*prog(t, j_big, 0.6))
        if i == 4: jump = 70*math.sin(math.pi*prog(t, j_small, 0.6))
        if u > 0.02:
            paste_layer(img, ticker_logo(tk, 210), cx, 1000 - s/2 - jump, scale=u * s/210)
    p.text(540, 1080, "+ hundreds more", F(30, "bold"), mix((150, 163, 184), prog(t, 0.5, 0.4)))
    a0 = prog(t, w("same") + 0.1, 0.4) * (1 - prog(t, L[1] - 0.1, 0.3))
    sprite_text(img, 540, 470, "Bigger company = bigger weight", F(44, "heavy"), C["amber"], a=a0)
    # index reaction meter
    if t > L[1] + 0.1:
        sprite_text(img, 420, 480, "S&P 500", F(48, "heavy"), C["white"], a=prog(t, L[1] + 0.1, 0.3))
        for k, (t0, size, label) in enumerate([(j_big, 40, "big move"), (j_small, 14, "tiny move")]):
            u = prog(t, t0 + 0.15, 0.3)
            end = 1 - prog(t, j_small, 0.2) if k == 0 else 1
            if u > 0 and end > 0:
                s = size * back(u)
                ax = 560
                p.poly([(ax, 480 - s), (ax + s*0.9, 480 + s*0.6), (ax - s*0.9, 480 + s*0.6)], mix(C["green"], end))
                p.text(ax + 60, 482, label, F(40, "bold"), mix(C["green"], end), anchor="lm")


def scene_swap(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    tracked(p, 540, 440, "THE S&P 500 LIST", F(30, "bold"), C["teal"], 4)
    rows = [("AAPL", "Apple"), ("MSFT", "Microsoft"), (None, "Fading Co."), ("KO", "Coca-Cola"), ("JPM", "JPMorgan")]
    t_shrink, t_out, t_in = w("shrink") - 0.2, w("swapped"), w("rising") - 0.1
    for i, (tk, name) in enumerate(rows):
        u = back(prog(t, 0.1 + i*0.1, 0.4))
        if u <= 0.02: continue
        y = 520 + i*125
        dx = 0
        if tk is None:
            out = eio(prog(t, t_out, 0.5))
            if out < 1:
                dx = 900*out
                sh = eo(prog(t, t_shrink, 0.5))
                p.rr(170 + dx, y - 50, 910 + dx, y + 50, 22, fill=mix((70, 28, 40), sh, (28, 40, 70)))
                name_tile(p, 240 + dx, y, 76*u*lerp(1, 0.7, sh), "FC", (110, 120, 140))
                p.text(300 + dx, y, name, F(38, "bold"), mix(C["red"], sh, C["white"]), anchor="lm")
                if sh > 0:
                    p.poly([(850 + dx, y + 16*sh), (834 + dx, y - 12*sh), (866 + dx, y - 12*sh)], C["red"])
            iu = eo(prog(t, t_in, 0.5))
            if iu > 0:
                dx = -900*(1 - iu)
                p.rr(170 + dx, y - 50, 910 + dx, y + 50, 22, fill=(24, 70, 60), outline=C["green"], width=3)
                name_tile(p, 240 + dx, y, 76, "RS", (0, 160, 120))
                p.text(300 + dx, y, "Rising Star Inc.", F(38, "bold"), C["white"], anchor="lm")
                p.rr(790 + dx, y - 22, 880 + dx, y + 22, 12, fill=C["green"])
                p.text(835 + dx, y, "NEW", F(24, "heavy"), INK)
            continue
        p.rr(170, y - 50*u, 910, y + 50*u, 22, fill=(28, 40, 70))
        if u > 0.6:
            paste_layer(img, ticker_logo(tk, 76), 240, y, scale=u)
            p.text(300, y, name, F(38, "bold"), C["white"], anchor="lm")


def scene_fund(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    t_buy = w("purchase") - 0.2
    # the index itself: not for sale
    a = prog(t, 0.0, 0.3) * (1 - prog(t, L[1] - 0.2, 0.3))
    if a > 0:
        p.rr(380, 520, 900, 740, 30, fill=mix((30, 44, 76), a), outline=mix((70, 90, 130), a), width=3)
        p.text(640, 600, "S&P 500", F(84, "heavy"), mix(C["white"], a))
        p.text(640, 685, "the index", F(32, "demi"), mix((150, 163, 184), a))
        u = prog(t, w("can't") + 0.1, 0.35)
        paste_layer(img, stamp("NOT FOR SALE"), 640, 850, a=min(1, u*2) * a, scale=lerp(1.4, 0.7, eo(u)), rot=-6)
    # the index fund: a box holding the companies
    bu = back(prog(t, L[1] + 0.1, 0.5))
    if bu > 0.02:
        fly = eio(prog(t, t_buy, 0.7))
        cx, cy = lerp(640, 300, fly), lerp(780, 960, fly)
        s = bu * lerp(1, 0.42, fly)
        p.rr(cx - 230*s, cy - 230*s, cx + 230*s, cy + 230*s, 30*s, fill=(24, 36, 64), outline=C["teal"], width=4)
        if s > 0.3:
            p.text(cx, cy - 180*s, "INDEX FUND", F(48*s, "heavy"), C["amber"])
            for k, tk in enumerate(BASKET):
                r, c = divmod(k, 4)
                paste_layer(img, ticker_logo(tk, 64), cx + (c - 1.5)*84*s, cy - 90*s + r*72*s, scale=s)
            p.text(cx, cy + 200*s, "copies the S&P 500", F(30*s, "bold"), C["teal"])
    after = t > t_buy + 0.7
    person(p, 200, GROUND, 1.1, mood="big" if after else ("worried" if t > w("can't") + 0.2 and t < L[1] + 0.2 else "smile"),
           arm_r=0.7 if after else 0.15, arm_l=0.15, look=1, blink=blinking(t))
    if t > t_buy:
        sprite_text(img, 680, 520, "1 purchase", F(72, "heavy"), C["white"], a=prog(t, t_buy + 0.3, 0.4))
        u = prog(t, w("slice") - 0.1, 0.45)
        sprite_text(img, 680, 610, "= a slice of 500 companies", F(44, "heavy"), C["amber"], a=u)
        if u > 0:
            # pie with 500 slivers; the viewer's own slice pops out
            pu = back(u)
            for k in range(60):
                a0, a1 = k*6, k*6 + 6
                col = [C["teal"], (0, 170, 160), (60, 230, 210), (0, 140, 135)][k % 4]
                bb = (720 - 150*pu, 850 - 150*pu, 720 + 150*pu, 850 + 150*pu)
                p.d.pieslice([v*SS for v in bb], a0, a1, fill=col)
            ox = 26*pu
            bb = (720 + ox - 150*pu, 850 - ox*0.4 - 150*pu, 720 + ox + 150*pu, 850 - ox*0.4 + 150*pu)
            p.d.pieslice([v*SS for v in bb], -20, -14, fill=C["amber"])


def scene_history(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    SP = SP500_YEAR_END
    years = sorted(SP)
    lo, hi = math.log(500), math.log(8000)
    def pt(yr, v): return (lerp(130, 950, (yr - 1995) / 30), lerp(1090, 560, (math.log(v) - lo) / (hi - lo)))
    pts = [pt(y, SP[y]) for y in years]
    p.line([(110, 1110), (970, 1110)], (70, 90, 130), 3)
    for yr in (1995, 2005, 2015, 2025):
        p.text(pt(yr, 600)[0], 1140, str(yr), F(26, "demi"), (130, 145, 170))
    p.text(140, 560, "S&P 500 price", F(26, "demi"), (130, 145, 170), anchor="lm")
    i07, i08 = years.index(2007), years.index(2008)
    keys = [(0.1, 0), (w("2008") - 0.3, i07), (w("fell") + 0.2, i08), (sc["D"] - 0.8, len(pts) - 1)]
    idx = 0
    for (ta, ia), (tb, ib) in zip(keys, keys[1:]):
        if t >= ta: idx = lerp(ia, ib, clamp((t - ta) / (tb - ta)))
    # straight "average" line for comparison
    su = eo(prog(t, L[1] - 0.1, 0.7))
    if su > 0:
        a, b = pts[0], pts[-1]
        for k in range(24):
            u0, u1 = k/24, k/24 + 0.5/24
            if u0 > su: break
            p.line([(lerp(a[0], b[0], u0), lerp(a[1], b[1], u0)), (lerp(a[0], b[0], min(u1, su)), lerp(a[1], b[1], min(u1, su)))],
                   (150, 163, 184), 4)
    seg = pts[:int(idx) + 1]
    if idx < len(pts) - 1:
        k = int(idx); f = idx - k
        seg = seg + [(lerp(pts[k][0], pts[k+1][0], f), lerp(pts[k][1], pts[k+1][1], f))]
    if len(seg) >= 2:
        p.line(seg[:i07 + 1], C["teal"], 8)
        if len(seg) > i07 + 1: p.line(seg[i07:i08 + 1], C["red"], 8)
        if len(seg) > i08 + 1: p.line(seg[i08:], C["teal"], 8)
        p.ell(seg[-1][0], seg[-1][1], 11, fill=C["white"])
    sprite_text(img, 540, 470, "≈10% a year, on average", F(50, "heavy"), C["amber"],
                a=prog(t, w("10") - 0.2, 0.4), scale=lerp(.8, 1, back(prog(t, w("10") - 0.2, 0.4))))
    cu = back(prog(t, w("fell") + 0.1, 0.4))
    if cu > 0.02:
        x8, y8 = pts[i08]
        p.ell(x8, y8, 16*cu, fill=C["red"])
        p.rr(x8 - 105*cu, y8 + 40, x8 + 105*cu, y8 + 96, 16, fill=C["red"])
        if cu > 0.6: p.text(x8, y8 + 68, "2008: −38%", F(32, "heavy"), C["white"])


def scene_bet(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    iu = prog(t, 0.0, 0.4) * (1 - prog(t, w("million") - 0.5, 0.3))
    sprite_text(img, 540, 640, "Warren Buffett's", F(64, "heavy"), C["white"], a=iu, scale=lerp(.8, 1, back(prog(t, 0, 0.4))))
    sprite_text(img, 540, 730, "famous bet", F(64, "heavy"), C["amber"], a=iu * prog(t, 0.3, 0.4), glow=C["amber"])
    coin(p, 540, 880, 60 * back(prog(t, 0.4, 0.5)) * (1 - prog(t, w("million") - 0.5, 0.3)))
    u = prog(t, w("million") - 0.2, 0.45)
    sprite_text(img, 540, 465, "$1,000,000 BET", F(78, "heavy"), C["amber"], a=u * (1 - prog(t, L[1] - 0.2, 0.3)),
                scale=lerp(.6, 1, back(u)), glow=C["amber"])
    lx, rx, base = 300, 780, 990
    la = prog(t, w("simple") - 0.2, 0.4)
    ra = prog(t, w("hedge") - 0.2, 0.4)
    p.text(lx, 560, "S&P 500 fund", F(36, "heavy"), mix(C["teal"], la))
    p.text(rx, 560, "Hedge funds", F(36, "heavy"), mix(PURPLE, ra))
    g = eio(prog(t, w("over") - 0.1, L[1] - w("over") - 0.2))
    if g > 0:
        p.line([(140, base), (940, base)], (70, 90, 130), 3)
        for x, pct, col in ((lx, 126, C["teal"]), (rx, 36, PURPLE)):
            h = 2.3 * pct * g
            p.rr(x - 70, base - h, x + 70, base, 14, fill=col)
            p.text(x, base - h - 30, f"+{int(round(pct * g))}%", F(40, "heavy"), C["white"])
        p.text(540, base + 34, f"Year {max(1, int(math.ceil(10 * g)))} of 10", F(28, "bold"), (150, 163, 184))
    won = t > L[1]
    if la > 0:
        person(p, lx, GROUND + 6, 0.7 * back(la), mood="big" if won else "smile", arm_l=0.9 if won else 0.15,
               arm_r=0.9 if won else 0.15, blink=blinking(t))
    for i, x in enumerate((rx - 110, rx, rx + 110)):
        if ra > 0:
            person(p, x, GROUND + 6, 0.62 * back(prog(t, w("hedge") - 0.2 + i*0.1, 0.4)), body=(70, 84, 120),
                   mood="worried" if won else "smile", tie=True, blink=blinking(t, i + 1))
    tu = back(prog(t, L[1] - 0.05, 0.5))
    if tu > 0.02:
        trophy(p, lx, 470, 0.68*tu)
        sprite_text(img, lx + 200, 470, "WINNER", F(56, "heavy"), C["amber"], a=prog(t, L[1] + 0.1, 0.3),
                    rot=6, glow=C["amber"])


if __name__ == "__main__":
    run(name="sp500", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["What actually is", "the S&P 500?"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "basket": scene_basket, "weight": scene_weight, "swap": scene_swap,
                   "fund": scene_fund, "history": scene_history, "bet": scene_bet, "end": end_card})
