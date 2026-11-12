#!/usr/bin/env python3
"""Explainer reel: "Why do stock prices actually move?".

Narration: stories/Prices-*.mp3 (ElevenLabs). Output: stories/out/prices.mp4

  python3 scripts/explainers/prices.py --still 3,20,40   # preview frames
  python3 scripts/explainers/prices.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("Prices-*.mp3"))

LINES = [
    ("hook", "A company announces"),
    ("hook", "So what actually"),
    ("supply", "At its core"),
    ("supply", "More buyers than"),
    ("supply", "More sellers than"),
    ("expect", "But why do"),
    ("expect", "A stock price reflects"),
    ("miss", "So if profits"),
    ("miss", "And if a struggling"),
    ("macro", "Then there's the"),
    ("macro", "Interest rates"),
    ("emotion", "And sometimes"),
    ("emotion", "Fear and excitement"),
    ("graham", "As Benjamin Graham"),
    ("graham", "in the short run"),
    ("graham", "In the long run"),
    ("end", "Follow for more"),
]

CARD = (28, 40, 70)
GREY = (150, 163, 184)


def scene_hook(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a = 1 - prog(t, L[1] - 0.25, 0.3)
    if a > 0:
        nu = back(prog(t, w("record") - 0.3, 0.45))
        if nu > 0.02:
            p.rr(540 - 330*nu, 500, 540 + 330*nu, 740, 18, fill=mix((240, 236, 226), a))
            if nu > 0.6:
                p.text(540, 535, "MARKET NEWS", F(26, "bold"), mix((90, 90, 100), a))
                p.rect(250, 556, 830, 559, mix((180, 175, 165), a))
                p.text(540, 640, "RECORD PROFITS!", F(66, "heavy"), mix((20, 120, 70), a))
        fu = back(prog(t, w("falls") - 0.15, 0.45))
        if fu > 0.02:
            p.rr(360 - 10*fu, 840, 720 + 10*fu, 1010, 26, fill=mix((70, 28, 40), a), outline=mix(C["red"], a), width=3)
            if fu > 0.6:
                p.poly([(420, 960), (450, 900), (390, 900)], mix(C["red"], a))
                p.text(475, 925, "−10%", F(84, "heavy"), mix(C["red"], a), anchor="lm")
        person(p, 880, GROUND, 1.0 * a, mood="wow" if t > w("falls") else "big", look=-1,
               arm_l=0.15, arm_r=0.15 if t > w("falls") else 0.8, blink=blinking(t))
    u = prog(t, L[1] - 0.05, 0.45)
    sprite_text(img, 540, 700, "What moves", F(96, "heavy"), C["white"], a=u, scale=lerp(.7, 1, back(u)))
    sprite_text(img, 540, 810, "stock prices?", F(96, "heavy"), C["amber"], a=u, scale=lerp(.7, 1, back(u)), glow=C["amber"])


def scene_supply(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    up, down = L[1] + 0.3, L[2] + 0.3
    pu, pd = eo(prog(t, up, 1.6)), eo(prog(t, down, 1.6))
    price = 100 + 12*pu - 22*pd
    col = C["red"] if t > down else (C["green"] if t > up else C["white"])
    bu = back(prog(t, 0.0, 0.4))
    if bu > 0.02:
        p.rr(540 - 230*bu, 470, 540 + 230*bu, 640, 26, fill=CARD, outline=(52, 70, 108), width=2)
        if bu > 0.6:
            p.text(470, 505, "ACME CO", F(26, "bold"), GREY)
            p.text(510, 570, f"${price:.2f}", F(72, "heavy"), col)
            if t > up:
                s = 22
                if t > down: p.poly([(700, 590), (700 + s, 550), (700 - s, 550)], col)
                else: p.poly([(700, 545), (700 + s, 585), (700 - s, 585)], col)
    buyers = 2 + (2 if up - 0.3 < t < down - 0.3 else 0)
    sellers = 2 + (2 if t > down - 0.3 else 0)
    for side, n, col_, xs, t_more in ((-1, buyers, C["green"], (440, 330, 220, 110), up - 0.3),
                                      (1, sellers, C["red"], (640, 750, 860, 970), down - 0.3)):
        for i in range(4):
            if i >= n: continue
            t_in = 0.2 + i*0.12 if i < 2 else t_more + (i - 2)*0.15
            s = 0.72 * back(prog(t, t_in, 0.4))
            happy = (side < 0 and up < t < down) or (side > 0 and t > down)
            person(p, xs[i], GROUND, s, body=col_, mood="big" if happy else "smile",
                   arm_l=0.85 if happy else 0.15, arm_r=0.85 if happy else 0.15, look=-side, blink=blinking(t, i + side))
    la = prog(t, 0.4, 0.4)
    p.text(280, 1252, "BUYERS", F(34, "heavy"), mix(C["green"], la))
    p.text(800, 1252, "SELLERS", F(34, "heavy"), mix(C["red"], la))
    sprite_text(img, 540, 760, "more buyers means price up", F(46, "heavy"), C["green"],
                a=prog(t, w("up") - 0.4, 0.3) * (1 - prog(t, L[2] - 0.2, 0.3)))
    sprite_text(img, 540, 760, "more sellers means price down", F(46, "heavy"), C["red"], a=prog(t, w("down") - 0.4, 0.3))


def scene_expect(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    person(p, 170, GROUND, 1.0, mood="wow" if t < L[1] else "smile", look=1, blink=blinking(t))
    bu = back(prog(t, 0.2, 0.4)) * (1 - prog(t, L[1] - 0.2, 0.3))
    if bu > 0.02:
        for k, (dx, dy, r) in enumerate(((60, -10, 10), (90, -50, 16))):
            p.ell(170 + dx*bu, 930 + dy*bu, r*bu, fill=(220, 228, 245))
        p.ell(330, 820, 110*bu, 80*bu, fill=(220, 228, 245))
        if bu > 0.6: p.text(330, 820, "buy or sell?", F(28, "heavy"), INK)
    u = prog(t, w("expectations") - 0.3, 0.45)
    sprite_text(img, 600, 520, "EXPECTATIONS", F(92, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    # today → future, profits growing along the way
    au = eo(prog(t, L[1] + 0.1, 0.9))
    if au > 0:
        arrow(p, [(lerp(330, 970, i/30), 1100) for i in range(31)], au, GREY, 8)
        p.text(340, 1150, "TODAY", F(28, "bold"), GREY, anchor="lm")
        if au > 0.95: p.text(960, 1150, "FUTURE", F(28, "bold"), C["amber"], anchor="rm")
    for i in range(5):
        cu = back(prog(t, L[1] + 0.4 + i*0.22, 0.35))
        x = 400 + i*125
        for k in range(1 + i*2):
            if cu > 0.02: flat_coin(p, x, 1070 - k*20, 40*cu)
    ru = prog(t, w("future") - 0.4, 0.5)
    if ru > 0:
        p.ell(900, 990, 110, 140, outline=mix(C["amber"], ru), width=4)
    sprite_text(img, 650, 640, "price = what investors expect", F(40, "heavy"), C["white"], a=prog(t, w("earn") - 0.4, 0.4))


def dashed_box(p, x0, y0, x1, y1, color, width=4, dash=16):
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        n = max(1, int(math.hypot(bx - ax, by - ay) / (dash*2)))
        for k in range(n):
            u0, u1 = k/n, k/n + 0.5/n
            p.line([(lerp(ax, bx, u0), lerp(ay, by, u0)), (lerp(ax, bx, u1), lerp(ay, by, u1))], color, width)


def scene_miss(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    base = 1080
    panels = (
        (290, 0.0, "Record profits", ("expected", 330, w("expected")), ("actual", 280, w("record")), C["green"],
         w("drop"), False),
        (790, L[1], "Struggling co.", ("feared", 130, w("feared")), ("actual", 210, w("better")), C["teal"],
         w("jump"), True),
    )
    for cx, t0, title, (elab, eh, et), (alab, ah, at), acol, rt, good in panels:
        pu = back(prog(t, t0, 0.4))
        if pu <= 0.02: continue
        p.rr(cx - 225*pu, 470, cx + 225*pu, 1150, 28, fill=CARD, outline=(52, 70, 108), width=2)
        if pu < 0.6: continue
        p.text(cx, 515, title, F(38, "heavy"), C["white"])
        du = eo(prog(t, et - 0.3, 0.5))
        if du > 0:
            dashed_box(p, cx - 120, base - eh*du, cx - 20, base, GREY)
            p.text(cx - 70, base + 30, elab, F(26, "bold"), GREY)
        su = eo(prog(t, at - 0.3, 0.5))
        if su > 0:
            p.rr(cx + 20, base - ah*su, cx + 120, base, 12, fill=acol)
            p.text(cx + 70, base + 30, alab, F(26, "bold"), acol)
        ru = back(prog(t, rt - 0.2, 0.4))
        if ru > 0.02:
            col = C["green"] if good else C["red"]
            y = 600
            p.rr(cx - 140*ru, y - 40, cx + 140*ru, y + 40, 20, fill=col)
            if ru > 0.6:
                if good: p.poly([(cx - 90, y + 14), (cx - 70, y - 18), (cx - 50, y + 14)], INK)
                else: p.poly([(cx - 90, y - 14), (cx - 70, y + 18), (cx - 50, y - 14)], INK)
                p.text(cx + 20, y, "stock", F(36, "heavy"), INK)


def scene_macro(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    sprite_text(img, 540, 470, "the bigger picture", F(52, "heavy"), C["white"], a=prog(t, 0.0, 0.4))
    for word, label, x, y in (("interest", "INTEREST RATES", 540, 570), ("inflation", "INFLATION", 300, 665),
                              ("economy", "ECONOMY", 780, 665)):
        u = back(prog(t, w(word) - 0.2, 0.4))
        if u > 0.02:
            tw = F(38, "heavy").getlength(label) / SS + 60
            p.rr(x - tw/2*u, y - 36*u, x + tw/2*u, y + 36*u, 36*u, fill=(40, 30, 70), outline=PURPLE, width=3)
            if u > 0.6: p.text(x, y, label, F(38, "heavy"), C["white"])
    mt = w("move") - 0.1
    mu = eio(prog(t, mt, 0.8))
    for k in range(40):
        r, c = divmod(k, 10)
        x, y = 150 + c*87, 800 + r*82
        u = back(prog(t, 0.3 + (r + c)*0.03, 0.3))
        if u <= 0.02: continue
        immune = k in (7, 22, 33)
        drop = 0 if immune else 34*mu
        col = C["teal"] if immune else mix(C["red"], mu, C["teal"])
        sz = 28*u
        p.rr(x - sz, y - sz + drop, x + sz, y + sz + drop, 8, fill=col)
    sprite_text(img, 540, 1140, "almost every stock, at once", F(40, "heavy"), C["red"], a=prog(t, w("once") - 0.3, 0.4))


def scene_emotion(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    mid = 800
    du = eo(prog(t, w("worth") - 0.6, 0.6))
    if du > 0:
        for k in range(26):
            u0, u1 = k/26, k/26 + 0.5/26
            if u0 > du: break
            p.line([(lerp(120, 960, u0), mid), (lerp(120, 960, min(u1, du)), mid)], GREY, 4)
        p.text(960, mid + 36, "what it's really worth", F(28, "bold"), mix(GREY, du), anchor="rm")
    n = 60
    pts = [(lerp(120, 960, i/n), mid - (40 + 190*(i/n)) * math.sin(i/n * 5.2 * math.pi) * 0.9) for i in range(n + 1)]
    lu = prog(t, 0.2, sc["D"] - 1.0)
    partial(p, pts, lu, C["amber"], 8)
    sprite_text(img, 540, 470, "EMOTION", F(92, "heavy"), C["amber"], a=prog(t, w("emotion") - 0.3, 0.45),
                scale=lerp(.6, 1, back(prog(t, w("emotion") - 0.3, 0.45))), glow=C["amber"])
    fu = back(prog(t, w("fear") - 0.2, 0.4))
    person(p, 200, GROUND, 0.85*fu, body=(90, 120, 200), mood="worried", blink=blinking(t))
    if fu > 0.6: p.text(200, 1250, "FEAR", F(34, "heavy"), (120, 160, 255))
    eu = back(prog(t, w("excitement") - 0.2, 0.4))
    person(p, 880, GROUND, 0.85*eu, body=C["amber"], mood="big", arm_l=0.9, arm_r=0.9, blink=blinking(t, 1))
    if eu > 0.6: p.text(880, 1250, "EXCITEMENT", F(34, "heavy"), C["amber"])


def ballot_box(img, p, cx, cy, s, t):
    if s <= 0.02: return
    for k in range(3):
        u = ((t * 1.3) + k / 3) % 1
        y = lerp(cy - 190*s, cy - 70*s, eio(u))
        if u < 0.85:
            p.rr(cx - 34*s + k*6, y - 22*s, cx + 34*s + k*6, y + 22*s, 4, fill=C["white"])
            p.line([(cx - 18*s + k*6, y - 2*s), (cx - 6*s + k*6, y + 10*s), (cx + 18*s + k*6, y - 14*s)], C["green"], 5*s)
    p.rr(cx - 120*s, cy - 70*s, cx + 120*s, cy + 110*s, 16*s, fill=(44, 58, 94))
    p.rr(cx - 60*s, cy - 78*s, cx + 60*s, cy - 64*s, 6*s, fill=INK)
    p.text(cx, cy + 25*s, "VOTE", F(44*s, "heavy"), C["teal"])


def balance(img, p, cx, cy, s, t):
    if s <= 0.02: return
    tilt = 26 * math.exp(-max(0, t) * 1.2) * math.cos(t * 5)
    p.poly([(cx, cy + 40*s), (cx + 80*s, cy + 130*s), (cx - 80*s, cy + 130*s)], (70, 90, 130))
    p.rect(cx - 7*s, cy - 120*s, cx + 7*s, cy + 60*s, (70, 90, 130))
    lx, ly = cx - 130*s, cy - 120*s + tilt*s
    rx, ry = cx + 130*s, cy - 120*s - tilt*s
    p.line([(lx, ly), (rx, ry)], (130, 150, 190), 10*s)
    for px_, py_, side in ((lx, ly, -1), (rx, ry, 1)):
        p.line([(px_, py_), (px_ - 45*s, py_ + 80*s)], GREY, 3*s)
        p.line([(px_, py_), (px_ + 45*s, py_ + 80*s)], GREY, 3*s)
        p.chord(px_ - 60*s, py_ + 50*s, px_ + 60*s, py_ + 110*s, 0, 180, (130, 150, 190))
    for k in range(3):
        flat_coin(p, lx, ly + 72*s - k*14*s, 30*s)
    name_tile(p, rx, ry + 52*s, 48*s, "$", C["teal"])


def scene_graham(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    qa = prog(t, 0.0, 0.4) * (1 - prog(t, L[1] - 0.25, 0.3))
    if qa > 0:
        sprite_text(img, 540, 640, "“", F(220, "heavy"), C["amber"], a=qa)
        sprite_text(img, 540, 800, "Benjamin Graham", F(72, "heavy"), C["white"], a=qa, scale=lerp(.8, 1, back(prog(t, 0, 0.4))))
        sprite_text(img, 540, 880, "the father of value investing", F(36, "demi"), GREY, a=qa * prog(t, 0.6, 0.4))
    su = back(prog(t, L[1] - 0.05, 0.45))
    if su > 0.02:
        tracked(p, 290, 480, "SHORT RUN", F(30, "bold"), C["teal"], 4)
        ballot_box(img, p, 290, 820, su, t - L[1])
        p.text(290, 1090, "a voting machine", F(40, "heavy"), mix(C["white"], prog(t, w("voting") - 0.2, 0.4)))
    lu = back(prog(t, L[2] - 0.05, 0.45))
    if lu > 0.02:
        tracked(p, 790, 480, "LONG RUN", F(30, "bold"), C["amber"], 4)
        balance(img, p, 790, 820, lu, t - L[2])
        p.text(790, 1090, "a weighing machine", F(40, "heavy"), mix(C["white"], prog(t, w("weighing") - 0.2, 0.4)))


if __name__ == "__main__":
    run(name="prices", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["Why do stock prices", "actually move?"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "supply": scene_supply, "expect": scene_expect, "miss": scene_miss,
                   "macro": scene_macro, "emotion": scene_emotion, "graham": scene_graham, "end": end_card})
