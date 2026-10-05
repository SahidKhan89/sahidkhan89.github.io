#!/usr/bin/env python3
"""
tiktok_post.py — Send a reel to the TikTok account's inbox as a draft.

Uses the Content Posting API's upload (inbox) flow rather than direct post:
the video lands in TikTok as a draft notification, and it's published from
the TikTok app — where a trending sound and TikTok-specific caption can be
added. That flow also doesn't need TikTok's app audit to be useful (direct
posts from unaudited apps are forced private).

    python scripts/tiktok_post.py --reel h2h          # or --reel investment

Reads that reel's manifest for the date, uploads images/<reel>-reel/<date>.mp4
and records it in data/posted_tiktok.json so a re-run doesn't send it twice.
Exits quietly (status 0) if the TikTok secrets aren't configured, so the
workflows work unchanged until TikTok is set up.

Env: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN, and
optionally GH_PAT (a fine-grained token with "Secrets: write" on this repo) so
a rotated refresh token can be saved back to the TIKTOK_REFRESH_TOKEN secret.
"""

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT      = Path(__file__).parent.parent
TRACKING  = ROOT / "data" / "posted_tiktok.json"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL  = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"

REELS = {
    "investment": (Path(__file__).parent / "_investment_reel_manifest.json", "investment-reel"),
    "h2h":        (Path(__file__).parent / "_h2h_reel_manifest.json",        "h2h-reel"),
}

MIN_CHUNK = 5 * 1024 * 1024    # TikTok: chunks are 5-64 MB, files under 5 MB go up whole
CHUNK     = 10 * 1024 * 1024


def refresh_access_token() -> str:
    old = os.environ["TIKTOK_REFRESH_TOKEN"]
    r = requests.post(TOKEN_URL, data={
        "client_key":    os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type":    "refresh_token",
        "refresh_token": old,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"token refresh failed: {data.get('error_description') or data}. "
                           "Re-run scripts/tiktok_auth.py locally.")

    new = data.get("refresh_token")
    if new and new != old:
        # TikTok may rotate the refresh token; the old one stops working, so
        # the secret has to be updated or the next run fails.
        print(f"::add-mask::{new}")
        if os.environ.get("GH_PAT"):
            subprocess.run(["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--body", new],
                           check=True, env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]})
            print("  TikTok rotated the refresh token — TIKTOK_REFRESH_TOKEN secret updated.")
        else:
            print("  ⚠ TikTok rotated the refresh token but GH_PAT isn't set, so the secret "
                  "couldn't be updated — re-run scripts/tiktok_auth.py locally.")
    return data["access_token"]


def upload_to_inbox(video: Path, access_token: str) -> str:
    size = video.stat().st_size
    if size < MIN_CHUNK:
        chunk_size, count = size, 1
    else:
        chunk_size = CHUNK
        count = max(1, size // chunk_size)   # last chunk absorbs the remainder

    r = requests.post(INIT_URL, json={"source_info": {
        "source": "FILE_UPLOAD", "video_size": size,
        "chunk_size": chunk_size, "total_chunk_count": count,
    }}, headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json; charset=UTF-8"}, timeout=30)
    data = r.json()
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"upload init failed: {data.get('error')}")
    upload_url, publish_id = data["data"]["upload_url"], data["data"]["publish_id"]

    with open(video, "rb") as f:
        for i in range(count):
            start = i * chunk_size
            end = size - 1 if i == count - 1 else start + chunk_size - 1
            f.seek(start)
            body = f.read(end - start + 1)
            put = requests.put(upload_url, data=body, headers={
                "Content-Type":   "video/mp4",
                "Content-Length": str(len(body)),
                "Content-Range":  f"bytes {start}-{end}/{size}",
            }, timeout=120)
            if put.status_code not in (200, 201, 206):
                raise RuntimeError(f"chunk {i + 1}/{count} upload failed: "
                                   f"HTTP {put.status_code} {put.text[:200]}")
    return publish_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reel", choices=sorted(REELS), required=True)
    args = parser.parse_args()

    needed = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    if not all(os.environ.get(k) for k in needed):
        print("TikTok secrets not configured — skipping.")
        return

    manifest_path, folder = REELS[args.reel]
    if not manifest_path.exists():
        print("No manifest found — nothing to send.")
        return
    date = json.loads(manifest_path.read_text())["date"]
    video = ROOT / "images" / folder / f"{date}.mp4"
    key = f"{folder}/{date}"

    tracking = json.loads(TRACKING.read_text()) if TRACKING.exists() else {"sent": []}
    if key in tracking["sent"]:
        print(f"{key} already sent to TikTok — skipping.")
        return
    if not video.exists():
        print(f"{video.relative_to(ROOT)} not found — nothing to send.")
        return

    try:
        publish_id = upload_to_inbox(video, refresh_access_token())
    except Exception as e:
        print(f"  ✗ TikTok: {e}")
        sys.exit(1)
    print(f"  ✓ TikTok draft sent ({publish_id}) — open TikTok to post it.")

    tracking["sent"] = (tracking["sent"] + [key])[-500:]
    TRACKING.write_text(json.dumps(tracking, indent=2) + "\n")


if __name__ == "__main__":
    main()
