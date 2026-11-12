#!/usr/bin/env python3
"""Explainer reel: "Compound interest".

Narration: stories/Compound-*.mp3 (ElevenLabs). Output: stories/out/compound.mp4
All figures are real compounding maths: $100/month at 7% a year, compounded monthly.

  python3 scripts/explainers/compound.py --still 3,20,40   # preview frames
  python3 scripts/explainers/compound.py                    # full render
"""
from engine import *  # noqa: F401,F403
from engine import ROOT, run

AUDIO = next((ROOT / "stories").glob("Compound-*.mp3"))

LINES = [
    ("hook", "Put $100 a month"),
    ("hook", "You'd pay in"),
    ("hook", "But at 7"),
    ("how", "How"),
    ("how", "Compound interest"),
    ("year1", "Say you invest"),
    ("year1", "That's $70"),
    ("year2", "Next year"),
    ("year2", "your growth starts"),
    ("curve", "At first"),
    ("curve", "But give it"),
    ("early", "That's why starting"),
    ("early", "Start 10 years"),
    ("early", "Time is the"),
    ("end", "Follow for more"),
]

GREY = (150, 163, 184)
R = 0.07 / 12


def value(years, monthly=100):
    n = 12 * years
    return monthly * ((1 + R) ** n - 1) / R


def bar(p, x, base, h, w, col, label, value_txt, u, value_col=C["white"]):
    if u <= 0.01: return
    p.rr(x - w/2, base - h*u, x + w/2, base, 16, fill=col)
    p.text(x, base + 34, label, F(30, "bold"), GREY)
    if u > 0.3:
        p.text(x, base - h*u - 34, value_txt, F(46, "heavy"), value_col)


def coin_stack(p, x, base, n, u=1.0, w=56):
    for k in range(int(n * u)):
        flat_coin(p, x, base - k*18, w)


