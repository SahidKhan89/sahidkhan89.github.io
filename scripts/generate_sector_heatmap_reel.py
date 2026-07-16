#!/usr/bin/env python3
"""
generate_sector_heatmap_reel.py — Render today's sector heatmap as a vertical
(1080x1920) "build-up" reveal video, posted to Instagram as a Reel by
scripts/post_sector_heatmap.py (which falls back to the static card image
for Instagram if this script hasn't produced a video for the date — and
always uses the static image for Threads/Facebook, since their reel/video
publishing flows aren't wired up).

Reuses generate_sector_heatmap_card.py's color logic and column packing
(_heat_color, FULL_NAME, OUTER_COLS/MARGIN/GAP) so the reel matches the
static card's palette, but draws headers/cells at reel-specific (larger)
sizes with its own two-stage reveal per sector:
  1. header pops in (fade + scale), its % counting up from 0
  2. its industries then cascade in one at a time (fade + slide up), each
     with its own % counting up — a different transition from the header's,
     so the two levels read as visually distinct
Once every sector has landed, the full grid holds with the legend for a
couple of seconds at the end.

Requires ffmpeg on PATH (invoked via subprocess — not a pip dependency).

Set FORCE_DATE=YYYY-MM-DD (or pass --date) same as the card script — the
underlying data is always whatever the backend currently has cached.
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
import generate_sector_heatmap_card as card

ROOT          = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT / "images" / "sector-heatmap-reel"
AUDIO_DIR     = ROOT / "assets" / "audio"
REEL_MANIFEST = Path(__file__).parent / "_sector_heatmap_reel_manifest.json"

# Background track picked at random each run for variety. Tracks are by
# Kevin MacLeod (incompetech.com), CC BY 4.0.
AUDIO_CREDITS = {
    "tech-live.mp3":     "Tech Live by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0",
    "presenterator.mp3": "Presenterator by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0",
    "motivator.mp3":     "Motivator by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0",
    "news-theme.mp3":    "News Theme by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0",
    "news-sting.mp3":    "NewsSting by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0",
}

FPS            = 30
REEL_W, REEL_H = 1080, 1920
FOOTER_ZONE    = 90   # matches draw_footer's fixed offset from img.height
LEGEND_ZONE    = 58   # 14 pre-gap + 16 bar + 28 label offset, per card._draw_legend

# Reel-specific layout — noticeably bigger than the static card's (HEADER_H
# 42/CELL_ROW_H 74) so the grid fills more of the taller vertical canvas.
HEADER_H    = 60
CELL_ROW_H  = 108
CELL_GAP    = 6
BLOCK_GAP_Y = 24

NAME_FONT_SIZE   = 20
PCT_FONT_SIZE    = 27
HEADER_FONT_SIZE = 28

HEADER_FRAMES   = 10   # ~0.33s header pop-in
CELL_FRAMES     = 10   # ~0.33s per industry cell's own slide-in
CELL_STAGGER    = 4    # frames between each industry cell starting
HOLD_FRAMES     = 5    # ~0.17s pause before the next sector starts
END_HOLD_FRAMES = 60   # ~2s holding on the finished grid + legend
SLIDE_OFFSET    = 34   # px an industry cell slides up from as it fades in


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


# ── Reel-specific drawing (bigger sizes than the static card's) ────────────

def _reel_draw_header(draw, x, y, w, name, pct):
    color = card._heat_color(pct, card.BLEND_MAX_HEADER)
    draw.rectangle([x, y, x + w, y + HEADER_H], fill=color)
    sign = "+" if pct >= 0 else ""
    pct_str = f"{sign}{pct:.2f}%"
    header_font = ss.font(True, HEADER_FONT_SIZE)
    avail_w = w - 20

    full_text  = f"{card.FULL_NAME.get(name, name)}  {pct_str}"
    short_text = f"{name}  {pct_str}"
    if draw.textbbox((0, 0), full_text, font=header_font)[2] <= avail_w:
        text = full_text
    elif draw.textbbox((0, 0), short_text, font=header_font)[2] <= avail_w:
        text = short_text
    else:
        text = ss.ellipsize(draw, short_text, header_font, avail_w)
    draw.text((x + w / 2, y + HEADER_H / 2), text, font=header_font,
               fill=ss.C["white"], anchor="mm")


def _reel_draw_cell(draw, x, y, w, h, name, pct):
    color = card._heat_color(pct, card.BLEND_MAX_CELL)
    draw.rectangle([x, y, x + w, y + h], fill=color)
    cx = x + w / 2

    name_font = ss.font(False, NAME_FONT_SIZE)
    lines  = card._best_label(draw, name, name_font, w - 14, max_lines=2)
    line_h = NAME_FONT_SIZE + 6
    start_y = y + h * 0.30 - (len(lines) - 1) * line_h / 2
    for i, line in enumerate(lines):
        draw.text((cx, start_y + i * line_h), line, font=name_font,
                   fill=(235, 238, 242), anchor="mm")

    sign = "+" if pct >= 0 else ""
    draw.text((cx, y + h * 0.76), f"{sign}{pct:.2f}%", font=ss.font(True, PCT_FONT_SIZE),
               fill=ss.C["white"], anchor="mm")


def _reel_block_height(n_industries: int) -> int:
    rows = (n_industries + 1) // 2
    return HEADER_H + CELL_GAP + rows * CELL_ROW_H + (rows - 1) * CELL_GAP


def _industry_cell_positions(x, y, w, industries):
    """Absolute (cx, cy, cw, ch, industry_dict) for each cell in a block
    whose top-left is (x, y) — mirrors the static card's cell packing."""
    n = len(industries)
    cell_w = (w - CELL_GAP) / 2
    cy = y + HEADER_H + CELL_GAP
    out = []
    for i, ind in enumerate(industries):
        full_width = (i == n - 1 and n % 2 == 1)
        row = i // 2
        cell_y = cy + row * (CELL_ROW_H + CELL_GAP)
        if full_width:
            out.append((x, cell_y, w, CELL_ROW_H, ind))
        else:
            col = i % 2
            cell_x = x + col * (cell_w + CELL_GAP)
            out.append((cell_x, cell_y, cell_w, CELL_ROW_H, ind))
    return out


