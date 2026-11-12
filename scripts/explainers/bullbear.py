#!/usr/bin/env python3
"""Explainer reel: "Bull vs bear markets".

Narration: stories/BullBear-*.mp3 (ElevenLabs). Output: stories/out/bullbear.mp4

  python3 scripts/explainers/bullbear.py --still 3,20,40   # preview frames
  python3 scripts/explainers/bullbear.py                    # full render
"""
import math
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("BullBear-*.mp3"))

LINES = [
    ("hook", "Why do investors"),
    ("bull", "A bull market"),
    ("bull", "Think of a bull"),
    ("bear", "A bear market"),
    ("bear", "Think of a bear"),
    ("crash", "Bear markets feel"),
    ("crash", "In 2020"),
    ("history", "But here's the thing"),
    ("recover", "That 2020 crash"),
    ("both", "Nobody can reliably"),
    ("both", "which is why"),
    ("end", "Follow for more"),
]

GREY = (150, 163, 184)
BULL, BULL_D, SNOUT = (165, 98, 56), (120, 68, 38), (225, 165, 132)
BEAR, BEAR_D, MUZZLE = (122, 88, 66), (88, 62, 46), (196, 156, 124)
HORN = (246, 236, 212)

# S&P 500 closes through 2020 (approx.): peak 19 Feb, low 23 Mar, back to the high 18 Aug
Y2020 = [(1, 3258), (35, 3335), (49, 3386), (60, 2954), (70, 2741), (82, 2237), (95, 2664), (120, 2912),
         (159, 3232), (182, 3116), (205, 3216), (230, 3389), (245, 3580), (275, 3363), (303, 3270),
         (330, 3638), (365, 3756)]


def bull_head(p, cx, cy, s):
    if s <= 0.02: return
    for side in (-1, 1):
        p.limb(cx + side*58*s, cy - 52*s, cx + side*118*s, cy - 92*s, 24*s, HORN)
        p.limb(cx + side*118*s, cy - 92*s, cx + side*128*s, cy - 150*s, 18*s, HORN)
        p.ell(cx + side*98*s, cy - 20*s, 34*s, 18*s, fill=BULL_D)
    p.rr(cx - 84*s, cy - 84*s, cx + 84*s, cy + 74*s, 62*s, fill=BULL)
    p.ell(cx, cy + 58*s, 74*s, 46*s, fill=SNOUT)
    for side in (-1, 1):
        p.ell(cx + side*26*s, cy + 60*s, 9*s, 13*s, fill=BULL_D)
        p.ell(cx + side*36*s, cy - 14*s, 10*s, fill=INK)
        p.line([(cx + side*18*s, cy - 30*s), (cx + side*54*s, cy - 42*s)], INK, 6*s)


def bear_head(p, cx, cy, s, worried=False):
    if s <= 0.02: return
    for side in (-1, 1):
        p.ell(cx + side*72*s, cy - 72*s, 34*s, fill=BEAR)
        p.ell(cx + side*72*s, cy - 72*s, 17*s, fill=MUZZLE)
    p.ell(cx, cy, 98*s, fill=BEAR)
    p.ell(cx, cy + 38*s, 52*s, 40*s, fill=MUZZLE)
    p.ell(cx, cy + 20*s, 19*s, 13*s, fill=INK)
    p.arc(cx - 16*s, cy + 34*s, cx + 16*s, cy + 58*s, 200 if worried else 20, 340 if worried else 160, INK, 4*s)
    for side in (-1, 1):
        p.ell(cx + side*36*s, cy - 20*s, 10*s, fill=INK)


def bear_paw(p, x, y, s):
    p.ell(x, y, 44*s, fill=BEAR)
    p.ell(x, y + 8*s, 22*s, 18*s, fill=MUZZLE)
    for k in (-1, 0, 1):
        p.limb(x + k*20*s, y + 36*s, x + k*24*s, y + 60*s, 7*s, HORN)


def chart_pts(data, x0, x1, ylo, yhi, vlo, vhi, xlo, xhi, log=False):
    f = (lambda v: math.log(v)) if log else (lambda v: v)
    return [(lerp(x0, x1, (d - xlo) / (xhi - xlo)), lerp(ylo, yhi, (f(v) - f(vlo)) / (f(vhi) - f(vlo)))) for d, v in data]


def scene_hook(img, p, t, sc):
    w = sc["w"]
    bu = back(prog(t, w("bulls") - 0.3, 0.45))
    bull_head(p, 280, 820 - 10*math.sin(t*4), bu)
    if bu > 0.6: p.text(280, 1010, "BULL", F(48, "heavy"), C["green"])
    ru = back(prog(t, w("bears") - 0.3, 0.45))
    bear_head(p, 800, 820 + 8*math.sin(t*3), ru)
    if ru > 0.6: p.text(800, 1010, "BEAR", F(48, "heavy"), C["red"])
    vu = back(prog(t, w("and") - 0.1, 0.35))
    if vu > 0.02:
        p.ell(540, 820, 50*vu, fill=(16, 24, 44), outline=C["amber"], width=3)
        p.text(540, 820, "vs", F(40*vu, "heavy"), C["amber"])


