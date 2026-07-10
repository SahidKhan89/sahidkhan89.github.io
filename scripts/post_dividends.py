#!/usr/bin/env python3
"""
post_dividends.py — Post the generated ex-dividend calendar card to Threads,
Instagram and Facebook.

Reads the manifest written by generate_dividends_card.py and posts it using a
raw.githubusercontent.com URL. Dedupes against data/posted_dividends.json by
the *target ex-dividend date* (not the run date) — since the generator looks
ahead to the next market day, this keeps the lookahead window from ever
posting the same date twice.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_facebook

MANIFEST    = Path(__file__).parent / "_dividends_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_dividends.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/dividends/{date_str}.png"
    )


def build_caption(entry: dict, max_chars: int) -> str:
    lines = [f"Ex-Dividend: {entry['human_date']}"]

    tickers = entry.get("tickers", [])
    if tickers:
        lines.append("")
        lines.append(" ".join(f"#{t}" for t in tickers[:10]))

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
        print("Manifest is empty — no dividends to post.")
        return

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {"posted": []}
    posted   = set(tracking.get("posted", []))

    if entry["date"] in posted and not dry_run:
        print(f"Already posted for ex-div date {entry['date']} — nothing new.")
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
        print(f"DRY RUN — ex-div date {entry['date']}")
        print(f"  Image: {img_url}")
        print("\n  ── Threads caption (max 500) ──")
        print(threads_caption)
        print("\n  ── Instagram caption (max 2200) ──")
        print(ig_caption)
        return

    print(f"Posting dividends calendar for ex-div date {entry['date']}")
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