def _draw_full_sector(draw, x, y, w, sector):
    """Sector fully landed — header + all industries at their final values."""
    name = sector["sector"]
    pct  = sector.get("change_pct", 0.0)
    _reel_draw_header(draw, x, y, w, name, pct)
    for cx, cy, cw, ch, ind in _industry_cell_positions(x, y, w, sector.get("industries", [])):
        _reel_draw_cell(draw, cx, cy, cw, ch, ind["name"], ind.get("change_pct", 0.0))


# ── Two transition types: header pops (scale), cells slide (translate) ─────

def _render_header_overlay(name, w, pct):
    overlay = Image.new("RGBA", (int(w) + 1, HEADER_H + 1), (0, 0, 0, 0))
    _reel_draw_header(ImageDraw.Draw(overlay), 0, 0, w, name, pct)
    return overlay


def _render_cell_overlay(ind, w, h, pct):
    overlay = Image.new("RGBA", (int(w) + 1, int(h) + 1), (0, 0, 0, 0))
    _reel_draw_cell(ImageDraw.Draw(overlay), 0, 0, w, h, ind["name"], pct)
    return overlay


def _paste_popin(base, overlay, x, y, w, h, t: float) -> None:
    """t in [0,1] — fades in while popping from 0.85x to 1.0x scale, centered
    on the element's own box. Used for sector headers."""
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


def _paste_slide_fade(base, overlay, x, y, t: float) -> None:
    """t in [0,1] — slides up into place from below while fading in. A
    distinct transition from the header's scale pop-in. Used for industry
    cells cascading in under an already-landed header."""
    eased = ease_out_cubic(t)
    offset = round((1 - eased) * SLIDE_OFFSET)
    if eased < 1.0:
        alpha = overlay.split()[3].point(lambda v: int(v * eased))
        overlay = overlay.copy()
        overlay.putalpha(alpha)
    base.paste(overlay, (round(x), round(y + offset)), overlay)


def _layout(sectors: list) -> tuple:
    """Same greedy shortest-column packing as the static card, but using the
    reel's own (bigger) block heights."""
    outer_col_w = (ss.CW - 2 * card.OUTER_MARGIN - (card.OUTER_COLS - 1) * card.OUTER_GAP) / card.OUTER_COLS
    col_x = [card.OUTER_MARGIN + i * (outer_col_w + card.OUTER_GAP) for i in range(card.OUTER_COLS)]
    col_heights = [0] * card.OUTER_COLS
    positions = []
    for sector in sectors:
        block_h = _reel_block_height(len(sector.get("industries", [])))
        col = min(range(card.OUTER_COLS), key=lambda i: col_heights[i])
        positions.append((col_x[col], col_heights[col], outer_col_w, block_h))
        col_heights[col] += block_h + BLOCK_GAP_Y
    return positions, max(col_heights)


