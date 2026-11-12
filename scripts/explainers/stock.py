#!/usr/bin/env python3
"""Explainer reel: "What actually is a stock?".

Narration: stories/Stock-*.mp3 (ElevenLabs). Output: stories/out/stock.mp4

  python3 scripts/explainers/stock.py --still 3,20,40   # preview frames
  python3 scripts/explainers/stock.py                    # full render
"""
import math, random
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("Stock-*.mp3"))

LINES = [
    ("hook", "When you buy"),
    ("piece", "A stock is"),
    ("piece", "Buy one share"),
    ("why", "So why do"),
    ("why", "To raise money"),
    ("why", "To build"),
    ("reward", "In return"),
    ("reward", "If the company grows"),
    ("reward", "And some companies"),
    ("risk", "But owning"),
    ("risk", "If the company struggles"),
    ("billions", "Big companies"),
    ("billions", "Owning one"),
    ("end", "Follow for more"),
]

CARD = (28, 40, 70)
GREY = (150, 163, 184)


def share_card(p, cx, cy, s, price, col=C["white"], crack=0.0):
    if s <= 0.02: return
    p.rr(cx - 230*s, cy - 110*s, cx + 230*s, cy + 110*s, 26*s, fill=CARD, outline=(70, 90, 130), width=3)
    if s < 0.6: return
    p.text(cx, cy - 60*s, "ACME CO · 1 SHARE", F(26*s, "bold"), GREY)
    p.text(cx, cy + 20*s, price, F(84*s, "heavy"), col)
    if crack > 0:
        pts = [(cx - 200*s, cy - 90*s), (cx - 60*s, cy - 10*s), (cx - 110*s, cy + 30*s), (cx + 60*s, cy + 60*s),
               (cx + 30*s, cy + 90*s), (cx + 210*s, cy + 100*s)]
        partial(p, pts, crack, C["red"], 7)


def scene_hook(img, p, t, sc):
    w = sc["w"]
    pu = back(prog(t, 0.0, 0.5))
    if pu > 0.02:
        phone(p, 360, 820, 1.0*pu, price="$182.40")
    person(p, 780, GROUND, 1.2, mood="wow" if t > w("what") else "smile", look=-1, arm_l=0.15, arm_r=0.15,
           blink=blinking(t))
    qu = prog(t, w("own") - 0.3, 0.4)
    sprite_text(img, 780, 790, "?", F(120, "heavy"), C["amber"], a=qu, scale=lerp(.5, 1, back(qu)) * (1 + 0.05*math.sin(t*6)))
    sprite_text(img, 540, 480, "What do you actually own?", F(54, "heavy"), C["white"], a=prog(t, w("what") - 0.2, 0.4))