def scene_bull(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, w("bull") - 0.2, 0.45)
    sprite_text(img, 540, 470, "BULL MARKET", F(96, "heavy"), C["green"], a=u, scale=lerp(.6, 1, back(u)), glow=C["green"])
    pts = [(lerp(560, 950, i/20), 1040 - 380*(i/20)**1.3 - 22*math.sin(i*1.1)) for i in range(21)]
    partial(p, pts, eo(prog(t, 0.2, 2.6)), C["green"], 9)
    thrust = 0
    tt = t - w("thrusting") + 0.2
    if tt > 0: thrust = 46 * abs(math.sin(min(tt, 2.2) * 4.2)) * (1 - prog(t, w("thrusting") + 2.0, 0.3))
    bull_head(p, 280, 860 - thrust, 1.15 * back(prog(t, 0.0, 0.45)))
    if t > w("up") - 0.2:
        s = 36
        p.poly([(280, 560 - s), (280 + s, 560 + s*0.7), (280 - s, 560 + s*0.7)], C["green"])
    p.text(760, 1110, "prices rising", F(36, "heavy"), mix(C["green"], prog(t, w("rising") - 0.2, 0.4)))
    p.text(760, 1160, "confidence high", F(32, "bold"), mix(C["white"], prog(t, w("confidence") - 0.2, 0.4)))


def scene_bear(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, w("bear") - 0.2, 0.45)
    sprite_text(img, 540, 470, "BEAR MARKET", F(96, "heavy"), C["red"], a=u, scale=lerp(.6, 1, back(u)), glow=C["red"])
    x0, x1, peak = 130, 540, 600
    pts = [(lerp(x0, x1, i/20), peak + 20*math.sin(i*0.6) if i < 6 else peak + (i - 6)*30 + 18*math.sin(i*1.4)) for i in range(21)]
    partial(p, pts, eo(prog(t, 0.2, 2.4)), C["red"], 9)
    du = prog(t, w("20") - 0.4, 0.5)
    if du > 0:
        y20 = peak + 0.2 * (1060 - 500)
        for k in range(12):
            u0 = k/12
            if u0 > du: break
            p.line([(lerp(x0, x1, u0), peak), (lerp(x0, x1, u0 + 0.5/12), peak)], GREY, 3)
        p.line([(x1 + 20, peak), (x1 + 20, y20)], C["red"], 5)
        p.line([(x1 + 8, peak), (x1 + 32, peak)], C["red"], 5)
        p.line([(x1 + 8, y20), (x1 + 32, y20)], C["red"], 5)
        if du >= 1: p.text(x1 + 44, (peak + y20) / 2, "−20%", F(40, "heavy"), C["red"], anchor="lm")
        p.text(330, 570, "peak", F(28, "bold"), mix(GREY, du))
    swipe = prog(t, w("swiping") - 0.2, 1.6)
    bear_head(p, 820, 830, 1.1 * back(prog(t, 0.0, 0.45)))
    if 0 < swipe < 1:
        a = (swipe * 3) % 1
        bear_paw(p, lerp(720, 660, a), lerp(720, 1060, eio(a)), 1.0)
    elif swipe >= 1:
        bear_paw(p, 680, 1040, 1.0)
    if t > w("down") - 0.2:
        s = 36
        p.poly([(820, 1100 + s), (820 + s, 1100 - s*0.7), (820 - s, 1100 - s*0.7)], C["red"])


def draw_2020(p, t_line, u_crash, u_rec, u_rest=0.0):
    x0, x1, ylo, yhi = 140, 940, 1080, 560
    pts = chart_pts(Y2020, x0, x1, ylo, yhi, 2000, 3900, 1, 365)
    p.line([(x0 - 10, ylo + 20), (x1 + 10, ylo + 20)], (70, 90, 130), 3)
    for lab, d in (("Jan", 1), ("Apr", 91), ("Jul", 182), ("Oct", 274), ("Dec", 360)):
        p.text(lerp(x0, x1, (d - 1) / 364), ylo + 52, lab, F(26, "demi"), (130, 145, 170))
    i_peak, i_low, i_back = 2, 5, 11
    partial(p, pts[:i_peak + 1], min(1, u_crash * 3), C["teal"], 8)
    if u_crash > 1/3: partial(p, pts[i_peak:i_low + 1], (u_crash - 1/3) * 1.5, C["red"], 8)
    if u_rec > 0: partial(p, pts[i_low:i_back + 1], u_rec, C["green"], 8)
    if u_rest > 0: partial(p, pts[i_back:], u_rest, C["teal"], 8)
    return pts, i_peak, i_low, i_back


