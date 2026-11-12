#!/usr/bin/env python3
"""Explainer reel: "Dollar-cost averaging".

Narration: stories/DCA-*.mp3 (ElevenLabs). Output: stories/out/dca.mp4
The worked example ($100/month over six prices) is real arithmetic, computed below.

  python3 scripts/explainers/dca.py --still 3,20,40   # preview frames
  python3 scripts/explainers/dca.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("DCA-*.mp3"))

LINES = [
    ("hook", "What if you"),
    ("what", "It's called dollar-cost"),
    ("what", "Instead of investing"),
    ("clever", "Here's the clever"),
    ("clever", "When prices are high"),
    ("clever", "When prices drop"),
    ("over", "So over time"),
    ("over", "and you avoid"),
    ("calm", "It also takes"),
    ("lump", "Is it always"),
    ("lump", "Markets tend to"),
    ("lump", "But for most"),
    ("end", "Follow for more"),
]

GREY = (150, 163, 184)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
PRICES = [20, 25, 10, 12, 25, 20]
SHARES = [100 / p for p in PRICES]
AVG_COST = 600 / sum(SHARES)          # $16.51
AVG_PRICE = sum(PRICES) / len(PRICES)  # $18.67


def scene_hook(img, p, t, sc):
    w = sc["w"]
    n = 30
    pts = [(lerp(140, 940, i/n), 860 - 120*math.sin(i*0.55) - 60*math.sin(i*1.37) - 4*i) for i in range(n + 1)]
    partial(p, pts, eo(prog(t, 0.1, 1.6)), C["teal"], 8)
    if t > 0.8:
        u = (t - 0.8) * 0.45
        f = (0.5 + 0.45*math.sin(u * 4.1)) * n
        k = int(f); fr = f - k
        x = lerp(pts[k][0], pts[min(k+1, n)][0], fr); y = lerp(pts[k][1], pts[min(k+1, n)][1], fr)
        p.ell(x, y, 46, outline=C["amber"], width=5)
        p.line([(x - 64, y), (x - 30, y)], C["amber"], 5); p.line([(x + 30, y), (x + 64, y)], C["amber"], 5)
        p.line([(x, y - 64), (x, y - 30)], C["amber"], 5); p.line([(x, y + 30), (x, y + 64)], C["amber"], 5)
    sprite_text(img, 540, 480, "the perfect time to buy?", F(54, "heavy"), C["white"], a=prog(t, w("perfect") - 0.3, 0.4))
    person(p, 880, GROUND, 0.9, mood="wow", look=-1, blink=blinking(t))


def scene_what(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, w("dollar-cost") - 0.2, 0.45)
    sprite_text(img, 540, 500, "DOLLAR-COST", F(96, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 600, "AVERAGING", F(96, "heavy"), C["amber"], a=prog(t, w("averaging") - 0.2, 0.45), glow=C["amber"])
    sprite_text(img, 540, 700, "same amount · regular schedule", F(40, "heavy"), C["white"], a=prog(t, w("same") - 0.2, 0.4))
    t0 = w("$100") - 0.2
    for i, m in enumerate(MONTHS):
        x = 140 + i*160
        tu = back(prog(t, L[1] + 0.2 + i*0.1, 0.35))
        if tu <= 0.02: continue
        p.rr(x - 66*tu, 870 - 70*tu, x + 66*tu, 870 + 70*tu, 16, fill=(28, 40, 70), outline=(70, 90, 130), width=2)
        if tu > 0.6:
            p.rect(x - 66, 800, x + 66, 836, C["teal"])
            p.text(x, 818, m, F(26, "heavy"), INK)
        cu = prog(t, t0 + i*0.18, 0.4)
        if cu > 0:
            coin(p, x, lerp(760, 880, eio(cu)), 26 if cu < 1 else 28)
        if cu >= 1:
            p.text(x, 1000, "$100", F(32, "heavy"), C["green"])


def price_chart(p, t, top=540, bottom=780, hi_a=0.0, lo_a=0.0, draw_u=1.0):
    xs = [140 + i*160 for i in range(6)]
    ys = [lerp(bottom, top, (pr - 5) / 25) for pr in PRICES]
    partial(p, list(zip(xs, ys)), draw_u, C["teal"], 6)
    for i, (x, y, pr) in enumerate(zip(xs, ys, PRICES)):
        if draw_u * 5 + 1e-6 < i: continue
        hot = (pr >= 20 and hi_a) or (pr <= 12 and lo_a)
        col = (C["red"] if pr >= 20 else C["green"]) if hot else C["white"]
        p.ell(x, y, 12, fill=col)
        p.text(x, y - 34, f"${pr}", F(30, "heavy"), col)
    return xs


def scene_clever(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    hi = t > L[1]
    lo = t > L[2]
    xs = price_chart(p, t, hi_a=hi, lo_a=lo, draw_u=eo(prog(t, 0.0, 1.2)))
    base = 1130
    for i, x in enumerate(xs):
        pr = PRICES[i]
        show = (pr >= 20 and hi) or (pr <= 12 and lo)
        u = eo(prog(t, (w("fewer") if pr >= 20 else w("more")) - 0.4 + i*0.05, 0.6)) if show else 0
        if u <= 0: continue
        h = SHARES[i] * 30 * u
        col = C["red"] if pr >= 20 else C["green"]
        p.rr(x - 50, base - h, x + 50, base, 12, fill=col)
        if u > 0.8: p.text(x, base - h - 26, f"{SHARES[i]:.1f}".rstrip("0").rstrip("."), F(30, "heavy"), C["white"])
    p.text(540, base + 34, "shares your $100 buys", F(30, "bold"), mix(GREY, prog(t, L[1], 0.4)))
    sprite_text(img, 540, 470, "high price = fewer shares", F(44, "heavy"), C["red"],
                a=prog(t, w("fewer") - 0.3, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)))
    sprite_text(img, 540, 470, "low price = more shares", F(44, "heavy"), C["green"], a=prog(t, w("more") - 0.3, 0.4))


def scene_over(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a = 1 - prog(t, L[1] - 0.25, 0.3)
    if a > 0:
        xs = price_chart(p, t, top=560, bottom=760, hi_a=0, lo_a=0)
        base = 1060
        for i, x in enumerate(xs):
            h = SHARES[i] * 22
            p.rr(x - 50, base - h, x + 50, base, 12, fill=mix(C["green"] if PRICES[i] <= 12 else C["teal"], a))
        u = prog(t, w("cheap") - 0.4, 0.4) * a
        if u > 0:
            p.rr(150, 1090, 930, 1180, 20, fill=mix((24, 70, 60), u), outline=mix(C["green"], u), width=3)
            p.text(540, 1135, f"avg cost ${AVG_COST:.2f}  vs  avg price ${AVG_PRICE:.2f}", F(36, "heavy"), mix(C["white"], u))
    if t > L[1] - 0.2:
        b = prog(t, L[1] - 0.2, 0.3)
        n = 24
        pts = [(lerp(140, 940, i/n), 860 - 200*math.sin(i/n*math.pi*0.8) if i <= 14 else 860 - 200*math.sin(14/n*math.pi*0.8) + (i - 14)*40)
               for i in range(n + 1)]
        partial(p, pts, eo(prog(t, L[1], 1.4)), mix(C["teal"], b), 8)
        bu = back(prog(t, w("everything") - 0.3, 0.45))
        if bu > 0.02:
            px, py = pts[14]
            for k in range(6):
                flat_coin(p, px, py - 40 - k*16, 46*bu)
            p.text(px, py - 235, "all in", F(36, "heavy"), C["red"])
        cu = prog(t, w("crash") - 0.2, 0.4)
        if cu > 0:
            px, py = pts[14]
            p.line([(px - 70*cu, py - 200), (px + 70*cu, py - 60)], C["red"], 10)
            p.line([(px + 70*cu, py - 200), (px - 70*cu, py - 60)], C["red"], 10)
            for k in (2, 6, 10, 18, 22):
                coin(p, pts[k][0], pts[k][1] - 40, 18*back(cu))
            sprite_text(img, 540, 1160, "no going all in at the top", F(46, "heavy"), C["white"], a=cu)


def scene_calm(img, p, t, sc):
    w = sc["w"]
    calm = t > w("guessing") - 0.2
    person(p, 540, GROUND, 1.2, mood="smile" if calm else "wow", blink=blinking(t))
    for k, (txt, x, y, col, word) in enumerate((("MARKET PANIC!", 270, 600, C["red"], "emotion"),
                                                ("BUY NOW!", 800, 560, C["green"], "emotion"),
                                                ("SELL EVERYTHING?", 300, 760, C["red"], "out"),
                                                ("TOP IS IN?", 790, 720, C["amber"], "out"))):
        u = back(prog(t, w(word) - 0.3 + k*0.12, 0.35))
        out = prog(t, w("guessing") - 0.1 + k*0.08, 0.3)
        if u > 0.02 and out < 1:
            s = u * (1 - out)
            tw = F(34, "heavy").getlength(txt) / SS + 50
            p.rr(x - tw/2*s, y - 34*s, x + tw/2*s, y + 34*s, 16, fill=(16, 24, 44), outline=col, width=3)
            if s > 0.6: p.text(x, y, txt, F(34, "heavy"), col)
    sprite_text(img, 540, 480, "no guessing · no panic", F(52, "heavy"), C["teal"], a=prog(t, w("panic") - 0.3, 0.4))
    gu = prog(t, w("going") - 0.6, 1.2)
    if gu > 0:
        for i in range(12):
            x = 175 + i*66
            on = gu * 12 > i
            p.rr(x - 26, 640, x + 26, 692, 10, fill=C["green"] if on else (40, 52, 84))
            if on: p.text(x, 666, "$", F(28, "heavy"), INK)
        p.text(540, 730, "just keep going", F(40, "heavy"), C["white"])


def scene_lump(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a = 1 - prog(t, L[2] - 0.25, 0.3)
    if a > 0:
        sprite_text(img, 540, 480, "Lump sum or DCA?", F(60, "heavy"), C["white"], a=prog(t, 0.0, 0.4) * a)
        x0, x1, base = 160, 920, 1080
        n = 24
        mkt = [1.0 * 1.006 ** (i*2) * (1 + 0.02*math.sin(i*1.3)) for i in range(n + 1)]
        lump = [1200 * m / mkt[0] for m in mkt]
        dca, units = [], 0.0
        for i in range(n + 1):
            if i % 2 == 0 and i < 24: units += 100 / mkt[i]   # 12 monthly $100 buys
            dca.append(units * mkt[i])
        vmax = max(lump) * 1.05
        def pts(vals): return [(lerp(x0, x1, i/n), lerp(base, 560, v / vmax)) for i, v in enumerate(vals)]
        u = eo(prog(t, L[1] - 0.2, 2.0))
        p.line([(x0 - 10, base), (x1 + 10, base)], (70, 90, 130), 3)
        partial(p, pts(lump), u, mix(C["amber"], a), 8)
        partial(p, pts(dca), u, mix(C["teal"], a), 8)
        if u >= 1:
            p.text(x1, pts(lump)[-1][1] - 34, "lump sum", F(34, "heavy"), mix(C["amber"], a), anchor="rm")
            p.text(x1, pts(dca)[-1][1] + 40, "monthly", F(34, "heavy"), mix(C["teal"], a), anchor="rm")
        sprite_text(img, 540, 1150, "in a rising market, lump sum often wins", F(36, "heavy"), C["amber"],
                    a=prog(t, w("ahead") - 0.3, 0.4) * a)
    if t > L[2] - 0.2:
        b = back(prog(t, L[2] - 0.1, 0.45))
        person(p, 250, GROUND, 1.1*b, mood="big", arm_r=0.6, blink=blinking(t))
        if b > 0.02:
            p.rr(330, 860 - 70*b, 510, 860 + 70*b, 12, fill=(235, 240, 250))
            if b > 0.6:
                p.text(420, 820, "SALARY", F(26, "heavy"), INK)
                p.rect(360, 850, 480, 856, GREY); p.rect(360, 872, 450, 878, GREY)
                p.text(420, 905, "−$100", F(26, "heavy"), (0, 140, 120))
        for k, (word, txt) in enumerate((("simple", "simple"), ("steady", "steady"), ("mess", "hard to mess up"))):
            u = prog(t, w(word) - 0.3, 0.35)
            sprite_text(img, 760, 620 + k*90, txt, F(44, "heavy"), C["teal"], a=u, scale=lerp(.7, 1, back(u)))


if __name__ == "__main__":
    run(name="dca", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["Dollar-cost", "averaging"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "what": scene_what, "clever": scene_clever, "over": scene_over,
                   "calm": scene_calm, "lump": scene_lump, "end": end_card})
