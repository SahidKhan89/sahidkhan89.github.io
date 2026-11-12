#!/usr/bin/env python3
"""Explainer reel: "IPOs: how companies go public".

Narration: stories/IPO-*.mp3 (ElevenLabs). Output: stories/out/ipo.mp4

  python3 scripts/explainers/ipo.py --still 3,20,40   # preview frames
  python3 scripts/explainers/ipo.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("IPO-*.mp3"))

LINES = [
    ("hook", "One day"),
    ("name", "It's called an"),
    ("before", "Before an IPO"),
    ("before", "The public can't"),
    ("go", "To raise more"),
    ("go", "Banks help set"),
    ("dayone", "Then on day"),
    ("dayone", "Now anyone with"),
    ("first", "Some IPOs soar"),
    ("first", "That first price"),
    ("wrap", "The company gets"),
    ("wrap", "and everyone else"),
    ("end", "Follow for more"),
]

GREY = (150, 163, 184)
CROWD = [C["amber"], C["green"], PURPLE, (90, 160, 255), C["teal"]]


def rope(p, x0, x1, y, u=1.0):
    if u <= 0.02: return
    for x in (x0, x1):
        p.rr(x - 9, y - 70*u, x + 9, y + 90, 6, fill=(200, 170, 80))
        p.ell(x, y - 74*u, 15*u, fill=(220, 190, 100))
    pts = [(lerp(x0, x1, i/20), y - 60*u + 34*math.sin(math.pi*i/20)) for i in range(21)]
    p.line(pts, (190, 40, 60), 10)


def padlock(p, cx, cy, s, open_=0.0):
    if s <= 0.02: return
    lift = 34*open_*s
    p.arc(cx - 34*s, cy - 70*s - lift, cx + 34*s, cy + 0*s - lift, 180, 360, (200, 205, 215), 12*s)
    p.line([(cx - 28*s, cy - 36*s - lift), (cx - 28*s, cy - 10*s)], (200, 205, 215), 12*s) if open_ < 0.5 else None
    p.line([(cx + 28*s, cy - 36*s - lift), (cx + 28*s, cy - 10*s - lift)], (200, 205, 215), 12*s)
    p.rr(cx - 50*s, cy - 14*s, cx + 50*s, cy + 64*s, 14*s, fill=C["amber"])
    p.ell(cx, cy + 22*s, 9*s, fill=INK)


def bank(p, cx, base, s=1.0):
    if s <= 0.02: return
    w, h = 300*s, 300*s
    p.rect(cx - w/2, base - 30*s, cx + w/2, base, (150, 160, 185))
    for k in range(4):
        x = cx - w/2 + 40*s + k*(w - 80*s)/3
        p.rect(x - 16*s, base - h + 80*s, x + 16*s, base - 30*s, (205, 212, 228))
    p.rect(cx - w/2 + 10*s, base - h + 60*s, cx + w/2 - 10*s, base - h + 84*s, (170, 180, 205))
    p.poly([(cx - w/2 - 10*s, base - h + 62*s), (cx, base - h - 40*s), (cx + w/2 + 10*s, base - h + 62*s)], (150, 160, 185))
    if s > 0.6: p.text(cx, base - h + 30*s, "BANK", F(34*s, "heavy"), INK)


def scene_hook(img, p, t, sc):
    w = sc["w"]
    h = 460 * eo(prog(t, 0.0, 0.5))
    building(p, 290, GROUND, 250, h)
    t_open = w("next") - 0.1
    op = eio(prog(t, t_open, 0.4))
    pu = back(prog(t, 0.3, 0.4)) * (1 - prog(t, t_open, 0.3))
    if pu > 0.02:
        p.rr(290 - 100*pu, GROUND - h - 120, 290 + 100*pu, GROUND - h - 70, 25, fill=C["red"])
        if pu > 0.6: p.text(290, GROUND - h - 95, "PRIVATE", F(30, "heavy"), C["white"])
    rope(p, 560, 1000, 1090, 1 - op)
    padlock(p, 780, 1010, back(prog(t, 0.4, 0.4)) * (1 - prog(t, t_open + 0.5, 0.3)), op)
    for i, x in enumerate((640, 760, 880, 980)):
        s = 0.72 * back(prog(t, w("anyone") - 0.2 + i*0.1, 0.4))
        person(p, x, GROUND, s, body=CROWD[i], mood="big" if op > 0.5 else "smile",
               arm_r=0.85 if op > 0.5 else 0.15, look=-1, blink=blinking(t, i))
    u = prog(t, w("how") - 0.2, 0.4)
    sprite_text(img, 540, 480, "How?", F(96, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])


def scene_name(img, p, t, sc):
    w = sc["w"]
    u = prog(t, w("ipo") - 0.2, 0.45)
    sprite_text(img, 540, 560, "IPO", F(180, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    for k, (word, rest) in enumerate((("initial", "nitial"), ("public", "ublic"), ("offering", "ffering"))):
        a = prog(t, w(word) - 0.2, 0.35)
        if a <= 0: continue
        y = 760 + k*110
        f = F(76, "heavy")
        first = word[0].upper()
        x0 = 330
        p.text(x0, y, first, f, mix(C["amber"], a), anchor="lm")
        p.text(x0 + f.getlength(first) / SS + 4, y, rest, f, mix(C["white"], a), anchor="lm")


def scene_before(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    cx, cy, r = 300, 800, 190
    bb = [(cx - r)*SS, (cy - r)*SS, (cx + r)*SS, (cy + r)*SS]
    segs = (("founders", C["teal"], 180), ("employees", C["green"], 72), ("investors", PURPLE, 108))
    a0 = -90
    for word, col, span in segs:
        u = eio(prog(t, w(word) - 0.3, 0.5))
        if u > 0: p.d.pieslice(bb, a0, a0 + span*u, fill=col)
        a0 += span
    p.ell(cx, cy, r*0.5, fill=STAGE)
    if t > 0.2: p.text(cx, cy, "owners", F(30, "bold"), GREY)
    la = 1 - prog(t, L[1] - 0.25, 0.3)
    for k, (word, col, _) in enumerate(segs):
        u = prog(t, w(word) - 0.2, 0.35) * la
        if u > 0:
            y = 680 + k*100
            p.rr(560, y - 20, 600, y + 20, 8, fill=mix(col, u))
            p.text(620, y, {"founders": "founders", "employees": "employees", "investors": "early investors"}[word],
                   F(42, "heavy"), mix(C["white"], u), anchor="lm")
    if t > L[1] - 0.2:
        for i, x in enumerate((650, 780, 910)):
            s = 0.7 * back(prog(t, L[1] - 0.1 + i*0.1, 0.4))
            person(p, x, GROUND, s, body=CROWD[i], mood="worried", look=-1, blink=blinking(t, i))
        rope(p, 590, 990, 1090, back(prog(t, L[1], 0.4)))
        sprite_text(img, 780, 620, "the public can't buy", F(44, "heavy"), C["red"], a=prog(t, w("can't") - 0.2, 0.4))


def scene_go(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    shrink = 1 - eio(prog(t, L[1] - 0.3, 0.5))
    h = 480 * eo(prog(t, 0.0, 0.5)) * shrink
    building(p, 540, GROUND, 260, h, sign="ACME CO." if shrink > 0.8 else "")
    u = prog(t, w("public") - 0.3, 0.45) * shrink
    sprite_text(img, 540, 480, "GOING PUBLIC", F(84, "heavy"), C["green"], a=u, scale=lerp(.6, 1, back(prog(t, w("public") - 0.3, 0.45))),
                glow=C["green"])
    if t > L[1] - 0.2:
        bank(p, 250, GROUND, back(prog(t, L[1] - 0.1, 0.45)))
        price_tag(p, 270, 560, "$20", s=1.1*back(prog(t, w("price") - 0.2, 0.4)))
        for i, x in enumerate((660, 800, 940)):
            s = 0.72 * back(prog(t, w("big") - 0.4 + i*0.1, 0.4))
            su = prog(t, w("sell") - 0.1 + i*0.2, 0.6)
            person(p, x, GROUND, s, body=(70, 84, 120), tie=True, mood="big" if su >= 1 else "smile",
                   arm_l=0.8 if su >= 1 else 0.15, look=-1, blink=blinking(t, i))
            if 0 < su < 1:
                sx, sy = qb((300, 900), ((300 + x)/2, 640), (x, 960), eio(su))
                p.rr(sx - 34, sy - 20, sx + 34, sy + 20, 6, fill=C["amber"])
        p.text(800, 1250, "big investors", F(34, "heavy"), mix(GREY, prog(t, w("investors") - 0.2, 0.4)))


def scene_dayone(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    cu = back(prog(t, w("day") - 0.2, 0.4))
    if cu > 0.02:
        p.rr(210 - 110*cu, 500, 210 + 110*cu, 720, 18, fill=(240, 240, 245))
        p.rr(210 - 110*cu, 500, 210 + 110*cu, 560, 18, fill=C["red"])
        p.rect(210 - 110*cu, 540, 210 + 110*cu, 560, C["red"])
        if cu > 0.6:
            p.text(210, 530, "DAY", F(30, "heavy"), C["white"])
            p.text(210, 640, "1", F(110, "heavy"), INK)
    bu = back(prog(t, w("exchange") - 0.4, 0.45))
    if bu > 0.02:
        p.rr(380, 500, 380 + 620*bu, 720, 20, fill=(10, 14, 26), outline=(70, 90, 130), width=3)
        if bu > 0.6:
            p.text(690, 535, "STOCK EXCHANGE", F(26, "bold"), GREY)
            pu = prog(t, w("trading") - 0.3, 3.0)
            price = 20 + 3.4*eo(pu) + 0.6*math.sin(t*6)*(pu > 0)
            up = price >= 20
            p.text(420, 625, "ACME", F(56, "heavy"), C["white"], anchor="lm")
            p.text(950, 625, f"${price:.2f}", F(56, "heavy"), C["green"] if up else C["red"], anchor="rm")
            for k in range(9):
                p.rect(400 + k*66, 690, 440 + k*66, 696, (40, 52, 84))
    for i, x in enumerate((150, 345, 540, 735, 930)):
        s = 0.66 * back(prog(t, w("anyone") - 0.2 + i*0.08, 0.4))
        act = t > w("buy") + i*0.12
        person(p, x, GROUND, s, body=CROWD[i], mood="big" if act else "smile",
               arm_r=0.7 if act else 0.15, blink=blinking(t, i))
    for k in range(6):
        su = prog(t, w("sell") - 0.2 + k*0.3, 0.6)
        if 0 < su < 1:
            a, b = (150 + (k % 4)*195, 980), (345 + ((k + 2) % 4)*195, 980)
            sx, sy = qb(a, ((a[0] + b[0])/2, 820), b, eio(su))
            p.rr(sx - 26, sy - 16, sx + 26, sy + 16, 5, fill=C["amber"])


def scene_first(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a = 1 - prog(t, L[1] - 0.25, 0.3)
    if a > 0:
        for cx, word, col, sign in ((290, "soar", C["green"], -1), (790, "others", C["red"], 1)):
            u = back(prog(t, w(word) - 0.3, 0.45))
            if u <= 0.02: continue
            p.rr(cx - 220*u, 500, cx + 220*u, 1100, 26, fill=mix((28, 40, 70), a), outline=mix(col, a), width=3)
            if u < 0.6: continue
            ipo_y = 820
            for k in range(14):
                x = cx - 190 + k*28
                p.line([(x, ipo_y), (x + 14, ipo_y)], mix(GREY, a), 3)
            p.text(cx + 190, ipo_y - 24, "IPO price", F(24, "bold"), mix(GREY, a), anchor="rm")
            pts = [(cx - 190 + i*19, ipo_y + sign*(220*(i/20)**0.8) + 14*math.sin(i*1.7)) for i in range(21)]
            partial(p, pts, eo(prog(t, w(word) - 0.1, 0.9)), mix(col, a), 8)
            p.text(cx, 560, "soars" if sign < 0 else "falls", F(48, "heavy"), mix(col, a))
    if t > L[1] - 0.2:
        b = back(prog(t, L[1] - 0.1, 0.45))
        price_tag(p, 560, 740, "$20", s=1.8*b)
        qu = prog(t, w("guess") - 0.3, 0.4)
        sprite_text(img, 800, 640, "?", F(140, "heavy"), C["amber"], a=qu, scale=1 + 0.06*math.sin(t*6))
        sprite_text(img, 540, 940, "just a best guess", F(56, "heavy"), C["amber"], a=qu, glow=C["amber"])
        sprite_text(img, 540, 1030, "at what the company is worth", F(36, "demi"), C["white"], a=prog(t, w("worth") - 0.3, 0.4))


def scene_wrap(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    # column 1: the company
    cu = prog(t, 0.0, 0.5)
    building(p, 200, 1080, 170, 340*eo(cu), sign="")
    p.text(200, 1140, "money to grow", F(28, "heavy"), mix(C["green"], prog(t, w("grow") - 0.3, 0.4)))
    # column 2: early owners
    eu = back(prog(t, w("early") - 0.3, 0.4))
    cash = t > w("cash")
    person(p, 540, 1080, 0.9*eu, body=C["amber"], mood="big" if cash else "smile", arm_l=0.8 if cash else 0.15,
           arm_r=0.8 if cash else 0.15, blink=blinking(t))
    for k in range(8):
        ku = prog(t, w("cash") - 0.2 + k*0.12, 0.5)
        if 0 < ku < 1:
            coin(p, 540 + ((k*47) % 140) - 70, lerp(700, 860, ku*ku), 20)
    p.text(540, 1140, "a chance to cash in", F(28, "heavy"), mix(C["amber"], prog(t, w("cash") - 0.3, 0.4)))
    # column 3: everyone else
    for i, x in enumerate((800, 880, 960)):
        s = 0.55 * back(prog(t, L[1] - 0.1 + i*0.1, 0.4))
        own = t > w("piece") - 0.2
        person(p, x, 1080, s, body=CROWD[i + 2], mood="big" if own else "smile", arm_r=0.8 if own else 0.15,
               blink=blinking(t, i))
    p.text(880, 1140, "a piece to own", F(28, "heavy"), mix(C["teal"], prog(t, w("piece") - 0.3, 0.4)))
    sprite_text(img, 540, 480, "everyone gets something", F(52, "heavy"), C["white"], a=prog(t, L[1] + 0.2, 0.4))


if __name__ == "__main__":
    run(name="ipo", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["How companies", "go public (IPOs)"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "name": scene_name, "before": scene_before, "go": scene_go,
                   "dayone": scene_dayone, "first": scene_first, "wrap": scene_wrap, "end": end_card})
