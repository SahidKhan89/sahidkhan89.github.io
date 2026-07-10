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
