#!/usr/bin/env python3
"""
post_vix_gauge.py — Post the generated VIX fear gauge card to Threads,
Instagram and Facebook.

Instagram posts the needle-sweep reel (scripts/generate_vix_gauge_reel.py's
output) as a Reel when images/vix-gauge-reel/<date>.mp4 exists, falling back
to the static image otherwise. Threads and Facebook always use the static
card — their reel/video publishing flows aren't wired up yet.

Reads the manifest written by generate_vix_gauge_card.py and posts it using
a raw.githubusercontent.com URL. Dedupes against data/posted_vix_gauge.json
by date so a re-run on the same day doesn't double-post.
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
import generate_vix_gauge_reel as reel

ROOT        = Path(__file__).parent.parent
MANIFEST    = Path(__file__).parent / "_vix_gauge_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_vix_gauge.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/vix-gauge/{date_str}.png"
    )


def video_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/vix-gauge-reel/{date_str}.mp4"
    )


def reel_exists(date_str: str) -> bool:
    return (ROOT / "images" / "vix-gauge-reel" / f"{date_str}.mp4").exists()


ZONE_BLURB = {
    "Calm":     "Markets are unusually quiet — volatility expectations are running low.",
    "Normal":   "Volatility expectations are sitting around their long-run average.",
    "Elevated": "Markets are pricing in more uncertainty than usual.",
    "Panic":    "Fear is elevated — volatility expectations are running well above normal.",
    "Extreme":  "Crisis-level readings — volatility expectations are at their most extreme.",
}


def build_caption(entry: dict, max_chars: int) -> str:
    date_full = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %d %b %Y")
    blurb = ZONE_BLURB.get(entry["zone_label"], "")
    lines = [
        f"VIX Fear Gauge: {date_full}",
        f"{entry['price']:.2f} ({entry['change_pct']:+.2f}%) - {entry['zone_label'].upper()}",
        "",
        blurb,
        "",
        "The VIX (\"fear index\") tracks the market's expectation of S&P 500",
        "volatility over the next 30 days - the higher it is, the more",
        "turbulence traders expect ahead",
        "",
        "#VIX",
    ]
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 1] + "…"
    return result


HASHTAG_LINE = "#VIX"


def llm_caption(entry: dict, max_chars: int) -> str | None:
    """Reword today's VIX reading into fresh copy via the Anthropic API so
    captions don't read identically every post. Returns None on any failure
    (missing key, network error, bad response) so the caller falls back to
    the static template — a post going out with boilerplate text beats no
    post at all."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    date_full = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %d %b %Y")
    blurb = ZONE_BLURB.get(entry["zone_label"], "")
    facts = (
        f"Date: {date_full}\n"
        f"VIX level: {entry['price']:.2f}\n"
        f"Change: {entry['change_pct']:+.2f}%\n"
        f"Zone: {entry['zone_label']}\n"
        f"Zone meaning: {blurb}"
    )

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
                    "everyday retail investors, not a news outlet. Given today's VIX (fear "
                    "index) reading, write a short caption explaining what it means for "
                    "traders today, like you're texting a friend, not filing a report. "
                    "Lead with the concrete number and what zone it's in. Short, punchy "
                    "sentences, contractions are fine. Avoid stiff financial-journalism "
                    "words. Vary your phrasing and structure each time so posts don't read "
                    "like a template. Factual only, never invent numbers not given to you. "
                    "You may use at most one emoji if it genuinely fits, skip it entirely "
                    "rather than force one. No hashtags in the body, no quotation marks "
                    f"around the output. Under {max_chars - len(HASHTAG_LINE) - 4} characters. "
                    "Output ONLY the caption text, nothing else."
                ),
                "messages": [{"role": "user", "content": facts}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = next(b["text"] for b in data["content"] if b["type"] == "text").strip()
        if not text:
            return None
    except Exception as e:
        print(f"  ✗ LLM caption reword failed, falling back to template: {e}")
        return None

    result = f"{text}\n\n{HASHTAG_LINE}"
    if len(result) > max_chars:
        result = text[:max_chars - len(HASHTAG_LINE) - 5] + f"…\n\n{HASHTAG_LINE}"
    return result


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
        print("Manifest is empty — no VIX reading to post.")
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

    # One LLM call reworded caption, shared across Threads/IG/FB so wording
    # is consistent per post and we don't spend extra API calls per platform.
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

    print(f"Posting VIX fear gauge for {entry['date']}")
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
