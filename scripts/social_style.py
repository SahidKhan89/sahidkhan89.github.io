#!/usr/bin/env python3
"""
social_style.py — shared PIL card-rendering helpers for the "daily digest"
social posts (earnings calendar, analyst ratings, dividends calendar).

Same brand palette/wordmark/footer as scripts/sec_trend_chart.py's matplotlib
chart, but built with plain PIL (grid-of-cards layouts don't need matplotlib).
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Brand palette (matches C in sec_trend_chart.py) ────────────────────────────
C = {
    "bg":    (7,   16,  31),   # #07101f
    "card":  (13,  24,  41),   # #0d1829
    "hdr_l": (20,  209, 195),  # #14d1c3
    "hdr_r": (0,   151, 167),  # #0097a7
    "teal":  (20,  209, 195),  # #14d1c3
    "green": (61,  224, 122),  # #3de07a
    "red":   (255, 77,  109),  # #ff4d6d
    "amber": (255, 179, 71),   # #ffb347
    "white": (255, 255, 255),
    "grey":  (110, 127, 150),  # #6e7f96
    "div":   (26,  38,  64),   # #1a2640
}

CW, CH = 1080, 1350
HDR_H  = 170

ROOT     = Path(__file__).parent.parent
LOGO_DIR = ROOT / "logos"

# ── Fonts ────────────────────────────────────────────────────────────────────

_BOLD_FONTS = [
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/System/Library/Fonts/Supplemental/Verdana Bold.ttf',
]
_REG_FONTS = [
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/System/Library/Fonts/Supplemental/Verdana.ttf',
]


def font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    for path in (_BOLD_FONTS if bold else _REG_FONTS):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ── Drawing primitives ─────────────────────────────────────────────────────────

def _gradient(width: int, height: int, left_rgb, right_rgb) -> Image.Image:
    img  = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    lr, lg, lb = left_rgb
    rr, rg, rb = right_rgb
    for x in range(width):
        t = x / max(width - 1, 1)
        draw.line([(x, 0), (x, height)], fill=(
            int(lr + (rr - lr) * t),
            int(lg + (rg - lg) * t),
            int(lb + (rb - lb) * t),
        ))
    return img


def _rounded_mask(w: int, h: int, radius: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int, max_lines: int) -> list:
    words = text.split()
    lines, current, truncated = [], "", False
    for word in words:
        test = (current + " " + word).strip()
        w = draw.textbbox((0, 0), test, font=fnt)[2]
        if w > max_w and current:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                truncated = True
                break
        else:
            current = test
    if current and len(lines) < max_lines:
        lines.append(current)
    if truncated and lines:
        last = lines[-1]
        while draw.textbbox((0, 0), last + "…", font=fnt)[2] > max_w and last:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def ellipsize(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> str:
    if draw.textbbox((0, 0), text, font=fnt)[2] <= max_w:
        return text
    s = text
    while s and draw.textbbox((0, 0), s + "…", font=fnt)[2] > max_w:
        s = s[:-1]
    return s + "…" if s else text


def ordinal_date(dt) -> str:
    """'Thu 4th Jun' style — matches the in-app share-page date format."""
    day = dt.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return dt.strftime(f"%a {day}{suffix} %b")


# ── Brand logo ─────────────────────────────────────────────────────────────────

def load_brand_logo(size: int = 108) -> Image.Image | None:
    candidates = [ROOT / "app_logo.png", ROOT / "brand_logo.png",
                  LOGO_DIR / "app_logo.png", LOGO_DIR / "brand_logo.png"]
    for p in candidates:
        if p.exists():
            img = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
            img.putalpha(_rounded_mask(size, size, radius=int(size * 0.22)))
            return img
    return None


# ── Header / footer ────────────────────────────────────────────────────────────

def new_canvas() -> Image.Image:
    """Fixed 1080x1350 (4:5) — Instagram's ideal portrait ratio. Every card
    type renders at this exact size so posts stay visually consistent.
    """
    return Image.new("RGB", (CW, CH), C["bg"])


HEADER_MARGIN = 24
HEADER_RADIUS = 24


def draw_header(img: Image.Image, subtitle: str, brand_logo: Image.Image | None = None) -> int:
    """Floating rounded card header. Returns the y-coordinate below it."""
    m      = HEADER_MARGIN
    hdr_w  = CW - 2 * m
    header = _gradient(hdr_w, HDR_H, C["hdr_l"], C["hdr_r"]).convert("RGBA")
    header.putalpha(_rounded_mask(hdr_w, HDR_H, HEADER_RADIUS))
    img.paste(header, (m, m), header)

    draw = ImageDraw.Draw(img)
    draw.text((m + 28, m + 34), "StockScore.co.uk", font=font(True, 46), fill=C["white"])
    draw.text((m + 28, m + 96), subtitle, font=font(False, 25), fill=(224, 255, 250))
    if brand_logo is not None:
        lx = CW - m - 28 - brand_logo.width
        ly = m + (HDR_H - brand_logo.height) // 2
        img.paste(brand_logo, (lx, ly), brand_logo)

    return m + HDR_H + m


# Same footer on every card type — matches the in-app share pages exactly.
FOOTER_TEXT = "@StockScoreUK - daily market insights"


def draw_footer(img: Image.Image, source_text: str = FOOTER_TEXT) -> None:
    draw = ImageDraw.Draw(img)
    y = img.height - 46
    draw.line([(40, y - 18), (CW - 40, y - 18)], fill=C["div"], width=2)
    draw.text((CW / 2, y), source_text, font=font(False, 22), fill=C["grey"],
               anchor="mm")


# ── Section header (e.g. "Before Open", "Upgrades") ────────────────────────────

def draw_section_header(img: Image.Image, x: int, y: int, label: str, color) -> int:
    """Draws a small colored dot + label. Returns the y-coordinate below it."""
    draw = ImageDraw.Draw(img)
    fnt  = font(True, 30)
    draw.ellipse([x, y + 6, x + 16, y + 22], fill=color)
    draw.text((x + 28, y), label, font=fnt, fill=C["white"])
    return y + 46


# ── Ticker card ─────────────────────────────────────────────────────────────────

CARD_GAP_X = 16
CARD_GAP_Y = 14


def grid_card_width(cols: int, margin_x: int = 40) -> int:
    return (CW - 2 * margin_x - (cols - 1) * CARD_GAP_X) // cols


def draw_side_card(img: Image.Image, x: int, y: int, w: int, h: int,
                    logo: Image.Image | None, title: str, lines: list,
                    fallback_bg=None, logo_cap: int = 84, title_size: int = 28) -> None:
    """A bordered card with the logo on the left (vertically centered) and a
    bold title plus a few lines stacked to its right, the whole text block
    vertically centered against the logo.

    `lines` is a list of (text, font_size, color, bold) tuples.
    """
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10,
                            outline=C["div"], width=2, fill=C["card"])

    pad = 14
    logo_size = min(h - 2 * pad, logo_cap)
    logo_x    = x + pad
    logo_y    = y + (h - logo_size) // 2

    if logo is not None:
        lg   = logo.resize((logo_size, logo_size), Image.LANCZOS).convert("RGBA")
        mask = _rounded_mask(logo_size, logo_size, int(logo_size * 0.2))
        alpha = Image.composite(lg.split()[3], Image.new("L", (logo_size, logo_size), 0), mask)
        lg.putalpha(alpha)
        img.paste(lg, (logo_x, logo_y), lg)
    else:
        draw.rounded_rectangle(
            [logo_x, logo_y, logo_x + logo_size, logo_y + logo_size],
            radius=int(logo_size * 0.2), fill=fallback_bg or C["bg"])

    text_x = logo_x + logo_size + 26
    text_w = x + w - pad - text_x

    row_heights = [title_size + 8] + [size + 6 for (text, size, _, _) in lines if text]
    total_h = sum(row_heights)
    ty = y + (h - total_h) // 2

    draw.text((text_x, ty), title, font=font(True, title_size), fill=C["white"])
    ty += title_size + 8

    for text, size, color, bold in lines:
        if not text:
            continue
        fnt  = font(bold, size)
        text = ellipsize(draw, text, fnt, text_w)
        draw.text((text_x, ty), text, font=fnt, fill=color)
        ty += size + 6


def draw_grid(img: Image.Image, items: list, x0: int, y0: int, cols: int,
              card_w: int, card_h: int, render_fn, gap_y: int = CARD_GAP_Y) -> int:
    """Lays out `items` in a `cols`-wide grid starting at (x0, y0).

    `render_fn(img, item, x, y, w, h)` draws one cell. Returns the y-coordinate
    below the grid.
    """
    for i, item in enumerate(items):
        col = i % cols
        row = i // cols
        x = x0 + col * (card_w + CARD_GAP_X)
        y = y0 + row * (card_h + gap_y)
        render_fn(img, item, x, y, card_w, card_h)
    rows = (len(items) + cols - 1) // cols
    return y0 + rows * (card_h + gap_y)


def draw_empty_note(img: Image.Image, x: int, y: int, text: str = "None scheduled") -> int:
    draw = ImageDraw.Draw(img)
    draw.text((x, y), text, font=font(False, 20), fill=C["grey"])
    return y + 40


# ── Icons (no emoji — Ubuntu CI runners don't have color-emoji glyphs) ─────────

def draw_icon_sun(img: Image.Image, cx: int, cy: int, r: int, color) -> None:
    """`r` is the total footprint radius (rays included) — kept equal to
    draw_icon_moon's so both icons occupy the same box and align with the
    grid below them instead of one bleeding wider than the other.
    """
    draw = ImageDraw.Draw(img)
    core = r * 0.44
    draw.ellipse([cx - core, cy - core, cx + core, cy + core], fill=color)
    ray_w = max(2, int(r * 0.16))
    for i in range(8):
        ang = i * math.pi / 4
        x1 = cx + math.cos(ang) * r * 0.62
        y1 = cy + math.sin(ang) * r * 0.62
        x2 = cx + math.cos(ang) * r * 0.94
        y2 = cy + math.sin(ang) * r * 0.94
        draw.line([x1, y1, x2, y2], fill=color, width=ray_w)


def draw_icon_moon(img: Image.Image, cx: int, cy: int, r: int, color, cutout_color) -> None:
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    off = r * 0.55
    draw.ellipse([cx - r + off, cy - r - off * 0.2, cx + r + off, cy + r - off * 0.2],
                 fill=cutout_color)


# ── Logo tile (app-icon-grid style — no card border, matches earnings calendar) ─

def draw_logo_tile(img: Image.Image, x: int, y: int, size: int,
                    logo: Image.Image | None, ticker: str, fallback_bg) -> int:
    """Logo (rounded corners) with the ticker centered as a label underneath.
    If no logo is available, draws a rounded fallback tile with the ticker
    text inside it instead. Returns the y-coordinate below the label.
    """
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.18)

    if logo is not None:
        lg   = logo.resize((size, size), Image.LANCZOS).convert("RGBA")
        mask = _rounded_mask(size, size, radius)
        alpha = Image.composite(lg.split()[3], Image.new("L", (size, size), 0), mask)
        lg.putalpha(alpha)
        img.paste(lg, (x, y), lg)
    else:
        draw.rounded_rectangle([x, y, x + size, y + size], radius=radius, fill=fallback_bg)
        fnt = font(True, max(12, int(size * 0.2)))
        draw.text((x + size / 2, y + size / 2), ticker, font=fnt, fill=C["white"], anchor="mm")

    label_y = y + size + 14
    draw.text((x + size / 2, label_y), ticker, font=font(False, 20), fill=(214, 220, 228),
               anchor="mm")
    return label_y + 20


def draw_tile_grid(img: Image.Image, items: list, x0: int, y0: int, cols: int,
                    tile_size: int, gap_x: int, gap_y: int, render_fn,
                    group_width: int | None = None) -> int:
    """Lays out `items` as logo tiles in a `cols`-wide grid starting at (x0, y0).

    Each row (including a short last row) is centered within `group_width` if
    given, rather than left-packed — otherwise rows are left-aligned to x0.
    `render_fn(img, item, x, y, size) -> label_bottom_y` draws one tile.
    Returns the y-coordinate below the grid.
    """
    bottom = y0
    rows = (len(items) + cols - 1) // cols
    for row in range(rows):
        row_items = items[row * cols:(row + 1) * cols]
        row_x0 = x0
        if group_width is not None:
            row_w  = len(row_items) * tile_size + (len(row_items) - 1) * gap_x
            row_x0 = x0 + (group_width - row_w) // 2
        y = y0 + row * (tile_size + gap_y)
        for i, item in enumerate(row_items):
            x = row_x0 + i * (tile_size + gap_x)
            bottom = max(bottom, render_fn(img, item, x, y, tile_size))
    return bottom