def scene_crash(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    a = 1 - prog(t, L[1] - 0.25, 0.3)
    if a > 0:
        bear_head(p, 540, 820, 1.3 * back(prog(t, 0.0, 0.45)), worried=False)
        sprite_text(img, 540, 1080, "scary", F(64, "heavy"), C["red"], a=prog(t, w("scary") - 0.3, 0.4) * a)
    if t > L[1] - 0.2:
        tracked(p, 540, 455, "S&P 500 · 2020", F(32, "bold"), C["teal"], 4)
        uc = prog(t, L[1], w("month") - L[1] + 0.2)
        pts, ip, il, _ = draw_2020(p, t, uc, 0)
        lu = back(prog(t, w("30") - 0.2, 0.4))
        if lu > 0.02:
            x, y = pts[il]
            p.rr(x + 60, y - 28*lu, x + 310, y + 28*lu, 16, fill=C["red"])
            if lu > 0.6: p.text(x + 185, y, "−34% in a month", F(30, "heavy"), C["white"])


def scene_history(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    SP = SP500_YEAR_END
    years = sorted(SP)
    x0, x1, ylo, yhi = 140, 940, 1090, 560
    pts = chart_pts([(y, SP[y]) for y in years], x0, x1, ylo, yhi, 500, 8000, years[0], years[-1], log=True)
    p.line([(x0 - 10, ylo + 20), (x1 + 10, ylo + 20)], (70, 90, 130), 3)
    for yr in (1995, 2005, 2015, 2025):
        p.text(lerp(x0, x1, (yr - 1995) / 30), ylo + 52, str(yr), F(26, "demi"), (130, 145, 170))
    u = eo(prog(t, 0.3, sc["D"] - 1.2)) * (len(pts) - 1)
    for k in range(len(pts) - 1):
        if u <= k: break
        f = min(1, u - k)
        (ax, ay), (bx, by) = pts[k], pts[k + 1]
        col = C["red"] if SP[years[k + 1]] < SP[years[k]] else C["green"]
        p.line([(ax, ay), (lerp(ax, bx, f), lerp(ay, by, f))], col, 9)
    la = prog(t, 0.6, 0.4)
    p.rr(160, 590, 186, 616, 6, fill=mix(C["green"], la)); p.text(198, 603, "bull years", F(28, "bold"), mix(C["white"], la), anchor="lm")
    p.rr(160, 640, 186, 666, 6, fill=mix(C["red"], la)); p.text(198, 653, "bear years", F(28, "bold"), mix(C["white"], la), anchor="lm")
    sprite_text(img, 540, 470, "Bulls last longer", F(60, "heavy"), C["green"], a=prog(t, w("longer") - 0.3, 0.4), glow=C["green"])


def scene_recover(img, p, t, sc):
    w = sc["w"]
    tracked(p, 540, 455, "S&P 500 · 2020", F(32, "bold"), C["teal"], 4)
    ur = eo(prog(t, w("market") - 0.2, 1.6))
    pts, ip, il, ib = draw_2020(p, t, 1.0, ur, eo(prog(t, w("months") + 0.3, 1.0)))
    px, py = pts[ip]
    for k in range(20):
        x = lerp(px, 940, k/20)
        p.line([(x, py), (x + 16, py)], GREY, 3)
    x, y = pts[il]
    p.rr(x + 60, y - 28, x + 310, y + 28, 16, fill=C["red"])
    p.text(x + 185, y, "−34% in a month", F(30, "heavy"), C["white"])
    lu = back(prog(t, w("months") - 0.3, 0.4))
    if lu > 0.02:
        bx, by = pts[ib]
        p.rr(bx - 160*lu, by - 110, bx + 160*lu, by - 50, 16, fill=C["green"])
        if lu > 0.6: p.text(bx, by - 80, "back in ~5 months", F(30, "heavy"), INK)


def scene_both(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    bull_head(p, 220, 760, 0.8 * back(prog(t, 0.0, 0.4)))
    bear_head(p, 860, 760, 0.8 * back(prog(t, 0.1, 0.4)))
    qa = prog(t, 0.3, 0.3) * (1 - prog(t, L[1] - 0.2, 0.3))
    sprite_text(img, 540, 760, "?", F(170, "heavy"), C["amber"], a=qa, scale=1 + 0.08*math.sin(t*5))
    sprite_text(img, 540, 470, "Nobody knows what's next", F(52, "heavy"), C["white"], a=prog(t, w("predict") - 0.3, 0.4) * (1 - prog(t, L[1] - 0.2, 0.3)))
    su = prog(t, w("stay") - 0.3, 0.45)
    sprite_text(img, 540, 470, "STAY INVESTED", F(88, "heavy"), C["teal"], a=su, scale=lerp(.6, 1, back(su)), glow=C["teal"])
    pu = back(prog(t, L[1] - 0.1, 0.45))
    person(p, 540, GROUND, 1.1*pu, mood="big" if t > w("stay") else "smile", arm_l=0.15, arm_r=0.15, blink=blinking(t))


if __name__ == "__main__":
    run(name="bullbear", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["Bull vs bear", "markets"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "bull": scene_bull, "bear": scene_bear, "crash": scene_crash,
                   "history": scene_history, "recover": scene_recover, "both": scene_both, "end": end_card})
