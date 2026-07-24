#!/usr/bin/env python3
"""
post_sector_heatmap.py — Post the generated sector heatmap card to Threads,
Instagram and Facebook.

Instagram posts the build-up reel (scripts/generate_sector_heatmap_reel.py's
output) as a Reel when images/sector-heatmap-reel/<date>.mp4 exists, falling
back to the static image otherwise. Threads and Facebook always use the
static card — their reel/video publishing flows aren't wired up yet.

Reads the manifest written by generate_sector_heatmap_card.py and posts it
using a raw.githubusercontent.com URL. Dedupes against
data/posted_sector_heatmap.json by date so a re-run on the same day doesn't
double-post.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_instagram_reel, post_to_facebook
import generate_sector_heatmap_reel as reel

ROOT          = Path(__file__).parent.parent
MANIFEST      = Path(__file__).parent / "_sector_heatmap_manifest.json"
TRACKING      = Path(__file__).parent.parent / "data" / "posted_sector_heatmap.json"
MAX_HISTORY   = 500
REPO          = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH        = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/sector-heatmap/{date_str}.png"
    )


def video_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/sector-heatmap-reel/{date_str}.mp4"
    )


def reel_exists(date_str: str) -> bool:
    return (ROOT / "images" / "sector-heatmap-reel" / f"{date_str}.mp4").exists()


HASHTAG_LINE = "#StockMarket"


def sector_lines(sectors: list) -> list:
    lines = []
    for s in sectors:
        pct   = s["change_pct"]
        emoji = "🟢" if pct >= 0 else "🔴"
        sign  = "+" if pct >= 0 else ""
        lines.append(f"{emoji} {s['name']}: {sign}{pct:.2f}%")
    return lines


def build_caption(entry: dict, max_chars: int) -> str:
    date_full = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %d %b %Y")
    sectors = entry.get("sectors", [])

    lines = [f"Market Sector: {date_full}"]
    if sectors:
        best  = max(sectors, key=lambda s: s["change_pct"])
        worst = min(sectors, key=lambda s: s["change_pct"])
        lines.append(f"🏆 Best: {best['name']} {best['change_pct']:+.2f}%")
        lines.append(f"📉 Worst: {worst['name']} {worst['change_pct']:+.2f}%")
    lines.append("")

    lines += sector_lines(sectors)
    lines += ["", "Which sector are you watching? Drop it below 👇"]

    # Hashtags are appended after truncation so a long sector list never eats
    # into them — they always survive, same pattern as post_earnings_charts.py.
    body   = "\n".join(lines)
    result = body + "\n\n" + HASHTAG_LINE

    if len(result) > max_chars:
        trim = max_chars - len(HASHTAG_LINE) - len("...\n\n")
        result = body[:trim] + "...\n\n" + HASHTAG_LINE

    return result


def llm_caption(entry: dict, max_chars: int) -> str | None:
    """Reword today's sector story into a fresh intro hook via the Anthropic
    API, then append the exact per-sector breakdown (never LLM-generated, so
    the numbers stay guaranteed-accurate) and the fixed CTA/hashtag. Returns
    None on any failure so the caller falls back to the static template."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    sectors = entry.get("sectors", [])
    if not api_key or not sectors:
        return None

    date_full = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %d %b %Y")
    best  = max(sectors, key=lambda s: s["change_pct"])
    worst = min(sectors, key=lambda s: s["change_pct"])
    positive = sum(1 for s in sectors if s["change_pct"] >= 0)
    facts = (
        f"Date: {date_full}\n"
        f"Best sector: {best['name']} {best['change_pct']:+.2f}%\n"
        f"Worst sector: {worst['name']} {worst['change_pct']:+.2f}%\n"
        f"Sectors up: {positive}/{len(sectors)}\n"
        f"Full breakdown: " + ", ".join(f"{s['name']} {s['change_pct']:+.2f}%" for s in sectors)
    )

    breakdown = "\n".join(sector_lines(sectors))
    footer = "\n\n" + breakdown + "\n\nWhich sector are you watching? Drop it below 👇" + "\n\n" + HASHTAG_LINE
    intro_budget = max_chars - len(footer) - 2

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 300,
                "system": (
                    "You post on Threads/Instagram for Stock Score, a stock market app for "
                    "everyday retail investors, not a news outlet. Given today's S&P 500 "
                    "sector performance data, write a short 1-3 sentence hook — like you're "
                    "texting a friend, not filing a report — that calls out the standout "
                    "story: the biggest mover, a broad rally or selloff, a rotation between "
                    "sectors, whatever is most notable. Lead with the concrete fact. Short, "
                    "punchy sentences, contractions are fine. This text will be followed "
                    "immediately by an itemized sector-by-sector breakdown, so don't list "
                    "every sector yourself — focus only on the headline story. Vary your "
                    "phrasing and structure each time so posts don't read like a template. "
                    "Factual only, never invent numbers not given to you. You may use at "
                    "most one emoji if it genuinely fits, skip it entirely rather than "
                    "force one. No hashtags, no quotation marks around the output. Under "
                    f"{intro_budget} characters. Output ONLY the hook text, nothing else."
                ),
                "messages": [{"role": "user", "content": facts}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        intro = next(b["text"] for b in data["content"] if b["type"] == "text").strip()
        if not intro:
            return None
    except Exception as e:
        print(f"  ✗ LLM caption reword failed, falling back to template: {e}")
        return None

    if len(intro) > intro_budget:
        intro = intro[:intro_budget - 1] + "…"
    return intro + footer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print caption and image URL without posting")
    args = parser.parse_args()
    dry_run = args.dry_run

    if not MANIFEST.exists():
        print("No manifest found — nothing to post.")
        return

    entry = json.loads(MANIFEST.read_text())
    if not entry:
        print("Manifest is empty — no sector heatmap to post.")
        return

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {"posted": []}
    posted   = set(tracking.get("posted", []))

    if entry["date"] in posted and not dry_run:
        print(f"Already posted for {entry['date']} — nothing new.")
        return

    has_threads = bool(os.environ.get("THREADS_ACCESS_TOKEN") and
                       os.environ.get("THREADS_USER_ID"))
    has_ig      = bool(os.environ.get("IG_ACCESS_TOKEN") and
                       os.environ.get("IG_USER_ID"))
    has_fb      = bool(os.environ.get("FB_PAGE_ACCESS_TOKEN") and
                       os.environ.get("FB_PAGE_ID"))

    img_url         = image_url(entry["date"])
    has_reel        = reel_exists(entry["date"])
    vid_url         = video_url(entry["date"]) if has_reel else None

    # One LLM call reworded intro, shared across Threads/IG/FB captions.
    # Falls back to the static template on any failure.
    reworded        = llm_caption(entry, 500)
    threads_caption = reworded or build_caption(entry, 500)
    ig_caption      = reworded or build_caption(entry, 2200)

    if dry_run:
        print(f"DRY RUN — {entry['date']}")
        print(f"  Image: {img_url}")
        print(f"  Video: {vid_url if has_reel else '(none — falling back to image for IG)'}")
        print("\n  ── Threads caption (max 500) ──")
        print(threads_caption)
        print("\n  ── Instagram caption (max 2200) ──")
        print(ig_caption)
        return

    print(f"Posting sector heatmap for {entry['date']}")
    print(f"  Image: {img_url}")
    if has_reel:
        print(f"  Video: {vid_url}")
    success = False

    if has_threads:
        try:
            tid = post_to_threads(threads_caption, img_url)
            print(f"  ✓ Threads: {tid}")
            success = True
        except Exception as e:
            print(f"  ✗ Threads: {e}")

    if has_ig:
        try:
            if has_reel:
                # Mid-way through the title card's static hold, so the cover
                # frame is always the readable title, never a blank/fading one.
                thumb_offset_ms = round(
                    (reel.TITLE_FADE_FRAMES + reel.TITLE_HOLD_FRAMES / 2) / reel.FPS * 1000
                )
                igid = post_to_instagram_reel(ig_caption, vid_url, thumb_offset_ms=thumb_offset_ms)
                print(f"  ✓ Instagram (reel): {igid}")
            else:
                igid = post_to_instagram(ig_caption, img_url)
                print(f"  ✓ Instagram: {igid}")
            success = True
        except Exception as e:
            print(f"  ✗ Instagram: {e}")

    if has_fb:
        try:
            fbid = post_to_facebook(ig_caption, img_url)
            print(f"  ✓ Facebook: {fbid}")
            success = True
        except Exception as e:
            print(f"  ✗ Facebook: {e}")

    if success:
        posted.add(entry["date"])
        tracking["posted"] = list(posted)[-MAX_HISTORY:]
        TRACKING.write_text(json.dumps(tracking, indent=2) + "\n")
        print("\nTracking file updated.")

    print("\nDone.")


if __name__ == "__main__":
    main()
