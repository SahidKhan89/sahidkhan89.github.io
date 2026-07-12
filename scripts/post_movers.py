#!/usr/bin/env python3
"""
post_movers.py — Post the generated movers card (Gainers & Losers / Most
Active / Trending Now) to Threads, Instagram and Facebook.

Reads the manifest written by generate_movers_card.py and posts it using a
raw.githubusercontent.com URL. Dedupes against data/posted_movers.json by
date so a re-run on the same day doesn't double-post.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_facebook

MANIFEST    = Path(__file__).parent / "_movers_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_movers.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/movers/{date_str}.png"
    )


def build_caption(entry: dict, max_chars: int) -> str:
    title = entry["title"]
    lines = [f"{title}: {entry['human_date']}"]

    if entry.get("post_type") == "movers":
        gainers = entry.get("gainers", [])
        losers  = entry.get("losers", [])
        if gainers:
            lines.append("")
            lines.append("🟢 Gainers: " + " ".join(f"#{t}" for t in gainers[:3]))
        if losers:
            lines.append("")
            lines.append("🔴 Losers: " + " ".join(f"#{t}" for t in losers[:3]))
    else:
        tickers = entry.get("tickers", [])
        if tickers:
            lines.append("")
            lines.append(" ".join(f"#{t}" for t in tickers[:3]))

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
        print("Manifest is empty — no movers to post.")
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
    threads_caption = build_caption(entry, 500)
    ig_caption      = build_caption(entry, 2200)

    if dry_run:
        print(f"DRY RUN — {entry['date']} ({entry.get('post_type')})")
        print(f"  Image: {img_url}")
        print("\n  ── Threads caption (max 500) ──")
        print(threads_caption)
        print("\n  ── Instagram caption (max 2200) ──")
        print(ig_caption)
        return

    print(f"Posting movers ({entry.get('post_type')}) for {entry['date']}")
    print(f"  Image: {img_url}")
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
