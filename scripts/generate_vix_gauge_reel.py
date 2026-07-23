#!/usr/bin/env python3
"""
generate_vix_gauge_reel.py — Render today's VIX reading as a vertical
(1080x1920) "needle sweep" reveal video, posted to Instagram as a Reel by
scripts/post_vix_gauge.py (which falls back to the static card image for
Instagram if this script hasn't produced a video for the date — and always
uses the static image for Threads/Facebook, since their reel/video
publishing flows aren't wired up).

Reuses generate_vix_gauge_card.py's render_gauge_tile() as-is (same arc/
needle/hub drawing at the same size) rather than reimplementing the dial —
unlike the sector heatmap grid, a single gauge doesn't need reel-specific
proportions, so calling it once per frame with an interpolated value sweeps
the needle for free.

Sequence: title card -> needle sweeps from 0 up to the live reading (price
counting up in lockstep) -> price/change/zone badge fade in -> zone legend
fades in -> hold.

Requires ffmpeg on PATH (invoked via subprocess — not a pip dependency).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) same as the card script — the
underlying reading is always whatever the backend currently has cached.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import social_style as ss
import generate_vix_gauge_card as card

ROOT          = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT / "images" / "vix-gauge-reel"
AUDIO_DIR     = ROOT / "assets" / "audio"
REEL_MANIFEST = Path(__file__).parent / "_vix_gauge_reel_manifest.json"

# Background track picked at random each run for variety (see assets/audio/).
AUDIO_CREDITS = {
    "Game Time.mp3":               "Game Time",
    "Golden Brown.mp3":            "Golden Brown",
    "Just the Way You Are.mp3":    "Just the Way You Are",
    "Stupid Song.mp3":             "Stupid Song",
    "summer on the inside.mp3":    "summer on the inside",
    "Young Hearts Run Free.mp3":   "Young Hearts Run Free",
}

FPS            = 30
REEL_W, REEL_H = 1080, 1920
FOOTER_ZONE    = 90    # matches draw_footer's fixed offset from img.height
TOP_SAFE_PAD   = 450   # keeps the header out of the very top of the frame — both
                       # the immersive Reel viewer's own UI chrome up there, and
                       # (more importantly) the profile grid thumbnail, which
                       # center-crops the 9:16 frame down towards square and
                       # would otherwise cut the branded header off entirely

TOP_TITLE_SIZE = 34

PRICE_FONT_SIZE  = 128
CHANGE_FONT_SIZE = 36
BADGE_FONT_SIZE  = 38

SWEEP_FRAMES    = 54   # ~1.8s needle sweep from 0 up to the live reading
SWEEP_HOLD      = 10   # ~0.33s pause once the needle lands, before readout fades in
READOUT_FRAMES  = 14   # ~0.47s fade-in for price/change/badge
LEGEND_FRAMES   = 14   # ~0.47s fade-in for the zone legend strip
END_HOLD_FRAMES = 65   # ~2.2s holding on the finished card

TITLE_HEADLINE      = "VIX FEAR GAUGE"
TITLE_TAGLINE       = "Wall Street's volatility index"
TITLE_HEADLINE_SIZE = 84
TITLE_DATE_SIZE     = 40
TITLE_TAGLINE_SIZE  = 30
TITLE_FADE_FRAMES   = 15   # ~0.5s pop-in
TITLE_HOLD_FRAMES   = 55   # ~1.8s static hold (readable by a cover-frame grab)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def _render_title_overlay(w: int, human_date: str) -> Image.Image:
    block_h = (TITLE_HEADLINE_SIZE + 22) + (TITLE_DATE_SIZE + 26) + (TITLE_TAGLINE_SIZE + 4)
    overlay = Image.new("RGBA", (w + 1, block_h + 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx = w / 2

    y = 0
    draw.text((cx, y), TITLE_HEADLINE, font=ss.font(True, TITLE_HEADLINE_SIZE),
               fill=ss.C["white"], anchor="ma")
    y += TITLE_HEADLINE_SIZE + 22
    draw.text((cx, y), human_date, font=ss.font(True, TITLE_DATE_SIZE),
               fill=ss.C["teal"], anchor="ma")
    y += TITLE_DATE_SIZE + 26
    draw.text((cx, y), TITLE_TAGLINE, font=ss.font(False, TITLE_TAGLINE_SIZE),
               fill=(214, 220, 228), anchor="ma")
    return overlay


def _paste_popin(base, overlay, x, y, w, h, t: float) -> None:
    eased = ease_out_cubic(t)
    scale = 0.85 + 0.15 * eased
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    scaled = overlay.resize((new_w, new_h), Image.LANCZOS)
    if eased < 1.0:
        alpha = scaled.split()[3].point(lambda v: int(v * eased))
        scaled.putalpha(alpha)
    px = int(x + (w - new_w) / 2)
    py = int(y + (h - new_h) / 2)
    base.paste(scaled, (px, py), scaled)


def _render_header_band() -> tuple:
    """Header card only — static every frame, so rendered once and blitted.
    The 'Market Volatility Index' subtitle line is drawn separately as part
    of the vertically-centered content block (see render_frames)."""
    canvas = Image.new("RGB", (REEL_W, 260), ss.C["bg"])
    header_bottom = ss.draw_header(canvas, "VIX Fear Gauge", ss.load_brand_logo())
    return canvas.crop((0, 0, REEL_W, header_bottom)), header_bottom


def _render_readout_overlay(price: float, change_pct: float, zone_color, zone_label) -> Image.Image:
    sign_pct = "+" if change_pct >= 0 else ""
    change_color = ss.C["red"] if change_pct >= 0 else ss.C["green"]

    badge_font = ss.font(True, BADGE_FONT_SIZE)
    badge_text = zone_label.upper()
    dummy = Image.new("RGBA", (1, 1))
    tb = ImageDraw.Draw(dummy).textbbox((0, 0), badge_text, font=badge_font)
    pad_x, pad_y = 34, 18
    bw, bh = (tb[2] - tb[0]) + pad_x * 2, (tb[3] - tb[1]) + pad_y * 2

    price_h  = PRICE_FONT_SIZE + 10
    change_h = CHANGE_FONT_SIZE + 20
    total_h  = price_h + change_h + bh

    overlay = Image.new("RGBA", (REEL_W, total_h + 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx = REEL_W / 2

    y = price_h / 2
    draw.text((cx, y), f"{price:.2f}", font=ss.font(True, PRICE_FONT_SIZE),
               fill=ss.C["white"], anchor="mm")
    y = price_h + change_h / 2
    draw.text((cx, y), f"{sign_pct}{change_pct:.2f}%", font=ss.font(True, CHANGE_FONT_SIZE),
               fill=change_color, anchor="mm")

    by0 = price_h + change_h
    bx0 = cx - bw / 2
    draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=bh / 2,
                            outline=zone_color, width=3, fill=ss.C["card"])
    draw.text((cx, by0 + bh / 2), badge_text, font=badge_font, fill=zone_color, anchor="mm")

    return overlay


def _render_legend_overlay() -> Image.Image:
    overlay = Image.new("RGBA", (REEL_W, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    card._draw_zone_legend(overlay, draw, 10)
    return overlay


def render_frames(human_date: str, price: float, change_pct: float, out_dir: Path) -> int:
    header_band, header_h = _render_header_band()

    footer_canvas = Image.new("RGB", (REEL_W, REEL_H), ss.C["bg"])
    ss.draw_footer(footer_canvas)
    footer_top = REEL_H - FOOTER_ZONE
    footer_band = footer_canvas.crop((0, footer_top, REEL_W, REEL_H))

    zone_color, zone_label = card._zone_for(price)
    readout_overlay = _render_readout_overlay(price, change_pct, zone_color, zone_label)
    legend_overlay  = _render_legend_overlay()

    # Vertically center the whole content block (subtitle + gauge + readout
    # + legend) in the space between the header and footer — matches the
    # sector heatmap reel's approach, so a short reading doesn't leave the
    # gauge stranded near the top with dead space below it.
    y0 = TOP_SAFE_PAD + header_h
    available_h = footer_top - y0
    gauge_h = card.R + card.TILE_MARGIN_TOP + card.TILE_MARGIN_BOT
    gap_title_gauge   = 50
    gap_gauge_readout = 30
    gap_readout_legend = 30
    content_h = (TOP_TITLE_SIZE + gap_title_gauge + gauge_h + gap_gauge_readout
                 + readout_overlay.height + gap_readout_legend + legend_overlay.height)
    y_content = y0 + max(0, (available_h - content_h) // 2)

    title_y   = y_content
    gauge_top = title_y + TOP_TITLE_SIZE + gap_title_gauge
    cy        = gauge_top + card.TILE_MARGIN_TOP + card.R
    readout_y = gauge_top + gauge_h + gap_gauge_readout
    legend_y  = readout_y + readout_overlay.height + gap_readout_legend

    price_line_y = readout_y + (PRICE_FONT_SIZE + 10) / 2

    def new_frame(show_subtitle: bool = True) -> tuple:
        img = Image.new("RGB", (REEL_W, REEL_H), ss.C["bg"])
        img.paste(header_band, (0, TOP_SAFE_PAD))
        draw = ImageDraw.Draw(img)
        if show_subtitle:
            draw.text((REEL_W / 2, title_y + TOP_TITLE_SIZE / 2), "Market Volatility Index",
                       font=ss.font(True, TOP_TITLE_SIZE), fill=ss.C["white"], anchor="mm")
        img.paste(footer_band, (0, footer_top))
        return img, draw

    frame_idx = 0

    # Title card.
    title_overlay = _render_title_overlay(REEL_W, human_date)
    title_card_y = y0 + max(0, (available_h - title_overlay.height) // 2)
    for f in range(TITLE_FADE_FRAMES):
        t = (f + 1) / TITLE_FADE_FRAMES
        img, draw = new_frame(show_subtitle=False)
        _paste_popin(img, title_overlay, 0, title_card_y, REEL_W, title_overlay.height, t)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1
    for _ in range(TITLE_HOLD_FRAMES):
        img, draw = new_frame(show_subtitle=False)
        img.paste(title_overlay, (0, title_card_y), title_overlay)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    # Needle sweep — price counts up in lockstep with the same interpolated
    # value that drives the needle, so they always agree.
    for f in range(SWEEP_FRAMES):
        t = (f + 1) / SWEEP_FRAMES
        v = price * ease_out_cubic(t)
        tile, px, py, _, _ = card.render_gauge_tile(v)
        img, draw = new_frame()
        img.paste(tile, (int(card.CX - px), int(cy - py)), tile)
        draw.text((REEL_W / 2, price_line_y), f"{v:.2f}",
                   font=ss.font(True, PRICE_FONT_SIZE), fill=ss.C["white"], anchor="mm")
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    final_tile, fpx, fpy, _, _ = card.render_gauge_tile(price)

    for _ in range(SWEEP_HOLD):
        img, draw = new_frame()
        img.paste(final_tile, (int(card.CX - fpx), int(cy - fpy)), final_tile)
        draw.text((REEL_W / 2, price_line_y), f"{price:.2f}",
                   font=ss.font(True, PRICE_FONT_SIZE), fill=ss.C["white"], anchor="mm")
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    # Readout (price/change/badge) fades in as a unit — price is already on
    # screen from the sweep, but redrawing it as part of the overlay keeps
    # the fade-in code simple and it's a no-op visually at t=1.
    for f in range(READOUT_FRAMES):
        t = (f + 1) / READOUT_FRAMES
        img, draw = new_frame()
        img.paste(final_tile, (int(card.CX - fpx), int(cy - fpy)), final_tile)
        alpha = readout_overlay.split()[3].point(lambda v: int(v * t))
        faded = readout_overlay.copy()
        faded.putalpha(alpha)
        img.paste(faded, (0, readout_y), faded)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    for f in range(LEGEND_FRAMES):
        t = (f + 1) / LEGEND_FRAMES
        img, draw = new_frame()
        img.paste(final_tile, (int(card.CX - fpx), int(cy - fpy)), final_tile)
        img.paste(readout_overlay, (0, readout_y), readout_overlay)
        alpha = legend_overlay.split()[3].point(lambda v: int(v * t))
        faded = legend_overlay.copy()
        faded.putalpha(alpha)
        img.paste(faded, (0, legend_y), faded)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    for _ in range(END_HOLD_FRAMES):
        img, draw = new_frame()
        img.paste(final_tile, (int(card.CX - fpx), int(cy - fpy)), final_tile)
        img.paste(readout_overlay, (0, readout_y), readout_overlay)
        img.paste(legend_overlay, (0, legend_y), legend_overlay)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    return frame_idx


def encode_video(frame_dir: Path, out_path: Path, fps: int, n_frames: int) -> str:
    track_name = random.choice(sorted(AUDIO_CREDITS))
    track_path = AUDIO_DIR / track_name
    duration   = n_frames / fps
    fade_start = max(0.0, duration - 1.0)

    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(track_path),
        "-t", f"{duration:.3f}",
        "-af", f"afade=t=out:st={fade_start:.3f}:d=1.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return AUDIO_CREDITS[track_name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD label override, defaults to the last market day")
    parser.add_argument("--out", help="output mp4 path override")
    args = parser.parse_args()

    forced = args.date or os.environ.get("FORCE_DATE")
    if forced:
        date_obj = datetime.strptime(forced, "%Y-%m-%d").date()
    else:
        date_obj = ss.last_market_day(datetime.now(timezone.utc).date())
    date_str   = date_obj.strftime("%Y-%m-%d")
    human_date = date_obj.strftime("%a %d %b")

    print("Fetching VIX reading...")
    vix = card.fetch_vix()
    if not vix:
        print("No VIX reading available — nothing to render.")
        return

    price      = vix["price"]
    change_pct = vix.get("change_pct", 0.0)
    print(f"  VIX {price:.2f} ({change_pct:+.2f}%)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        n_frames = render_frames(human_date, price, change_pct, tmp_path)
        print(f"  rendered {n_frames} frames @ {FPS}fps (~{n_frames / FPS:.1f}s)")
        audio_credit = encode_video(tmp_path, out_path, FPS, n_frames)
        print(f"  audio: {audio_credit}")

    REEL_MANIFEST.write_text(json.dumps(
        {"date": date_str, "audio_credit": audio_credit}, indent=2) + "\n")

    try:
        shown_path = out_path.relative_to(ROOT)
    except ValueError:
        shown_path = out_path
    print(f"  video saved -> {shown_path}")


if __name__ == "__main__":
    main()