def scene_piece(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    bx, base, bw = 300, GROUND, 300
    h = 560 * eo(prog(t, 0.0, 0.6))
    building(p, bx, base, bw, h, sign="ACME CO.")
    # grid lines carving the company into pieces
    gu = prog(t, w("piece") - 0.4, 0.4)
    if gu > 0 and h > 100:
        for k in range(1, 4):
            x = bx - bw/2 + bw*k/4
            p.line([(x, base - h), (x, base)], mix(C["teal"], gu, (44, 58, 94)), 3)
        for k in range(1, 6):
            y = base - h*k/6
            p.line([(bx - bw/2, y), (bx + bw/2, y)], mix(C["teal"], gu, (44, 58, 94)), 3)
    fly = eio(prog(t, w("piece") + 0.2, 0.9))
    if gu > 0 and h > 100:
        px0, py0 = bx + bw*3/8, base - h*9/12
        x, y = lerp(px0, 740, fly), lerp(py0, 860, fly) - 140*math.sin(math.pi*fly)
        cw, ch = bw/4, h/6
        p.rr(x - cw/2, y - ch/2, x + cw/2, y + ch/2, 10, fill=C["amber"])
        if fly > 0.9: p.text(x, y, "YOU", F(28, "heavy"), INK)
    got = fly >= 1
    person(p, 860, GROUND, 1.0, mood="big" if got else "smile", arm_l=0.85 if got else 0.15, arm_r=0.15,
           look=-1, blink=blinking(t))
    sprite_text(img, 540, 470, "a tiny piece of a real company", F(46, "heavy"), C["white"],
                a=prog(t, w("tiny") - 0.2, 0.4) * (1 - prog(t, L[1] - 0.1, 0.3)))
    sprite_text(img, 540, 470, "you're a part-owner", F(54, "heavy"), C["amber"], a=prog(t, w("part") - 0.3, 0.4), glow=C["amber"])
    for k, (word, label) in enumerate((("buildings", "buildings"), ("products", "products"), ("profits", "profits"))):
        u = back(prog(t, w(word) - 0.2, 0.4))
        if u <= 0.02: continue
        x, y = 620 + k*150, 590
        p.rr(x - 66*u, y - 50*u, x + 66*u, y + 50*u, 18, fill=CARD, outline=(70, 90, 130), width=2)
        if k == 0:
            p.rect(x - 22*u, y - 30*u, x + 22*u, y + 22*u, (255, 205, 100))
        elif k == 1:
            p.rr(x - 26*u, y - 22*u, x + 26*u, y + 22*u, 6, fill=(176, 118, 52))
            p.line([(x - 26*u, y - 6*u), (x + 26*u, y - 6*u)], (115, 72, 26), 4)
        else:
            coin(p, x, y - 4*u, 26*u)
        p.text(x, y + 76, label, F(26, "bold"), mix(C["white"], min(1, u)))


def scene_why(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    grow = eio(prog(t, w("grow") - 0.3, 1.0))
    h = 420 * eo(prog(t, 0.0, 0.5)) + 160*grow
    building(p, 540, GROUND, 240, h, sign="ACME CO.")
    xs = (150, 280, 800, 930)
    for i, x in enumerate(xs):
        s = 0.7 * back(prog(t, 0.3 + i*0.1, 0.4))
        cu = prog(t, w("money") - 0.6 + i*0.12, 0.6)
        person(p, x, GROUND, s, body=[C["amber"], C["green"], PURPLE, (90, 160, 255)][i],
               mood="big" if cu >= 1 else "smile", look=1 if x < 540 else -1, blink=blinking(t, i))
        if 0 < cu < 1:
            cx, cy = qb((x, 960), ((x + 540)/2, 760), (540, GROUND - h/2), eio(cu))
            coin(p, cx, cy, 22)
        su = prog(t, w("sell") - 0.2 + i*0.1, 0.6)
        if 0 < su < 1:
            cx, cy = qb((540, GROUND - h*0.7), ((x + 540)/2, 700), (x, 940), eio(su))
            p.rr(cx - 30, cy - 18, cx + 30, cy + 18, 6, fill=C["amber"])
    sprite_text(img, 540, 470, "to raise money", F(60, "heavy"), C["green"], a=prog(t, w("money") - 0.3, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)),
                glow=C["green"])
    for k, (word, label) in enumerate((("build", "BUILD"), ("hire", "HIRE"), ("grow", "GROW"))):
        u = back(prog(t, w(word) - 0.2, 0.35))
        if u > 0.02:
            x = 300 + k*240
            tw = F(40, "heavy").getlength(label) / SS + 60
            p.rr(x - tw/2*u, 440, x + tw/2*u, 510, 35, fill=(24, 70, 60), outline=C["green"], width=3)
            if u > 0.6: p.text(x, 475, label, F(40, "heavy"), C["green"])


def scene_reward(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    gu = eo(prog(t, w("worth") - 0.6, 1.2))
    price = 50 + 70*gu
    share_card(p, 540, 640, back(prog(t, 0.0, 0.45)), f"${price:.0f}", C["green"] if gu > 0 else C["white"])
    if gu > 0:
        s = 26
        p.poly([(800, 610 - s), (800 + s, 610 + s*0.7), (800 - s, 610 + s*0.7)], C["green"])
    sprite_text(img, 540, 810, "your piece is worth more", F(44, "heavy"), C["green"],
                a=prog(t, w("more") - 0.2, 0.4) * (1 - prog(t, w("dividends") - 0.9, 0.3)))
    happy = t > w("worth")
    person(p, 540, GROUND, 1.0, mood="big" if happy else "smile", arm_l=0.85 if t > L[2] else 0.15,
           arm_r=0.85 if t > L[2] else 0.15, blink=blinking(t))
    for k in range(10):
        cu = prog(t, w("dividends") - 0.6 + k*0.15, 0.6)
        if 0 < cu < 1:
            coin(p, 540 + ((k*53) % 160) - 80, lerp(780, 950, cu*cu), 22)
    sprite_text(img, 540, 455, "+ dividends", F(48, "heavy"), C["amber"], a=prog(t, w("dividends") - 0.1, 0.4), glow=C["amber"])


def scene_risk(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    du = eio(prog(t, w("fall") - 0.4, 1.4))
    price = 120 * (1 - du)
    zero = t > w("zero")
    share_card(p, 540, 640, 1.0, f"${price:.0f}", C["red"] if du > 0 else C["white"], crack=eo(prog(t, w("zero") - 0.1, 0.4)))
    u = prog(t, w("risk") - 0.2, 0.35)
    paste_layer(img, stamp("RISK"), 540, 820, a=min(1, u*2), scale=lerp(1.6, 0.8, eo(u)), rot=-6)
    person(p, 540, GROUND, 1.0, mood="worried" if t > w("struggles") else "smile", blink=blinking(t))
    if zero:
        sprite_text(img, 540, 470, "it can go to zero", F(54, "heavy"), C["red"], a=prog(t, w("zero"), 0.3))


def scene_billions(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a1 = 1 - prog(t, L[1] - 0.25, 0.3)
    if a1 > 0:
        sprite_text(img, 540, 470, "billions of shares", F(56, "heavy"), C["white"], a=prog(t, w("billions") - 0.3, 0.4) * a1)
        rnd = random.Random(3)
        for k in range(30*20):
            r, c = divmod(k, 30)
            u = prog(t, 0.1 + (r + c)*0.02, 0.3)
            if u <= 0: continue
            x, y = 170 + c*25, 560 + r*25
            mine = (r, c) == (12, 18)
            col = C["amber"] if mine and t > w("shares") else mix([C["teal"], (0, 150, 140), (40, 90, 110)][rnd.randrange(3)], a1 * 0.9)
            sz = 8 * (1.8 if mine and t > w("shares") else 1) * u
            p.rect(x - sz, y - sz, x + sz, y + sz, col)
    if t > L[1] - 0.3:
        bu = back(prog(t, L[1] - 0.2, 0.45))
        if bu > 0.02:
            p.rr(380 - 300*bu, 900, 380 + 300*bu, 960, 18, fill=(100, 70, 40))
            for i, x in enumerate((200, 320, 440, 560)):
                person(p, x, 980, 0.62*bu, body=(70, 84, 120), tie=True, mood="smile", blink=blinking(t, i))
            p.rr(380 - 300*bu, 940, 380 + 300*bu, 1000, 18, fill=(126, 90, 52))
            p.text(380, 600, "THE BOARDROOM", F(30, "bold"), mix(GREY, bu)) if bu > 0.6 else None
        nope = prog(t, w("boardroom") - 0.2, 0.4)
        if nope > 0:
            p.ell(380, 790, 230*eo(nope), outline=C["red"], width=10)
            p.line([(380 - 160*eo(nope), 790 + 160*eo(nope)), (380 + 160*eo(nope), 790 - 160*eo(nope))], C["red"], 10)
        own = t > w("owner") - 0.2
        person(p, 860, GROUND, 1.05, mood="big" if own else "smile", arm_r=0.85 if own else 0.15, look=-1, blink=blinking(t, 2))
        u = prog(t, w("owner") - 0.3, 0.4)
        sprite_text(img, 860, 790, "OWNER", F(60, "heavy"), C["amber"], a=u, scale=lerp(.5, 1, back(u)), glow=C["amber"])


if __name__ == "__main__":
    run(name="stock", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["What actually", "is a stock?"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "piece": scene_piece, "why": scene_why, "reward": scene_reward,
                   "risk": scene_risk, "billions": scene_billions, "end": end_card})
