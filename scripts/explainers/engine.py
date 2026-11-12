"""Shared engine for narrated cartoon explainer reels (stories/*).

A story module supplies: the narration audio, the line breakdown (scene name +
the first word(s) of each line), and one draw function per scene. The engine
transcribes the narration once with faster-whisper (cached as
<audio>.words.json next to the mp3) so scene beats and word-by-word captions
follow the real voice, then renders frames and encodes a 1080x1920 MP4 with
the narration only (music is added by hand when posting; pass music= to bake
a quiet bed in instead).

Scene functions are called as fn(img, p, t, sc) with t in seconds since the
scene started; sc["L"] holds each line's start (scene-local) and sc["w"](word)
gives a specific word's scene-local start, for beats like "pop in on 'Amazon'".
"""
import json, math, random, re, subprocess, sys, tempfile
from multiprocessing import get_context
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import social_style as ss  # noqa: E402

FPS, W, H, SS = 30, 1080, 1920, 2   # SS: supersample factor (PIL shapes aren't antialiased)
LEAD, TAIL = 0.3, 2.2
MUSIC_VOLUME = 0.10

C = ss.C
STAGE = (20, 30, 54)
SKY = (27, 39, 68)
GROUND_C = (16, 24, 44)
CREAM = (250, 236, 214)
INK = (15, 23, 42)
HAIR = (40, 30, 34)
LEG = (34, 46, 74)
PURPLE = (150, 120, 255)
COIN, COIN_RIM = (255, 200, 70), (214, 146, 30)
SX0, SY0, SX1, SY1 = 40, 380, 1040, 1300   # stage panel
GROUND = 1200
CAPTION_Y = 1440

AV = "/System/Library/Fonts/Avenir Next.ttc"
_WEIGHT = {"bold": 0, "demi": 2, "medium": 5, "regular": 7, "heavy": 8}
_fonts = {}


def F(size, weight="bold"):
    k = (int(size), weight)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(AV, int(size) * SS, index=_WEIGHT[weight])
    return _fonts[k]


