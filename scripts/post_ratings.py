#!/usr/bin/env python3
"""
post_ratings.py — Post the generated analyst-ratings card to Threads,
Instagram and Facebook.

Reads the manifest written by generate_ratings_card.py and posts it using a
raw.githubusercontent.com URL. Dedupes against data/posted_ratings.json by
date so a re-run on the same day doesn't double-post.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_facebook

MANIFEST    = Path(__file__).parent / "_ratings_manifest.json"
TRACKING    = Path(__file__).parent.parent / "data" / "posted_ratings.json"
MAX_HISTORY = 500
REPO        = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH      = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(date_str: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/ratings/{date_str}.png"
    )


def build_caption(entry: dict, max_chars: int) -> str:
    lines = [f"Analyst Ratings: {entry['human_date']}",
              "Latest broker upgrades & downgrades"]

    ups   = entry.get("upgrades", [])
    downs = entry.get("downgrades", [])
    if ups:
        lines.append("")
        lines.append("🟢 Upgrades: " + " ".join(f"#{t['ticker']}" for t in ups[:6]))
    if downs:
        lines.append("")
        lines.append("🔴 Downgrades: " + " ".join(f"#{t['ticker']}" for t in downs[:6]))

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 1] + "…"

    return result


def _pt_str(entry: dict) -> str:
    pt  = entry.get("pt_current")
    pct = entry.get("pt_pct_change")
    if not isinstance(pt, (int, float)):
        return ""
    pt_str = f"${pt:.0f}" if pt == int(pt) else f"${pt:.2f}"
    if isinstance(pct, (int, float)):
        pt_str += f" ({pct:+.0f}%)"
    return f", PT {pt_str}"


def llm_caption(entry: dict, max_chars: int) -> str | None:
    """Reword today's analyst actions into a fresh intro hook via the
    Anthropic API, then append the exact ticker list (never LLM-generated).
    Returns None on any failure so the caller falls back to the static
    template."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    ups   = entry.get("upgrades", [])
    downs = entry.get("downgrades", [])
    if not api_key or (not ups and not downs):
        return None

    facts_lines = [f"Date: {entry['human_date']}"]
    if ups:
        top = max(ups, key=lambda t: t.get("pt_pct_change") if isinstance(t.get("pt_pct_change"), (int, float)) else float("-inf"))
        facts_lines.append(f"Notable upgrade: {top['ticker']} by {top.get('analyst') or 'a broker'}{_pt_str(top)}")
    if downs:
        top = min(downs, key=lambda t: t.get("pt_pct_change") if isinstance(t.get("pt_pct_change"), (int, float)) else float("inf"))
        facts_lines.append(f"Notable downgrade: {top['ticker']} by {top.get('analyst') or 'a broker'}{_pt_str(top)}")
    facts_lines.append(f"{len(ups)} upgrades, {len(downs)} downgrades tracked today")
    facts = "\n".join(facts_lines)

    footer_lines = []
    if ups:
        footer_lines.append("🟢 Upgrades: " + " ".join(f"#{t['ticker']}" for t in ups[:6]))
    if downs:
        footer_lines.append("🔴 Downgrades: " + " ".join(f"#{t['ticker']}" for t in downs[:6]))
    footer = "\n\n" + "\n".join(footer_lines)
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
                    "everyday retail investors, not a news outlet. Given today's analyst "
                    "upgrade/downgrade actions from Wall Street brokers, write a short 1-3 "
                    "sentence hook — like you're texting a friend, not filing a report — "
                    "that calls out the standout action: a notable price target change, a "
                    "high-conviction call, or the overall tilt (more upgrades than "
                    "downgrades or vice versa). Lead with the concrete fact. Short, punchy "
                    "sentences, contractions are fine. This text will be followed "
                    "immediately by the full ticker list, so don't just repeat the names "
                    "with nothing added. Vary your phrasing and structure each time so "
                    "posts don't read like a template. Factual only, never invent numbers "
                    "not given to you. You may use at most one emoji if it genuinely fits, "
                    "skip it entirely rather than force one. No hashtags, no quotation "
                    f"marks around the output. Under {intro_budget} characters. Output ONLY "
                    "the hook text, nothing else."
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
        print("Manifest is empty — no rating changes to post.")
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

    print(f"Posting analyst ratings for {entry['date']}")
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