def scene_hook(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    cu = back(prog(t, 0.0, 0.4))
    if cu > 0.02:
        p.rr(540 - 260*cu, 420, 540 + 260*cu, 490, 35, fill=(24, 70, 60), outline=C["green"], width=3)
        if cu > 0.6: p.text(540, 455, "$100 a month · 30 years", F(36, "heavy"), C["green"])
    # 360 monthly deposits ticking in until the totals arrive
    t_end = w("$36000") - 0.6
    mu = prog(t, 0.4, t_end - 0.4)
    ma = 1 - prog(t, t_end, 0.3)
    if ma > 0 and mu > 0:
        sprite_text(img, 540, 640, f"month {max(1, int(360 * mu))}", F(84, "heavy"), C["white"], a=ma)
        for k in range(40):
            cu = prog(t, 0.4 + k*(t_end - 0.8)/40, 0.5)
            if 0 < cu < 1 and ma > 0.5:
                coin(p, 540 + ((k*67) % 200) - 100, lerp(720, 1080, cu*cu), 22)
    base, k = 1100, 0.0042
    paid, final = 36000, value(30)
    bar(p, 330, base, paid*k, 200, (90, 104, 132), "you pay in", "$36,000", eo(prog(t, w("$36000") - 0.6, 0.8)))
    bar(p, 750, base, final*k, 200, C["green"], "you could have", "$120,000+",
        eo(prog(t, w("$120000") - 1.0, 1.4)), C["green"])


def scene_how(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    u = prog(t, 0.0, 0.35) * (1 - prog(t, L[1] - 0.5, 0.25))
    sprite_text(img, 540, 620, "How?", F(120, "heavy"), C["white"], a=u, scale=lerp(.6, 1, back(prog(t, 0, 0.35))))
    u = prog(t, w("compound") - 0.2, 0.45)
    sprite_text(img, 540, 540, "COMPOUND", F(110, "heavy"), C["amber"], a=u, scale=lerp(.6, 1, back(u)), glow=C["amber"])
    sprite_text(img, 540, 650, "INTEREST", F(110, "heavy"), C["amber"], a=prog(t, w("interest") - 0.2, 0.45), glow=C["amber"])
    # snowball rolling and growing
    ru = prog(t, w("compound") - 0.2, max(1.0, sc["D"] - L[1]))
    if ru > 0:
        r = lerp(18, 120, ru ** 1.6)
        x = lerp(140, 860, eo(ru))
        p.ell(x, GROUND - r, r, fill=(235, 242, 255))
        p.arc(x - r*0.6, GROUND - r*1.6, x + r*0.6, GROUND - r*0.4, int(200 + ru*900) % 360, int(260 + ru*900) % 360, (190, 205, 230), max(3, r*0.08))


def scene_year1(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    tracked(p, 540, 455, "YEAR 1", F(32, "bold"), C["teal"], 5)
    su = prog(t, 0.0, 0.6)
    coin_stack(p, 320, 1060, 10, su)
    if su > 0.5:
        p.text(320, 1130, "$1,000", F(48, "heavy"), C["white"])
    gu = back(prog(t, w("7") - 0.2, 0.4))
    if gu > 0.02:
        p.rr(540 - 90*gu, 640, 540 + 90*gu, 710, 35, fill=(24, 70, 60), outline=C["green"], width=3)
        if gu > 0.6: p.text(540, 675, "+7%", F(40, "heavy"), C["green"])
    nu = back(prog(t, w("$70") - 0.2, 0.4))
    if nu > 0.02:
        coin(p, 760, 1000, 40*nu)
        p.text(760, 1130, "+$70", F(48, "heavy"), C["amber"])
        p.text(760, 1180, "growth", F(28, "demi"), GREY)


def scene_year2(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    tracked(p, 540, 455, "YEAR 2", F(32, "bold"), C["teal"], 5)
    coin_stack(p, 320, 1060, 10)
    mu = eio(prog(t, 0.1, 0.6))
    flat_coin(p, lerp(760, 320, mu), lerp(1000, 1060 - 10*18, mu), 56 if mu > 0.5 else 40)
    p.text(320, 1130, "$1,070" if mu > 0.5 else "$1,000", F(48, "heavy"), C["white"])
    gu = back(prog(t, w("7") - 0.2, 0.4))
    if gu > 0.02:
        p.rr(540 - 90*gu, 640, 540 + 90*gu, 710, 35, fill=(24, 70, 60), outline=C["green"], width=3)
        if gu > 0.6: p.text(540, 675, "+7%", F(40, "heavy"), C["green"])
    a = prog(t, w("$1070") + 0.1, 0.4)
    if a > 0:
        p.text(780, 820, "+$70.00", F(44, "heavy"), mix(C["teal"], a))
        p.text(780, 868, "on your $1,000", F(28, "demi"), mix(GREY, a))
    b = back(prog(t, w("growth") - 0.2, 0.45))
    if b > 0.02:
        p.rr(780 - 190*b, 920, 780 + 190*b, 1050, 24, fill=(70, 50, 20), outline=C["amber"], width=3)
        if b > 0.6:
            p.text(780, 965, "+$4.90", F(48, "heavy"), C["amber"])
            p.text(780, 1015, "on your growth", F(30, "bold"), C["amber"])
    sprite_text(img, 540, 540, "growth earning growth", F(52, "heavy"), C["amber"], a=prog(t, w("own") - 0.3, 0.4), glow=C["amber"])


def scene_curve(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    x0, x1, y0, ytop, vmax = 150, 900, 1100, 540, 125000
    def pt(yr, v): return (lerp(x0, x1, yr/30), lerp(y0, ytop, v/vmax))
    vals = [pt(m/12, value(m/12)) for m in range(0, 361, 6)]
    paid = [pt(m/12, 1200*m/12) for m in range(0, 361, 6)]
    p.line([(x0 - 10, y0), (x1 + 20, y0)], (70, 90, 130), 3)
    for yr in (0, 10, 20, 30):
        p.text(pt(yr, 0)[0], y0 + 34, f"{yr}y", F(26, "demi"), (130, 145, 170))
    keys = [(0.1, 0.0), (L[1] - 0.1, 0.4), (sc["D"] - 0.6, 1.0)]
    u = 0.0
    for (ta, ua), (tb, ub) in zip(keys, keys[1:]):
        if t >= ta: u = lerp(ua, ub, clamp((t - ta) / (tb - ta)))
    n = int(u * (len(paid) - 1))
    for k in range(0, n, 2):
        p.line([paid[k], paid[min(k + 1, n)]], GREY, 4)
    partial(p, vals, u, C["teal"], 9)
    if u > 0.02:
        f = u * (len(vals) - 1); k = int(f)
        hx, hy = vals[k] if k + 1 >= len(vals) else (lerp(vals[k][0], vals[k+1][0], f - k), lerp(vals[k][1], vals[k+1][1], f - k))
        p.ell(hx, hy, 12, fill=C["white"])
    if u >= 0.999:
        p.text(x1 - 10, vals[-1][1] - 40, f"${value(30)/1000:.0f}k", F(46, "heavy"), C["teal"], anchor="rm")
        p.text(x1 + 10, paid[-1][1] + 10, "$36k paid in", F(30, "bold"), GREY, anchor="rm")
    sprite_text(img, 540, 470, "barely anything at first...", F(46, "heavy"), C["white"],
                a=prog(t, w("barely") - 0.3, 0.4) * (1 - prog(t, L[1] - 0.2, 0.3)))
    sprite_text(img, 540, 470, "then faster and faster", F(52, "heavy"), C["amber"], a=prog(t, w("faster") - 0.3, 0.4), glow=C["amber"])


def scene_early(img, p, t, sc):
    L, w = sc["L"], sc["w"]
    sprite_text(img, 540, 455, "Start early", F(60, "heavy"), C["white"], a=prog(t, 0.0, 0.4) * (1 - prog(t, L[2] - 0.2, 0.3)))
    base, k = 1100, 0.0021
    v30, v40 = value(30), value(40)
    gu = eo(prog(t, L[1], 1.4))
    bar(p, 340, base, v30*k, 210, C["teal"], "invest for 30 years", f"${v30/1000:.0f}k", gu)
    bar(p, 740, base, v40*k, 210, C["green"], "invest for 40 years", f"${v40/1000:.0f}k", gu, C["green"])
    if gu > 0.5:
        p.text(340, base - 30, "$36k in", F(28, "bold"), INK)
        p.text(740, base - 30, "$48k in", F(28, "bold"), INK)
    du = back(prog(t, w("double") - 0.2, 0.4))
    if du > 0.02:
        p.ell(930, 760, 62*du, fill=C["amber"])
        if du > 0.6: p.text(930, 760, "2×+", F(40, "heavy"), INK)
    u = prog(t, L[2] - 0.05, 0.45)
    sprite_text(img, 540, 455, "Time is the secret ingredient", F(50, "heavy"), C["amber"], a=u, scale=lerp(.7, 1, back(u)), glow=C["amber"])


if __name__ == "__main__":
    run(name="compound", audio=AUDIO, eyebrow="STOCK MARKET BASICS",
        title_lines=["The magic of", "compound interest"], line_specs=LINES,
        scene_fns={"hook": scene_hook, "how": scene_how, "year1": scene_year1, "year2": scene_year2,
                   "curve": scene_curve, "early": scene_early, "end": end_card})