def render_frames(human_date: str, sectors: list, out_dir: Path) -> int:
    positions, content_h = _layout(sectors)

    # Header/footer never change frame-to-frame — render once, blit every frame.
    header_canvas = Image.new("RGB", (REEL_W, REEL_H), ss.C["bg"])
    y0 = ss.draw_header(header_canvas, f"Sector Heatmap  ·  {human_date}", ss.load_brand_logo())
    header_band = header_canvas.crop((0, 0, REEL_W, y0))

    footer_canvas = Image.new("RGB", (REEL_W, REEL_H), ss.C["bg"])
    ss.draw_footer(footer_canvas)
    footer_top = REEL_H - FOOTER_ZONE
    footer_band = footer_canvas.crop((0, footer_top, REEL_W, REEL_H))

    available_h = footer_top - y0
    content_total = content_h + LEGEND_ZONE
    y_content = y0 + max(0, (available_h - content_total) // 2)

    def new_frame() -> tuple:
        img = Image.new("RGB", (REEL_W, REEL_H), ss.C["bg"])
        img.paste(header_band, (0, 0))
        img.paste(footer_band, (0, footer_top))
        return img, ImageDraw.Draw(img)

    frame_idx = 0
    n = len(sectors)

    for i, sector in enumerate(sectors):
        x, y, w, h = positions[i]
        name = sector["sector"]
        final_pct = sector.get("change_pct", 0.0)
        industries = sector.get("industries", [])
        cell_positions = _industry_cell_positions(x, y_content + y, w, industries)

        # Phase A — header pops in.
        for f in range(HEADER_FRAMES):
            t = (f + 1) / HEADER_FRAMES
            img, draw = new_frame()
            for j in range(i):
                xj, yj, wj, hj = positions[j]
                _draw_full_sector(draw, xj, y_content + yj, wj, sectors[j])
            overlay = _render_header_overlay(name, w, final_pct * ease_out_cubic(t))
            _paste_popin(img, overlay, x, y_content + y, w, HEADER_H, t)
            img.save(out_dir / f"frame_{frame_idx:05d}.png")
            frame_idx += 1

        # Phase B — industries cascade in under the now-settled header.
        phase_b_len = CELL_STAGGER * max(len(industries) - 1, 0) + CELL_FRAMES if industries else 0
        for pf in range(phase_b_len):
            img, draw = new_frame()
            for j in range(i):
                xj, yj, wj, hj = positions[j]
                _draw_full_sector(draw, xj, y_content + yj, wj, sectors[j])
            _reel_draw_header(draw, x, y_content + y, w, name, final_pct)
            for k, (cx, cy, cw, ch, ind) in enumerate(cell_positions):
                local = pf - k * CELL_STAGGER
                if local < 0:
                    continue
                elif local >= CELL_FRAMES:
                    _reel_draw_cell(draw, cx, cy, cw, ch, ind["name"], ind.get("change_pct", 0.0))
                else:
                    t = (local + 1) / CELL_FRAMES
                    overlay = _render_cell_overlay(ind, cw, ch, ind.get("change_pct", 0.0) * ease_out_cubic(t))
                    _paste_slide_fade(img, overlay, cx, cy, t)
            img.save(out_dir / f"frame_{frame_idx:05d}.png")
            frame_idx += 1

        # Hold before the next sector starts.
        if i < n - 1:
            for _ in range(HOLD_FRAMES):
                img, draw = new_frame()
                for j in range(i + 1):
                    xj, yj, wj, hj = positions[j]
                    _draw_full_sector(draw, xj, y_content + yj, wj, sectors[j])
                img.save(out_dir / f"frame_{frame_idx:05d}.png")
                frame_idx += 1

    for _ in range(END_HOLD_FRAMES):
        img, draw = new_frame()
        for j, sector in enumerate(sectors):
            xj, yj, wj, hj = positions[j]
            _draw_full_sector(draw, xj, y_content + yj, wj, sector)
        card._draw_legend(img, draw, y_content + content_h + 14)
        img.save(out_dir / f"frame_{frame_idx:05d}.png")
        frame_idx += 1

    return frame_idx


def encode_video(frame_dir: Path, out_path: Path, fps: int, n_frames: int) -> str:
    """Encodes the frames and muxes in a randomly-picked background track,
    trimmed to the video's own length with a 1s fade-out at the tail.
    Returns that track's attribution line."""
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

    print(f"Fetching sector heatmap (labeling as {date_str})...")
    sectors = card.fetch_heatmap()
    if not sectors:
        print("No sector data — nothing to render.")
        return
    print(f"  {len(sectors)} sectors found")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{date_str}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        n_frames = render_frames(human_date, sectors, tmp_path)
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
