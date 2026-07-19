#!/usr/bin/env python3
"""
social_post.py — shared Threads / Instagram / Facebook posting functions.

Extracted from post_earnings_charts.py so the earnings-calendar, analyst-ratings
and dividends-calendar posters can reuse the same posting logic instead of each
re-implementing it.
"""

import os
import time

import requests


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


def post_to_instagram_reel(caption: str, video_url: str, thumb_offset_ms: int | None = None,
                           poll_interval: int = 5, timeout: int = 300) -> str:
    """Like post_to_instagram but for Reels — video processing is async, so
    unlike the image flow this has to poll the container's status_code
    before it's ready to publish.

    `thumb_offset_ms`, if given, pins the grid/thumbnail cover frame to that
    offset into the video — otherwise IG defaults to grabbing frame 0, which
    for a reel that opens on a fade-in can land on a near-blank frame."""
    token   = os.environ["IG_ACCESS_TOKEN"]
    user_id = os.environ["IG_USER_ID"]

    payload = {
        "media_type":   "REELS",
        "video_url":    video_url,
        "caption":      caption,
        "access_token": token,
    }
    if thumb_offset_ms is not None:
        payload["thumb_offset"] = thumb_offset_ms

    media = requests.post(
        f"https://graph.instagram.com/v23.0/{user_id}/media",
        json=payload,
    )
    md = media.json()
    if "error" in md:
        raise RuntimeError(f"IG reel media: {md['error']['message']}")
    creation_id = md["id"]

    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        time.sleep(poll_interval)
        check = requests.get(
            f"https://graph.instagram.com/v23.0/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
        )
        cd = check.json()
        if "error" in cd:
            raise RuntimeError(f"IG reel status: {cd['error']['message']}")
        status = cd.get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"IG reel processing failed: {cd.get('status', status)}")
    else:
        raise RuntimeError(f"IG reel processing timed out after {timeout}s (last status: {status})")

    pub = requests.post(
        f"https://graph.instagram.com/v23.0/{user_id}/media_publish",
        json={"creation_id": creation_id, "access_token": token},
    )
    pd_ = pub.json()
    if "error" in pd_:
        raise RuntimeError(f"IG reel publish: {pd_['error']['message']}")
    return pd_["id"]


def post_to_facebook(caption: str, img_url: str) -> str:
    token   = os.environ["FB_PAGE_ACCESS_TOKEN"]
    page_id = os.environ["FB_PAGE_ID"]

    resp = requests.post(
        f"https://graph.facebook.com/v23.0/{page_id}/photos",
        json={"url": img_url, "caption": caption, "access_token": token},
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Facebook post: {data['error']['message']}")
    return data.get("post_id", data.get("id"))