# ── easing ───────────────────────────────────────────────────────────────────
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, t0, d): return clamp((t - t0) / d) if d > 0 else float(t >= t0)
def eo(x): return 1 - (1 - x) ** 3
def eio(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def back(x):
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2
def lerp(a, b, x): return a + (b - a) * x
def mix(c, a, bg=STAGE): return tuple(int(lerp(b, v, a)) for v, b in zip(c, bg))
def darker(c, f=0.78): return tuple(int(v * f) for v in c)
def qb(p0, p1, p2, u):
    return ((1-u)**2*p0[0] + 2*(1-u)*u*p1[0] + u*u*p2[0],
            (1-u)**2*p0[1] + 2*(1-u)*u*p1[1] + u*u*p2[1])


# ── drawing primitives (all coords in 1080x1920 space) ──────────────────────
class Pen:
    def __init__(self, img):
        self.img, self.d = img, ImageDraw.Draw(img)

    def _b(self, x0, y0, x1, y1): return [x0*SS, y0*SS, x1*SS, y1*SS]

    def rr(self, x0, y0, x1, y1, r, fill=None, outline=None, width=0):
        if x1 - x0 < 1 or y1 - y0 < 1: return
        r = min(r, (x1-x0)/2, (y1-y0)/2)
        self.d.rounded_rectangle(self._b(x0, y0, x1, y1), radius=r*SS, fill=fill,
                                 outline=outline, width=int(width*SS))

    def rect(self, x0, y0, x1, y1, fill):
        self.d.rectangle(self._b(x0, y0, x1, y1), fill=fill)

    def ell(self, cx, cy, rx, ry=None, fill=None, outline=None, width=0):
        ry = rx if ry is None else ry
        if rx <= 0 or ry <= 0: return
        self.d.ellipse(self._b(cx-rx, cy-ry, cx+rx, cy+ry), fill=fill,
                       outline=outline, width=int(width*SS))

    def arc(self, x0, y0, x1, y1, a0, a1, fill, width):
        self.d.arc(self._b(x0, y0, x1, y1), a0, a1, fill=fill, width=max(1, int(width*SS)))

    def chord(self, x0, y0, x1, y1, a0, a1, fill):
        self.d.chord(self._b(x0, y0, x1, y1), a0, a1, fill=fill)

    def line(self, pts, fill, width):
        self.d.line([(x*SS, y*SS) for x, y in pts], fill=fill, width=max(1, int(width*SS)), joint="curve")

    def limb(self, x0, y0, x1, y1, w, fill):
        self.line([(x0, y0), (x1, y1)], fill, w)
        self.ell(x0, y0, w/2, fill=fill); self.ell(x1, y1, w/2, fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([(x*SS, y*SS) for x, y in pts], fill=fill)

    def text(self, x, y, txt, font, fill, anchor="mm"):
        self.d.text((x*SS, y*SS), txt, font=font, fill=fill, anchor=anchor)


_sprites = {}


def sprite_text(img, cx, cy, txt, font, fill, a=1.0, scale=1.0, glow=None, rot=0):
    """Text as a composited layer so it can fade, scale, glow and rotate."""
    if a <= 0.01 or scale <= 0.01: return
    key = (txt, id(font), fill, glow)
    L = _sprites.get(key)
    if L is None:
        bb = font.getbbox(txt)
        pad = int((46 if glow else 4) * SS)
        L = Image.new("RGBA", (bb[2]-bb[0]+2*pad, bb[3]-bb[1]+2*pad), (0, 0, 0, 0))
        org = (pad - bb[0], pad - bb[1])
        if glow:
            ImageDraw.Draw(L).text(org, txt, font=font, fill=glow + (200,))
            L = L.filter(ImageFilter.GaussianBlur(14 * SS))
        ImageDraw.Draw(L).text(org, txt, font=font, fill=fill + (255,))
        _sprites[key] = L
    paste_layer(img, L, cx, cy, a, scale, rot)


def paste_layer(img, L, cx, cy, a=1.0, scale=1.0, rot=0):
    if a <= 0.01 or scale <= 0.01: return
    if rot: L = L.rotate(rot, expand=True, resample=Image.BICUBIC)
    if abs(scale - 1) > 1e-3:
        L = L.resize((max(1, int(L.width*scale)), max(1, int(L.height*scale))), Image.BICUBIC)
    if a < 0.999:
        L = L.copy(); L.putalpha(L.getchannel("A").point(lambda v: int(v * a)))
    img.paste(L, (int(cx*SS - L.width/2), int(cy*SS - L.height/2)), L)


def tracked(p, cx, cy, txt, font, fill, track):
    widths = [font.getlength(ch) for ch in txt]
    total = sum(widths) + track*SS*(len(txt)-1)
    x = cx*SS - total/2
    for ch, w in zip(txt, widths):
        p.d.text((x, cy*SS), ch, font=font, fill=fill, anchor="lm"); x += w + track*SS


_logos = {}


def ticker_logo(ticker, size):
    """Rounded ticker logo from logos/ as an RGBA layer at render scale."""
    k = (ticker, size)
    if k not in _logos:
        px = size * SS
        path = ROOT / "logos" / f"{ticker}.png"
        lg = Image.open(path).convert("RGBA").resize((px, px), Image.LANCZOS)
        # dark/colourful marks (e.g. KO's red script) vanish on the navy stage — back them with a light tile
        opaque = [l for l, a in zip(lg.convert("L").getdata(), lg.getchannel("A").getdata()) if a > 128]
        if opaque and sum(opaque) / len(opaque) < 170:
            tile = Image.new("RGBA", (px, px), (245, 247, 250, 255))
            tile.alpha_composite(lg); lg = tile
        mask = ss._rounded_mask(px, px, int(px * 0.2))
        lg.putalpha(Image.composite(lg.getchannel("A"), Image.new("L", (px, px), 0), mask))
        _logos[k] = lg
    return _logos[k]


# ── props ────────────────────────────────────────────────────────────────────
def person(p, x, feet, s=1.0, body=C["teal"], mood="smile", arm_l=0.0, arm_r=0.0,
           look=0.0, blink=False, tie=False):
    """The recurring character. arm_* 0=down .. 1=raised; mood smile|big|wow|worried;
    tie=True for suits (fund managers etc.)."""
    if s <= 0.03: return
    leg_h, bh, bw, hr = 46*s, 104*s, 82*s, 46*s
    hip = feet - leg_h; top = hip - bh
    for dx in (-17, 17):
        p.limb(x+dx*s, hip-10*s, x+dx*s, feet-6*s, 15*s, LEG)
    for side, amt in ((-1, arm_l), (1, arm_r)):
        sx, sy = x + side*(bw/2-12*s), top + 24*s
        th = math.radians(lerp(16, 158, amt)); L = 64*s
        ex, ey = sx + side*math.sin(th)*L, sy + math.cos(th)*L
        p.limb(sx, sy, ex, ey, 16*s, darker(body))
        p.ell(ex, ey, 11*s, fill=CREAM)
    p.rr(x-bw/2, top, x+bw/2, hip, 32*s, fill=body)
    if tie:
        p.poly([(x-14*s, top+2*s), (x, top+18*s), (x+14*s, top+2*s)], C["white"])
        p.poly([(x-6*s, top+14*s), (x+6*s, top+14*s), (x+9*s, top+62*s), (x, top+72*s), (x-9*s, top+62*s)], C["red"])
    else:
        p.rr(x-bw/2+16*s, top+46*s, x+bw/2-16*s, top+70*s, 10*s, fill=darker(body, .86))
    hx, hy = x + look*5*s, top - hr + 12*s
    p.ell(hx, hy, hr, fill=CREAM)
    p.chord(hx-hr, hy-hr, hx+hr, hy+hr, 192, 348, HAIR)
    ex_off = look*6*s
    for side in (-1, 1):
        ex, ey = hx + side*15*s + ex_off, hy + 4*s
        if blink: p.rr(ex-7*s, ey-1.5*s, ex+7*s, ey+1.5*s, 1.5*s, fill=INK)
        else: p.ell(ex, ey, 6*s, 8.5*s, fill=INK)
    mx, my = hx + ex_off*.6, hy + 22*s
    if mood == "big":
        p.chord(mx-15*s, my-12*s, mx+15*s, my+14*s, 0, 180, INK)
    elif mood == "wow":
        p.ell(mx, my+2*s, 7*s, 9*s, fill=INK)
    elif mood == "worried":
        p.arc(mx-12*s, my, mx+12*s, my+16*s, 200, 340, INK, 4*s)
        p.line([(hx-24*s, hy-10*s), (hx-8*s, hy-17*s)], INK, 4*s)
        p.line([(hx+8*s, hy-17*s), (hx+24*s, hy-10*s)], INK, 4*s)
    else:
        p.arc(mx-13*s, my-10*s, mx+13*s, my+8*s, 20, 160, INK, 4.5*s)


def blinking(t, seed=0.0): return (t + seed) % 3.4 < 0.11


def coin(p, cx, cy, r):
    if r <= 1: return
    p.ell(cx, cy, r, fill=COIN_RIM)
    p.ell(cx, cy, r*0.8, fill=COIN)
    p.text(cx, cy + r*0.04, "$", F(max(8, int(r*1.15)), "heavy"), COIN_RIM)


def flat_coin(p, cx, cy, w=34):
    p.ell(cx, cy+4, w, w*0.32, fill=COIN_RIM)
    p.ell(cx, cy, w, w*0.32, fill=COIN, outline=COIN_RIM, width=2)


def phone(p, cx, cy, s=1.0, price="$182.40", name="ACME CO"):
    w, h = 230*s, 420*s
    p.rr(cx-w/2, cy-h/2, cx+w/2, cy+h/2, 34*s, fill=(8, 12, 24), outline=(70, 86, 120), width=3)
    p.rr(cx-w/2+12*s, cy-h/2+12*s, cx+w/2-12*s, cy+h/2-12*s, 24*s, fill=(22, 33, 60))
    p.ell(cx-60*s, cy-150*s, 9*s, fill=PURPLE)
    p.text(cx-44*s, cy-150*s, name, F(22*s, "bold"), (180, 190, 210), anchor="lm")
    p.text(cx, cy-95*s, price, F(44*s, "heavy"), C["white"])
    pts = [(cx-80*s + i*16*s, cy-20*s - 26*s*math.sin(i*.7) * (i/10) - i*3*s) for i in range(11)]
    p.line(pts, C["green"], 4*s)
    p.rr(cx-70*s, cy+60*s, cx+70*s, cy+104*s, 22*s, fill=darker(C["green"], .35))
    p.text(cx, cy+82*s, "1 SHARE", F(24*s, "bold"), C["green"])


def building(p, cx, base, w, h, sign="ACME CO."):
    if h < 4: return
    top = base - h
    p.rr(cx-w/2, top, cx+w/2, base, 10, fill=(44, 58, 94))
    p.rect(cx-w/2+8, top, cx+w/2-8, top+14, fill=(56, 72, 112))
    cols, ww, wh = 4, 30, 34
    gx = (w - cols*ww) / (cols+1)
    y = base - 40 - wh; r = 0
    while y > top + 28:
        for c in range(cols):
            lit = (r*7 + c*3) % 5 != 0
            x = cx - w/2 + gx + c*(ww+gx)
            p.rr(x, y, x+ww, y+wh, 4, fill=(255, 205, 100) if lit else (58, 74, 112))
        y -= wh + 22; r += 1
    if sign:
        p.rr(cx-82, top-52, cx+82, top-10, 12, fill=(16, 24, 44), outline=C["teal"], width=2)
        p.text(cx, top-31, sign, F(24, "bold"), C["teal"])


def arrow(p, pts, prog_, color, width=10):
    """Polyline drawn up to prog_ (0..1) with an arrowhead at the tip."""
    if prog_ <= 0.01: return
    seg = pts[:max(2, int(len(pts) * prog_))]
    p.line(seg, color, width)
    (x0, y0), (x1, y1) = seg[-2], seg[-1]
    a = math.atan2(y1-y0, x1-x0); L = 30
    p.poly([(x1 + math.cos(a)*10, y1 + math.sin(a)*10),
            (x1 + math.cos(a+2.5)*L, y1 + math.sin(a+2.5)*L),
            (x1 + math.cos(a-2.5)*L, y1 + math.sin(a-2.5)*L)], color)


def partial(p, pts, u, color, width):
    """Polyline drawn up to fraction u of its points (with interpolation)."""
    if u <= 0 or len(pts) < 2: return
    f = u * (len(pts) - 1); k = int(f)
    seg = pts[:k+1]
    if k + 1 < len(pts):
        (x0, y0), (x1, y1) = pts[k], pts[k+1]
        seg = seg + [(lerp(x0, x1, f-k), lerp(y0, y1, f-k))]
    if len(seg) >= 2: p.line(seg, color, width)


def basket(p, bx, by, s=1.0, label=None):
    """Woven basket centred on (bx, by); s scales it (0 hides)."""
    if s <= 0.02: return
    bw, bh = 460*s, 190*s
    p.poly([(bx - bw/2, by - bh/2), (bx + bw/2, by - bh/2), (bx + bw*0.38, by + bh/2), (bx - bw*0.38, by + bh/2)], (150, 98, 40))
    for k in range(1, 4):
        yy = by - bh/2 + bh*k/4
        ww = lerp(bw/2, bw*0.38, k/4)
        p.line([(bx - ww, yy), (bx + ww, yy)], (115, 72, 26), 5*s)
    p.rr(bx - bw/2 - 14*s, by - bh/2 - 16*s, bx + bw/2 + 14*s, by - bh/2 + 10*s, 12*s, fill=(176, 118, 52))
    if label and s > 0.5:
        p.rr(bx - 70*s, by + 10*s, bx + 70*s, by + 60*s, 12*s, fill=(16, 24, 44))
        p.text(bx, by + 35*s, label, F(32*s, "heavy"), C["amber"])


def price_tag(p, cx, cy, text, s=1.0, fill=C["amber"], ink=INK):
    """Shop-style price tag pointing left."""
    if s <= 0.02: return
    w, h = 210*s, 90*s
    p.poly([(cx - w/2 - 36*s, cy), (cx - w/2, cy - h/2), (cx - w/2, cy + h/2)], fill)
    p.rr(cx - w/2 - 2*s, cy - h/2, cx + w/2, cy + h/2, 16*s, fill=fill)
    p.ell(cx - w/2 - 8*s, cy, 8*s, fill=STAGE)
    p.text(cx + 10*s, cy, text, F(40*s, "heavy"), ink)


def magnifier(p, cx, cy, s=1.0, color=C["white"]):
    p.limb(cx + 40*s, cy + 40*s, cx + 95*s, cy + 95*s, 18*s, color)
    p.ell(cx, cy, 62*s, fill=None, outline=color, width=12*s)


def trophy(p, cx, cy, s=1.0):
    gold, rim = COIN, COIN_RIM
    p.arc(cx-78*s, cy-60*s, cx-18*s, cy+10*s, 90, 270, rim, 10*s)
    p.arc(cx+18*s, cy-60*s, cx+78*s, cy+10*s, 270, 90, rim, 10*s)
    p.chord(cx-55*s, cy-120*s, cx+55*s, cy+40*s, 0, 180, gold)
    p.rect(cx-55*s, cy-62*s, cx+55*s, cy-38*s, gold)
    p.rect(cx-10*s, cy+30*s, cx+10*s, cy+70*s, rim)
    p.rr(cx-45*s, cy+66*s, cx+45*s, cy+92*s, 6*s, fill=rim)
    p.text(cx, cy-20*s, "1", F(48*s, "heavy"), rim)


def name_tile(p, cx, cy, size, label, fill):
    """Stand-in 'company logo' for made-up companies (initials on a coloured tile)."""
    p.rr(cx-size/2, cy-size/2, cx+size/2, cy+size/2, size*0.2, fill=fill)
    p.text(cx, cy, label, F(size*0.36, "heavy"), C["white"])


def warn_icon(p, cx, cy, s, color):
    p.poly([(cx, cy-22*s), (cx+25*s, cy+20*s), (cx-25*s, cy+20*s)], color)
    p.text(cx, cy+5*s, "!", F(30*s, "heavy"), INK)


_stamps = {}


def stamp(text, color=C["red"]):
    """Rubber-stamp layer (rounded outline + text), for paste_layer with rot."""
    if text not in _stamps:
        f = F(80, "heavy")
        tw = int(f.getlength(text)) + 100*SS
        w, h = tw, 150*SS
        L = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        d.rounded_rectangle([6*SS, 6*SS, w-6*SS, h-6*SS], radius=22*SS, outline=color + (255,), width=9*SS)
        d.text((w/2, h/2), text, font=f, fill=color + (255,), anchor="mm")
        _stamps[text] = L
    return _stamps[text]


_brand = {}


def end_card(img, p, t, sc):
    """Shared closing scene: brand logo, follow CTA, waving character, disclaimer."""
    if "logo" not in _brand:
        _brand["logo"] = ss.load_brand_logo(size=150*SS)
    if _brand["logo"] is not None:
        paste_layer(img, _brand["logo"], 540, 540, scale=back(prog(t, 0.0, 0.5)))
    sprite_text(img, 540, 690, "Follow for more", F(78, "heavy"), C["white"], a=prog(t, 0.3, 0.4))
    sprite_text(img, 540, 770, "stock market basics, explained simply", F(36, "demi"), C["teal"], a=prog(t, 0.6, 0.4))
    person(p, 540, GROUND, back(prog(t, 0.2, 0.5)), mood="big", arm_r=0.75 + 0.18*math.sin(t*7), arm_l=0.15,
           blink=blinking(t, 2))
    p.text(540, 1255, "For education only · not financial advice", F(28, "medium"), (130, 145, 170))


# ── narration → timeline ────────────────────────────────────────────────────
def norm(w): return re.sub(r"[^a-z0-9$]", "", w.lower())


def load_words(audio: Path):
    cache = audio.with_suffix(".words.json")
    if not cache.exists():
        try:
            import numpy as np
            from faster_whisper import WhisperModel
        except ImportError:
            sys.exit(f"No transcript cache at {cache} — `pip install faster-whisper` to create it.")
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "f32le", "-ac", "1",
                              "-ar", "16000", "-"], capture_output=True, check=True).stdout
        segs, _ = WhisperModel("small.en", compute_type="int8").transcribe(
            np.frombuffer(raw, np.float32), word_timestamps=True, language="en", beam_size=5)
        words = [[w.word.strip(), round(w.start, 3), round(w.end, 3)] for s in segs for w in s.words]
        cache.write_text(json.dumps(words, indent=0))
    out = []
    for txt, a, b in json.loads(cache.read_text()):
        if txt[:1] in "-&%" and out:   # whisper splits "Fast" "-growing", "S" "&P", "10" "%"
            out[-1]["text"] += txt; out[-1]["end"] = b
        else:
            out.append(dict(text=txt, start=a, end=b))
    return out


