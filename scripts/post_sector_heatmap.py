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

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_instagram_reel, post_to_facebook

ROOT        = Path(__file__).parent.parent
MANIFEST    = Path(__file__).parent / "_sector_heatmap_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_sector_heatmap.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


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


def build_caption(entry: dict, max_chars: int) -> str:
    date_full = datetime.strptime(entry["date"], "%Y-%m-%d").strftime("%a %d %b %Y")
    lines = [f"Market Sector: {date_full}", "How each S&P sector performed", ""]

    for s in entry.get("sectors", []):
        pct   = s["change_pct"]
        emoji = "🟢" if pct >= 0 else "🔴"
        sign  = "+" if pct >= 0 else ""
        lines.append(f"{emoji} {s['name']}: {sign}{pct:.2f}%")

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 1] + "…"
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
    threads_caption = build_caption(entry, 500)
    ig_caption      = build_caption(entry, 2200)

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
                igid = post_to_instagram_reel(ig_caption, vid_url)
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
