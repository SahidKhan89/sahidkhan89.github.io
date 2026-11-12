#!/usr/bin/env python3
"""Explainer reel: "What is a P/E ratio?".

Narration: stories/PE-*.mp3 (ElevenLabs, scripted as "P E" so the voice says it
properly — captions are switched back to "P/E"). Output: stories/out/pe.mp4

  python3 scripts/explainers/pe.py --still 3,20,40   # preview frames
  python3 scripts/explainers/pe.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("PE-*.mp3"))

LINES = [
    ("hook", "Two companies"),
    ("hook", "One is cheap"),
    ("hook", "How"),
    ("formula", "The answer is"),
    ("formula", "Price divided by"),
    ("earn", "Earnings are the"),
    ("earn", "Say a share"),
    ("earn", "That's a"),
    ("earn", "You're paying"),
    ("other", "Now the other"),
    ("other", "That's a"),
    ("why", "So why would"),
    ("why", "Because investors"),
    ("why", "A high"),
    ("low", "A low"),
    ("low", "Or a company"),
    ("low", "The number alone"),
    ("end", "Follow for more"),
]

CARD = (28, 40, 70)
CARD_LINE = (52, 70, 108)
CO_A, CO_B = (0, 150, 140), PURPLE


def company_card(img, p, cx, u, tile, name, tile_col, price="$100 / share"):
    if u <= 0.02: return
    p.rr(cx - 215*u, 540, cx + 215*u, 1060, 28, fill=CARD, outline=CARD_LINE, width=2)
    if u > 0.6:
        name_tile(p, cx, 650, 120*u, tile, tile_col)
        p.text(cx, 760, name, F(40, "heavy"), C["white"])
        price_tag(p, cx + 18, 860, price.split(" ")[0], s=u)
        p.text(cx, 935, "per share", F(28, "demi"), (150, 163, 184))


def scene_hook(img, p, t, sc):
    w = sc["w"]
    company_card(img, p, 290, back(prog(t, 0.1, 0.45)), "A", "Company A", CO_A)
    company_card(img, p, 790, back(prog(t, 0.3, 0.45)), "B", "Company B", CO_B)
    u = prog(t, w("cheap") - 0.1, 0.35)
    paste_layer(img, stamp("CHEAP", C["green"]), 290, 1000, a=min(1, u*2), scale=lerp(1.2, 0.62, eo(u)), rot=-7)
    u = prog(t, w("expensive") - 0.1, 0.35)
    paste_layer(img, stamp("EXPENSIVE", C["red"]), 790, 1000, a=min(1, u*2), scale=lerp(1.0, 0.5, eo(u)), rot=6)
    u = prog(t, w("how") - 0.15, 0.4)
    sprite_text(img, 540, 1150, "How?", F(80, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])


def scene_formula(img, p, t, sc):
    w = sc["w"]
    u = prog(t, w("p/e") - 0.15, 0.45)
    sprite_text(img, 540, 540, "P/E RATIO", F(120, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    pu = back(prog(t, w("price") - 0.1, 0.4))
    if pu > 0.02:
        price_tag(p, 330, 760, "$", s=0.8*pu)
        sprite_text(img, 600, 760, "Price", F(84, "heavy"), C["white"], scale=pu)
    bu = eo(prog(t, w("divided") - 0.1, 0.4))
    if bu > 0:
        p.rr(540 - 300*bu, 838, 540 + 300*bu, 850, 6, fill=C["teal"])
    eu = back(prog(t, w("earnings") - 0.1, 0.4))
    if eu > 0.02:
        coin(p, 300, 940, 44*eu)
        sprite_text(img, 600, 940, "Earnings", F(84, "heavy"), C["white"], scale=eu)


def scene_earn(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    # phase A: earnings = profit per share
    aA = 1 - prog(t, L[1] - 0.25, 0.3)
    if aA > 0:
        building(p, 250, GROUND, 220, lerp(0, 420, eo(prog(t, 0, 0.5))) * aA, sign="")
        tk = back(prog(t, 0.3, 0.4)) * aA
        if tk > 0.02:
            p.rr(700 - 200*tk, 640 - 64*tk, 700 + 200*tk, 640 + 64*tk, 20, fill=(30, 44, 76), outline=(70, 90, 130), width=3)
            if tk > 0.6: p.text(700, 640, "1 SHARE", F(48, "heavy"), C["white"])
        for k in range(5):
            cu = prog(t, w("profit") - 0.3 + k*0.25, 0.6)
            if 0 < cu < 1 and aA > 0.5:
                x, y = qb((250, 860), (480, 520), (700, 610), eio(cu))
                coin(p, x, y, 24)
        sprite_text(img, 700, 790, "= earnings per share", F(40, "heavy"), C["amber"], a=prog(t, w("share") - 0.2, 0.4) * aA)
    # phase B: $100 price, $5 earnings, P/E 20
    aB = prog(t, L[1] - 0.1, 0.3) * (1 - prog(t, L[3] - 0.25, 0.3))
    if aB > 0:
        pu = back(prog(t, w("$100") - 0.15, 0.4))
        if pu > 0.02:
            price_tag(p, 300, 600, "$100", s=1.1*pu)
            p.text(290, 680, "share price", F(30, "demi"), mix((150, 163, 184), aB))
        eu = back(prog(t, w("$5") - 0.15, 0.4))
        if eu > 0.02:
            coin(p, 700, 600, 50*eu)
            p.text(790, 600, "$5", F(64, "heavy"), mix(C["amber"], eu * aB), anchor="lm")
            p.text(760, 680, "earned per year", F(30, "demi"), mix((150, 163, 184), aB))
        ru = prog(t, L[2] - 0.05, 0.4)
        sprite_text(img, 540, 800, "$100 ÷ $5", F(56, "heavy"), C["white"], a=ru * aB)
        gu = prog(t, w("20") - 0.15, 0.45)
        sprite_text(img, 540, 930, "P/E = 20", F(120, "heavy"), C["green"], a=gu * aB, scale=lerp(.6, 1, back(gu)), glow=C["green"])
    # phase C: $20 paid for $1 of profit
    aC = prog(t, L[3] - 0.1, 0.3)
    if aC > 0:
        sprite_text(img, 540, 480, "P/E = 20", F(54, "heavy"), C["green"], a=aC)
        for k in range(20):
            r, c = divmod(k, 5)
            cu = back(prog(t, w("$20") - 0.2 + k*0.03, 0.3))
            coin(p, 170 + c*62, 640 + r*62, 26*cu)
        p.text(294, 920, "$20 paid", F(42, "heavy"), mix(C["white"], prog(t, w("$20"), 0.4)))
        au = prog(t, w("every") - 0.1, 0.5)
        if au > 0:
            arrow(p, [(lerp(480, 600, i/10), 730) for i in range(11)], eo(au), C["teal"], 10)
        ou = back(prog(t, w("$1") - 0.15, 0.4))
        coin(p, 790, 730, 56*ou)
        if ou > 0.5:
            p.text(790, 840, "$1 profit", F(42, "heavy"), C["amber"])
            p.text(790, 890, "per year", F(30, "demi"), (150, 163, 184))


def scene_other(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = back(prog(t, 0.0, 0.45))
    if u > 0.02:
        name_tile(p, 200, 560, 110*u, "B", CO_B)
        p.text(280, 535, "Company B", F(44, "heavy"), mix(C["white"], min(1, u)), anchor="lm")
        p.text(280, 590, "same $100 price", F(32, "demi"), mix((150, 163, 184), prog(t, w("same") - 0.1, 0.4)), anchor="lm")
    eu = back(prog(t, w("$1") - 0.15, 0.4))
    if eu > 0.02:
        coin(p, 760, 562, 40*eu)
        p.text(820, 562, "$1 / yr", F(44, "heavy"), C["amber"], anchor="lm")
    # P/E bars, A vs B
    bu = eio(prog(t, L[1] - 0.1, 0.9))
    x0 = 330
    for k, (lab, val, col, y) in enumerate((("Company A", 20, CO_A, 780), ("Company B", 100, CO_B, 930))):
        a = prog(t, L[1] - 0.3 + k*0.1, 0.3)
        if a <= 0: continue
        p.text(x0 - 20, y, lab, F(34, "bold"), mix(C["white"], a), anchor="rm")
        length = 4.6 * val * (bu if k == 1 else min(1, bu*5))
        p.rr(x0, y - 38, x0 + max(length, 10), y + 38, 14, fill=mix(col, a))
        if length > 40:
            p.text(x0 + length + 18, y, f"P/E {int(round(val * (bu if k == 1 else min(1, bu*5))))}", F(40, "heavy"), C["white"], anchor="lm")
    sprite_text(img, 540, 1100, "5× pricier for the same profit", F(40, "heavy"), C["amber"], a=prog(t, w("100") + 0.6, 0.4))


def scene_why(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    happy = t > L[1] + 0.3
    person(p, 190, GROUND, 1.05, mood="big" if happy else "wow", arm_l=0.15, arm_r=0.7 if happy else 0.15,
           look=1, blink=blinking(t))
    qu = prog(t, 0.2, 0.3) * (1 - prog(t, L[1], 0.3))
    sprite_text(img, 215, 820, "?", F(110, "heavy"), C["amber"], a=qu, scale=1 + 0.06*math.sin(t*6))
    sprite_text(img, 640, 520, "Why pay that?", F(64, "heavy"), C["white"], a=prog(t, 0.1, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)))
    # expected profits ramp
    base = 1100
    for i in range(5):
        x = 440 + i*120
        u = back(prog(t, w("grow") - 0.5 + i*0.18, 0.4))
        h = 40 * 1.75 ** i
        if u > 0.02:
            p.rr(x - 40, base - h*u, x + 40, base, 12, fill=C["amber"] if i else C["teal"])
            p.text(x, base + 34, "now" if i == 0 else f"Y{i}", F(26, "demi"), (130, 145, 170))
    la = prog(t, L[1] + 0.2, 0.4)
    if la > 0:
        p.text(680, 620, "expected profits", F(36, "bold"), mix(C["amber"], la))
        arrow(p, [(lerp(470, 920, i/20), lerp(1000, 700, (i/20)**2)) for i in range(21)], eo(prog(t, w("fast") - 0.3, 0.7)),
              mix(C["green"], la), 8)
    u = prog(t, w("future") - 0.6, 0.45)
    sprite_text(img, 640, 520, "A bet on the future", F(60, "heavy"), C["amber"], a=u, scale=lerp(.7, 1, back(u)), glow=C["amber"])


def scene_low(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, 0.0, 0.4)
    sprite_text(img, 540, 480, "LOW P/E =", F(64, "heavy"), C["white"], a=u, scale=lerp(.8, 1, back(u)))
    for cx, word, col, lab in ((290, "bargain", C["green"], "BARGAIN"), (790, "trouble", C["red"], "TROUBLE")):
        cu = back(prog(t, w(word) - 0.25, 0.45))
        if cu <= 0.02: continue
        p.rr(cx - 210*cu, 560, cx + 210*cu, 1050, 28, fill=CARD, outline=col, width=3)
        if cu > 0.6:
            if col == C["green"]:
                price_tag(p, cx + 18, 700, "SALE", s=cu, fill=C["green"])
                p.poly([(cx, 800), (cx + 40, 860), (cx - 40, 860)], C["green"])
                p.rect(cx - 14, 858, cx + 14, 900, C["green"])
            else:
                warn_icon(p, cx, 720, 2.2*cu, C["red"])
                p.poly([(cx, 900), (cx + 40, 840), (cx - 40, 840)], C["red"])
                p.rect(cx - 14, 800, cx + 14, 842, C["red"])
            p.text(cx, 980, lab, F(46, "heavy"), col)
    # can't tell which from the number alone: magnifier sweeps between the two
    mu = prog(t, L[2] - 0.1, 0.4)
    if mu > 0:
        sweep = 0.5 + 0.5*math.sin((t - L[2]) * 3.2)
        magnifier(p, lerp(250, 760, sweep), 760, 1.0*eo(mu), C["white"])
        sprite_text(img, 540, 1130, "look beyond the number", F(44, "heavy"), C["amber"], a=prog(t, w("alone"), 0.4))


if __name__ == "__main__":
    run(name="pe", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["What is a", "P/E ratio?"], line_specs=LINES, display={"P-E": "P/E"},
        scene_fns={"hook": scene_hook, "formula": scene_formula, "earn": scene_earn, "other": scene_other,
                   "why": scene_why, "low": scene_low, "end": end_card})
