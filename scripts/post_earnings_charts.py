#!/usr/bin/env python3
"""
post_earnings_charts.py — Post generated earnings charts to Threads and Instagram.

Reads the manifest written by generate_earnings_charts.py and posts each chart
using raw.githubusercontent.com URLs (available immediately after the commit step).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from social_post import post_to_threads, post_to_instagram, post_to_facebook

MANIFEST  = Path(__file__).parent / "_post_manifest.json"
TRACKING  = Path(__file__).parent.parent / "data" / "posted_earnings.json"
MAX_HISTORY = 500
REPO      = os.environ.get("GITHUB_REPOSITORY", "sahidkhan89/sahidkhan89.github.io")
BRANCH    = os.environ.get("GITHUB_REF_NAME", "main")


def image_url(ticker: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
        f"/images/earnings/{ticker}_trend.png"
    )


def build_caption(d: dict, max_chars: int) -> str:
    lines = [f"${d['ticker']} Quarterly Earnings Trend"]

    if d.get("revenue") and d["revenue"] != "N/A":
        pct = d.get("rev_yoy_pct")
        emoji = ("🟢" if pct >= 0 else "🔴") if pct is not None else ""
        yoy = f" ({pct:+.1f}% YoY)" if pct is not None else ""
        prefix = f"{emoji} " if emoji else ""
        lines.append(f"{prefix}Revenue: {d['revenue']}{yoy}")

    if d.get("net_income") and d["net_income"] != "N/A":
        pct = d.get("ni_yoy_pct")
        emoji = ("🟢" if pct >= 0 else "🔴") if pct is not None else ""
        yoy = f" ({pct:+.1f}% YoY)" if pct is not None else ""
        prefix = f"{emoji} " if emoji else ""
        lines.append(f"{prefix}Net Income: {d['net_income']}{yoy}")

    if d.get("nm_pct") is not None:
        lines.append(f"Net Margin: {d['nm_pct']:.1f}%")
    if d.get("gm_pct") is not None:
        lines.append(f"Gross Margin: {d['gm_pct']:.1f}%")

    ticker   = d["ticker"]
    hashtags = f"#{ticker}"
    body     = "\n".join(lines)
    result   = body + "\n\n" + hashtags

    if len(result) > max_chars:
        trim = max_chars - len(hashtags) - 4
        result = body[:trim] + "...\n\n" + hashtags

    return result


def posting_key(entry: dict) -> str:
    return f"{entry['ticker']}_{entry['label']}"


def _yoy_str(pct) -> str:
    return f" ({pct:+.1f}% YoY)" if isinstance(pct, (int, float)) else ""


def llm_caption(d: dict, max_chars: int) -> str | None:
    """Reword this ticker's quarterly earnings into a fresh intro hook via
    the Anthropic API, then append the ticker hashtag (never LLM-generated).
    Returns None on any failure so the caller falls back to the static
    template."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    facts_lines = [f"Ticker: {d['ticker']} ({d.get('company') or ''})",
                   f"Quarter: {d.get('label', '').replace(chr(10), ' ')}"]
    if d.get("revenue") and d["revenue"] != "N/A":
        facts_lines.append(f"Revenue: {d['revenue']}{_yoy_str(d.get('rev_yoy_pct'))}")
    if d.get("net_income") and d["net_income"] != "N/A":
        facts_lines.append(f"Net Income: {d['net_income']}{_yoy_str(d.get('ni_yoy_pct'))}")
    if d.get("nm_pct") is not None:
        facts_lines.append(f"Net Margin: {d['nm_pct']:.1f}%")
    if d.get("gm_pct") is not None:
        facts_lines.append(f"Gross Margin: {d['gm_pct']:.1f}%")
    facts = "\n".join(facts_lines)

    footer = f"\n\n#{d['ticker']}"
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
                    "everyday retail investors, not a news outlet. Given this company's "
                    "just-reported quarterly revenue, net income and margins, write a short "
                    "1-2 sentence hook — like you're texting a friend, not filing a report — "
                    "that leads with the standout figure (usually revenue or net income YoY "
                    "change). Short, punchy sentences, contractions are fine. This text will "
                    "be followed immediately by the ticker hashtag, so don't just restate the "
                    "ticker with nothing added. Factual only, never invent numbers not given "
                    "to you. Vary your phrasing and structure each time so posts don't read "
                    "like a template. You may use at most one emoji if it genuinely fits, "
                    "skip it entirely rather than force one. No hashtags, no quotation marks "
                    f"around the output. Under {intro_budget} characters. Output ONLY the "
                    "hook text, nothing else."
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
                        help="Print captions and image URLs without posting")
    args = parser.parse_args()
    dry_run = args.dry_run

    if not MANIFEST.exists():
        print("No manifest found — nothing to post.")
        return

    manifest = json.loads(MANIFEST.read_text())
    if not manifest:
        print("Manifest is empty — no charts to post.")
        return

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {"posted": []}
    posted   = set(tracking.get("posted", []))

    has_threads = bool(os.environ.get("THREADS_ACCESS_TOKEN") and
                       os.environ.get("THREADS_USER_ID"))
    has_ig      = bool(os.environ.get("IG_ACCESS_TOKEN") and
                       os.environ.get("IG_USER_ID"))
    has_fb      = bool(os.environ.get("FB_PAGE_ACCESS_TOKEN") and
                       os.environ.get("FB_PAGE_ID"))

    new_entries = [e for e in manifest if dry_run or posting_key(e) not in posted]
    skipped     = len(manifest) - len(new_entries)
    if skipped:
        print(f"Skipping {skipped} already-posted chart(s).")
    if not new_entries:
        print("Nothing new to post.")
        return

    mode_label = "DRY RUN" if dry_run else "Posting"
    print(f"{mode_label}: {len(new_entries)} chart(s) "
          f"[Threads={'yes' if has_threads else 'no'}, "
          f"Instagram={'yes' if has_ig else 'no'}, "
          f"Facebook={'yes' if has_fb else 'no'}]")

    any_posted = False
    for i, entry in enumerate(new_entries):
        ticker  = entry["ticker"]
        img_url = image_url(ticker)

        # One LLM call reworded intro, shared across Threads/IG/FB captions.
        # Falls back to the static template on any failure.
        reworded        = llm_caption(entry, 500)
        threads_caption = reworded or build_caption(entry, 500)
        ig_caption      = reworded or build_caption(entry, 2200)

        if dry_run:
            print(f"\n{'─'*60}")
            print(f"  Ticker : {ticker}")
            print(f"  Image  : {img_url}")
            print(f"\n  ── Threads caption (max 500) ──")
            print(f"{threads_caption}")
            print(f"\n  ── Instagram caption (max 2200) ──")
            print(f"{ig_caption}")
            print(f"{'─'*60}")
            continue

        print(f"\n[{ticker}] {img_url}")
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
            posted.add(posting_key(entry))
            any_posted = True

        if i < len(new_entries) - 1:
            time.sleep(5)

    if any_posted:
        tracking["posted"] = list(posted)[-MAX_HISTORY:]
        TRACKING.write_text(json.dumps(tracking, indent=2) + "\n")
        print("\nTracking file updated.")

    print("\nDone.")


if __name__ == "__main__":
    main()
