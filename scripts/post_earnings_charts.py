#!/usr/bin/env python3
"""
post_earnings_charts.py — Post generated earnings charts to Threads and Instagram.

Reads the manifest written by generate_earnings_charts.py and posts each chart
using raw.githubusercontent.com URLs (available immediately after the commit step).
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests

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


def post_to_threads(text: str, img_url: str) -> str:
    token   = os.environ["THREADS_ACCESS_TOKEN"]
    user_id = os.environ["THREADS_USER_ID"]
    base    = f"https://graph.threads.net/v1.0/{user_id}"

    resp = requests.post(f"{base}/threads", json={
        "media_type":   "IMAGE",
        "image_url":    img_url,
        "text":         text,
        "access_token": token,
    })
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Threads create: {data['error']['message']}")

    time.sleep(3)

    pub = requests.post(f"{base}/threads_publish", json={
        "creation_id":  data["id"],
        "access_token": token,
    })
    pub_data = pub.json()
    if "error" in pub_data:
        raise RuntimeError(f"Threads publish: {pub_data['error']['message']}")
    return pub_data["id"]


def post_to_instagram(caption: str, img_url: str) -> str:
    token   = os.environ["IG_ACCESS_TOKEN"]
    user_id = os.environ["IG_USER_ID"]

    media = requests.post(
        f"https://graph.instagram.com/v23.0/{user_id}/media",
        json={"image_url": img_url, "caption": caption, "access_token": token},
    )
    md = media.json()
    if "error" in md:
        raise RuntimeError(f"IG media: {md['error']['message']}")

    time.sleep(2)

    pub = requests.post(
        f"https://graph.instagram.com/v23.0/{user_id}/media_publish",
        json={"creation_id": md["id"], "access_token": token},
    )
    pd_ = pub.json()
    if "error" in pd_:
        raise RuntimeError(f"IG publish: {pd_['error']['message']}")
    return pd_["id"]


def posting_key(entry: dict) -> str:
    return f"{entry['ticker']}_{entry['label']}"


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
          f"Instagram={'yes' if has_ig else 'no'}]")

    any_posted = False
    for i, entry in enumerate(new_entries):
        ticker  = entry["ticker"]
        img_url = image_url(ticker)

        threads_caption = build_caption(entry, 500)
        ig_caption      = build_caption(entry, 2200)

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