def line_starts(words, line_specs):
    """Index of each line's first word. line_specs: [(scene, "first words of line"), ...]."""
    starts, i = [], 0
    for _, anchor in line_specs:
        a = [norm(x) for x in anchor.split()]
        while i < len(words) and [norm(w["text"]) for w in words[i:i+len(a)]] != a:
            i += 1
        if i >= len(words): sys.exit(f"line anchor not found in narration: {anchor!r}")
        starts.append(i); i += 1
    return starts


def stretch_pauses(audio, words, line_specs, starts, pauses, out_wav):
    """TTS tends to rush between lines (ElevenLabs ignored <break> tags), so cut the
    narration in the silence between lines and pad each gap up to pauses[0] (same
    scene) or pauses[1] (new scene). Shifts the word timings to match."""
    cuts, shifts, shift = [0.0], [0.0], 0.0
    for k in range(1, len(starts)):
        prev_end, nxt = words[starts[k] - 1]["end"], words[starts[k]]["start"]
        target = pauses[1] if line_specs[k][0] != line_specs[k-1][0] else pauses[0]
        shift += max(0.0, target - (nxt - prev_end))
        cuts.append((prev_end + nxt) / 2); shifts.append(shift)
    bounds = starts[1:] + [len(words)]
    for k, (i0, i1) in enumerate(zip(starts, bounds)):
        for wd in words[i0:i1]:
            wd["start"] += shifts[k]; wd["end"] += shifts[k]
    fc = ""
    for k in range(len(cuts)):
        end = f":end={cuts[k+1]:.3f}" if k + 1 < len(cuts) else ""
        fc += (f"[0]atrim=start={cuts[k]:.3f}{end},asetpts=PTS-STARTPTS,"
               f"adelay={int((cuts[k] + shifts[k]) * 1000)}:all=1[s{k}];")
    fc += "".join(f"[s{k}]" for k in range(len(cuts))) + f"amix=inputs={len(cuts)}:normalize=0[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-filter_complex", fc,
                    "-map", "[a]", "-ar", "44100", str(out_wav)], check=True)
    return out_wav


