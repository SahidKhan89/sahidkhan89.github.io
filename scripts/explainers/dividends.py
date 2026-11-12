#!/usr/bin/env python3
"""Explainer reel: "How dividends actually work".

Narration: stories/Dividends-*.mp3 (ElevenLabs). Output: stories/out/dividends.mp4

  python3 scripts/explainers/dividends.py --still 3,20,40   # preview frames
  python3 scripts/explainers/dividends.py                    # full render
"""
import math, random
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("Dividends-*.mp3"))

# (scene, first words of the line) — anchors are matched against the transcript
LINES = [
    ("hook", "What if a company"),
    ("hook", "That's called a dividend"),
    ("profit", "When a company makes"),
    ("profit", "It can reinvest"),
    ("profit", "or it can share"),
    ("who", "Not every company"),
    ("who", "Fast-growing companies"),
    ("who", "but steady giants"),
    ("share", "and every share"),
    ("maths", "Say a company pays"),
    ("maths", "If you own"),
    ("maths", "$200 a year"),
    ("snow", "Now reinvest those"),
    ("snow", "which pay you"),
    ("snow", "That snowball"),
    ("warn", "But remember"),
    ("warn", "A company can cut"),
    ("end", "Follow for more"),
]


def scene_hook(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    t_div = w("dividend")
    pu = back(prog(t, 0.0, 0.55))
    po = eio(prog(t, t_div - 0.5, 0.5))
    phone(p, 340, lerp(1000, 840, pu) + 90*po, s=lerp(1.0, 0.8, po))
    src, dst = (340, 660), (790, 1206)
    n = 0
    for k in range(14):
        t0 = 0.9 + k*0.2
        if t0 > t_div - 0.7: break
        u = prog(t, t0, 0.62)
        if u <= 0: continue
        if u >= 1: n += 1; continue
        x, y = qb(src, (600, 470), (dst[0], dst[1]-30*n), eio(u))
        coin(p, x, y, 26)
    for i in range(n):
        flat_coin(p, dst[0]+150, 1194 - i*12, 32)
    person(p, 790, GROUND, 1.25, mood="big" if n else "smile", arm_r=0.15, arm_l=0.85 if n else 0.15,
           look=-1, blink=blinking(t))
    u = prog(t, t_div - 0.1, 0.5)
    sprite_text(img, 540, 520, "DIVIDEND", F(118, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 610, "money a company pays its owners", F(38, "demi"), C["white"], a=prog(t, t_div + 0.6, 0.4))


def scene_profit(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    grow = eio(prog(t, w("reinvest") + 0.5, 1.2))
    h = lerp(0, 470, eo(prog(t, 0, 0.6))) + 130*grow
    bx, base = 290, GROUND
    building(p, bx, base, 250, h)
    top = base - h
    up = back(prog(t, w("profit") - 0.1, 0.45))
    if up > 0.02:
        for dx, dy in [(-34, 0), (34, 0), (0, -44)]:
            coin(p, bx + 185 + dx, top + 40 + dy, 30*up)
        sprite_text(img, bx+185, top - 50, "PROFIT", F(36, "heavy"), C["green"], a=up)
    ar = prog(t, w("reinvest"), 0.8)
    if ar > 0:
        pts = [qb((bx+185, top+80), (bx+200, top+230), (bx+20, top+210), i/30) for i in range(31)]
        arrow(p, pts, ar, C["teal"], 9)
        sprite_text(img, bx, 1252, "REINVEST TO GROW", F(32, "bold"), C["teal"], a=prog(t, w("reinvest") + 0.1, 0.4))
    xs, cols = [640, 790, 940], [C["amber"], C["green"], PURPLE]
    t_share = w("share")
    for i, (x, col) in enumerate(zip(xs, cols)):
        s = 0.82 * back(prog(t, t_share - 0.2 + i*0.15, 0.4))
        u = prog(t, w("shareholders") - 0.6 + i*0.25, 0.6)
        got = u >= 1
        person(p, x, GROUND, s, body=col, mood="big" if got else "smile",
               arm_l=0.9 if got else 0.2, arm_r=0.9 if got else 0.2, look=-1, blink=blinking(t, i))
        if 0 < u < 1:
            cx, cy = qb((bx+185, top+20), ((bx+185+x)/2, top-160), (x, 940), eio(u))
            coin(p, cx, cy, 24)
    sprite_text(img, 790, 1252, "SHARE WITH OWNERS", F(32, "bold"), C["amber"], a=prog(t, t_share, 0.4))


def scene_who(img, p, t, sc):
    w = sc["w"]
    sprite_text(img, 540, 470, "Not every company pays one", F(46, "heavy"), C["white"],
                a=prog(t, 0.0, 0.35), scale=lerp(.85, 1, back(prog(t, 0.0, 0.4))))
    # two mystery cards hold the stage until each company is named
    for i, cx in enumerate((290, 790)):
        u = back(prog(t, 0.3 + i*0.15, 0.45))
        reveal = w("amazon") if i == 0 else w("coca-cola")
        if u > 0.02 and t < reveal - 0.2:
            p.rr(cx - 215*u, 545, cx + 215*u, 1170, 28, fill=(28, 40, 70), outline=(52, 70, 108), width=2)
            if u > 0.6:
                sprite_text(img, cx, 830, "?", F(160, "heavy"), (70, 90, 130), scale=u * (1 + 0.04*math.sin(t*5 + i)))
    # Amazon: keeps everything to grow
    ua = back(prog(t, w("amazon") - 0.2, 0.45))
    if ua > 0.02:
        cx = 290
        p.rr(cx - 215*ua, 545, cx + 215*ua, 1170, 28, fill=(28, 40, 70), outline=(52, 70, 108), width=2)
        if ua > 0.6:
            paste_layer(img, ticker_logo("AMZN", 130), cx, 650, scale=ua)
            p.text(cx, 760, "Amazon", F(40, "heavy"), C["white"])
            p.text(cx, 845, "$0", F(76, "heavy"), (150, 163, 184))
            p.text(cx, 905, "dividend", F(28, "demi"), (150, 163, 184))
            spin = prog(t, w("reinvest") - 0.1, 0.9)
            if spin > 0:
                r = 46; a0 = -90 + 360*eio(spin)*0.0
                pts = [(cx + r*math.cos(math.radians(a0 + 300*u)), 1010 + r*math.sin(math.radians(a0 + 300*u)))
                       for u in [i/40 for i in range(41)]]
                arrow(p, pts, eio(spin), C["teal"], 8)
                p.text(cx, 1110, "reinvests it all", F(30, "bold"), mix(C["teal"], spin, (28, 40, 70)))
    # Coca-Cola: decades of payouts
    uk = back(prog(t, w("coca-cola") - 0.2, 0.45))
    if uk > 0.02:
        cx = 790
        p.rr(cx - 215*uk, 545, cx + 215*uk, 1170, 28, fill=(28, 40, 70), outline=(52, 70, 108), width=2)
        if uk > 0.6:
            paste_layer(img, ticker_logo("KO", 130), cx, 650, scale=uk)
            p.text(cx, 760, "Coca-Cola", F(40, "heavy"), C["white"])
            p.text(cx, 860, "Pays dividends", F(40, "heavy"), C["amber"])
            t0 = w("coca-cola") + 0.2
            for k in range(30):
                u = prog(t, t0 + k*0.22, 0.9)
                if 0 < u < 1:
                    dx = ((k * 37) % 120) - 60
                    coin(p, cx + dx*u, lerp(1060, 930, eo(u)), 20*(1 - 0.4*u))
            p.text(cx, 1110, "for decades", F(30, "bold"), mix(C["amber"], prog(t, w("decades"), 0.4), (28, 40, 70)))


def scene_share(img, p, t, sc):
    w = sc["w"]
    u = prog(t, 0.0, 0.45)
    sprite_text(img, 540, 520, "EVERY SHARE", F(104, "heavy"), C["amber"], a=u, scale=lerp(.7, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 610, "gets the same amount", F(40, "demi"), C["white"], a=prog(t, 0.4, 0.4))
    xs, cols = [195, 425, 655, 885], [C["teal"], C["amber"], C["green"], PURPLE]
    t_drop = w("exactly") - 0.1
    for i, (x, col) in enumerate(zip(xs, cols)):
        s = 0.9 * back(prog(t, 0.1 + i*0.1, 0.4))
        tk = back(prog(t, 0.4 + i*0.1, 0.35))
        if tk > 0.02:
            p.rr(x-62*tk, 905-20*tk, x+62*tk, 905+20*tk, 12, fill=(30, 44, 76), outline=(70, 90, 130), width=2)
            if tk > .6: p.text(x, 905, "1 SHARE", F(22, "bold"), (200, 210, 230))
        u = prog(t, t_drop, 0.45)
        got = u >= 1
        if 0 < u < 1:
            coin(p, x, lerp(700, 860, eio(u)), 26)
        if got:
            sprite_text(img, x, 820, "+$0.50", F(40, "heavy"), C["green"], scale=lerp(.6, 1, back(prog(t, t_drop + 0.45, 0.3))))
        person(p, x, GROUND, s, body=col, mood="big" if got else "smile",
               arm_l=0.8 if got else 0.15, arm_r=0.8 if got else 0.15, blink=blinking(t, i*.7))


def scene_maths(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a1 = prog(t, 0, 0.35) * (1 - prog(t, L[1] - 0.15, 0.3))
    sprite_text(img, 540, 600, "$0.50", F(150, "heavy"), C["white"], a=a1,
                scale=lerp(.6, 1, back(prog(t, w("50") - 0.15, 0.5))), glow=C["green"])
    sprite_text(img, 540, 720, "per share · every quarter", F(42, "demi"), (190, 200, 220), a=a1 * prog(t, w("per"), 0.4))
    coin(p, 540, 900, 70 * back(prog(t, w("50"), 0.5)) * (1 - prog(t, L[1] - 0.15, 0.3)))
    sprite_text(img, 540, 520, "100 shares × $0.50 = $50", F(54, "heavy"), C["white"], a=prog(t, L[1] + 0.1, 0.35))
    t_four = w("four")
    for i, x in enumerate([195, 425, 655, 885]):
        bu = back(prog(t, L[1] + 0.3 + i*0.08, 0.35))
        if bu <= 0.02: continue
        lit = prog(t, t_four - 0.1 + i*0.3, 0.25)
        bw, bh = 96*bu, 84*bu
        p.rr(x-bw, 760-bh, x+bw, 760+bh, 20, fill=mix((28, 70, 60), lit, (30, 42, 72)),
             outline=mix(C["green"], lit, (70, 90, 130)), width=3)
        if bu > .7:
            p.text(x, 720, f"Q{i+1}", F(30, "bold"), (170, 182, 205))
            if lit > 0:
                sprite_text(img, x, 785, "+$50", F(48, "heavy"), C["green"], scale=lerp(.5, 1, back(lit)))
    cu = prog(t, L[2], 1.0)
    if cu > 0:
        sprite_text(img, 540, 1000, f"${int(round(200 * eo(cu)))}", F(150, "heavy"), C["green"],
                    scale=lerp(.7, 1, back(prog(t, L[2], 0.4))), glow=C["green"])
        sprite_text(img, 540, 1110, "every year", F(44, "demi"), C["white"], a=prog(t, L[2] + 0.3, 0.4))
        sprite_text(img, 540, 1225, "without selling a single share", F(38, "demi"), C["amber"], a=prog(t, w("without"), 0.4))


def scene_snow(img, p, t, sc):
    w = sc["w"]
    n, x0, x1, base = 10, 140, 940, 1150
    step = (x1 - x0) / (n - 1)
    hv = [46 * 1.27 ** i for i in range(n)]
    tracked(p, 540, 470, "SHARES YOU OWN", F(30, "bold"), C["teal"], 4)
    p.line([(100, base), (980, base)], (70, 90, 130), 3)
    times = [0.25 + i*0.7 for i in range(n)]
    for i in range(n):
        x = x0 + i*step
        p.text(x, base + 34, f"Y{i+1}", F(24, "demi"), (130, 145, 170))
        u = prog(t, times[i], 0.4)
        if u <= 0: continue
        prev = hv[i-1] if i else 0
        hh = prev + (hv[i] - prev) * back(u)
        if prev: p.rr(x-27, base-prev, x+27, base, 8, fill=C["teal"])
        if hh > prev + 1:
            p.rr(x-27, base-hh, x+27, base-prev + (8 if prev else 0), 8, fill=C["amber"])
        cu = prog(t, times[i] - 0.45, 0.45)
        if i and 0 < cu < 1:
            px = x0 + (i-1)*step
            cx, cy = qb((px, base-hv[i-1]-20), ((px+x)/2, base-hv[i]-110), (x, base-hv[i]+10), eio(cu))
            coin(p, cx, cy, 18)
    la = prog(t, 1.2, 0.4)
    if la > 0:
        p.rr(160, 545, 186, 571, 6, fill=mix(C["teal"], la)); p.text(198, 558, "shares you bought", F(28, "demi"), mix((200, 210, 230), la), anchor="lm")
        p.rr(160, 595, 186, 621, 6, fill=mix(C["amber"], la)); p.text(198, 608, "bought with dividends", F(28, "demi"), mix((200, 210, 230), la), anchor="lm")
    u = prog(t, w("compounding") - 0.15, 0.5)
    sprite_text(img, 600, 690, "COMPOUNDING", F(84, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"], rot=4)


def scene_warn(img, p, t, sc):
    w = sc["w"]
    t_cut = w("cut") - 0.1
    rnd = random.Random(11)
    for k in range(60):
        t0 = 0.1 + k*0.16 + rnd.uniform(-.05, .05)
        x = 540 + rnd.uniform(-70, 70)
        if t0 > t_cut - 0.5: break
        u = prog(t, t0, 0.55)
        if 0 < u < 1:
            coin(p, x, lerp(560, 905, u*u), 22)
    cut = t >= t_cut
    arms = lerp(0.85, 0.12, eo(prog(t, t_cut, 0.4)))
    person(p, 540, GROUND, 1.3, mood="worried" if cut else "big", arm_l=arms, arm_r=arms, blink=blinking(t, 1))
    u = prog(t, t_cut, 0.35)
    paste_layer(img, stamp("DIVIDEND CUT"), 540, 620, a=min(1, u*2), scale=lerp(1.8, 1, eo(u)), rot=8)
    wa = prog(t, w("guaranteed") - 0.2, 0.4)
    if wa > 0:
        warn_icon(p, 360, 1252, 0.9, mix(C["amber"], wa))
        p.text(395, 1252, "not guaranteed", F(36, "bold"), mix(C["amber"], wa), anchor="lm")


if __name__ == "__main__":
    run(name="dividends", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["How dividends", "actually work"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "profit": scene_profit, "who": scene_who, "share": scene_share,
                   "maths": scene_maths, "snow": scene_snow, "warn": scene_warn, "end": end_card})
