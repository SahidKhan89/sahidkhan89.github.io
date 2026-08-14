#!/usr/bin/env python3
"""
post_earnings_calendar.py — Post the generated earnings-calendar card to
Threads, Instagram and Facebook.

Reads the manifest written by generate_earnings_calendar_card.py and posts it
using a raw.githubusercontent.com URL (available immediately after the commit
step). Dedupes against data/posted_earnings_calendar.json by date so a re-run
on the same day doesn't double-post.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_facebook

MANIFEST    = Path(__file__).parent / "_earnings_calendar_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_earnings_calendar.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/earnings-calendar/{date_str}.png"
    )


def build_caption(entry: dict, max_chars: int) -> str:
    before = entry.get("before_open", [])[:2]
    after  = entry.get("after_close", [])[:3]
    tickers = before + after

    lines = [f"Earnings Calendar: {entry['human_date']}",
              "Companies reporting earnings"]
    if tickers:
        lines.append("")
        lines.append(" ".join(f"#{t}" for t in tickers))

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 1] + "…"
    return result


def llm_caption(entry: dict, max_chars: int) -> str | None:
    """Reword today's earnings-calendar lineup into a fresh intro hook via
    the Anthropic API, then append the exact ticker list (never
    LLM-generated). Returns None on any failure so the caller falls back to
    the static template."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    before  = entry.get("before_open", [])
    after   = entry.get("after_close", [])
    if not api_key or (not before and not after):
        return None

    facts_lines = [f"Date: {entry['human_date']}"]
    if before:
        facts_lines.append(f"Reporting before market open: {', '.join(before[:8])}")
    if after:
        facts_lines.append(f"Reporting after market close: {', '.join(after[:8])}")
    facts = "\n".join(facts_lines)

    tickers = before[:2] + after[:3]
    footer  = "\n\n" + " ".join(f"#{t}" for t in tickers)
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
                    "everyday retail investors, not a news outlet. Given today's earnings "
                    "calendar — which companies report before market open vs after market "
                    "close — write a short 1-2 sentence hook — like you're texting a friend, "
                    "not filing a report — that calls out a standout name or two worth "
                    "watching. Lead with a concrete ticker. Short, punchy sentences, "
                    "contractions are fine. This text will be followed immediately by the "
                    "ticker list, so don't just repeat the names with nothing added. No EPS "
                    "estimates or financial figures were given to you, so never invent one. "
                    "Vary your phrasing and structure each time so posts don't read like a "
                    "template. You may use at most one emoji if it genuinely fits, skip it "
                    "entirely rather than force one. No hashtags, no quotation marks around "
                    f"the output. Under {intro_budget} characters. Output ONLY the hook text, "
                    "nothing else."
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
        print("Manifest is empty — no earnings calendar to post.")
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

    # One LLM call reworded intro, shared across Threads/IG/FB captions.
    # Falls back to the static template on any failure.
    reworded        = llm_caption(entry, 500)
    threads_caption = reworded or build_caption(entry, 500)
    ig_caption      = reworded or build_caption(entry, 2200)

    if dry_run:
        print(f"DRY RUN — {entry['date']}")
        print(f"  Image: {img_url}")
        print("\n  ── Threads caption (max 500) ──")
        print(threads_caption)
        print("\n  ── Instagram caption (max 2200) ──")
        print(ig_caption)
        return

    print(f"Posting earnings calendar for {entry['date']}")
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