def build_timeline(words, line_specs, starts):
    lines = []
    for k, (sc, _) in enumerate(line_specs):
        ws = words[starts[k]:(starts[k+1] if k + 1 < len(starts) else len(words))]
        lines.append(dict(scene=sc, words=ws, start=ws[0]["start"], end=ws[-1]["end"]))
    total = words[-1]["end"] + TAIL
    scenes = []
    for ln in lines:
        if not scenes or scenes[-1]["name"] != ln["scene"]:
            scenes.append(dict(name=ln["scene"], start=0.0 if not scenes else ln["start"] - 0.12, lines=[]))
        scenes[-1]["lines"].append(ln)
    for a, b in zip(scenes, scenes[1:]): a["end"] = b["start"]
    scenes[-1]["end"] = total
    for s in scenes:
        s["L"] = [ln["start"] - s["start"] for ln in s["lines"]]
        s["D"] = s["end"] - s["start"]
        sw = [w for ln in s["lines"] for w in ln["words"]]
        s["w"] = (lambda sw, s0: lambda word, n=0: [w["start"] - s0 for w in sw if norm(w["text"]) == norm(word)][n])(sw, s["start"])
    return lines, scenes, total


# ── static background ───────────────────────────────────────────────────────
def build_bg(eyebrow, title_lines):
    size = (W*SS, H*SS)
    grad = Image.linear_gradient("L").resize(size)
    img = Image.composite(Image.new("RGB", size, C["bg2"]), Image.new("RGB", size, C["bg"]), grad)
    p = Pen(img)
    tracked(p, 540, 150, eyebrow, F(28, "bold"), C["teal"], 5)
    for k, ln in enumerate(title_lines):
        p.text(540, 228 + 80*k, ln, F(70, "heavy"), C["white"])
    p.rr(SX0, SY0, SX1, SY1, 36, fill=STAGE, outline=(38, 52, 86), width=2)
    rnd = random.Random(7)
    for _ in range(70):
        p.ell(rnd.uniform(SX0+30, SX1-30), rnd.uniform(SY0+30, SY0+640), rnd.choice([1.5, 2, 2.6]),
              fill=mix((210, 220, 245), rnd.uniform(.12, .45)))
    x = SX0 + 24
    while x < SX1 - 24:
        bw, bh = rnd.uniform(50, 110), rnd.uniform(50, 190)
        x1 = min(x + bw, SX1 - 24)
        p.rect(x, GROUND - bh, x1, GROUND, SKY)
        for wy in range(int(GROUND - bh + 14), GROUND - 14, 22):
            for wx in range(int(x + 10), int(x1 - 10), 18):
                if rnd.random() < 0.18: p.rect(wx, wy, wx+6, wy+8, (52, 66, 100))
        x = x1 + rnd.uniform(4, 14)
    p.rr(SX0+1, GROUND, SX1-1, SY1-1, 35, fill=GROUND_C)
    p.rect(SX0+1, GROUND, SX1-1, GROUND+40, GROUND_C)
    return img


