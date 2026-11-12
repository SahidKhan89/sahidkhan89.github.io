#!/usr/bin/env python3
"""Explainer reel: "ETFs vs individual stocks".

Narration: stories/ETF-*.mp3 (ElevenLabs). Output: stories/out/etf.mp4

  python3 scripts/explainers/etf.py --still 3,20,40   # preview frames
  python3 scripts/explainers/etf.py                    # full render
"""
import math, random
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("ETF-*.mp3"))

LINES = [
    ("hook", "Should you buy"),
    ("single", "An individual stock"),
    ("single", "If it soars"),
    ("single", "If it crashes"),
    ("etf", "An ETF"),
    ("etf", "You buy and"),
    ("divers", "One ETF can"),
    ("divers", "So if one"),
    ("divers", "That's called"),
    ("trade", "The trade-off"),
    ("trade", "You won't get"),
    ("trade", "but you also"),
    ("fees", "Most ETFs"),
    ("fees", "Some cost just"),
    ("both", "Plenty of investors"),
    ("both", "A core of"),
    ("end", "Follow for more"),
]

LOGOS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "KO"]
CARD = (28, 40, 70)


def scene_hook(img, p, t, sc):
    w = sc["w"]
    u = back(prog(t, 0.1, 0.45))
    if u > 0.02:
        p.rr(270 - 150*u, 640, 270 + 150*u, 980, 28, fill=CARD, outline=(52, 70, 108), width=2)
        if u > 0.6:
            name_tile(p, 270, 760, 130*u, "1", C["teal"])
            p.text(270, 900, "one stock", F(40, "heavy"), C["white"])
    ou = back(prog(t, w("or") - 0.1, 0.35))
    if ou > 0.02:
        p.ell(540, 810, 56*ou, fill=(16, 24, 44), outline=C["amber"], width=3)
        p.text(540, 810, "or", F(44*ou, "heavy"), C["amber"])
    bt = w("basket") - 0.25
    basket(p, 800, 930, 0.75*back(prog(t, bt, 0.45)))
    for k, tk in enumerate(LOGOS[:6]):
        lu = prog(t, bt + 0.2 + k*0.08, 0.45)
        if lu > 0:
            x = 680 + (k % 3)*120 + (k // 3)*30
            y = lerp(560, 830 - (k // 3)*60, eio(lu))
            paste_layer(img, ticker_logo(tk, 90), x, y, scale=min(1, lu*2))
    p.text(800, 1080, "a whole basket", F(40, "heavy"), mix(C["white"], prog(t, bt + 0.6, 0.4)))


def scene_single(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    sprite_text(img, 540, 470, "One stock = one company", F(52, "heavy"), C["white"],
                a=prog(t, w("piece") - 0.3, 0.4))
    up, down = w("soars") - 0.2, w("crashes") - 0.2
    flat = [(lerp(430, 580, i/6), 820 + 14*math.sin(i*1.7)) for i in range(7)]
    rise = [(lerp(580, 770, i/8), lerp(820, 600, (i/8)**1.6) + 10*math.sin(i*2.1)) for i in range(9)]
    crash = [(lerp(770, 950, i/8), lerp(600, 1060, (i/8)**0.8)) for i in range(9)]
    partial(p, flat, eo(prog(t, 0.2, 1.4)), C["teal"], 8)
    partial(p, rise, eo(prog(t, up, 0.9)), C["green"], 8)
    partial(p, crash, eo(prog(t, down, 0.7)), C["red"], 8)
    sprite_text(img, 770, 545, "you win big", F(40, "heavy"), C["green"], a=prog(t, up + 0.6, 0.3))
    sprite_text(img, 790, 1110, "you feel all of it", F(40, "heavy"), C["red"], a=prog(t, down + 0.5, 0.3))
    won, lost = t > up + 0.6, t > down + 0.5
    person(p, 200, GROUND, 1.15, mood="worried" if lost else ("big" if won else "smile"),
           arm_l=0.85 if won and not lost else 0.15, arm_r=0.85 if won and not lost else 0.15, look=1,
           blink=blinking(t))
    name_tile(p, 200, 610, 100*back(prog(t, 0.0, 0.4)), "1", C["teal"])


def scene_etf(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, 0.0, 0.45)
    sprite_text(img, 540, 520, "ETF", F(140, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 620, "exchange-traded fund", F(44, "heavy"), C["white"], a=prog(t, w("exchange") - 0.1, 0.4))
    mv = eio(prog(t, L[1] - 0.2, 0.6))
    bx, s = lerp(540, 290, mv), lerp(1.0, 0.75, mv)
    bt = w("bundled") - 0.4
    for k, tk in enumerate(LOGOS):
        lu = prog(t, bt + k*0.07, 0.45)
        if lu > 0:
            tx = bx + ((k % 4) - 1.5)*95*s + (k // 4)*30*s
            ty = 1000 - 60*s - (k // 4)*55*s
            paste_layer(img, ticker_logo(tk, 90), lerp(tx, tx, 1), lerp(700, ty, eio(lu)), scale=min(1, lu*2) * s)
    basket(p, bx, 1010, s * back(prog(t, w("basket") - 0.3, 0.45)), label="ETF")
    pu = back(prog(t, L[1] + 0.1, 0.45))
    if pu > 0.02:
        phone(p, 780, 900, 0.9*pu, price="$512.30", name="YOUR ETF")
    sprite_text(img, 780, 1150, "trades like one share", F(36, "heavy"), C["teal"], a=prog(t, w("single") - 0.3, 0.4))


def scene_divers(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    rnd = random.Random(5)
    shades = [C["teal"], (0, 170, 160), (60, 230, 210), (0, 140, 135), (90, 200, 255)]
    fail_k = 3*12 + 5
    dim = 1 - 0.65*prog(t, L[2] - 0.1, 0.4)
    t_fail = w("fails") - 0.1
    for k in range(96):
        r, c = divmod(k, 12)
        x, y = 188 + c*64, 560 + r*64
        u = back(prog(t, w("hundreds") - 0.6 + (r + c)*0.03, 0.3))
        col = shades[rnd.randrange(len(shades))]
        if u <= 0.02: continue
        if k == fail_k:
            fu = prog(t, t_fail, 0.3)
            fall = eio(prog(t, t_fail + 0.5, 0.8))
            if fall >= 1: continue
            col = mix(C["red"], fu, col)
            y += 520*fall
            u *= 1 - 0.5*fall
        sz = 25*u
        p.rr(x - sz, y - sz, x + sz, y + sz, 8, fill=mix(col, dim if k != fail_k else 1))
    sprite_text(img, 540, 470, "hundreds of companies", F(48, "heavy"), C["white"],
                a=prog(t, w("hundreds") - 0.2, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)))
    sprite_text(img, 540, 1110, "one fails = a small dent", F(44, "heavy"), C["amber"],
                a=prog(t, w("dent") - 0.3, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)))
    u = prog(t, w("diversification") - 0.2, 0.5)
    sprite_text(img, 540, 780, "DIVERSIFICATION", F(92, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])


def scene_trade(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    tracked(p, 540, 455, "THE TRADE-OFF", F(32, "bold"), C["teal"], 5)
    x0, x1, y0 = 150, 900, 860
    n = 24
    etf = [(lerp(x0, x1, i/n), y0 - 150*(i/n) - 14*math.sin(i*0.9)) for i in range(n + 1)]
    win = [(lerp(x0, x1, i/n), y0 - 300*(i/n)**2.2 - 22*math.sin(i*1.3)*(i/n)) for i in range(n + 1)]
    lose = [(lerp(x0, x1, i/n), y0 - 70*math.sin(i/n*3) + 220*(i/n)**3 + 18*math.sin(i*1.6)) for i in range(n + 1)]
    p.line([(x0 - 20, 1100), (x1 + 20, 1100)], (70, 90, 130), 3)
    partial(p, etf, eo(prog(t, 0.2, 1.6)), C["teal"], 9)
    if t > 1.6: p.text(x1 + 12, etf[-1][1], "ETF", F(34, "heavy"), C["teal"], anchor="lm")
    wu = eo(prog(t, w("rocket") - 0.2, 1.0))
    partial(p, win, wu, C["green"], 7)
    if wu >= 1:
        p.text(x1 - 20, win[-1][1] - 40, "the next big winner", F(32, "heavy"), C["green"], anchor="rm")
    lu = eo(prog(t, w("bet") - 0.3, 1.0))
    partial(p, lose, lu, C["red"], 7)
    if lu >= 1:
        p.text(x1 - 20, lose[-1][1] + 44, "the wrong one", F(32, "heavy"), C["red"], anchor="rm")


def scene_fees(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, w("expense") - 0.2, 0.45)
    sprite_text(img, 540, 500, "EXPENSE RATIO", F(84, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 585, "a small yearly fee", F(40, "demi"), C["white"], a=prog(t, w("fee") - 0.2, 0.4))
    for k in range(12):
        cu = back(prog(t, 0.2 + k*0.06, 0.3))
        if cu > 0.02:
            flat_coin(p, 320, 1080 - k*22, 70*cu)
    p.text(320, 1150, "$100 invested", F(38, "heavy"), mix(C["white"], prog(t, 0.6, 0.4)))
    cu = prog(t, w("cents") - 0.3, 0.7)
    if cu > 0:
        x, y = qb((320, 800), (560, 640), (760, 900), eio(cu))
        coin(p, x, y, 22)
        if cu >= 1:
            p.text(760, 980, "a few cents", F(48, "heavy"), C["amber"])
            p.text(760, 1035, "per $100, per year", F(32, "demi"), (150, 163, 184))


def scene_both(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, w("both") - 0.2, 0.4)
    sprite_text(img, 540, 480, "Why not both?", F(64, "heavy"), C["white"], a=u, scale=lerp(.7, 1, back(u)))
    cx, cy, r = 400, 820, 210
    cu = eio(prog(t, w("core") - 0.2, 0.8))
    su = eio(prog(t, w("stocks") - 0.3, 0.6))
    bb = [(cx - r)*SS, (cy - r)*SS, (cx + r)*SS, (cy + r)*SS]
    if cu > 0: p.d.pieslice(bb, -90, -90 + 288*cu, fill=C["teal"])
    if su > 0:
        for k, col in enumerate((C["amber"], (255, 150, 60), (255, 215, 120))):
            a0 = 198 + k*24
            p.d.pieslice(bb, a0, a0 + 24*su, fill=col)
    if cu > 0 or su > 0:
        p.ell(cx, cy, r*0.55, fill=STAGE)
    if cu > 0.6:
        p.text(660, 760, "ETFs", F(52, "heavy"), C["teal"], anchor="lm")
        p.text(660, 815, "the core", F(34, "demi"), (150, 163, 184), anchor="lm")
    if su > 0.6:
        p.text(660, 900, "a few stocks", F(44, "heavy"), C["amber"], anchor="lm")
        p.text(660, 950, "you believe in", F(34, "demi"), (150, 163, 184), anchor="lm")


if __name__ == "__main__":
    run(name="etf", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["ETFs vs", "individual stocks"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "single": scene_single, "etf": scene_etf, "divers": scene_divers,
                   "trade": scene_trade, "fees": scene_fees, "both": scene_both, "end": end_card})
