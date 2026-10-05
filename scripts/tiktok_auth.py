#!/usr/bin/env python3
"""
tiktok_auth.py — One-time (well, once a year) TikTok login, run locally.

Connects your TikTok account to the Stock Score TikTok developer app and
stores the resulting refresh token as the TIKTOK_REFRESH_TOKEN GitHub secret,
which scripts/tiktok_post.py uses from the reel workflows.

    export TIKTOK_CLIENT_KEY=...  TIKTOK_CLIENT_SECRET=...
    python scripts/tiktok_auth.py

1. Opens TikTok's login page in your browser.
2. After you approve, TikTok redirects to www.stockscore.co.uk/tiktok-callback.html,
   which shows a code — paste it back here.
3. Exchanges the code for tokens and saves the refresh token with
   `gh secret set` (or prints it if gh isn't available).

The refresh token lasts 365 days; tiktok_post.py keeps the secret updated if
TikTok rotates it, but re-run this before it expires (or if posting starts
failing with an auth error).
"""

import os
import secrets
import shutil
import subprocess
import sys
import webbrowser
from urllib.parse import urlencode

import requests

REDIRECT_URI = "https://www.stockscore.co.uk/tiktok-callback.html"
SCOPES       = "user.info.basic,video.upload"
TOKEN_URL    = "https://open.tiktokapis.com/v2/oauth/token/"
SECRET_NAME  = "TIKTOK_REFRESH_TOKEN"


def main():
    client_key    = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    if not (client_key and client_secret):
        sys.exit("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET first (from your app's page "
                 "on developers.tiktok.com).")

    state = secrets.token_urlsafe(16)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key":    client_key,
        "scope":         SCOPES,
        "response_type": "code",
        "redirect_uri":  REDIRECT_URI,
        "state":         state,
    })
    print("Opening TikTok login. If the browser doesn't open, visit:\n\n" + url + "\n")
    webbrowser.open(url)

    pasted = input("Paste the code from the callback page: ").strip().split()
    if not pasted:
        sys.exit("No code entered.")
    code = pasted[0]
    if len(pasted) > 1 and pasted[1] != state:
        sys.exit("State mismatch — that code is from a different login attempt. Run this again.")

    r = requests.post(TOKEN_URL, data={
        "client_key":    client_key,
        "client_secret": client_secret,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    data = r.json()
    if "refresh_token" not in data:
        sys.exit(f"Token exchange failed: {data}")

    missing = set(SCOPES.split(",")) - set(data.get("scope", "").split(","))
    if missing:
        print(f"Warning: TikTok didn't grant {', '.join(sorted(missing))} — check the "
              "scopes are added to the app.")

    refresh = data["refresh_token"]
    days = int(data.get("refresh_expires_in", 0)) // 86400

    # user.info.basic — confirms which TikTok account was connected.
    info = requests.get("https://open.tiktokapis.com/v2/user/info/",
                        params={"fields": "open_id,display_name"},
                        headers={"Authorization": f"Bearer {data['access_token']}"},
                        timeout=30).json().get("data", {}).get("user", {})
    who = info.get("display_name") or data.get("open_id")
    print(f"\nConnected TikTok account: {who}. Refresh token valid ~{days} days.")

    if shutil.which("gh"):
        subprocess.run(["gh", "secret", "set", SECRET_NAME, "--body", refresh], check=True)
        print(f"Saved as the {SECRET_NAME} GitHub secret.")
    else:
        print(f"\ngh CLI not found — add this as the {SECRET_NAME} repository secret:\n\n{refresh}\n")


if __name__ == "__main__":
    main()