# ── captions ─────────────────────────────────────────────────────────────────
def chunks(words, max_words=3, max_chars=20):
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) >= max_words or len(" ".join(words[j] for j in cur + [i])) > max_chars):
            out.append(cur); cur = []
        cur.append(i)
        if w[-1] in ".,?!" and len(cur) >= 2: out.append(cur); cur = []
    if cur: out.append(cur)
    return out


def draw_captions(img, t, lines):
    active = None
    for k, ln in enumerate(lines):
        nxt = lines[k+1]["start"] if k + 1 < len(lines) else ln["end"] + 0.4
        if ln["start"] <= t < min(nxt, ln["end"] + 0.8):
            active = ln
    if not active: return
    words = [w["text"] for w in active["words"]]
    cur = max([i for i, w in enumerate(active["words"]) if w["start"] <= t] or [0])
    chunk = next(c for c in chunks(words) if cur in c)
    font = F(64, "heavy")
    space = font.getlength(" ")
    ws = [font.getlength(words[i]) for i in chunk]
    total = sum(ws) + space*(len(chunk)-1)
    if total > 860*SS:
        font = F(52, "heavy"); space = font.getlength(" "); ws = [font.getlength(words[i]) for i in chunk]
        total = sum(ws) + space*(len(chunk)-1)
    d = ImageDraw.Draw(img)
    x = W*SS/2 - total/2
    for i, w in zip(chunk, ws):
        d.text((x, CAPTION_Y*SS), words[i], font=font, fill=C["amber"] if i == cur else C["white"],
               anchor="lm", stroke_width=7*SS, stroke_fill=(5, 10, 22))
        x += w + space


# ── render ───────────────────────────────────────────────────────────────────
G = {}


def render(t):
    img = G["bg"].copy()
    p = Pen(img)
    scenes = G["scenes"]
    sc = next((s for s in scenes if s["start"] <= t < s["end"]), scenes[-1])
    lt = t - sc["start"]
    G["scene_fns"][sc["name"]](img, p, lt, sc)
    a = prog(lt, 0, 0.22) if sc is not scenes[0] else 1.0
    if sc is not scenes[-1]: a = min(a, 1 - prog(lt, sc["D"] - 0.18, 0.18))
    if a < 1:
        box = (SX0*SS, SY0*SS, SX1*SS, SY1*SS)
        img.paste(Image.blend(G["stage_bg"], img.crop(box), a), box[:2])
    draw_captions(img, t, G["lines"])
    out = img.resize((W, H), Image.LANCZOS)
    ss.draw_footer(out, G["logo"])
    return out


def _render_frame(args):
    f, frame_dir = args
    render(f / FPS).save(Path(frame_dir) / f"{f:05d}.jpg", quality=92)


def run(*, name, audio, eyebrow, title_lines, line_specs, scene_fns, music=None, pauses=(0.7, 1.2), display=None):
    """CLI entry for a story: `--still 2,10.5` writes preview PNGs, otherwise renders the MP4.
    pauses: (between lines, between scenes) in seconds, or None to keep the narration's own gaps.
    display: caption text fixes, e.g. {"P-E": "P/E"} when the script was spelled for the voice."""
    out_dir = ROOT / "stories" / "out"; out_dir.mkdir(parents=True, exist_ok=True)
    words = load_words(audio)
    for wd in words:
        for a, b in (display or {}).items():
            wd["text"] = wd["text"].replace(a, b)
    starts = line_starts(words, line_specs)
    if pauses:
        audio = stretch_pauses(audio, words, line_specs, starts, pauses, out_dir / f"{name}.narration.wav")
    for wd in words:
        wd["start"] += LEAD; wd["end"] += LEAD
    G["lines"], G["scenes"], G["total"] = build_timeline(words, line_specs, starts)
    G["scene_fns"] = scene_fns
    G["bg"] = build_bg(eyebrow, title_lines)
    G["stage_bg"] = G["bg"].crop((SX0*SS, SY0*SS, SX1*SS, SY1*SS))
    G["logo"] = ss.load_brand_logo()
    for s in G["scenes"]:
        print(f"{s['name']:8s} {s['start']:6.2f} -> {s['end']:6.2f}  lines at {[round(x, 2) for x in s['L']]}")

    if "--still" in sys.argv:
        for s in sys.argv[sys.argv.index("--still") + 1].split(","):
            path = out_dir / f"{name}_t{float(s):05.1f}.png"
            render(float(s)).save(path); print("wrote", path)
        return

    n = int(G["total"] * FPS)
    with tempfile.TemporaryDirectory() as frames:
        with get_context("fork").Pool() as pool:   # forked workers inherit G
            for i, _ in enumerate(pool.imap_unordered(_render_frame, [(f, frames) for f in range(n)], chunksize=8)):
                if i % 300 == 0: print(f"frame {i}/{n}", flush=True)
        mp4 = out_dir / f"{name}.mp4"
        total = G["total"]
        fc = f"[1]adelay={int(LEAD*1000)}:all=1,apad[vo];"
        music_in = []
        if music:
            music_in = ["-i", str(music)]
            fc += (f"[2]atrim=0:{total:.2f},volume={MUSIC_VOLUME},afade=t=out:st={total-1.8:.2f}:d=1.8[mu];"
                   f"[vo][mu]amix=inputs=2:normalize=0:duration=first[vm];")
        fc += ("[vm]" if music else "[vo]") + "loudnorm=I=-14:TP=-1.5,aresample=44100[a]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{frames}/%05d.jpg",
                        "-i", str(audio), *music_in, "-filter_complex", fc,
                        "-map", "0:v", "-map", "[a]", "-t", f"{total:.2f}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(mp4)], check=True)
    print(f"wrote {mp4} ({total:.1f}s)")
